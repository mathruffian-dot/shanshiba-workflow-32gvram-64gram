"""在模擬的硬體配置下，從零跑完整支全本地示範片（repo 的 pipeline/demo_local/run_demo.py）。H3 venv：python demo_tier.py t3 [--bg 12]
記錄每個階段的時間、顯存峰值、記憶體最低值，結果寫 demo_<tier>/demo_tier_result.json。"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

import run_32g as Q
import run_test as R
from run_tier import TIERS

HERE = R.HERE
SRC = HERE.parents[1] / "分享repo準備" / "src" / "common" / "pipeline" / "demo_local" / "run_demo.py"


def main(tier, bg):
    C = TIERS[tier]; d = HERE / f"demo_{tier}"; d.mkdir(exist_ok=True)
    shutil.copy2(SRC, d / "run_demo.py")
    _, total = R.smi_used()
    if C["vram_hog"]:
        vh = subprocess.Popen([R.PY, str(HERE / "hog.py"), str(total - R.CARD_MIB)], stdout=subprocess.PIPE, text=True); print(vh.stdout.readline().strip(), flush=True)
    base_vram, _ = R.smi_used()
    if C["ramcap"]:
        hog = max(0, int(Q.memstat()["avail_phys"] - (C["ramcap"] - bg)))
        rh = subprocess.Popen([R.PY, str(HERE / "ram_hog.py"), str(hog)], stdout=subprocess.PIPE, text=True); print(rh.stdout.readline().strip(), flush=True)
    time.sleep(5); print("mem", Q.memstat(), flush=True)
    log = open(d / "comfy.log", "w", encoding="utf-8")
    comfy = subprocess.Popen([R.PY, "-X", "utf8", str(HERE / "comfy_ramcap.py"), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch",
                              "--preview-method", "none", "--cache-none", "--fast", "fp16_accumulation"] + C["flags"],
                             cwd=str(R.COMFY), stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "RAMCAP_GB": str(C["ramcap"] or 1024)})
    for _ in range(180):
        time.sleep(2)
        try:
            R.req("/system_stats"); break
        except Exception:
            pass
    peak = dict(vram=0, avail=1e9)
    stop = threading.Event()

    def mon():
        while not stop.is_set():
            try:
                peak["vram"] = max(peak["vram"], R.smi_used()[0]); peak["avail"] = min(peak["avail"], Q.memstat()["avail_phys"])
            except Exception:
                pass
            time.sleep(0.5)
    rows = []
    for st in ["chars", "frames", "voices", "h3", "music", "cut"]:
        peak.update(vram=0, avail=1e9); th = threading.Thread(target=mon, daemon=True); stop.clear(); th.start(); t0 = time.time()
        r = subprocess.run([R.PY, "run_demo.py", st], cwd=str(d), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        stop.set(); th.join()
        row = dict(stage=st, ok=r.returncode == 0, seconds=round(time.time() - t0, 1), vram_peak_mib=max(0, peak["vram"] - base_vram),
                   sys_avail_min_gib=round(peak["avail"], 2), tail=(r.stdout + r.stderr)[-800:])
        rows.append(row); print(json.dumps({k: v for k, v in row.items() if k != "tail"}, ensure_ascii=False), flush=True)
        (d / "demo_tier_result.json").write_text(json.dumps(dict(tier=tier, bg=bg, stages=rows), ensure_ascii=False, indent=1), encoding="utf-8")
        if not row["ok"]:
            print(row["tail"], flush=True); break
    print("DONE", tier, flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    started = []
    _P = subprocess.Popen

    def track(*x, **k):
        p = _P(*x, **k); started.append(p.pid); return p
    subprocess.Popen = track
    try:
        main(a[0], int(a[a.index("--bg") + 1]) if "--bg" in a else 12)
    finally:
        for pid in started:
            Q.kill_tree(pid)
