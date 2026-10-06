"""配音挑選（Voice venv）：每個候選（voice_cand/<id>_vx*／_bz*）→ 去頭尾靜音 → ASR 必須全對 → 對照 edge-tts 台灣國語參考音（voice_ref_tw/）
算腔調距離＋「一聲不夠高」＋「升降方向反」扣分 → 挑最低分，寫 voice/<id>.wav 與 voice_state.json。報告 voice_pick.json。
  C:/AI/Voice/venv/Scripts/python.exe voice_pick.py [ID ...]"""
import sys, json, re, difflib
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, r"C:\AI\tools")
src = open("C:/AI/tools/stt.py", encoding="utf-8").read(); a = src.index("def _add_cuda_dll_dirs"); b = src.index("def ", a + 10); exec(src[a:b]); _add_cuda_dll_dirs()
from faster_whisper import WhisperModel
from opencc import OpenCC
from pron_compare import contours
from pron_check import expected
import voice_plan as P

HERE = P.HERE; C = HERE / "voice_cand"; TRIM = C / "_trim"; TRIM.mkdir(exist_ok=True); OUT = HERE / "voice"; OUT.mkdir(exist_ok=True)
t2s = OpenCC("t2s"); asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root="C:/AI/Voice/models/whisper", local_files_only=True)
TEXT = {l: t for l, _, t in P.LINES}; SPK = {l: s for l, s, _ in P.LINES}
def norm(s): return re.sub(r"[\s，。？！、,.?!…—～~]", "", t2s.convert(s)).replace("周", "週").replace("断", "段").replace("烤", "考")   # 同音同調的辨識字錯不算


def trim(p, out):
    x, sr = sf.read(str(p), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
    e = np.convolve(np.abs(x), np.ones(int(sr * 0.02)) / int(sr * 0.02), "same"); i = np.nonzero(e > 0.012)[0]
    if len(i): x = x[max(0, i[0] - int(0.06 * sr)): i[-1] + int(0.12 * sr)]
    sf.write(str(out), x, sr, subtype="PCM_16"); return len(x) / sr


def score(lid, wav):
    text = P.TTS[lid]; chars, base, tones, sur = expected(text)
    segs, _ = asr.transcribe(str(wav), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False)
    heard = "".join(s.text for s in segs); asr_s = difflib.SequenceMatcher(None, norm(text), norm(heard)).ratio()
    Cc, Rc = contours(wav, base), contours(HERE / "voice_ref_tw" / f"{lid}.wav", base)
    d, t1def, per, wrongdir = [], 0.0, [], []
    for ch, tn, (cc, _), (rc, _) in zip(chars, sur, Cc, Rc):
        if tn == 5 or cc is None or rc is None: continue
        dist = float(np.sqrt(np.mean((cc - rc) ** 2))); d.append(dist); per.append((ch, round(dist, 1)))
        if tn == 1: t1def += max(0.0, float(rc.mean() - cc.mean()) - 1.5)
        cr, rr = float(cc[-3:].mean() - cc[:3].mean()), float(rc[-3:].mean() - rc[:3].mean())
        if (tn == 2 and rr > 1.0 and cr < -1.0) or (tn == 4 and rr < -1.0 and cr > 1.0): wrongdir.append(ch)
    md = float(np.mean(d)) if d else 9
    total = md + 1.0 * t1def / max(1, len(d)) + 1.5 * len(wrongdir) + (0 if asr_s >= 0.999 else 3 + 5 * (1 - asr_s))
    return dict(total=round(total, 3), mean_dist=round(md, 2), t1_deficit=round(t1def, 2), wrong_dir=wrongdir, asr=round(asr_s, 2), heard=heard, per=per)


if __name__ == "__main__":
    ids = sys.argv[1:] or [l for l, _, _ in P.LINES]
    rep = json.loads((HERE / "voice_pick.json").read_text(encoding="utf-8")) if (HERE / "voice_pick.json").exists() else {}
    SF = HERE / "voice_state.json"; S = json.loads(SF.read_text(encoding="utf-8")) if SF.exists() else {}
    for lid in ids:
        rows = []
        for p in sorted(C.glob(f"{lid}_vx*.wav")) + sorted(C.glob(f"{lid}_bz*.wav")):
            tp = TRIM / p.name; dur = trim(p, tp)
            if dur > 1.2 + len(norm(TEXT[lid])) / 2.2: continue        # 太慢／拖長的候選不要
            r = score(lid, tp); r.update(cand=p.name, file=str(tp), dur=round(dur, 2)); rows.append(r)
        rows.sort(key=lambda r: r["total"]); rep[lid] = rows
        print(f"\n{lid} {TEXT[lid]}", flush=True)
        for r in rows[:4]:
            print(f"  {r['cand']:14s} total {r['total']:.2f} dist {r['mean_dist']:.2f} 一聲 {r['t1_deficit']:.1f} 方向反 {r['wrong_dir']} asr {r['asr']} {r['heard']}", flush=True)
        if rows:
            x, sr = sf.read(rows[0]["file"], dtype="float32"); sf.write(str(OUT / f"{lid}.wav"), x, sr, subtype="PCM_16")
            S[lid] = dict(speaker=SPK[lid], text=TEXT[lid], dur=rows[0]["dur"], pick=rows[0]["cand"], total=rows[0]["total"], asr=rows[0]["asr"])
    (HERE / "voice_pick.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    SF.write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PICK_DONE", flush=True)
