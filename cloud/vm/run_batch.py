"""Runs ON the Colab VM (started by cloud/colab_h3.py batch): renders every job in /content/jobs/<batch>/jobs.json with h3_shot.py,
spread over the ComfyUI instances that setup_h3.py started. Instance k starts its first job 30 s after instance k-1, so the
text encoders do not load at the same moment (simultaneous loading filled the 96 GB of a G4 and failed one job in the test).
Progress: /content/jobs/<batch>/progress.jsonl ; when finished: /content/jobs/<batch>_out.zip and a DONE line.
Usage: python run_batch.py <batch_name>"""
import json, os, queue, subprocess, sys, threading, time, zipfile
from pathlib import Path

B = Path("/content/jobs") / sys.argv[1]
REPO = Path(os.environ.get("REPO", "/content/repo"))
state = json.loads(Path("/content/h3_state.json").read_text())
jobs = json.loads((B / "jobs.json").read_text(encoding="utf-8"))
prog = open(B / "progress.jsonl", "a", encoding="utf-8")
lock = threading.Lock()


def log(**k):
    k["t"] = round(time.time(), 1)
    with lock:
        prog.write(json.dumps(k, ensure_ascii=False) + "\n"); prog.flush()


q = queue.Queue()
for j in jobs:
    if not (B / j["id"] / "out" / "clip.mp4").exists():       # a re-run of the same batch skips finished shots
        q.put(j)
env_base = {**os.environ}
if state.get("encoder") == "nvfp4":
    env_base["H3_CLIP"] = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
log(event="start", jobs=len(jobs), todo=q.qsize(), instances=len(state["instances"]))


def worker(k, inst):
    time.sleep(30 * k)
    env = {**env_base, "COMFY_DIR": inst["dir"], "COMFY_HOST": f"http://127.0.0.1:{inst['port']}"}
    while True:
        try:
            j = q.get_nowait()
        except queue.Empty:
            return
        d = B / j["id"]; t = time.time()
        r = subprocess.run(["python", str(REPO / "tools" / "h3_shot.py"), str(d / "spec.json"), "--out", str(d / "out")],
                           capture_output=True, text=True, cwd=d, env=env)
        ok = r.returncode == 0 and (d / "out" / "clip.mp4").exists()
        log(event="job", id=j["id"], ok=ok, sec=round(time.time() - t, 1), inst=k,
            err="" if ok else (r.stdout + r.stderr)[-600:])


ts = [threading.Thread(target=worker, args=(k, x)) for k, x in enumerate(state["instances"])]
t0 = time.time()
[x.start() for x in ts]; [x.join() for x in ts]
zp = B.parent / f"{B.name}_out.zip"
with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:          # mp4 is already compressed
    for j in jobs:
        out = B / j["id"] / "out"
        if out.exists():
            for f in out.rglob("*"):
                if f.is_file():
                    z.write(f, f"{j['id']}/{f.relative_to(out).as_posix()}")
log(event="DONE", sec=round(time.time() - t0, 1), zip=str(zp), zip_mb=round(zp.stat().st_size / 1e6, 1))
