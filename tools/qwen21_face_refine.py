"""Per-character refine for multi-person Qwen-Image 2.1 frames (2026-10-06).

Why: stacking two character LoRAs (e.g. 0.8 + 0.8) dilutes both identities. Instead, generate the composition first,
then for each character crop a box around head + upper body, re-denoise ONLY that crop with that character's LoRA at
1.0 and a single-person prompt, and paste it back with a feathered mask. Everything outside the boxes stays identical.

Usage (H3 venv or any python with Pillow; ComfyUI must be running):
  python qwen21_face_refine.py src.png out.png --box x0 y0 x1 y1 --lora afu_img25_qwen21_768_1600.safetensors
         --prompt "afu_img25, the boy Afu, ..." [--box ... --lora ... --prompt ...] [--denoise 0.55] [--seed 1] [--steps 30]
Boxes are in source-image pixels; each --box needs its own --lora and --prompt (same order).
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, r"C:\AI\tools")
import gen_image as gi  # noqa: E402

WORK = 1024  # crop is processed at this size (square boxes recommended)


def refine_crop(crop_path, lora, prompt, denoise, seed, steps, w, h):
    p = gi.PRESETS["qwen21"]
    g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": p["unet"], "weight_dtype": "default"}},
         "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": p["clip"], "type": p["clip_type"], "device": "default"}},
         "3": {"class_type": "VAELoader", "inputs": {"vae_name": p["vae"]}},
         "40": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": 1.0}},
         "10": {"class_type": "LoadImage", "inputs": {"image": gi.stage_image(str(crop_path))}},
         "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["3", 0]}},
         "4": {"class_type": "TextEncodeQwenImage21",
               "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": "blurry, deformed", "resolution": 1024}},
         "6": {"class_type": "KSampler", "inputs": {"model": ["40", 0], "latent_image": ["12", 0], "seed": seed, "steps": steps,
                                                    "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": denoise,
                                                    "positive": ["4", 0], "negative": ["4", 1]}},
         "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
         "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "refine/crop"}}}
    pid = gi._req(gi.DEFAULT_HOST, "/prompt", {"prompt": g})["prompt_id"]
    while True:
        time.sleep(2)
        hist = gi._req(gi.DEFAULT_HOST, f"/history/{pid}")
        if pid in hist:
            break
    st = hist[pid].get("status", {})
    if st.get("status_str") != "success":
        sys.exit(str(st)[:1500])
    f = hist[pid]["outputs"]["8"]["images"][0]
    return Image.open(gi.COMFY_DIR / "output" / f.get("subfolder", "") / f["filename"]).convert("RGB").resize((w, h), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--box", nargs=4, type=int, action="append", required=True)
    ap.add_argument("--lora", action="append", required=True)
    ap.add_argument("--prompt", action="append", required=True)
    ap.add_argument("--denoise", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=30)
    a = ap.parse_args()
    assert len(a.box) == len(a.lora) == len(a.prompt), "each --box needs its own --lora and --prompt"
    img = Image.open(a.src).convert("RGB")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for i, (box, lora, prompt) in enumerate(zip(a.box, a.lora, a.prompt)):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        tmp = out.with_name(f"{out.stem}_crop{i}.png")
        img.crop(box).resize((WORK, round(WORK * h / w / 16) * 16), Image.LANCZOS).save(tmp)
        t0 = time.time()
        new = refine_crop(tmp, lora, prompt, a.denoise, a.seed + i, a.steps, w, h)
        new.save(out.with_name(f"{out.stem}_crop{i}_refined.png"))
        # feathered mask: full inside, fades over the outer ~12% of the box so the seam disappears
        f = max(8, int(min(w, h) * 0.12))
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rectangle((f, f, w - f, h - f), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(f / 2))
        img.paste(new, (x0, y0), m)
        print(f"[box {i}] {lora} {round(time.time() - t0, 1)}s", flush=True)
    img.save(out)
    print("ok", out)


if __name__ == "__main__":
    main()
