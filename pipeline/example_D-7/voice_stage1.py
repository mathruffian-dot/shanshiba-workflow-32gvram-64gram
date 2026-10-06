"""配音第一階段（Voice venv）：①阿禾參考音逐字稿 ②Breeze 任務 breeze_jobs.json ③edge-tts 台灣國語參考音 voice_ref_tw/ ④VoxCPM2 候選（繁轉簡）voice_cand/<id>_vx<k>.wav
  C:/AI/Voice/venv/Scripts/python.exe voice_stage1.py [--n 6]"""
import asyncio, json, subprocess, sys
from pathlib import Path
import voice_plan as P
HERE = P.HERE; C = HERE / "voice_cand"; C.mkdir(exist_ok=True); TW = HERE / "voice_ref_tw"; TW.mkdir(exist_ok=True)
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 6
src = open("C:/AI/tools/stt.py", encoding="utf-8").read(); a = src.index("def _add_cuda_dll_dirs"); b = src.index("def ", a + 10); exec(src[a:b]); _add_cuda_dll_dirs()
from faster_whisper import WhisperModel
asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root="C:/AI/Voice/models/whisper", local_files_only=True)
refs = {}
for sp, (p, t) in P.REFS.items():
    if t is None:
        segs, _ = asr.transcribe(str(p), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。"); t = "".join(s.text for s in segs).strip()
    refs[sp] = dict(ref_audio=str(p), ref_text=t); print(sp, t, flush=True)
(HERE / "voice_refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), encoding="utf-8")
del asr
jobs = [dict(name=f"{lid}_bz{k}", text=P.TTS[lid], seed=37 + 23 * k, **refs[sp]) for lid, sp, _ in P.LINES for k in range(N + (4 if sp == "xw" else 0))]
(HERE / "breeze_jobs.json").write_text(json.dumps(dict(out_dir="voice_cand", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
print("breeze jobs", len(jobs), flush=True)
import edge_tts
async def edge():
    for lid, sp, _ in P.LINES:
        w = TW / f"{lid}.wav"
        if w.exists(): continue
        mp3 = TW / f"{lid}.mp3"; await edge_tts.Communicate(P.TTS[lid], P.EDGE[sp]).save(str(mp3))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(w)])
asyncio.run(edge()); print("edge refs done", flush=True)
import soundfile as sf, torch
from voxcpm import VoxCPM
from opencc import OpenCC
t2s = OpenCC("t2s")
tts = VoxCPM.from_pretrained(r"C:\AI\Voice\models\VoxCPM2", load_denoiser=False, optimize=False, device="cuda")
for lid, sp, _ in P.LINES:
    if sp == "xw": continue
    for k in range(N):
        p = C / f"{lid}_vx{k}.wav"
        if p.exists(): continue
        torch.manual_seed(20261004 + 53 * k + sum(map(ord, lid)))
        w = tts.generate(text=t2s.convert(P.TTS[lid]), cfg_value=2.0, inference_timesteps=10, normalize=False, denoise=False, reference_wav_path=str(P.REFS[sp][0]))
        sf.write(str(p), w, tts.tts_model.sample_rate, subtype="PCM_16")
    print(lid, "vox done", flush=True)
print("STAGE1_DONE", flush=True)
