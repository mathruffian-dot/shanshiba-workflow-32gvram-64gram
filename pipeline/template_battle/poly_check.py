"""破音字檢查：歌詞與 DJ 口白裡「一個字有兩種以上唸法」的字，逐字上網查教育部《重編國語辭典修訂本》，用前後文找出這裡該念哪個音。
有 DJ 錄音時，再用強制對齊比「各種念法」哪個最像，抓出 TTS 念錯音的字（例：〈Bravo 之戰〉「樂長」被念成 lè zhǎng）。

用法（Voice venv，在對決的 battle/ 資料夾）：
  python poly_check.py                 # 只查文字 → out/review/poly_check.md
  python poly_check.py --audio         # 另外比對 DJ 錄音（out/voice/ming/dj_<key>.wav＋dj_align.json，先跑 dj_align.py）

判讀：
  - 「詞典有這個詞」→ 用詞條的音當答案；歌詞有用同音字（sing／dj.tts 和字幕不同）時，檢查同音字的音是否等於答案。
  - 「要人看上下文」→ 詞典沒有剛好的詞（多半是句子用法，如「我一毛沒收」的「沒」＝ㄇㄟˊ，不是「沒收 ㄇㄛˋ ㄕㄡ」），要自己判斷，
    必要時查 https://dict.revised.moe.edu.tw/ 例句。工具只列出來，不替你決定。
  - 唱的部分聲調被旋律蓋掉，機器量不準 → 只在報告標「要聽」；DJ 口白（說話）才做錄音比對。
查詢結果快取在 out/review/moe_cache.json（重跑不再上網）。查詢只送詞語，不送其他資料。"""
import argparse, json, re, sys, time, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
URL = "https://dict.revised.moe.edu.tw/search.jsp"
UA = {"User-Agent": "Mozilla/5.0 (poly-check script)"}
LIGHT = set("的了著得地一不個們嗎呢吧啊")          # 虛字、變調字：念法跟著句子走，預設不列（--all 才列）
CJK = re.compile(r"[一-鿿]")

_cache = None
CACHE = OUT / "review" / "moe_cache.json"
SITES = {"concised": "https://dict.concised.moe.edu.tw/search.jsp",   # 簡編本：只收常用音，判斷「是不是破音字」用這本
         "revised": "https://dict.revised.moe.edu.tw/search.jsp"}     # 修訂本：詞條多，找前後文的詞用這本補


def moe(word, site="revised"):
    """回傳 [(詞條, [每字注音…]), …]；查無資料回傳 []。"""
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    key = word if site == "revised" else f"{site}:{word}"
    if key in _cache:
        return _cache[key]
    import requests
    for k in range(3):
        try:
            r = requests.get(SITES[site], params=dict(md=1, word=word, qMd=0, qCol=1), headers=UA, timeout=30)
            break
        except Exception:
            time.sleep(2 + 3 * k)
    else:
        raise SystemExit(f"教育部辭典連不上（查「{word}」）")
    t = r.text
    res = []
    def syl(block):
        return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<(?:code|phon)>(.*?)</(?:code|phon)>", block)]
    if "id=searchL" in t:
        for row in re.findall(r"<tr data-link=.*?</tr>", t, flags=re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
            if len(tds) < 3: continue
            ent = re.sub(r"<sub>.*?</sub>", "", tds[1], flags=re.S)
            ent = re.sub(r"<[^>]+>", "", ent).strip()
            youyin = "又音" in row
            res.append([ent + ("（又音）" if youyin else ""), syl(tds[2])])
    else:
        m = re.search(r"<h3>(.*?)</h3>", t, flags=re.S)
        if m and re.search(r"<(code|phon)>", m.group(1)):
            ent = re.sub(r"<[^>]+>", "", m.group(1).split(":")[0]).strip()
            res.append([ent, syl(m.group(1))])
    _cache[key] = res
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0), encoding="utf-8")
    time.sleep(0.25)
    return res


def char_readings(c, site="concised"):
    """這個字的常用念法（簡編本；簡編本沒收就用修訂本）。"""
    seen = []
    for ent, ph in moe(c, site):
        if ent.replace("（又音）", "") == c and ph and ph[0] not in seen:
            seen.append(ph[0] + ("（又音）" if "又音" in ent else ""))
    if not seen and site == "concised":
        return char_readings(c, "revised")
    return seen


def word_hits(phrase, i):
    """phrase 裡第 i 個字：找詞典裡剛好等於「含這個字的 2–4 字片段」的詞條 → [(詞, 這個字的注音)]，長的在前。"""
    hits = []
    for n in (4, 3, 2):
        for a in range(max(0, i - n + 1), min(i, len(phrase) - n) + 1):
            w = phrase[a:a + n]
            if not all(CJK.match(x) for x in w): continue
            for ent, ph in moe(w, "concised") + moe(w):
                e = ent.replace("（又音）", "")
                if e == w and len(ph) == len(w):
                    hits.append((w + ("（又音）" if "又音" in ent else ""), ph[i - a]))
    out = []
    for h in hits:
        if h not in out: out.append(h)
    return out


