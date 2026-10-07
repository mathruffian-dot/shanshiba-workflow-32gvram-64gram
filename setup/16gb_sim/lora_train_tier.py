"""在模擬的硬體配置下訓練角色 LoRA（AI Toolkit）。H3 venv：python lora_train_tier.py t3 lora_yun/train.yaml [--bg 12]
不啟動 ComfyUI（訓練時要整張顯卡）。記錄總時間、每步秒數、顯存峰值（扣掉佔位）、記憶體最低值。"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import run_32g as Q
import run_test as R
from run_tier import TIERS

HERE = R.HERE
AIT = HERE.parents[1] / "訓練" / "角色LoRA_20260926" / "tools" / "ai-toolkit"
HF = HERE.parents[1] / "訓練" / "角色LoRA_20260926" / "hf_cache"


def main(tier, cfg, bg):
    C = TIERS[tier]; cfg = Path(cfg).resolve(); outd = cfg.parent
    _, total = R.smi_used()
    if C["vram_hog"]:
        vh = subprocess.Popen([R.PY, str(HERE / "hog.py"), str(total - R.CARD_MIB)], stdout=subprocess.PIPE, text=True); print(vh.stdout.readline().strip(), flush=True)
    base_vram, _ = R.smi_used()
    if C["ramcap"]:
        hog = max(0, int(Q.memstat()["avail_phys"] - (C["ramcap"] - bg)))
        rh = subprocess.Popen([R.PY, str(HERE / "ram_hog.py"), str(hog)], stdout=subprocess.PIPE, text=True); print(rh.stdout.readline().strip(), flush=True)
    time.sleep(5); print("mem", Q.memstat(), flush=True)
    peak = dict(vram=0, avail=1e9); stop = threading.Event()

    def mon():
        while not stop.is_set():
            try:
                peak["vram"] = max(peak["vram"], R.smi_used()[0]); peak["avail"] = min(peak["avail"], Q.memstat()["avail_phys"])
            except Exception:
                pass
            time.sleep(1)
    th = threading.Thread(target=mon, daemon=True); th.start(); t0 = time.time()
    log = open(outd / f"train_{tier}.log", "w", encoding="utf-8")
    p = subprocess.Popen([str(AIT / ".venv" / "Scripts" / "python.exe"), "run.py", str(cfg)], cwd=str(AIT), stdout=log, stderr=subprocess.STDOUT,
                         env={**os.environ, "HF_HOME": str(HF), "PYTHONIOENCODING": "utf-8"})
    rc = p.wait(); stop.set(); th.join(); log.close()
    txt = (outd / f"train_{tier}.log").read_text(encoding="utf-8", errors="replace")
    its = re.findall(r"(\d+)/(\d+) \[([0-9:]+)<", txt)
    res = dict(tier=tier, bg=bg, rc=rc, total_s=round(time.time() - t0), vram_peak_mib=max(0, peak["vram"] - base_vram),
               sys_avail_min_gib=round(peak["avail"], 2), last_progress=its[-1] if its else None)
    (outd / f"train_{tier}_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    started = []
    _P = subprocess.Popen

    def track(*x, **k):
        p = _P(*x, **k); started.append(p.pid); return p
    subprocess.Popen = track
    try:
        main(a[0], a[1], int(a[a.index("--bg") + 1]) if "--bg" in a else 12)
    finally:
        for pid in started:
            Q.kill_tree(pid)
