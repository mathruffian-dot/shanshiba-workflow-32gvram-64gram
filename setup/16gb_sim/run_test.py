"""版本 B（16GB VRAM）模擬驗證。H3 venv 執行：python run_test.py A|B
A＝原設定（Heretic int8 文字編碼器、fp16 影片 VAE，不限顯存）
B＝16GB 設定（官方 NVFP4 文字編碼器、int8 影片 VAE、--reserve-vram 1.5），另開一支程式佔住顯存，讓 ComfyUI 只剩約 16GB 卡的可用量
每個 profile：啟動 ComfyUI → 依序跑 SHOTS（同 seed、DMAD 4 步）→ 第一鏡再跑一次量暖機速度 → 關閉。
紀錄：ComfyUI /history 執行時間、顯存峰值（扣掉佔位程式）、ComfyUI 程序記憶體峰值、系統可用記憶體最低值。"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILM = ROOT / "短片" / "阿禾出場介紹_20261006" / "h3"
SHOTS = [("B06", "B06_a0", "對白近景 158 格（老師兩句）"), ("B08", "B08_a1", "手部動作 158 格（摺紙）"), ("C04", "C04_a0", "雙人耳語 107 格")]
PY = r"C:\AI\H3\venv\Scripts\python.exe"
COMFY = Path(r"C:\AI\H3\ComfyUI-0.36.0")
HOST = "http://127.0.0.1:8188"
CARD_MIB = 16303          # RTX 4080／5070 Ti／5080 的 16GB 卡實際總量約 16303 MiB
PROFILES = {
    "A": dict(env={}, flags=[], hog=0),
    "B": dict(env={"H3_CLIP": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                   "H3_VIDEO_VAE": "minimax_h3_video_vae_int8_convrot.safetensors"},
              flags=["--reserve-vram", "1.5"], hog=None),
    "C": dict(env={}, flags=["--reserve-vram", "1.5"], hog=None),   # 原模型組合＋16GB 限制：分辨差異來自換模型還是來自卸載
}


def req(path, data=None, timeout=10):
    r = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read().decode())


def smi_used():
    o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True).stdout.split(",")
    return int(o[0]), int(o[1])


class Monitor(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True)
        self.p = psutil.Process(pid); self.stop = False
        self.vram_peak = 0; self.rss_peak = 0; self.private_peak = 0; self.sys_avail_min = 1 << 60

    def run(self):
        while not self.stop:
            try:
                u, _ = smi_used(); self.vram_peak = max(self.vram_peak, u)
                ps = [self.p] + self.p.children(recursive=True)   # venv python.exe 是啟動器，真正的 ComfyUI 是子程序
                ms = [q.memory_info() for q in ps]
                self.rss_peak = max(self.rss_peak, sum(m.rss for m in ms))
                self.private_peak = max(self.private_peak, sum(getattr(m, "private", 0) for m in ms))
                self.sys_avail_min = min(self.sys_avail_min, psutil.virtual_memory().available)
            except Exception:
                pass
            time.sleep(0.5)

    def reset(self):
        self.vram_peak = 0; self.rss_peak = 0; self.private_peak = 0; self.sys_avail_min = 1 << 60


def history_time(tag):
    h = req("/history", timeout=30)
    for pid, e in h.items():
        g = e.get("prompt", [None, None, {}])[2]
        if any(n.get("inputs", {}).get("filename_prefix", "") == f"h3_shot/{tag}" for n in g.values()):
            msgs = {m[0]: m[1] for m in e.get("status", {}).get("messages", [])}
            a = msgs.get("execution_start", {}).get("timestamp"); b = (msgs.get("execution_success") or msgs.get("execution_error") or {}).get("timestamp")
            return round((b - a) / 1000, 1) if a and b else None, e.get("status", {}).get("status_str")
    return None, None


def main(prof, tag=""):
    P = PROFILES[prof]; out_root = HERE / "out" / (prof + tag); out_root.mkdir(parents=True, exist_ok=True)
    log = open(HERE / f"comfy_{prof}{tag}.log", "w", encoding="utf-8")
    hog = None
    base_used, total = smi_used()
    if prof in ("B", "C"):
        hog_mib = total - CARD_MIB
        hog = subprocess.Popen([PY, str(HERE / "hog.py"), str(hog_mib)], stdout=subprocess.PIPE, text=True)
        print(hog.stdout.readline().strip(), flush=True)
    else:
        hog_mib = 0
    used_after_hog, _ = smi_used()
    cmd = [PY, "-X", "utf8", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch", "--preview-method", "none",
           "--cache-none", "--fast", "fp16_accumulation"] + P["flags"]
    comfy = subprocess.Popen(cmd, cwd=str(COMFY), stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(2)
        try:
            req("/system_stats"); break
        except Exception:
            pass
    else:
        sys.exit("ComfyUI did not start")
    mon = Monitor(comfy.pid); mon.start()
    results = []
    env = {**os.environ, **P["env"], "PYTHONIOENCODING": "utf-8"}
    runs = [(s, a, d, "cold" if i == 0 else "warm") for i, (s, a, d) in enumerate(SHOTS)]
    if not os.environ.get("NO_REPEAT"):
        runs.append((SHOTS[0][0], SHOTS[0][1], SHOTS[0][2], "warm-repeat"))
    for shot, att, desc, kind in runs:
        spec = json.loads((FILM / att / "shot.json").read_text(encoding="utf-8"))
        spec["draft"] = True
        od = out_root / (shot + ("_r2" if kind == "warm-repeat" else "")); od.mkdir(parents=True, exist_ok=True)
        sp = od / "spec.json"; sp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        mon.reset(); t0 = time.time()
        r = subprocess.run([PY, r"C:\AI\tools\h3_shot.py", str(sp), "--out", str(od)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        wall = round(time.time() - t0, 1)
        meta = json.loads((od / "meta.json").read_text(encoding="utf-8")) if (od / "meta.json").exists() else {}
        exec_s, status = history_time(meta.get("tag", "")) if meta else (None, "no-meta")
        row = dict(profile=prof, shot=shot, desc=desc, kind=kind, frames=meta.get("length"), seed=spec["seed"], ok=meta.get("ok"), status=status,
                   exec_s=exec_s, wall_s=wall, vram_peak_comfy_mib=max(0, mon.vram_peak - used_after_hog),
                   vram_total_used_mib=mon.vram_peak, comfy_rss_peak_gib=round(mon.rss_peak / 2**30, 2),
                   comfy_private_peak_gib=round(mon.private_peak / 2**30, 2), sys_avail_min_gib=round(mon.sys_avail_min / 2**30, 2),
                   tail=(r.stdout + r.stderr)[-400:] if not meta.get("ok") else "")
        results.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
        (HERE / f"results_{prof}{tag}.json").write_text(json.dumps(dict(hog_mib=hog_mib, base_used_mib=base_used, used_after_hog_mib=used_after_hog,
                                                                    flags=P["flags"], env=P["env"], runs=results), ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        pr = psutil.Process(comfy.pid); ms = [q.memory_info() for q in [pr] + pr.children(recursive=True)]
        peak = dict(peak_wset_gib=round(sum(getattr(m, "peak_wset", 0) for m in ms) / 2**30, 2), peak_pagefile_gib=round(sum(getattr(m, "peak_pagefile", 0) for m in ms) / 2**30, 2))
    except Exception:
        peak = {}
    mon.stop = True
    comfy.terminate(); comfy.wait(30)
    if hog: hog.terminate(); hog.wait(30)
    d = json.loads((HERE / f"results_{prof}{tag}.json").read_text(encoding="utf-8")); d["process_peak"] = peak
    (HERE / f"results_{prof}{tag}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("DONE", prof, peak, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