def phrases(text):
    return [p for p in re.split(r"[^一-鿿]+", text) if p]


def collect(B):
    """[(來源, 字幕文字, 送去生成的文字)]"""
    rows = []
    for k, r in B["rappers"].items():
        for sec in r["lyrics"]:
            for ln in sec["lines"]:
                rows.append((f"{r['short']}歌詞", ln["show"].replace("　", " "), ln["sing"]))
    dj = B["dj"]
    for k, t in dj["lines"].items():
        rows.append((f"DJ {k}", t, dj.get("tts", {}).get(k, t)))
    return rows


def align_sub(show, sing):
    """字幕與生成文字逐字對應（只比漢字；數字寫法不同的段落跳過，只對等長的替換段）。"""
    from difflib import SequenceMatcher
    a, b = "".join(CJK.findall(show)), "".join(CJK.findall(sing))
    m = {}
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            m.update({i1 + k: b[j1 + k] for k in range(i2 - i1)})
    return m


def guess(text):
    """pypinyin 依詞組猜的念法（大陸預設，TTS 前端多半照這個念）→ 注音，給人對照。"""
    from pypinyin import pinyin, Style
    cs = CJK.findall(text)
    return [p[0] for p in pinyin("".join(cs), style=Style.BOPOMOFO)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "battle.json"))
    ap.add_argument("--audio", action="store_true", help="DJ 錄音比對各種念法")
    ap.add_argument("--all", action="store_true", help="連「的了著得地一不」也列")
    a = ap.parse_args()
    B = json.loads(Path(a.json).read_text(encoding="utf-8"))
    md = ["# 破音字檢查（教育部《重編國語辭典修訂本》）", "",
          "| 來源 | 字 | 前後文 | 這個字的念法 | 詞典裡的詞 → 這裡的音 | pypinyin 猜 | 生成文字 | 判斷 |", "|:--|:--|:--|:--|:--|:--|:--|:--|"]
    bad, ok_dict, ctxq, dj_expect, tw = [], [], [], [], []
    for src, show, sing in collect(B):
        sub = align_sub(show, sing); gs = guess(show); pos = 0
        for ph in phrases(show):
            for i, c in enumerate(ph):
                gi = pos + i
                if c in LIGHT and not a.all: continue
                rd = char_readings(c)
                if len(rd) < 2:                                    # 台灣只有一個音、但大陸預設念別的（2026-11-08 〈弦歌〉松柏：台灣ㄅㄛˊ，Suno 唱 bǎi，使用者聽出）
                    g0 = gs[gi] if gi < len(gs) else ""
                    if len(rd) == 1 and g0 and rd[0].replace("˙", "") != g0.replace("˙", ""):
                        sc0 = sub.get(gi) if sub else None
                        srd0 = [x.replace("（又音）", "") for x in char_readings(sc0)] if sc0 and sc0 != c else []
                        done = rd[0] in srd0
                        tw.append(f"| {src} | {c} | {ph[max(0, i - 3):i]}【{c}】{ph[i + 1:i + 4]} | {rd[0]} | {g0} | {'寫成「' + sc0 + '」' if srd0 else ''} | {'同音字對' if done else '⚠ 要改同音字，生成器多半照大陸音'} |")
                    continue
                hits = word_hits(ph, i)
                ans = sorted({h[1] for h in hits if "又音" not in h[0]})
                sc = sub.get(gi) if sub else None
                gen = ""
                verdict = "要人看上下文" if len(ans) != 1 else "照詞典"
                if sc and sc != c:
                    srd = [x.replace("（又音）", "") for x in char_readings(sc)] or ["?"]
                    gen = f"寫成「{sc}」（{'／'.join(srd)}）"
                    if len(ans) == 1:
                        verdict = "同音字對" if ans[0] in srd else "⚠ 同音字的音跟詞典不同"
                elif src.startswith("DJ"):
                    dj_expect.append((src[3:], gi, c, ans[0] if len(ans) == 1 else None, rd))
                g = gs[gi] if gi < len(gs) else ""
                if verdict == "照詞典" and g and ans[0].replace("˙", "") != g.replace("˙", ""):
                    verdict = "照詞典 ★和大陸預設不同，確認意思"          # 例：記載 ㄗㄞˋ（陸 zǎi）、一毛沒收（詞條＝充公）
                ctx = ph[max(0, i - 3):i] + f"【{c}】" + ph[i + 1:i + 4]
                hs = "、".join(f"{w} {p}" for w, p in hits[:4]) or "—"
                line = f"| {src} | {c} | {ctx} | {'／'.join(rd)} | {hs} | {g} | {gen} | {verdict} |"
                md.append(line)
                (bad if verdict.startswith("⚠") else ok_dict if verdict.startswith(("照詞典", "同音字對")) else ctxq).append(line)
            pos += len(ph)
    H = [md[2], md[3]]
    md += ["", f"共 {len(md) - 4} 個破音字。", "",
           f"## ⚠ 同音字的音跟詞典不同（{len(bad)}）", "", *H, *(bad or ["（無）"]), "",
           f"## 詞典詞條定的音（{len(ok_dict)}）— 要確認詞條的意思跟句子一樣（「一毛沒收」≠ 詞條「沒收＝充公 ㄇㄛˋ」）", "", *H, *(ok_dict or ["（無）"]), "",
           f"## 詞典沒有剛好的詞（{len(ctxq)}）— 看前後文自己定（pypinyin 猜的是大陸預設，TTS 多半照它念）", "", *H, *(ctxq or ["（無）"])]
    TH = ["| 來源 | 字 | 前後文 | 台灣音 | pypinyin（大陸預設） | 生成文字 | 判斷 |", "|:--|:--|:--|:--|:--|:--|:--|"]
    md += ["", f"## 台灣只有一個音、但和大陸預設不同（{len(tw)}）— 字幕照原字，生成文字要寫同音字", "", *TH, *(tw or ["（無）"])]
    flags = bad + [x for x in tw if "⚠" in x]
    if a.audio:
        md += ["", "## DJ 錄音比對（強制對齊分數：越接近 0 越像）", ""] + audio_check(B, dj_expect)
    rep = OUT / "review" / "poly_check.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(flags) or "沒有要處理的破音字"); print("→", rep)


