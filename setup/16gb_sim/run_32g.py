"""16GB VRAM＋32GB RAM 模擬。H3 venv：python run_32g.py D|E|F [--target 24]
顯存：hog.py 佔住，ComfyUI 只剩約 14.6GB（同 16GB 測試）。
記憶體：ram_hog.py 佔住實體記憶體，讓系統可用量剩 --target GB（32GB 電腦扣掉 Windows 與常駐約 8GB ≈ 24GB）；
        並用 comfy_ramcap.py 讓 ComfyUI 以為總記憶體只有 32GB（它的釘選量、卸載判斷會照 32GB 算）。
D＝原模型（int8 文字編碼器）、E＝原模型＋--fast-disk、F＝NVFP4 文字編碼器＋int8 影片 VAE（低記憶體備案）、G＝F＋--fast-disk
每鏡最多等 TIMEOUT 秒，超過就中斷並記為失敗。"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

import run_test as R

HERE = R.HERE
SHOTS = [("B06", "B06_a0", "對白中景 158 格"), ("C04", "C04_a0", "雙人近景 107 格")]
TIMEOUT = 900
NVFP4 = {"H3_CLIP": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "H3_VIDEO_VAE": "minimax_h3_video_vae_int8_convrot.safetensors"}
PROFILES = {
    "D": dict(env={}, flags=[]),
    "E": dict(env={}, flags=["--fast-disk"]),
    "F": dict(env=NVFP4, flags=[]),
    "G": dict(env=NVFP4, flags=["--fast-disk"]),
    "A64": dict(env={}, flags=[], ramcap=64, vram_hog=False),   # 32GB VRAM＋64GB RAM（完整版）
}


class MEMSTAT(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memstat():
    m = MEMSTAT(); m.dwLength = ctypes.sizeof(MEMSTAT); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return dict(avail_phys=m.ullAvailPhys / 2**30, commit_limit=m.ullTotalPageFile / 2**30, commit_used=(m.ullTotalPageFile - m.ullAvailPageFile) / 2**30)


class Mon(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True); self.p = psutil.Process(pid); self.stop = False; self.tripped = False; self.reset()

    def reset(self):
        self.vram = 0; self.private = 0; self.avail_min = 1e9; self.commit_max = 0; self.swap_max = 0; self.read0 = self.reads()

    def reads(self):
        try:
            return sum(q.io_counters().read_bytes for q in [self.p] + self.p.children(recursive=True))
        except Exception:
            return 0

    def run(self):
        while not self.stop:
            try:
                u, _ = R.smi_used(); self.vram = max(self.vram, u)
                self.private = max(self.private, sum(getattr(q.memory_info(), "private", 0) for q in [self.p] + self.p.children(recursive=True)))
                ms = memstat(); self.avail_min = min(self.avail_min, ms["avail_phys"]); self.commit_max = max(self.commit_max, ms["commit_used"])
                self.swap_max = max(self.swap_max, psutil.swap_memory().used)
                if ms["commit_limit"] > 250 and ms["commit_limit"] - ms["commit_used"] < 3.0:   # 保護：分頁檔已長到上限、虛擬記憶體快用完才停
                    self.tripped = True
                    for q in [self.p] + self.p.children(recursive=True):
                        try: q.kill()
                        except Exception: pass
            except Exception:
                pass
            time.sleep(0.5)


def main(prof, target):
    P = PROFILES[prof]; tag = os.environ.get("RUN_TAG", ""); out_root = HERE / "out" / f"32g_{prof}{tag}"; out_root.mkdir(parents=True, exist_ok=True)
    resf = HERE / f"results_32g_{prof}{tag}.json"
    _, total = R.smi_used()
    if P.get("vram_hog", True):
        vhog = subprocess.Popen([R.PY, str(HERE / "hog.py"), str(total - R.CARD_MIB)], stdout=subprocess.PIPE, text=True)
        print(vhog.stdout.readline().strip(), flush=True)
    else:
        vhog = subprocess.Popen([R.PY, "-c", "import time; time.sleep(86400)"])
    used_after_hog, _ = R.smi_used()
    ms0 = memstat()
    hog_gb = max(0, int(ms0["avail_phys"] - target))
    if False:   # 分頁檔是系統管理、會自動長大（2026-10-07 實測可從 101 長到 155GB 再縮回），不在起跑前擋
        vhog.terminate(); sys.exit(f"commit headroom too small: {ms0}")
    rhog = subprocess.Popen([R.PY, str(HERE / "ram_hog.py"), str(hog_gb)], stdout=subprocess.PIPE, text=True)
    print(rhog.stdout.readline().strip(), flush=True)
    time.sleep(5); ms1 = memstat(); print(f"after ram hog: {ms1}", flush=True)
    log = open(HERE / f"comfy_32g_{prof}{os.environ.get('RUN_TAG', '')}.log", "w", encoding="utf-8")
    cmd = [R.PY, "-X", "utf8", str(HERE / "comfy_ramcap.py"), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch",
           "--preview-method", "none", "--cache-none", "--fast", "fp16_accumulation", "--reserve-vram", "1.5"] + P["flags"]
    comfy = subprocess.Popen(cmd, cwd=str(R.COMFY), stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "RAMCAP_GB": str(P.get("ramcap", 32))})
    for _ in range(180):
        time.sleep(2)
        try:
            R.req("/system_stats"); break
        except Exception:
            if comfy.poll() is not None:
                break
    else:
        pass
    mon = Mon(comfy.pid); mon.start()
    env = {**os.environ, **P["env"], "PYTHONIOENCODING": "utf-8"}
    rows = []
    for i, (shot, att, desc) in enumerate(SHOTS):
        if comfy.poll() is not None:
            rows.append(dict(shot=shot, ok=False, status="comfy-exited")); break
        spec = json.loads((R.FILM / att / "shot.json").read_text(encoding="utf-8")); spec["draft"] = True
        od = out_root / shot; od.mkdir(parents=True, exist_ok=True)
        sp = od / "spec.json"; sp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        mon.reset(); t0 = time.time(); timed_out = False
        try:
            r = subprocess.run([R.PY, r"C:\AI\tools\h3_shot.py", str(sp), "--out", str(od)], env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=TIMEOUT)
            tail = (r.stdout + r.stderr)[-500:]
        except subprocess.TimeoutExpired:
            timed_out = True; tail = "timeout"
            try:
                R.req("/interrupt", {}); R.req("/queue", {"clear": True})
            except Exception:
                pass
        meta = json.loads((od / "meta.json").read_text(encoding="utf-8")) if (od / "meta.json").exists() else {}
        exec_s, status = R.history_time(meta.get("tag", "")) if meta else (None, "timeout" if timed_out else "no-meta")
        same = None
        if meta.get("ok"):
            a = HERE / "out" / "A" / shot / "clip.mp4"
            o = subprocess.run(["ffmpeg", "-i", str(od / "clip.mp4"), "-i", str(a), "-lavfi", "psnr", "-f", "null", "-"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace").stderr or ""
            same = o[o.rfind("average:"):].split()[0] if "average:" in o else None
        row = dict(profile=prof, shot=shot, desc=desc, kind="cold" if i == 0 else "warm", ok=bool(meta.get("ok")), status=status, exec_s=exec_s,
                   wall_s=round(time.time() - t0, 1), psnr_vs_A=same, vram_peak_comfy_mib=max(0, mon.vram - used_after_hog),
                   comfy_private_peak_gib=round(mon.private / 2**30, 2), sys_avail_min_gib=round(mon.avail_min, 2),
                   commit_peak_gib=round(mon.commit_max, 1), watchdog_killed=mon.tripped, pagefile_used_peak_gib=round(mon.swap_max / 2**30, 1),
                   disk_read_gib=round((mon.reads() - mon.read0) / 2**30, 1), tail="" if meta.get("ok") else tail)
        rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
        resf.write_text(json.dumps(dict(target_avail_gb=target, ram_hog_gb=hog_gb, mem_before=ms0, mem_after_hog=ms1, flags=P["flags"], env=P["env"],
                                        runs=rows), ensure_ascii=False, indent=1), encoding="utf-8")
    mon.stop = True
    comfy.terminate()
    try:
        comfy.wait(30)
    except Exception:
        comfy.kill()
    for p in (rhog, vhog):
        p.terminate(); p.wait(30)
    print("DONE", prof, flush=True)


def kill_tree(pid):
    try:
        p = psutil.Process(pid)
        for q in p.children(recursive=True) + [p]:
            try: q.kill()
            except Exception: pass
    except Exception:
        pass


STARTED = []
_Popen = subprocess.Popen


def _tracked(*a, **k):
    p = _Popen(*a, **k); STARTED.append(p.pid); return p


subprocess.Popen = _tracked

if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        main(a[0], float(a[a.index("--target") + 1]) if "--target" in a else 24.0)
    finally:                      # 不管成功或出錯，一定收掉佔位程式與 ComfyUI
        for pid in STARTED:
            kill_tree(pid)
