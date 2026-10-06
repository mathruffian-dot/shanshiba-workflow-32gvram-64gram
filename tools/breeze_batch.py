"""Batch Breeze TTS 2 generation (loads the model once). Mirrors the official infer.py eager path.
Run with C:\\AI\\BreezeTTS\\venv\\Scripts\\python.exe breeze_batch.py jobs.json
jobs.json: {"out_dir": "...", "jobs": [{"name", "text", "instruction"?, "ref_audio"?, "ref_text"?, "seed"?, "cfg"?}]}
Existing outputs are skipped. Log -> <out_dir>/breeze_log.jsonl."""
import json
import sys
import time
from pathlib import Path

REPO = Path(r"C:\AI\BreezeTTS\breeze-tts")
MODEL = Path(r"C:\AI\BreezeTTS\breeze-tts-2")
sys.path.insert(0, str(REPO))

import soundfile as sf  # noqa: E402
import torch  # noqa: E402

from breeze_infer.runtime import load_runtime, resolve_device, set_all_seeds, update_generation_config_for_breeze  # noqa: E402
from breeze_infer.templates import get_template, prepare_inputs, select_template_name  # noqa: E402
from models.fast_streaming import FastBreezeStreamingRuntime, FastStreamingConfig  # noqa: E402


def main():
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    out = (spec_path.parent / spec["out_dir"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    tok, model, atok = load_runtime(MODEL, device=resolve_device(), attn_implementation="eager")
    update_generation_config_for_breeze(model)
    rt = FastBreezeStreamingRuntime(model, atok, FastStreamingConfig(max_new_tokens=1500, max_seq_len=2048,
                                                                       repetition_penalty=1.1), tokenizer=tok)
    for j in spec["jobs"]:
        dest = out / f"{j['name']}.wav"
        if dest.exists():
            print("[skip]", dest.name)
            continue
        req = {"id": j["name"], "text": j["text"], "speaker": "S0"}
        if j.get("instruction"):
            req["instruction"] = j["instruction"]
        if j.get("ref_audio"):
            req["ref_audio_path"] = str((spec_path.parent / j["ref_audio"]).resolve()) if not Path(j["ref_audio"]).is_absolute() else j["ref_audio"]
            req["ref_text"] = j["ref_text"]
        seed = j.get("seed", 42)
        cfg = j.get("cfg", 4.0 if j.get("instruction") else 1.0)
        t0 = time.time()
        set_all_seeds(seed)
        inputs = prepare_inputs(tok, atok, model, [req], get_template(select_template_name(req)),
                                guidance_scale=cfg, guidance_scale_ref=None, guidance_scale_ins=None)
        with sf.SoundFile(dest, mode="w", samplerate=rt.sample_rate, channels=1, subtype="PCM_16") as f:
            for chunk in rt.iter_audio_chunks(inputs, request_id=j["name"], seed=seed):
                f.write(chunk.audio)
        rec = {**j, "seed": seed, "cfg": cfg, "sec": round(time.time() - t0, 2),
               "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)}
        with open(out / "breeze_log.jsonl", "a", encoding="utf-8") as lf:
            lf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[ok] {dest.name} {rec['sec']}s", flush=True)


if __name__ == "__main__":
    main()
