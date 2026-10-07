"""Local voice generation and speech synthesis (TTS) via VoxCPM2 and Edge-TTS.

Engines:
  voxcpm2   OpenBMB VoxCPM2 on NVIDIA RTX 5090 CUDA (48 kHz high-fidelity, voice cloning)
  edge      Microsoft Edge TTS (fast, zero GPU memory, broadcast neural voices)

Examples:
  & "C:\\AI\\Voice\\venv\\Scripts\\python.exe" C:\\AI\\tools\\gen_voice.py --text "大家好，今天進行語音生成測試。"
  & "C:\\AI\\Voice\\venv\\Scripts\\python.exe" C:\\AI\\tools\\gen_voice.py --text "測試" --ref "C:\\path\\sample.wav" --out "out.wav"
  & "C:\\AI\\Voice\\venv\\Scripts\\python.exe" C:\\AI\\tools\\gen_voice.py --engine edge --text "微軟雲端語音測試" --voice zh-TW-HsiaoChenNeural
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

VOICE_DIR = Path(r"C:\AI\Voice")
DEFAULT_REF = VOICE_DIR / "references" / "default.wav"
OUTPUT_DIR = VOICE_DIR / "output"
MODEL_PATH = VOICE_DIR / "models" / "VoxCPM2"


def generate_voxcpm2(text: str, ref_wav: str | None, out_path: Path, cfg: float, steps: int, seed: int, control: str | None = None, no_default_ref: bool = False):
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"VoxCPM2 model path does not exist: {MODEL_PATH}")

    ref_audio = ref_wav if (ref_wav and Path(ref_wav).exists()) else (str(DEFAULT_REF) if DEFAULT_REF.exists() and not no_default_ref else None)
    if control:  # VoxCPM2 voice design: "(description)text"; with no reference audio it designs a new voice (2026-10-07)
        text = f"({control.strip()}){text}"
    
    torch.manual_seed(seed)
    model = VoxCPM.from_pretrained(str(MODEL_PATH), load_denoiser=False, optimize=False, device="cuda")
    
    kwargs = {
        "text": text,
        "cfg_value": cfg,
        "inference_timesteps": steps,
        "normalize": False,
        "denoise": False,
    }
    if ref_audio:
        kwargs["reference_wav_path"] = ref_audio

    wav = model.generate(**kwargs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), wav, model.tts_model.sample_rate, subtype="PCM_16")
    return out_path


def generate_edge(text: str, voice: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    edge_exe = shutil_which("edge-tts") or "edge-tts"
    cmd = [edge_exe, "--text", text, "--write-media", str(out_path)]
    if voice:
        cmd.extend(["--voice", voice])
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"edge-tts failed: {res.stderr}")
    return out_path


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


def main():
    parser = argparse.ArgumentParser(description="Generate speech locally or via Edge-TTS.")
    parser.add_argument("--text", type=str, help="Text to speak")
    parser.add_argument("--text-file", type=str, help="File containing text to speak")
    parser.add_argument("--engine", choices=["voxcpm2", "edge"], default="voxcpm2", help="TTS Engine")
    parser.add_argument("--ref", type=str, help="Reference audio path for voice cloning (VoxCPM2)")
    parser.add_argument("--voice", type=str, default="zh-TW-HsiaoChenNeural", help="Voice name for Edge-TTS")
    parser.add_argument("--cfg", type=float, default=2.0, help="Guidance scale (VoxCPM2)")
    parser.add_argument("--steps", type=int, default=10, help="Inference timesteps (VoxCPM2)")
    parser.add_argument("--seed", type=int, default=20260918, help="Random seed")
    parser.add_argument("--out", type=str, help="Output audio file path (.wav or .mp3)")
    parser.add_argument("--control", type=str, default=None, help="VoxCPM2 voice description, e.g. 'a bright 11-year-old Taiwanese girl' (voice design)")
    parser.add_argument("--design", action="store_true", help="VoxCPM2: do not fall back to the default reference voice (pure voice design with --control)")
    args = parser.parse_args()

    text = args.text
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()

    if not text:
        sys.exit("Error: Either --text or --text-file must be provided.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".mp3" if args.engine == "edge" and (not args.out or args.out.endswith(".mp3")) else ".wav"
    if args.out:
        out_path = Path(args.out).resolve()
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUT_DIR / f"voice_{args.engine}_{timestamp}{ext}"

    t0 = time.time()
    if args.engine == "voxcpm2":
        dest = generate_voxcpm2(text, args.ref, out_path, args.cfg, args.steps, args.seed, args.control, args.design)
    else:
        dest = generate_edge(text, args.voice, out_path)

    elapsed = round(time.time() - t0, 2)
    print(f"[OK] Generated in {elapsed}s: {dest}")


if __name__ == "__main__":
    main()
