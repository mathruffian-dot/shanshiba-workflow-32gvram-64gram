"""MiniMax Music 3 via local ComfyUI API (int8 DiT + pruned int8 text encoder + DAV VAE).
Usage: C:\\AI\\H3\\venv\\Scripts\\python.exe C:\\AI\\tools\\gen_music3.py --caption-file cap.txt --lyrics-file lyr.txt --seconds 60 --seed 7 --prefix audio/MM3/afu --out <dir>
Instrumental: lyrics file with section tags only ([Intro] [Verse] [Chorus] [Instrumental] [Outro]) and no text under them.
License: MiniMax-Music3 Community License (check LICENSE: attribution + AI disclosure; revenue cap) - verify before commercial use."""
import argparse, json, shutil, time, urllib.request
import os
from pathlib import Path

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY_DIR = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0"))
DIT = "minimax_music3_dit_int8_convrot.safetensors"
TE = "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"
VAE = "minimax_music3_dav.safetensors"


def _req(path, data=None, timeout=60):
    req = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def build(caption, lyrics, seed, seconds, steps, cfg, tiled):
    g = {
        "6": {"class_type": "UNETLoader", "inputs": {"unet_name": DIT, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": TE, "type": "minimax", "device": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "13": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {"clip": ["3", 0], "caption": caption, "lyrics": lyrics, "seed": seed, "max_duration": float(seconds), "cfg_scale": 1.7, "top_k": 50}},
        "15": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {"seconds": ["13", 1], "batch_size": 1}},
        "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["13", 0]}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["6", 0], "positive": ["13", 0], "negative": ["10", 0], "latent_image": ["15", 0], "seed": seed, "steps": steps, "cfg": cfg,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
    }
    if tiled:
        g["12"] = {"class_type": "VAEDecodeAudioTiled", "inputs": {"samples": ["9", 0], "vae": ["7", 0], "tile_size": 1536, "overlap": 64}}
    else:
        g["12"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["9", 0], "vae": ["7", 0]}}
    g["20"] = {"class_type": "SaveAudio", "inputs": {"audio": ["12", 0], "filename_prefix": "audio/MM3/gen"}}
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caption", default=None); ap.add_argument("--caption-file", default=None)
    ap.add_argument("--lyrics", default=None); ap.add_argument("--lyrics-file", default=None)
    ap.add_argument("--seconds", type=float, default=60.0); ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--steps", type=int, default=30); ap.add_argument("--cfg", type=float, default=1.7)
    ap.add_argument("--tiled", action="store_true"); ap.add_argument("--prefix", default="audio/MM3/gen"); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    caption = Path(a.caption_file).read_text(encoding="utf-8").strip() if a.caption_file else (a.caption or "")
    lyrics = Path(a.lyrics_file).read_text(encoding="utf-8").strip() if a.lyrics_file else (a.lyrics or "[Intro]\n[Instrumental]\n[Outro]")
    g = build(caption, lyrics, a.seed, a.seconds, a.steps, a.cfg, a.tiled); g["20"]["inputs"]["filename_prefix"] = a.prefix
    pid = _req("/prompt", {"prompt": g})["prompt_id"]; print("[queued]", pid, flush=True); t0 = time.time()
    while True:
        time.sleep(3); h = _req(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {}); print("[status]", st.get("status_str"), round(time.time() - t0, 1), "s", flush=True)
            if st.get("status_str") == "error": print(json.dumps(st, ensure_ascii=False, indent=1)[:4000]); return
            for o in h[pid].get("outputs", {}).values():
                for f in (o.get("audio") or []):
                    p = COMFY_DIR / "output" / f.get("subfolder", "") / f["filename"]; print("[out]", p)
                    if a.out: Path(a.out).mkdir(parents=True, exist_ok=True); shutil.copy2(p, Path(a.out) / p.name); print("[copy]", Path(a.out) / p.name)
            print("[done] total", round(time.time() - t0, 1), "s"); return


if __name__ == "__main__":
    main()
