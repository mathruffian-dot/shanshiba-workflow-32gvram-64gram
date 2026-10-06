"""首幀總覽：python sheet_frames.py out.jpg id1 id2 ...（直式小格自動並排）"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
H = Path(__file__).resolve().parent; f = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 26)
out, ids = sys.argv[1], sys.argv[2:]
tiles = []
for k in ids:
    im = Image.open(H / "first" / f"{k}.png").convert("RGB"); h = 432; im = im.resize((int(im.width * h / im.height), h))
    ImageDraw.Draw(im).text((8, 6), k, font=f, fill=(255, 255, 0), stroke_width=3, stroke_fill=(0, 0, 0)); tiles.append(im)
rows, cur, w = [], [], 0
for t in tiles:
    if w + t.width > 2300 and cur: rows.append(cur); cur, w = [], 0
    cur.append(t); w += t.width
rows.append(cur)
S = Image.new("RGB", (max(sum(t.width for t in r) for r in rows), 432 * len(rows)))
for i, r in enumerate(rows):
    x = 0
    for t in r: S.paste(t, (x, 432 * i)); x += t.width
S.save(H / out, quality=82)
