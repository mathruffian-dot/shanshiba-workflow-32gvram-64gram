# SPDX-License-Identifier: GPL-3.0-or-later
# This script imports ComfyUI and ComfyUI-FlashVSR_Ultra_Fast (GPL-3.0) code at runtime, so it is licensed GPL-3.0-or-later.
"""FlashVSR v1.1 x2（不經 ComfyUI 伺服器，直接載入節點程式）。H3 venv：python flashvsr_cli.py in.mp4 out_dir"""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

COMFY = Path(r"C:\AI\H3\ComfyUI-0.36.0")
sys.path.insert(0, str(COMFY))
src, d = Path(sys.argv[1]), Path(sys.argv[2]); d.mkdir(parents=True, exist_ok=True)
NODE = COMFY / "custom_nodes" / "ComfyUI-FlashVSR_Ultra_Fast"
spec = importlib.util.spec_from_file_location("flashvsr_node", NODE / "__init__.py", submodule_search_locations=[str(NODE)])
mod = importlib.util.module_from_spec(spec); sys.modules["flashvsr_node"] = mod; spec.loader.exec_module(mod)
Node = mod.NODE_CLASS_MAPPINGS["FlashVSRNode"]
w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True).stdout.strip().split(","))
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
frames = torch.from_numpy(np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32) / 255.0)
t0 = time.time()
out = Node().main(model="FlashVSR-v1.1", frames=frames, mode="tiny", scale=2, tiled_vae=True, tiled_dit=True, unload_dit=False, seed=0)[0]
wall = time.time() - t0
o = (out.clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
n, oh, ow, _ = o.shape
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}", "-r", "24", "-i", "-", "-c:v", "libx264",
                "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", str(d / "clip.mp4")], input=o.tobytes(), check=True)
(d / "meta.json").write_text(json.dumps({"ok": True, "frames": n, "size": f"{ow}x{oh}", "wall_s": round(wall, 1)}), encoding="utf-8")
print("FLASHVSR_OK", n, ow, oh, round(wall, 1))
