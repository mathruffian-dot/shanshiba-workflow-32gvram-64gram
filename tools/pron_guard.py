# -*- coding: utf-8 -*-
"""配音讀音自審（使用者叫修過的字，交片前一定要過這一關）。Voice venv。

三種檢查，規則在 pron_guard_rules.json（使用者每指出一個念錯的字就加一條）：
  ① 輸入：字幕有規則裡的詞、規則有寫 tts 換字，配音輸入卻沒換 → 標出來。
  ② 音高：用強制對齊找到那個字，量起點／終點（相對整句高音區的半音），跟該有的聲調比：
       一聲＝平（起終差 ≤1.5 半音）且不低（起點 ≥ −3.5）；二聲＝不往下掉超過 1.5；四聲＝掉 ≥2；三聲＝低（起點 ≤ −3）。
  ③ 聽寫：整句「不帶提示」聽寫（提示詞會把念錯的字拉回正確字，〈抓→多〉就是這樣漏掉的），
       逐音節比拼音（不比聲調，同音字不算錯）；規則字的把握度 < 0.85 也標出來。
用法：
  python pron_guard.py <lines.json> <wav 資料夾> [--ids P54,V65] [--no-asr] [--all-asr]
    lines.json：[{id, sub, tts}]；wav 資料夾裡是 <id>.wav（選用檔）
    --all-asr：每一句都做③（預設只做有規則字的句子）
回傳碼 1＝有標出來的。報告印在畫面，另存 <lines.json 同資料夾>/pron_guard_report.txt。
"""
import argparse, difflib, json, re, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
RULES = json.loads((Path(__file__).with_name("pron_guard_rules.json")).read_text(encoding="utf-8"))["rules"]


def apply_tts(text):
    """配音輸入套用規則裡的換字（各集 build_jobs 在自己的 TTS_FIX 之後呼叫，修過的字跨集自動帶過去）。"""
    for r in RULES:
        if re.search(r["match"], text):
            for src, dst in r.get("tts", {}).items():
                text = text.replace(src, dst)
    return text


def st(f, ref):
    return 12 * np.log2(f / ref)


def tone_ok(tone, s, e):
    if tone == 1:
        return abs(e - s) <= 1.5 and s >= -3.5
    if tone == 2:
        return e - s >= -1.5
    if tone == 4:
        return s - e >= 2.0
    if tone == 3:
        return s <= -3.0
    return True


