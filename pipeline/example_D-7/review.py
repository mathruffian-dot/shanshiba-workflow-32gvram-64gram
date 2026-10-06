"""〈D-7〉自審五遍（專案規則：答案索引 §6＋使用者常退件清單 feedback_auto_recurring_checks）。
  C:/AI/H3/venv/Scripts/python.exe review.py <cut.mp4>          pass 1/3/4/5
  C:/AI/Voice/venv/Scripts/python.exe review.py <cut.mp4> --asr  pass 2（語音轉文字比對台詞）
輸出 review/<cut>_*.jpg 與 review/<cut>_review.json。自動數字只是警示，pass 1／5 的圖一定要逐張人工看。
 1 逐鏡抽格（每鏡 4 格，原尺寸 1/3）：鏡頭漂移、多出人、臉換人、多手多腳、手沒動、背景亂動、老師碰學生、學生方向
 2 ASR：每句台詞在成片中的實際內容（字錯、被切）
 3 雜訊：H3 片段色度雜訊 > 0.54 且比首幀高 25% 以上才警告（畫面本身細節多不算）
 4 黑畫面、定格（連續 >0.8 秒幾乎不動）、整體響度
 5 切點前後對照＋接點明暗差（>12 警告）＋字幕重疊"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent; RV = HERE / "review"; RV.mkdir(exist_ok=True)
cut = Path(sys.argv[1]).resolve(); stem = cut.stem
ST = json.loads((HERE / "post/starts.json").read_text(encoding="utf-8")); TOTAL = ST.pop("_total"); VT = ST.pop("_vo")
ST = {k: v for k, v in ST.items() if not k.endswith("_end")}
VS = json.loads((HERE / "voice_state.json").read_text(encoding="utf-8"))
TR = json.loads((HERE / "post/trims.json").read_text(encoding="utf-8"))
TL = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
ORDER = sorted([k for k in ST], key=lambda k: ST[k])
font = ImageFont.truetype(r"C:\Windows\Fonts\msjh.ttc", 20)
out = {}


def grab(t, w=448, h=252):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(cut), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return Image.frombytes("RGB", (w, h), raw) if len(raw) == w * h * 3 else Image.new("RGB", (w, h))


def end_of(k):
    i = ORDER.index(k); return ST[ORDER[i + 1]] if i + 1 < len(ORDER) else TOTAL


if "--asr" in sys.argv:
    src = open("C:/AI/tools/stt.py", encoding="utf-8").read(); a = src.index("def _add_cuda_dll_dirs"); b = src.index("def ", a + 10); exec(src[a:b]); _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel
    from opencc import OpenCC
    import difflib
    t2s = OpenCC("t2s"); asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root="C:/AI/Voice/models/whisper", local_files_only=True)
    norm = lambda s: re.sub(r"[\s，。？！、,.?!…—]", "", t2s.convert(s))
    res = []
    for k in ORDER:
        for l in TL.get(k, {}).get("lines", []):
            if k not in TR: continue
            st = ST[k] + l["start"] - TR[k][0] - 0.2
            wav = RV / "_seg.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, st - 0.3):.2f}", "-t", f"{l['end'] - l['start'] + 0.8:.2f}", "-i", str(cut),
                            "-ar", "16000", "-ac", "1", str(wav)])
            segs, _ = asr.transcribe(str(wav), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False)
            h = "".join(s.text for s in segs); sc = difflib.SequenceMatcher(None, norm(l["text"]), norm(h)).ratio()
            res.append(dict(shot=k, line=l["text"], heard=h, score=round(sc, 2))); print(k, round(sc, 2), l["text"], "→", h, flush=True)
    for lid, t0 in VT.items():
        wav = RV / "_seg.wav"; d = VS[lid]["dur"]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, t0 - 0.2):.2f}", "-t", f"{d + 0.5:.2f}", "-i", str(cut), "-ar", "16000", "-ac", "1", str(wav)])
        segs, _ = asr.transcribe(str(wav), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False)
        h = "".join(x.text for x in segs); sc = difflib.SequenceMatcher(None, norm(VS[lid]["text"]), norm(h)).ratio()
        res.append(dict(shot="VO", line=VS[lid]["text"], heard=h, score=round(sc, 2))); print("VO", round(sc, 2), VS[lid]["text"], "→", h, flush=True)
    out["pass2_asr"] = res
    (RV / f"{stem}_asr.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit()

# ---- pass 1：逐鏡抽格
rows = []
for k in ORDER:
    a, b = ST[k], end_of(k); row = Image.new("RGB", (448 * 4, 252))
    for j in range(4): row.paste(grab(a + (b - a) * (j + 0.5) / 4), (448 * j, 0))
    ImageDraw.Draw(row).text((6, 4), f"{k}  {a:.1f}–{b:.1f}s", font=font, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0)); rows.append(row)
for p in range(0, len(rows), 11):
    sheet = Image.new("RGB", (448 * 4, 252 * len(rows[p:p + 11])))
    for i, r in enumerate(rows[p:p + 11]): sheet.paste(r, (0, 252 * i))
    sheet.save(RV / f"{stem}_pass1_{p // 11 + 1}.jpg", quality=80)
out["pass1_sheets"] = sorted(x.name for x in RV.glob(f"{stem}_pass1_*.jpg"))

# ---- pass 3：雜訊
sys.path.insert(0, r"C:\AI\tools")
import noise_scan
noisy = []
for k in ORDER:
    c = HERE / "h3" / k / "clip.mp4"
    if c.exists():
        d = noise_scan.dur(str(c)); fs = [f for f in (noise_scan.frame(str(c), d * q) for q in (0.35, 0.6, 0.85)) if f]
        s = max(noise_scan.hf(f) for f in fs) if fs else -1
        f0 = noise_scan.frame(str(c), 0.02); s0 = noise_scan.hf(f0) if f0 else 0
        ratio = s / s0 if s0 else 0
        if s > 0.54 and ratio > 1.25: noisy.append((k, round(s, 3), round(ratio, 2)))   # 比首幀（乾淨關鍵幀）髒 25% 以上才算雜訊
out["pass3_noisy"] = noisy

# ---- pass 4：黑畫面／定格／響度
r = subprocess.run(["ffmpeg", "-i", str(cut), "-vf", "blackdetect=d=0.2:pix_th=0.08,freezedetect=n=0.002:d=0.8", "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
out["pass4_black"] = [l.split("black_start:")[1].split()[0] for l in r.stderr.splitlines() if "black_start" in l]
out["pass4_freeze"] = [l.split("freeze_start:")[1].split()[0] for l in r.stderr.splitlines() if "freeze_start" in l]
summ = r.stderr[r.stderr.rfind("Summary:"):]; m = re.search(r"I:\s*(-?[\d.]+) LUFS", summ); pk = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summ)
out["pass4_loudness_LUFS"] = float(m.group(1)) if m else None; out["pass4_true_peak_dBFS"] = float(pk.group(1)) if pk else None

# ---- pass 5：切點對照、接點明暗、字幕重疊
tiles, jumps = [], []
for a_, b_ in zip(ORDER, ORDER[1:]):
    t = ST[b_]; L, R = grab(t - 0.06, 320, 180), grab(t + 0.03, 320, 180)
    dl = float(np.abs(np.asarray(L, np.float32).mean(axis=(0, 1)) - np.asarray(R, np.float32).mean(axis=(0, 1))).mean())
    if dl > 12: jumps.append((a_, b_, round(dl, 1)))
    row = Image.new("RGB", (640, 180)); row.paste(L, (0, 0)); row.paste(R, (320, 0))
    ImageDraw.Draw(row).text((4, 2), f"{a_}|{b_} {t:.1f}s Δ{dl:.0f}", font=font, fill=(255, 80, 80) if dl > 12 else (255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))
    tiles.append(row)
sheet = Image.new("RGB", (640 * 4, 180 * ((len(tiles) + 3) // 4)))
for i, im in enumerate(tiles): sheet.paste(im, ((i % 4) * 640, (i // 4) * 180))
sheet.save(RV / f"{stem}_pass5_cuts.jpg", quality=80)
out["pass5_brightness_jumps"] = jumps
caps = sorted([(ST[k] + l["start"] - TR[k][0] - 0.2, ST[k] + l["end"] - TR[k][0] - 0.2 + 0.1, l["id"]) for k in ORDER if k in TR for l in TL.get(k, {}).get("lines", [])]
              + [(t0, t0 + VS[lid]["dur"], lid) for lid, t0 in VT.items()])
out["pass5_voice_overlaps"] = [(a[2], b[2], round(a[1] - b[0], 2)) for a, b in zip(caps, caps[1:]) if b[0] < a[1] - 0.05]
out["pass5_lines_cut_by_shot_end"] = [l["id"] for k in ORDER if k in TR for l in TL.get(k, {}).get("lines", []) if l["end"] - TR[k][0] > TR[k][1] + 0.05]
(RV / f"{stem}_review.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
