"""佔住指定 GB 的實體記憶體，模擬小記憶體電腦。python ram_hog.py 55
先放大自己的工作集下限，再用 VirtualLock 鎖住（鎖住的頁不會被換到分頁檔）；鎖不住的部分改成每 2 秒摸一遍保持常駐。"""
import ctypes
import ctypes.wintypes as wt
import sys
import threading
import time

GB = 1 << 30
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.VirtualAlloc.restype = ctypes.c_void_p
k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
k32.GetCurrentProcess.restype = wt.HANDLE
k32.SetProcessWorkingSetSizeEx.argtypes = [wt.HANDLE, ctypes.c_size_t, ctypes.c_size_t, wt.DWORD]

size_gb = float(sys.argv[1])
n = int(size_gb)
ok_ws = k32.SetProcessWorkingSetSizeEx(k32.GetCurrentProcess(), int((n + 1) * GB), int((n + 2) * GB), 0)
chunks, locked, unlocked = [], 0, []
for i in range(n):
    p = k32.VirtualAlloc(None, GB, 0x3000, 0x04)          # MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE
    if not p:
        print(f"VirtualAlloc failed at {i} GB err={ctypes.get_last_error()}", flush=True); break
    ctypes.memset(p, 1, GB)
    if k32.VirtualLock(p, GB):
        locked += 1
    else:
        unlocked.append(p)
    chunks.append(p)
print(f"RAMHOG {len(chunks)} GB allocated, {locked} GB locked, {len(unlocked)} GB kept by touching (ws_set={bool(ok_ws)})", flush=True)


def toucher():
    page = 4096
    while True:
        for p in unlocked:
            for off in range(0, GB, page * 64):          # 每 64 頁摸一次，讓 Windows 認為整段都在用
                ctypes.c_char.from_address(p + off).value
        time.sleep(2)


if unlocked:
    threading.Thread(target=toucher, daemon=True).start()
while True:
    time.sleep(60)