def hits(sub):
    """回傳 [(rule, 這個字在字幕裡的位置)]"""
    out = []
    for r in RULES:
        for m in re.finditer(r["match"], sub):
            if r["char"] == "*":                     # 「*」＝符合的那段最後一個字（例：英文 AI 後面接的第一個中文字）
                out.append((dict(r, char=m.group(0)[-1]), m.end() - 1, m.group(0)))
                continue
            k = m.group(0).find(r["char"])
            if k >= 0:
                out.append((r, m.start() + k, m.group(0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines"); ap.add_argument("wavdir")
    ap.add_argument("--ids"); ap.add_argument("--no-asr", action="store_true"); ap.add_argument("--all-asr", action="store_true"); ap.add_argument("-v", "--verbose", action="store_true", help="通過的數值也印（挑候選用）")
    a = ap.parse_args()
    lines = json.loads(Path(a.lines).read_text(encoding="utf-8"))
    if a.ids:
        want = set(a.ids.split(","))
        lines = [l for l in lines if l["id"] in want]
    import librosa, vc_swap
    from pypinyin import lazy_pinyin
    asr = None
    if not a.no_asr:
        from breezyvoice_pick import MODEL_CACHE
        from faster_whisper import WhisperModel
        import opencc
        s2t = opencc.OpenCC("s2t")   # 只轉字；s2twp 會連詞一起換（局部→區域性）
        asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=str(MODEL_CACHE))
    han = lambda s: re.sub(r"[^一-鿿]", "", s)
    rep, nflag = [], 0
    for l in lines:
        sub, tts, lid = l.get("sub", l["tts"]), l["tts"], l["id"]
        H = hits(sub)
        if not H and not a.all_asr:
            continue
        wav = Path(a.wavdir) / f"{lid}.wav"
        msgs, notes = [], []
        # ① 輸入有沒有換（還沒配音＝要處理；已配音且②③都過＝只提醒，下次重配再換）
        for r, _, word in H:
            for src, dst in r.get("tts", {}).items():
                if src in sub and src in tts:
                    (notes if wav.exists() else msgs).append(f"①輸入沒換：「{src}」應寫「{dst}」（{r['src'][:30]}…）")
        # ② 音高
        if H and wav.exists():
            try:
                chars, sp = vc_swap.spans(wav, tts)
            except Exception as e:
                chars, sp = [], []
                msgs.append(f"②對齊失敗 {e}")
            if chars:
                y, sr = librosa.load(wav, sr=16000)
                f0, _, _ = librosa.pyin(y, fmin=50, fmax=400, sr=sr, frame_length=1024, hop_length=160)
                t = np.arange(len(f0)) * 160 / sr
                ok = ~np.isnan(f0); ref = np.percentile(f0[ok], 85)
                ok &= ~(np.nan_to_num(f0, nan=1e9) < 0.62 * np.median(f0[ok]))      # 嘎裂聲／半頻誤判（字頭常出現 70 Hz 上下的假值）不算
                hz_sub = han(sub)
                for r, pos, word in H:
                    # 字幕位置 → 配音輸入的第幾個漢字（同音字換字後字數相同）
                    idx = len(han(sub[:pos]))
                    if idx >= len(chars) or len(hz_sub) != len(chars):
                        msgs.append(f"②「{word}」字數對不上，改人工看"); continue
                    if not r.get("tone"):
                        continue
                    a0, b0 = sp[idx]
                    v = f0[(t >= a0) & (t <= b0) & ok]
                    if len(v) < 6:                       # 對齊窗常偏早（聲母、停頓），濁音落在窗外 → 往後延 60 ms 再量
                        v = f0[(t >= a0) & (t <= b0 + 0.06) & ok]
                    if len(v) < 4:
                        msgs.append(f"②「{word}」的「{chars[idx]}」量不到音高（{a0:.2f}s），要人聽"); continue
                    k = max(1, len(v) // 3)
                    s, e = st(np.median(v[:k]), ref), st(np.median(v[-k:]), ref)
                    good = tone_ok(r["tone"], s, e)
                    line = f"②「{word}」{r['char']}（該 {r['tone']} 聲）起 {s:+.1f} 尾 {e:+.1f} 半音 @{a0:.2f}s"
                    if not good and r["tone"] == 4 and s < -3.0 and s - e >= 0:
                        notes.append(line + "（又低又平，句尾四聲常被壓平：要人聽）")
                    elif not good:
                        msgs.append(line + " ✗")
                    elif a.verbose:
                        notes.append(line + " ✓")
        # ③ 不帶提示聽寫
        if asr and wav.exists() and (a.all_asr or H):
            seg, _ = asr.transcribe(str(wav), language="zh", beam_size=5, word_timestamps=True, condition_on_previous_text=False)
            words = [w for s in seg for w in s.words]
            got = han(s2t.convert("".join(w.word for w in words)))
            exp = han(sub)
            pe, pg = lazy_pinyin(exp), lazy_pinyin(got)
            sm = difflib.SequenceMatcher(a=pe, b=pg, autojunk=False)
            num = set("零一二三四五六七八九十百千兩")
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    continue
                es, gs = exp[i1:i2], got[j1:j2]
                if es and set(es) <= num and not gs:   # 聽寫寫成阿拉伯數字
                    continue
                msgs.append(f"③聽寫：「{exp[max(0, i1 - 3):i2 + 3]}」裡的「{es}」聽成「{gs}」")
            for r, pos, word in H:
                if r.get("asr"):
                    c = s2t.convert(r["char"])
                    ps = [w.probability for w in words if c in s2t.convert(w.word)]
                    if not ps:
                        msgs.append(f"③「{word}」的「{r['char']}」聽寫沒出現")
                    elif min(ps) < 0.85:
                        msgs.append(f"③「{word}」的「{r['char']}」聽寫把握度 {min(ps):.2f} < 0.85")
                    elif a.verbose:
                        notes.append(f"③「{r['char']}」把握度 {min(ps):.2f}")
        if msgs:
            nflag += 1
            rep.append(f"{lid}　{sub}")
            rep += ["    " + m for m in msgs + notes]
        elif notes:
            rep.append(f"（提醒）{lid}　音高、聽寫都過；" + "；".join(notes))
    rep.append(f"\n共 {nflag} 句要處理" if nflag else "\n讀音自審：全部通過")
    txt = "\n".join(rep)
    print(txt)
    Path(a.lines).with_name("pron_guard_report.txt").write_text(txt, encoding="utf-8")
    sys.exit(1 if nflag else 0)


if __name__ == "__main__":
    main()
