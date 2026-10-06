"""YuE2 music generation via the local ComfyUI API (native YuE2 nodes, ComfyUI >= 0.35).

Prereqs:
  * ComfyUI running on http://127.0.0.1:8188  (see tools/start_comfy.ps1)
  * YuE2 checkpoint in ComfyUI/models/checkpoints (see scripts/local_yue2/download_yue2.py)

Examples:
  & "C:\\AI\\H3\\venv\\Scripts\\python.exe" tools/gen_music.py --style "K-pop, female vocal" --lyrics-file song.txt --seconds 240 --mode abc
  ... --style-file style.txt --lyrics-file lyrics.txt --seed 42 --prefix audio/YuE2/mysong

Outputs go to ComfyUI/output/<prefix>_00001.flac (48 kHz stereo). The script prints the path.
"""
import argparse
import json
import shutil
import time
import urllib.request
from pathlib import Path

DEFAULT_HOST = "http://127.0.0.1:8188"
COMFY_DIR = Path(r"C:\AI\H3\ComfyUI-0.36.0")
CKPT = "yue2_3b_int8_convrot.safetensors"

DEFAULT_STYLE = "Mandarin pop, warm acoustic guitar, soft piano, 90 BPM, warm and sincere"
DEFAULT_LYRICS = "[verse]\n你好 世界\n[chorus]\n這是一首歌\n"


def _req(host, path, data=None, timeout=60):
    req = urllib.request.Request(
        host + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ensure_server(host):
    try:
        return _req(host, "/system_stats", timeout=5)
    except Exception as e:
        raise SystemExit(
            f"ComfyUI is not reachable at {host} ({e}).\n"
            f"Start it first:  tools\\start_comfy.ps1"
        )


def build(ckpt, style, lyrics, seed, mode, seconds, steps):
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "3": {"class_type": "EmptyYuE2LatentAudio",
              "inputs": {"seconds": ["2", 1], "batch_size": 1}},
        "4": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["4", 0],
                         "latent_image": ["3", 0], "seed": seed, "steps": steps,
                         "cfg": 1.0, "sampler_name": "dpm_2", "scheduler": "sgm_uniform",
                         "denoise": 1.0}},
        "6": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveAudio", "inputs": {"audio": ["6", 0], "filename_prefix": "audio/YuE2/gen"}},
    }
    gm = {"clip": ["1", 1], "style": style, "lyrics": lyrics, "seed": seed,
          "mode": "full", "max_duration": float(seconds),
          "temperature": 1.0, "top_p": 0.95, "top_k": 100, "repetition_penalty": 1.2}
    if mode == "abc":
        g["8"] = {"class_type": "YuE2GenerateABC",
                  "inputs": {"clip": ["1", 1], "style": style, "lyrics": lyrics,
                             "seed": seed, "mode": "full", "max_abc_tokens": 8192,
                             "temperature": 0.7, "top_p": 0.9, "top_k": 30,
                             "repetition_penalty": 1.005, "penalty_window": 100}}
        gm["abc"] = ["8", 0]
    else:
        gm["abc"] = ""
        gm["cfg_scale"] = 1.01
    g["2"] = {"class_type": "YuE2GenerateMusic", "inputs": gm}
    return g


def main():
    ap = argparse.ArgumentParser(description="Generate music with YuE2 (ComfyUI API).")
    ap.add_argument("--style", default=None)
    ap.add_argument("--style-file", default=None)
    ap.add_argument("--lyrics", default=None)
    ap.add_argument("--lyrics-file", default=None)
    ap.add_argument("--seconds", type=float, default=200.0, help="max duration (model may finish earlier)")
    ap.add_argument("--mode", choices=["off", "abc"], default="abc")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--ckpt", default=CKPT)
    ap.add_argument("--prefix", default="audio/YuE2/gen")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--out", default=None, help="optional folder to copy the finished audio into")
    a = ap.parse_args()

    style = Path(a.style_file).read_text(encoding="utf-8").strip() if a.style_file else (a.style or DEFAULT_STYLE)
    lyrics = Path(a.lyrics_file).read_text(encoding="utf-8").strip() if a.lyrics_file else (a.lyrics or DEFAULT_LYRICS)

    ensure_server(a.host)
    graph = build(a.ckpt, style, lyrics, a.seed, a.mode, a.seconds, a.steps)
    graph["7"]["inputs"]["filename_prefix"] = a.prefix

    res = _req(a.host, "/prompt", {"prompt": graph})
    pid = res["prompt_id"]
    print(f"[queued] prompt_id={pid} mode={a.mode} seconds={a.seconds} seed={a.seed}", flush=True)

    t0 = time.time()
    while True:
        time.sleep(3)
        h = _req(a.host, f"/history/{pid}")
        if pid in h:
            entry = h[pid]
            status = entry.get("status", {})
            print(f"[status] {status.get('status_str')} wall={time.time() - t0:.1f}s", flush=True)
            if status.get("status_str") == "error":
                print(json.dumps(status, ensure_ascii=False, indent=2)[:4000])
                return
            for node_id, o in entry.get("outputs", {}).items():
                for key in ("audio", "audios"):
                    for f in o.get(key, []) or []:
                        p = COMFY_DIR / "output" / f.get("subfolder", "") / f.get("filename", "")
                        print(f"[out] {p}")
                        if a.out:
                            dest = Path(a.out)
                            dest.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(p, dest / p.name)
                            print(f"[copy] {dest / p.name}")
            print(f"[done] total {time.time() - t0:.1f}s")
            return


if __name__ == "__main__":
    main()
