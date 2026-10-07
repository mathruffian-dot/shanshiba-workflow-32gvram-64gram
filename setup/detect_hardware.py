"""偵測這台電腦的顯卡、記憶體、硬碟，告訴你該用三個 repo 的哪一個。只用 Python 標準函式庫，任何 Python 3.10+ 都能跑。
python setup/detect_hardware.py"""
import ctypes
import json
import platform
import shutil
import subprocess
import sys
for _s in (sys.stdout, sys.stderr):                 # 中文輸出在非 UTF-8 主控台不變亂碼
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPOS = [
    ("shanshiba-workflow-32gvram-64gram", 30, 60, "32GB VRAM + 64GB RAM（完整版）"),
    ("shanshiba-workflow-16gvram-64gram", 15, 60, "16GB VRAM + 64GB RAM"),
    ("shanshiba-workflow-16gvram-32gram", 15, 30, "16GB VRAM + 32GB RAM"),
]


def gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout.strip().splitlines()
        name, mib, drv = [x.strip() for x in out[0].split(",")]
        return dict(name=name, vram_gb=round(int(mib) / 1024, 1), driver=drv)
    except Exception as e:
        return dict(error=f"nvidia-smi not available: {e}")


def ram_gb():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = M(); m.dwLength = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return dict(total_gb=round(m.ullTotalPhys / 2**30, 1), available_now_gb=round(m.ullAvailPhys / 2**30, 1),
                commit_limit_gb=round(m.ullTotalPageFile / 2**30, 1))


def main():
    g, r = gpu(), ram_gb()
    disk = shutil.disk_usage("C:\\")
    info = dict(os=platform.platform(), gpu=g, ram=r, disk_C_free_gb=round(disk.free / 2**30))
    vram = g.get("vram_gb", 0); ram = r["total_gb"]
    pick = next((x for x in REPOS if vram >= x[1] and ram >= x[2]), None)
    info["recommendation"] = (f"{pick[0]}（{pick[3]}）" if pick else
                              "低於最低需求（16GB VRAM＋32GB RAM）：H3 跑不動，請勿安裝")
    notes = []
    if vram >= 30 and ram < 60:
        notes.append("32GB 顯卡但記憶體不到 64GB：用 16gvram-32gram 的設定（--reserve-vram 不需要，但記憶體規則照它）")
    if r["available_now_gb"] < ram - 14:
        notes.append(f"目前常駐程式已用掉 {ram - r['available_now_gb']:.0f}GB；生成影片時請關掉瀏覽器等大程式")
    if disk.free / 2**30 < 250:
        notes.append("C 槽剩不到 250GB：模型約 145GB，加上工作檔與分頁檔會不夠")
    if "error" not in g and not any(k in g["name"] for k in ("RTX 50", "RTX 40", "RTX 30")):
        notes.append("顯卡不是 RTX 30／40／50 系列：comfy kitchen、RTX VSR 可能不支援，未驗證")
    info["notes"] = notes
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
