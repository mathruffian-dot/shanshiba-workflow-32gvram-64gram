"""H3 片段抽格表：python clip_sheet.py out.jpg S01 S02 ...（每鏡 6 格，標秒數）"""
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
H = Path(__file__).resolve().parent; f = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 20)
out, ids = sys.argv[1], sys.argv[2:]; rows = []
for k in ids:
    c = H / "h3" / k / "clip.mp4"
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(c)], capture_output=True, text=True).stdout)
    tiles = []
    for j in range(6):
        t = d * (j + 0.5) / 6; raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(c), "-frames:v", "1", "-vf", "scale=-2:240", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        import io; im = Image.open(io.BytesIO(raw)).convert("RGB"); ImageDraw.Draw(im).text((4, 2), f"{k} {t:.1f}s", font=f, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0)); tiles.append(im)
    row = Image.new("RGB", (sum(t.width for t in tiles), 240)); x = 0
    for t in tiles: row.paste(t, (x, 0)); x += t.width
    rows.append(row)
S = Image.new("RGB", (max(r.width for r in rows), 240 * len(rows)))
for i, r in enumerate(rows): S.paste(r, (0, 240 * i))
S.save(H / out, quality=80)
