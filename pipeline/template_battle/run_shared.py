"""共用本機 GPU 時跑 make_battle 的 stage：不呼叫 ComfyUI /free（別的 session 的模型不卸載）。
用法：python run_shared.py songs dj audio    （SHARED_CPU=1＝聽寫、分人聲改用 CPU）"""
import os
import sys
if os.environ.get("SHARED_CPU"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
import make_battle as mb
mb.free_comfy = lambda: None
if os.environ.get("SHARED_CPU"):
    import stable_whisper
    _load = stable_whisper.load_faster_whisper
    stable_whisper.load_faster_whisper = lambda name, **kw: _load(name, **{**kw, "device": "cpu", "compute_type": "int8"})
for st in [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--ver", "--battle")]:
    mb.ALL[st]()
