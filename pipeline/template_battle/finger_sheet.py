"""手指放大表（〈向日葵之戰〉使用者 2026-11-04 抓到 3:50 手只有 4 根）：
每鏡首幀用 YOLO pose 找手腕，沿「手肘→手腕」方向切出手部，拼成 out/review/fingers_XX.jpg，一隻一隻數。
--clips：改看 H3 成片（使用者 2026-11-04 抓到 1:55 第 6 根指頭：首幀是 5 根，H3 拍動作時才多長出來，只查首幀抓不到），每鏡取 25%／50%／75% 三格，只留看得清手指的大手。
用法（Voice venv）：python finger_sheet.py [--clips] [鏡號 …]"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
CLIPS = "--clips" in sys.argv
args = [x for x in sys.argv[1:] if x != "--clips"]
want = args or [s["id"] for s in CFG["shots"] if not s.get("painting")]
TH, COLS, ROWS = int(os.environ.get("FINGER_TH", 260)), int(os.environ.get("FINGER_COLS", 8)), 5
model = YOLO(os.environ.get("AI_ROOT", r"C:\AI") + r"\tools\models\yolo\yolo11x-pose.pt")
font = ImageFont.truetype(os.environ.get("FONT_JHBD", r"C:\Windows\Fonts\arial.ttf"), 22)
crops = []


def samples(sid):
    if not CLIPS:
        p = OUT / "first" / f"{sid}.png"
        if p.exists():
            yield sid, cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
        return
    p = OUT / "h3" / sid / "clip.mp4"
    if not p.exists():
        return
    cap = cv2.VideoCapture(str(p))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for f in (0.25, 0.5, 0.75):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * f))
        ok, im = cap.read()
        if ok:
            yield f"{sid} {int(f * 100)}", im
    cap.release()


for sid, img in (x for s_ in want for x in samples(s_)):
    res = model.predict(img, conf=0.35, verbose=False, device=os.environ.get("YOLO_DEVICE", "cpu"))[0]
    kp = res.keypoints.data.cpu().numpy() if res.keypoints is not None else np.zeros((0, 17, 3))
    H, W = img.shape[:2]
    for person in kp:
        shoulder = np.linalg.norm(person[5][:2] - person[6][:2])
        for el, wr in ((7, 9), (8, 10)):
            if person[wr][2] < 0.3:
                continue
            e, w = person[el][:2], person[wr][:2]
            c = w + (w - e) * 0.35
            r = int(max(70, min(220, np.linalg.norm(w - e) * 0.7, shoulder * 0.55) if shoulder else 110))
            if CLIPS and r < int(os.environ.get("FINGER_MIN_R", 75)):      # 手太小，觀眾也數不到
                continue
            x0, y0 = int(np.clip(c[0] - r, 0, W - 1)), int(np.clip(c[1] - r, 0, H - 1))
            x1, y1 = int(np.clip(c[0] + r, 1, W)), int(np.clip(c[1] + r, 1, H))
            if x1 - x0 < 40 or y1 - y0 < 40:
                continue
            crops.append((sid, Image.fromarray(cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)).resize((TH, TH), Image.LANCZOS)))
(OUT / "review").mkdir(exist_ok=True)
n = COLS * ROWS
for k in range(0, len(crops), n):
    sheet = Image.new("RGB", (COLS * TH, ROWS * TH), "black")
    d = ImageDraw.Draw(sheet)
    for i, (sid, c) in enumerate(crops[k:k + n]):
        x, y = i % COLS * TH, i // COLS * TH
        sheet.paste(c, (x, y))
        d.rectangle((x, y, x + 110, y + 28), fill="black")
        d.text((x + 4, y + 2), sid, fill="yellow", font=font)
    sheet.save(OUT / "review" / f"{'cfingers' if CLIPS else 'fingers'}_{k // n:02d}.jpg", quality=88)
print(len(crops), "隻手；", (len(crops) + n - 1) // n, "張表")
