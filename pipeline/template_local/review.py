"""自審五遍（讀 make_film.py 寫的 out/post/edl.json）。make_film.py 的 review 階段會自動呼叫，也可以單獨跑：
  C:\\AI\\H3\\venv\\Scripts\\python.exe review.py out\\cut\\film_1080p.mp4          第 1／3／4／5 遍
  C:\\AI\\Voice\\venv\\Scripts\\python.exe review.py out\\cut\\film_1080p.mp4 --asr  第 2 遍（成片聽寫）
結果在 out/review/：<片名>_pass1.jpg（逐鏡 4 格）、_pass5_cuts.jpg（切點前後）、_review.json、_asr.json。
判讀標準見 docs/04_自審清單.md；數字只是輔助，最後一定要人看成片。"""
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

cut = Path(sys.argv[1]).resolve(); stem = cut.stem
OUT = cut.parent.parent; RV = OUT / "review"; RV.mkdir(exist_ok=True)
E = json.loads((OUT / "post" / "edl.json").read_text(encoding="utf-8")); SH = E["shots"]
TOOLS = __import__("os").environ.get("AI_TOOLS", r"C:\AI\tools")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from fonts import font as _font  # noqa: E402  (Windows 字型；Linux 用 Noto CJK)
font = ImageFont.truetype(_font("jh"), 20)
out = {}


def grab(t, w=448, h=252):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(cut), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return Image.frombytes("RGB", (w, h), raw) if len(raw) == w * h * 3 else Image.new("RGB", (w, h))


if "--asr" in sys.argv:                              # 第 2 遍：每句台詞從成片裡切出來聽寫，跟劇本比對
    sys.path.insert(0, TOOLS)
    from stt import _add_cuda_dll_dirs, MODEL_CACHE
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel
    from opencc import OpenCC
    t2s = OpenCC("t2s"); asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=str(MODEL_CACHE))
    norm = lambda s: re.sub(r"[\s，。？！、,.?!…—「」]", "", t2s.convert(s))
    res = []
    for r in SH:
        for l in r["lines"]:
            wav = RV / "_seg.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, l['film_start'] - 0.3):.2f}", "-t", f"{l['film_end'] - l['film_start'] + 0.7:.2f}",
                            "-i", str(cut), "-ar", "16000", "-ac", "1", str(wav)])
            segs, _ = asr.transcribe(str(wav), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False)
            h = "".join(s.text for s in segs); sc = difflib.SequenceMatcher(None, norm(l["text"]), norm(h)).ratio()
            res.append(dict(shot=r["id"], line=l["text"], heard=h, score=round(sc, 2)))
            print(f"pass2 {r['id']} {sc:.2f} {l['text']} → {h}", flush=True)
    (RV / "_seg.wav").unlink(missing_ok=True)
    (RV / f"{stem}_asr.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    low = [x for x in res if x["score"] < 0.8]
    print("pass2 ASR：全部 ≥0.8" if not low else f"pass2 ASR 低於 0.8：{low}（同音字可能是 ASR 聽錯，請人聽確認）")
    sys.exit()

# 第 1 遍：逐鏡 4 格
rows = []
for r in SH:
    a, b = r["start"], r["start"] + r["dur"]; row = Image.new("RGB", (448 * 4, 252))
    for j in range(4):
        row.paste(grab(a + (b - a) * (j + 0.5) / 4), (448 * j, 0))
    ImageDraw.Draw(row).text((6, 4), f"{r['id']}  {a:.1f}-{b:.1f}s", font=font, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0)); rows.append(row)
sheet = Image.new("RGB", (448 * 4, 252 * len(rows)))
for i, r in enumerate(rows):
    sheet.paste(r, (0, 252 * i))
sheet.save(RV / f"{stem}_pass1.jpg", quality=82); out["pass1_sheet"] = f"{stem}_pass1.jpg"

# 第 3 遍：色度雜訊（跟首幀比，H3 偶爾整鏡變顆粒）
sys.path.insert(0, TOOLS)
import noise_scan  # noqa: E402
noisy = []
for r in SH:
    c = OUT / "h3" / r["id"] / "clip.mp4"
    d = noise_scan.dur(str(c)); fs = [f for f in (noise_scan.frame(str(c), d * q) for q in (0.35, 0.6, 0.85)) if f]
    s = max(noise_scan.hf(f) for f in fs) if fs else -1; f0 = noise_scan.frame(str(c), 0.02); s0 = noise_scan.hf(f0) if f0 else 0
    ratio = s / s0 if s0 else 0
    noisy.append((r["id"], round(s, 3), round(ratio, 2), "WARN" if (s > 0.54 and ratio > 1.25) else "ok"))
out["pass3_noise"] = noisy

# 第 4 遍：黑畫面、定格、響度
p = subprocess.run(["ffmpeg", "-i", str(cut), "-vf", "blackdetect=d=0.2:pix_th=0.08,freezedetect=n=0.002:d=0.8", "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
out["pass4_black"] = [l.split("black_start:")[1].split()[0] for l in p.stderr.splitlines() if "black_start" in l]
out["pass4_freeze"] = [l.split("freeze_start:")[1].split()[0] for l in p.stderr.splitlines() if "freeze_start" in l]
summ = p.stderr[p.stderr.rfind("Summary:"):]; m = re.search(r"I:\s*(-?[\d.]+) LUFS", summ); pk = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summ)
out["pass4_loudness_LUFS"] = float(m.group(1)) if m else None; out["pass4_true_peak_dBFS"] = float(pk.group(1)) if pk else None
out["pass4_loudness_ok"] = bool(m and pk and -16.5 <= float(m.group(1)) <= -14.5 and float(pk.group(1)) <= -1.0)

# 第 5 遍：切點明暗差、台詞重疊、台詞被鏡尾切掉
tiles, jumps = [], []
cuts = [(a["id"], b["id"], b["start"]) for a, b in zip(SH, SH[1:])] + [(SH[-1]["id"], "END", E["story_end"])]
for a_, b_, t in cuts:
    L, R = grab(t - 0.06, 320, 180), grab(t + 0.03, 320, 180)
    dl = float(np.abs(np.asarray(L, np.float32).mean(axis=(0, 1)) - np.asarray(R, np.float32).mean(axis=(0, 1))).mean())
    if dl > 12 and b_ != "END":
        jumps.append((a_, b_, round(dl, 1)))
    row = Image.new("RGB", (640, 180)); row.paste(L, (0, 0)); row.paste(R, (320, 0))
    ImageDraw.Draw(row).text((4, 2), f"{a_}|{b_} {t:.1f}s d{dl:.0f}", font=font, fill=(255, 80, 80) if dl > 12 else (255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))
    tiles.append(row)
sheet = Image.new("RGB", (640 * 4, 180 * ((len(tiles) + 3) // 4)))
for i, im in enumerate(tiles):
    sheet.paste(im, ((i % 4) * 640, (i // 4) * 180))
sheet.save(RV / f"{stem}_pass5_cuts.jpg", quality=82)
out["pass5_brightness_jumps"] = jumps
caps = sorted([(l["film_start"], l["film_end"], l["id"]) for r in SH for l in r["lines"]])
out["pass5_voice_overlaps"] = [(a[2], b[2], round(a[1] - b[0], 2)) for a, b in zip(caps, caps[1:]) if b[0] < a[1] - 0.05]
out["pass5_lines_cut_by_shot_end"] = [l["id"] for r in SH for l in r["lines"] if l["film_end"] > r["start"] + r["dur"] + 0.05]
(RV / f"{stem}_review.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
