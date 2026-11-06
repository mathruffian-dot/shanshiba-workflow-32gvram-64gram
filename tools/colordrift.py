"""逐鏡查「鏡頭內整體顏色漂移」（第 9 集：H3 偶爾在第 1–2 秒把布幕／天空的飽和度拉高，同一場前後鏡接不起來）。
用法：python colordrift.py <集資料夾> [鏡號...] [--th 10]
做法：每 0.5 秒取一格、縮成 64×36，算平均 RGB 與首幀的最大距離；超過門檻（預設 10，0–255 尺度）就列出。
只看整體顏色，人物走動不太影響；出現距離大但畫面其實是切鏡或打燈的，要人看過再決定。"""
import argparse
import subprocess
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("ep"); ap.add_argument("ids", nargs="*"); ap.add_argument("--th", type=float, default=10)
a = ap.parse_args()
EP = Path(a.ep).resolve()
ids = a.ids or sorted(p.name for p in (EP / "h3").iterdir() if (p / "clip.mp4").exists())
W, H = 64, 36
bad = 0
for k in ids:
    v = EP / "h3" / k / "clip.mp4"
    if not v.exists():
        continue
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-vf", f"fps=2,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.uint8)
    n = len(x) // (W * H * 3)
    if n < 2:
        continue
    m = x[:n * W * H * 3].reshape(n, H, W, 3).astype(np.float32).mean(axis=(1, 2))
    d = np.abs(m - m[0]).max(axis=1)
    i = int(d.argmax())
    if d[i] >= a.th:
        bad += 1
        print(f"{k} 漂移 {d[i]:.1f} @ {i / 2:.1f}s  首幀 RGB {m[0].round().astype(int).tolist()} → {m[i].round().astype(int).tolist()}")
print(f"共 {len(ids)} 鏡，{bad} 鏡超過 {a.th}")
