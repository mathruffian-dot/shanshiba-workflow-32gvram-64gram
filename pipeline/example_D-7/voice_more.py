"""單句補候選（Voice venv）：python voice_more.py L01 6 14  → voice_cand/L01_vx6..13"""
import sys
from pathlib import Path
import soundfile as sf, torch
from voxcpm import VoxCPM
from opencc import OpenCC
import voice_plan as P
lid, k0, k1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); sp = {l: s for l, s, _ in P.LINES}[lid]
tts = VoxCPM.from_pretrained(r"C:\AI\Voice\models\VoxCPM2", load_denoiser=False, optimize=False, device="cuda")
for k in range(k0, k1):
    p = P.HERE / "voice_cand" / f"{lid}_vx{k}.wav"
    if p.exists(): continue
    torch.manual_seed(20261004 + 53 * k + sum(map(ord, lid)))
    w = tts.generate(text=OpenCC("t2s").convert(P.TTS[lid]), cfg_value=2.0, inference_timesteps=10, normalize=False, denoise=False, reference_wav_path=str(P.REFS[sp][0]))
    sf.write(str(p), w, tts.tts_model.sample_rate, subtype="PCM_16")
print("done")
