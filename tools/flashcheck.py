"""逐格量閃爍：整個畫面突然亮一下或暗一下。
原專案實測：H3 開 Veda 稀疏注意力時，整個畫面會在第 51／119／187 格閃一下（亮度跳 18–25 級、約 4 格後退掉）。
關掉 Veda（h3_shot.py 預設關）就不會閃。有閃的鏡不能用。

兩種用法：
  python tools/flashcheck.py --clips <資料夾> [鏡號...]
      逐鏡查「全圖閃」：下一格亮度跳 ≥ 3，而且畫面 80% 以上同向變亮或變暗（手或人走動只動局部，不會被抓到）。
      資料夾裡有 h3/<鏡號>/clip.mp4 就查那些；沒有就查資料夾裡所有 .mp4（鏡號＝檔名）。有閃的鏡會讓程式回傳 1。
  python tools/flashcheck.py <成片.mp4> [--tl timeline.json] [--thr 0.6]
      成片逐格比對前後各 3 格的中位數，列出超過門檻的影格（時間、亮度差、所在鏡與鏡內秒數），
      再列相鄰閃爍的間隔統計，看是不是固定週期。亮度單位＝8-bit 灰階；鏡頭接點前後 2 格不算。
      timeline.json 格式：{"shots": {"鏡號": {"start": 秒, "dur": 秒}, ...}}
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
W, H = 192, 108


def gray_frames(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


def whole_frame(path):
    F = gray_frames(path)
    d = np.diff(F.mean(axis=(1, 2)))
    return [(int(i + 1), round(float(d[i]), 1)) for i in np.flatnonzero(np.abs(d) >= 3)
            if ((F[i + 1] - F[i]) * np.sign(d[i]) > 0).mean() >= 0.8]


def clip_list(folder, ids):
    """{鏡號: 影片路徑}：優先 h3/<鏡號>/clip.mp4，否則資料夾裡的 .mp4。"""
    h3 = folder / "h3"
    if h3.is_dir():
        found = {q.name: q / "clip.mp4" for q in sorted(h3.iterdir()) if (q / "clip.mp4").exists()}
    else:
        found = {q.stem: q for q in sorted(folder.glob("*.mp4"))}
    return {k: found[k] for k in ids} if ids else found


if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    print(__doc__)
    sys.exit(0)

if sys.argv[1] == "--clips":
    folder = Path(sys.argv[2])
    clips = clip_list(folder, sys.argv[3:])
    bad = {k: r for k, p in clips.items() if (r := whole_frame(p))}
    print(f"{folder.name}：{len(clips)} 鏡，全圖閃 {len(bad)} 鏡", flush=True)
    for k, r in bad.items():
        print(" ⚠", k, r, flush=True)
    sys.exit(1 if bad else 0)

p = sys.argv[1]
thr = float(sys.argv[sys.argv.index("--thr") + 1]) if "--thr" in sys.argv else 0.6
pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", p],
                    capture_output=True, text=True).stdout.strip().split("/")
fps = float(pr[0]) / float(pr[1]) if len(pr) == 2 else float(pr[0])
Y = gray_frames(p).mean(axis=(1, 2))
n = len(Y)
cuts, shots = set(), []
if "--tl" in sys.argv:
    tl = json.loads(Path(sys.argv[sys.argv.index("--tl") + 1]).read_text(encoding="utf-8"))
    shots = sorted((v["start"], v["dur"], k) for k, v in tl["shots"].items())
    for s, d, k in shots:
        for j in range(-2, 3):
            cuts.add(int(round(s * fps)) + j)


def where(i):
    t = i / fps
    for s, d, k in shots:
        if s <= t < s + d:
            return f"{k}+{t - s:.2f}"
    return ""


dev = np.zeros(n, np.float32)
for i in range(3, n - 3):
    if i in cuts:
        continue
    dev[i] = Y[i] - np.median(Y[[i - 3, i - 2, i - 1, i + 1, i + 2, i + 3]])
idx = [i for i in np.flatnonzero(np.abs(dev) >= thr)]
print(f"{Path(p).name} {n} 格 {fps:.3f} fps；|亮度差| ≥ {thr} 的影格 {len(idx)} 個；最大 {np.abs(dev).max():.2f}；平均亮度跳動 {np.abs(np.diff(Y)).mean():.3f}")
for i in idx[:60]:
    print(f"  {i / fps:7.2f}s 第{i}格 差{dev[i]:+.2f} {where(i)}")
if len(idx) > 1:
    print("  相鄰間隔（格）：", Counter(np.diff(idx).tolist()).most_common(8))
    print("  除以 8／17／24 的餘數分布：", {m: Counter((np.array(idx) % m).tolist()).most_common(3) for m in (8, 17, 24)})
