"""在候選上疊 S04 下課環境音（SNR 8/4 dB）跑 ASR，看「考」是否仍聽得出來。python voice_robust.py L01 L05"""
import sys, json, re, subprocess
from pathlib import Path
import numpy as np, soundfile as sf
src = open("C:/AI/tools/stt.py", encoding="utf-8").read(); a = src.index("def _add_cuda_dll_dirs"); b = src.index("def ", a + 10); exec(src[a:b]); _add_cuda_dll_dirs()
from faster_whisper import WhisperModel
from opencc import OpenCC
t2s = OpenCC("t2s"); asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root="C:/AI/Voice/models/whisper", local_files_only=True)
r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "h3/S04/clip.mp4", "-ar", "16000", "-ac", "1", "-f", "f32le", "-"], capture_output=True)
amb = np.frombuffer(r.stdout, np.float32).copy()
rep = json.load(open("voice_pick.json", encoding="utf-8"))
for lid in sys.argv[1:]:
    print(lid)
    for row in rep[lid][:16]:
        x, sr = sf.read(row["file"], dtype="float32"); x = x.mean(1) if x.ndim > 1 else x
        if sr != 16000:
            x = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
        hs = []
        for snr in (8, 4):
            n = amb[:len(x)] if len(amb) >= len(x) else np.resize(amb, len(x))
            y = x + n * np.sqrt((x ** 2).mean() / ((n ** 2).mean() + 1e-9)) / (10 ** (snr / 20))
            segs, _ = asr.transcribe(y, language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False)
            hs.append("".join(s.text for s in segs))
        ok = all(("考" in h or "烤" in h) for h in hs)
        print(f"  {row['cand']:12s} total {row['total']:.2f} asr {row['asr']} {'OK ' if ok else 'BAD'} {hs}", flush=True)
