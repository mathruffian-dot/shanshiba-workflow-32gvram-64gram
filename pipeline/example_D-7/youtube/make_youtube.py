"""封面（1280x720）＋字幕 srt。python youtube/make_youtube.py"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
H = Path(__file__).resolve().parents[1]; Y = H / "youtube"
JH = "C:/Windows/Fonts/msjhbd.ttc"; W, HH = 1280, 720
cols = [("N3a", "一週前", (120, 220, 140)), ("P3b", "前一天", (255, 200, 80)), ("N3c", "考卷發下來才知道", (255, 110, 110))]
im = Image.new("RGB", (W, HH), (10, 10, 12)); cw, gap = 420, 10
for i, (k, lab, col) in enumerate(cols):
    src = Image.open(H / "first" / f"{k}.png").convert("RGB"); s = cw / src.width; src = src.resize((cw, int(src.height * s)))
    top = max(0, min(int(src.height * 0.08), src.height - HH)); crop = src.crop((0, top, cw, top + HH))
    im.paste(ImageEnhance.Contrast(crop).enhance(1.08), (i * (cw + gap), 0))
d = ImageDraw.Draw(im, "RGBA")
d.rectangle((0, 0, W, 170), fill=(0, 0, 0, 165))
f1 = ImageFont.truetype(JH, 96); t = "段考，學生分三種"; b = d.textbbox((0, 0), t, font=f1)
d.text(((W - b[2]) / 2, 22), t, font=f1, fill=(255, 235, 120), stroke_width=7, stroke_fill=(0, 0, 0))
f2 = ImageFont.truetype(JH, 44)
for i, (k, lab, col) in enumerate(cols):
    fs = f2 if len(lab) < 6 else ImageFont.truetype(JH, 36)
    b = d.textbbox((0, 0), lab, font=fs); x = i * (cw + gap) + (cw - b[2]) / 2
    d.rounded_rectangle((x - 18, 600, x + b[2] + 18, 600 + b[3] + 22), 14, fill=(0, 0, 0, 190)); d.text((x, 606), lab, font=fs, fill=col)
f3 = ImageFont.truetype(JH, 34); t = "（其實還有第四種）"; b = d.textbbox((0, 0), t, font=f3)
d.text((W - b[2] - 24, 128), t, font=f3, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
im.save(Y / "thumbnail_1280x720_v1.jpg", quality=92)
caps = json.loads((H / "post/captions.json").read_text(encoding="utf-8"))
def ts(x): h, r = divmod(x, 3600); m, s = divmod(r, 60); return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"
(Y / "subtitles_zh-TW.srt").write_text("".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t.rstrip('。')}\n\n" for i, (a, b, t) in enumerate(caps, 1)), encoding="utf-8")
print("ok", len(caps))
