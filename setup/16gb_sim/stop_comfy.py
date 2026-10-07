"""關掉本機 8188 的 ComfyUI（排除自己與父程序，避免誤殺）。"""
import os
import psutil
me = {os.getpid()} | {p.pid for p in psutil.Process().parents()}
for p in psutil.process_iter(["pid", "cmdline"]):
    c = " ".join(p.info["cmdline"] or [])
    if p.info["pid"] not in me and "ComfyUI" not in __file__ and "main.py" in c and "--port" in c and "8188" in c and "stop_comfy" not in c:
        for q in p.children(recursive=True) + [p]:
            try:
                q.kill()
            except Exception:
                pass
        print("killed", p.info["pid"])
