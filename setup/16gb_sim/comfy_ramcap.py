"""用「記憶體上限」啟動 ComfyUI：讓 ComfyUI 以為整台電腦只有 RAMCAP_GB（借用它給 Linux 容器用的 cgroup 上限邏輯）。
實體可用量另外由 ram_hog.py 壓低。用法（在 ComfyUI 資料夾執行）：python comfy_ramcap.py main.py <ComfyUI 參數…>"""
import os
import runpy
import sys

sys.path.insert(0, os.getcwd())
import psutil  # noqa: E402

import comfy.system_memory as sm  # noqa: E402

CAP = int(float(os.environ.get("RAMCAP_GB", "32")) * (1 << 30))
sm.cgroup_memory_limit = lambda: CAP
sm.virtual_memory_total = lambda: min(CAP, psutil.virtual_memory().total)
sm.virtual_memory_available = lambda: max(0, min(psutil.virtual_memory().available, CAP))
print(f"[ramcap] ComfyUI sees total RAM {CAP / (1 << 30):.0f} GB", flush=True)

main = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(main, run_name="__main__")