# ------------------------------------------------------------------ DJ 錄音：各種念法的強制對齊分數
BOPO = None


def bopo2py(c, bp):
    """這個字的注音 → 去聲調拼音（用 pypinyin 同一字的多音清單對照）。"""
    from pypinyin import pinyin, Style
    nb = pinyin(c, style=Style.BOPOMOFO, heteronym=True)[0]
    nn = pinyin(c, style=Style.NORMAL, heteronym=True)[0]
    tb = pinyin(c, style=Style.TONE3, heteronym=True)[0]
    strip = lambda s: re.sub(r"[ˊˇˋ˙]", "", s.replace("（又音）", ""))
    for b, n in zip(nb, nn):
        if strip(b) == strip(bp): return n
    return None


def audio_check(B, expect):
    import torch, torchaudio, soundfile as sf
    from pypinyin import lazy_pinyin
    alp = OUT / "voice" / "ming" / "dj_align.json"
    if not alp.exists(): return ["（沒有 dj_align.json，先跑 dj_align.py）"]
    AL = json.loads(alp.read_text(encoding="utf-8"))
    FA = torchaudio.pipelines.MMS_FA; model = FA.get_model().cuda().eval(); D = FA.get_dict()
    out = []
    for key, gi, c, ans, rd in expect:
        wav = OUT / "voice" / "ming" / f"dj_{key}.wav"
        if key not in AL or not wav.exists(): continue
        chars = []
        for w, s, e in AL[key]:
            t = w.strip(); n = max(1, len(t))
            chars += [(x, s + j * (e - s) / n, s + (j + 1) * (e - s) / n) for j, x in enumerate(t) if CJK.match(x)]
        if gi >= len(chars) or chars[gi][0] != c: continue
        a0, a1 = max(0, gi - 2), min(len(chars), gi + 2)
        py = lazy_pinyin("".join(x for x, _, _ in chars[a0:a1]))
        alts = {}
        for r in rd:
            p = bopo2py(c, r)
            if p and p not in alts.values(): alts[r] = p
        exp_p = bopo2py(c, ans) if ans else None
        if len(set(alts.values())) < 2: continue                    # 只差聲調：對齊分數分不出，略
        x, sr = sf.read(str(wav), always_2d=True); x = x.mean(1)
        seg = x[int(max(0, chars[a0][1] - .1) * sr):int((chars[a1 - 1][2] + .1) * sr)]
        w = torchaudio.functional.resample(torch.tensor(seg, dtype=torch.float32)[None], sr, FA.sample_rate).cuda()
        with torch.inference_mode():
            em = torch.log_softmax(model(w)[0], -1)
        sc = {}
        for p in set(alts.values()):
            q = py[:]; q[gi - a0] = p
            toks = [D[ch] for ch in "*".join(q) if ch in D]
            _, s = torchaudio.functional.forced_align(em, torch.tensor([toks], device="cuda"), blank=0)
            sc[p] = float(s.mean())
        best = max(sc, key=sc.get)
        ctx = "".join(x for x, _, _ in chars[max(0, gi - 3):gi + 3])
        scs = "、".join(f"{p}={v:.2f}" for p, v in sorted(sc.items(), key=lambda kv: -kv[1]))
        if exp_p:
            ok = best == exp_p or sc[exp_p] >= sc[best] - 0.03
            out.append(f"- {'✅' if ok else '⚠ 可能念錯'} DJ {key}「{ctx}」的「{c}」：該念 {ans}（{exp_p}），錄音最像 {best}；{scs}")
        else:
            out.append(f"- ❓ DJ {key}「{ctx}」的「{c}」：詞典沒有剛好的詞，錄音最像 **{best}** → 自己對前後文判斷對不對；{scs}")
    return out or ["（沒有只靠聲母韻母就分得出的破音字）"]


if __name__ == "__main__":
    main()
