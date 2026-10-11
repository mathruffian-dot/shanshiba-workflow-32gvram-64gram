"""Runs ON the Colab VM in full-cloud mode: render H3 shots on 2 ComfyUI instances, then go back to the normal single instance.
make_film.py calls it when H3_PARALLEL=2 (cloud/colab_h3.py film sets this). Same recipe that measured best on a G4 (2026-10-10):
2 instances, --reserve-vram 46 each, models kept loaded, instance 2 starts its first shot 30 s later (loading both text encoders at
the same moment filled the 96 GB and failed a shot). In full-cloud mode one ComfyUI also serves Qwen / Music 3, so this script
restarts ComfyUI as 2 instances for the H3 stage and restores the single instance (no --reserve-vram) afterwards.
Usage: python parallel_h3.py <shot dir> ...      (each dir has spec.json; outputs are written into the same dir)"""
import json, os, queue, shutil, subprocess, sys, threading, time, urllib.request
from pathlib import Path

C = Path(os.environ.get("COMFY_DIR", "/content/AI/H3/ComfyUI-0.36.0"))
REPO = Path(__file__).resolve().parents[2]
FLAGS = "--disable-auto-launch --preview-method none --fast fp16_accumulation"


def instance_dir(i):
    if i == 0:
        return C
    d = Path(f"/content/ComfyUI_{i}")
    if not d.exists():
        top = {"models", "input", "output", "user", "temp"}          # top level only - comfy/ldm/models is code
        shutil.copytree(C, d, ignore=lambda p, names: [n for n in names if Path(p) == C and n in top], symlinks=True)
        (d / "models").symlink_to(C / "models")
        if (C / "extra_model_paths.yaml").exists():
            shutil.copy(C / "extra_model_paths.yaml", d / "extra_model_paths.yaml")
    return d


def start(n, reserve):
    subprocess.run("pkill -f 'main.py --listen'", shell=True); time.sleep(3)
    for i in range(n):
        extra = f"--reserve-vram {reserve}" if reserve else ""
        subprocess.Popen(f"nohup python main.py --listen 127.0.0.1 --port {8188 + i} {FLAGS} {extra} > /content/comfy_{i}.log 2>&1 &",
                         shell=True, cwd=instance_dir(i))
    for i in range(n):
        for _ in range(300):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{8188 + i}/system_stats", timeout=2); break
            except Exception:
                time.sleep(1)
        else:
            raise SystemExit(f"ComfyUI on port {8188 + i} did not start")


def main():
    dirs = [Path(d) for d in sys.argv[1:]]
    if not dirs:
        return
    if len(dirs) == 1:                       # one shot: not worth restarting ComfyUI
        r = subprocess.run(["python", str(REPO / "tools" / "h3_shot.py"), str(dirs[0] / "spec.json"), "--out", str(dirs[0])])
        sys.exit(r.returncode)
    t0 = time.time()
    start(2, 46)
    q = queue.Queue(); [q.put(d) for d in dirs]; fails = []; lock = threading.Lock()

    def worker(k):
        time.sleep(30 * k)
        env = {**os.environ, "COMFY_DIR": str(instance_dir(k)), "COMFY_HOST": f"http://127.0.0.1:{8188 + k}"}
        while True:
            try:
                d = q.get_nowait()
            except queue.Empty:
                return
            t = time.time()
            r = subprocess.run(["python", str(REPO / "tools" / "h3_shot.py"), str(d / "spec.json"), "--out", str(d)],
                               capture_output=True, text=True, env=env)
            ok = r.returncode == 0 and (d / "clip.mp4").exists()
            with lock:
                print(f"[parallel_h3] {d.name}: {'OK' if ok else 'FAIL'} {time.time() - t:.0f}s (ComfyUI {k + 1})", flush=True)
                if not ok:
                    fails.append(d.name); print((r.stdout + r.stderr)[-800:], flush=True)

    ts = [threading.Thread(target=worker, args=(k,)) for k in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    start(1, None)                           # back to the normal single ComfyUI for the other stages
    print(f"[parallel_h3] {len(dirs) - len(fails)}/{len(dirs)} shots in {time.time() - t0:.0f}s", flush=True)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
