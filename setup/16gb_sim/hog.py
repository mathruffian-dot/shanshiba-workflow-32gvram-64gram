"""佔住指定 MiB 的顯存，模擬小顯卡。python hog.py 16300  （Ctrl+C 或被 kill 才釋放）"""
import sys
import time

import torch

mib = int(sys.argv[1])
x = torch.empty(mib * 1024 * 1024, dtype=torch.uint8, device="cuda")
x.fill_(1)
torch.cuda.synchronize()
free, total = torch.cuda.mem_get_info()
print(f"HOG {mib} MiB held; free now {free / 2**20:.0f} / {total / 2**20:.0f} MiB", flush=True)
while True:
    time.sleep(60)
