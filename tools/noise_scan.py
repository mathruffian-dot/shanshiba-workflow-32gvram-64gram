"""Noise scan for H3 clips (2026-09-27): EasyCache on near-static shots leaves oil-paint / chroma speckle noise.
Metric per frame = mean |chroma - 3x3 box blur(chroma)| (Cb+Cr, 0-255 scale) on the 1344x768 frame; a clip's score is the
max over frames at 35/60/85 % of its length, and 'ratio' = score / score of its first frame (the clean pinned keyframe).
Usage: python noise_scan.py clip.mp4 [clip2 ...]  -> prints  score ratio path"""
import subprocess
import sys

import numpy as np
from PIL import Image


def frame(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=1344:768",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return Image.frombytes("RGB", (1344, 768), raw) if len(raw) == 1344 * 768 * 3 else None


def hf(im):
    a = np.asarray(im.convert("YCbCr"), dtype=np.float32)[:, :, 1:]
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    blur = sum(p[y:y + a.shape[0], x:x + a.shape[1]] for y in range(3) for x in range(3)) / 9
    return float(np.abs(a - blur).mean())


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True).stdout.strip() or 0)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        d = dur(p)
        f0 = frame(p, 0.02)
        fs = [f for f in (frame(p, d * k) for k in (0.35, 0.6, 0.85)) if f]
        if not fs:
            print(f"-1 0 {p}  (no frames, dur {d})", flush=True)
            continue
        s0 = hf(f0) if f0 else 0
        s = max(hf(f) for f in fs)
        print(f"{s:.3f} {s / s0 if s0 else 0:.2f} {p}", flush=True)
