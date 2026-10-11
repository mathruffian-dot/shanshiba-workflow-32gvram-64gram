"""本機＋Colab 一起跑 H3（H3_BACKEND=both）。

2026-10-11 第一次實戰（〈收假圖鑑〉直式 34 鏡、3370 格、DMAD 4 步，本機 RTX 5090＋Colab G4，HYBRID_CHUNK=8）：
  **17.9 分鐘**完成（本機 15 支、雲端 19 支、失敗 0），推算全部本機 32.6 分鐘 → **省 45%**；Colab 花 1.97 單元（含開機、關機）。
  Colab 開機 216 秒（這段時間本機先做了 4 支）；每批 8 支約 304–314 秒，其中上傳、解壓、輪詢、下載約 70 秒。
  依這次踩的坑改了：每批預設 8 支、輪詢 15 秒（colab_h3.py）、佇列快空時依兩邊速度估算雲端該拿幾支（避免本機做完還在等雲端）、
  關機放背景不算進等待、本機工具路徑可用 HYBRID_TOOLS 指定。

做法：所有鏡頭放進同一個佇列，兩個工人同時拿：
  - 本機：從佇列「前面」一支一支拿，用本機 ComfyUI（h3_shot.py）跑。開跑不用等。
  - 雲端：先開 Colab G4（只裝 ComfyUI＋H3，約 3.5 分鐘，這段時間本機已經在跑），開好後每次從佇列「後面」拿一批交給
    colab_h3.py batch（上傳 → 跑 → 下載回每個鏡頭的資料夾），做完再拿下一批。
    批次大小：佇列還多時拿 HYBRID_CHUNK 支；快空時用實測速度估算——讓「雲端這批做完」和「本機做完剩下的」差不多同時，
    算出來少於 2 支就不再派雲端（只剩 0–1 支時本機做比較快）。
  - 雲端失敗的鏡頭放回佇列給本機重跑；佇列空了就在背景關掉 Colab（HYBRID_KEEP=1 則不關，審片後要重抽可以接著用）。
接力鏡頭（spec 有 first_clip，要用上一鏡的結尾）等兩邊都做完、上一鏡一定已經在了，才由本機照順序跑。
鏡頭太少（< HYBRID_MIN，預設 8）不值得等雲端開機 → 全部本機跑。

用法：python cloud/hybrid_h3.py out/h3/S01 out/h3/S02 …   （每個資料夾要有 spec.json；成品 clip.mp4 寫回同一個資料夾）
      make_film.py 設 H3_BACKEND=both 會自動呼叫 run_hybrid()。
環境變數：HYBRID_CHUNK（雲端每批最多幾支，預設 8）、HYBRID_MIN（少於幾支就不開雲端，預設 8）、HYBRID_KEEP=1（做完不關 Colab）、
          HYBRID_TOOLS（本機 h3_shot.py 所在資料夾，預設 repo 的 tools/）、COLAB_NAME（Colab session 名稱，預設 h3）。
中途要停：本機要連 h3_shot.py 子程序與 ComfyUI 佇列一起清（POST /queue {"clear": true} 與 POST /interrupt）；
          停掉這支程式後 Colab 上的批次還在算，要另外 python cloud/colab_h3.py stop。"""
import collections
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AI_ROOT = Path(os.environ.get("AI_ROOT", "C:/AI"))
PYH3_DEFAULT = AI_ROOT / "H3" / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LOCAL_SEC, CLOUD_SEC, CLOUD_OVERHEAD = 62.0, 30.0, 70.0     # 起始估計（2026-10-11 實測：本機每支約 62 秒；雲端 2 個 ComfyUI 平均每支約 30 秒＋每批約 70 秒耗損）


def _log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def _relay(d):
    try:
        return "first_clip" in json.loads((Path(d) / "spec.json").read_text(encoding="utf-8"))
    except Exception:
        return False


def cloud_take(rem, chunk, local_sec, cloud_sec, overhead=CLOUD_OVERHEAD):
    """佇列剩 rem 支時雲端這批該拿幾支：讓 max(本機做完剩下的, 雲端這批做完) 最小。回傳 0／1 代表不值得派雲端。"""
    best_n, best_t = 0, rem * local_sec
    for n in range(1, min(chunk, rem) + 1):
        t = max((rem - n) * local_sec, overhead + n * cloud_sec)
        if t < best_t:
            best_n, best_t = n, t
    return best_n


def run_hybrid(dirs, pyh3=None, tools=None):
    """dirs：鏡頭資料夾（各有 spec.json）。回傳沒做出 clip.mp4 的資料夾清單（空＝全部成功）。"""
    pyh3 = str(pyh3 or PYH3_DEFAULT); tools = Path(tools or os.environ.get("HYBRID_TOOLS") or REPO / "tools")
    dirs = [Path(d) for d in dirs]
    chunk = int(os.environ.get("HYBRID_CHUNK", "8")); nmin = int(os.environ.get("HYBRID_MIN", "8"))
    name = os.environ.get("COLAB_NAME", "h3"); keep = os.environ.get("HYBRID_KEEP") == "1"
    relay = [d for d in dirs if _relay(d)]                          # 最後才由本機照順序跑
    shared = collections.deque(d for d in dirs if d not in relay)
    lock = threading.Lock(); stats = {"local": 0, "cloud": 0}; cloud_on = len(shared) >= nmin
    speed = {"local": [], "cloud": []}                              # 實測秒數，用來估算尾巴該怎麼分
    t0 = time.time()
    _log(f"[hybrid] {len(dirs)} 鏡（接力鏡 {len(relay)} 支只在本機）；" + ("本機＋Colab 一起跑" if cloud_on else f"少於 {nmin} 支，全部本機跑"))

    def avg(k, default):
        v = speed[k]
        return sum(v) / len(v) if v else default

    def local_worker(do_relay=False):
        while True:
            with lock:
                d = shared.popleft() if shared else (relay.pop(0) if do_relay and relay else None)
            if d is None:
                return
            if (d / "clip.mp4").exists():
                continue
            ts = time.time()
            r = subprocess.run([pyh3, str(tools / "h3_shot.py"), str(d / "spec.json"), "--out", str(d)])
            ok = r.returncode == 0 and (d / "clip.mp4").exists()
            with lock:
                stats["local"] += ok
                if ok:
                    speed["local"].append(time.time() - ts)
            _log(f"[hybrid] 本機 {d.name}: {'OK' if ok else 'FAIL'}")

    def colab(*args, wait=True):
        cmd = [sys.executable, str(REPO / "cloud" / "colab_h3.py"), "--name", name, *map(str, args)]
        return subprocess.run(cmd) if wait else subprocess.Popen(cmd)

    def cloud_worker():
        _log("[hybrid] 雲端開機中（只裝 H3，約 3.5 分鐘，本機先跑）")
        if colab("start", "--h3-only").returncode != 0:
            _log("[hybrid] Colab 開不起來 → 剩下的全部本機跑"); return
        try:
            while True:
                with lock:
                    rem = len(shared)
                    n = min(chunk, rem) if rem > 2 * chunk else cloud_take(rem, chunk, avg("local", LOCAL_SEC), avg("cloud", CLOUD_SEC))
                    if n < 2:                                       # 剩下的本機做比較快（不用上傳下載、不用等雲端）
                        return
                    batch = [shared.pop() for _ in range(n)]
                todo = [d for d in batch if not (d / "clip.mp4").exists()]
                if not todo:
                    continue
                _log(f"[hybrid] 雲端拿 {len(todo)} 支（佇列剩 {rem - n}）：{' '.join(d.name for d in todo)}")
                ts = time.time()
                colab("batch", *[d / "spec.json" for d in todo])
                back = [d for d in todo if not (d / "clip.mp4").exists()]
                done = len(todo) - len(back)
                with lock:
                    stats["cloud"] += done
                    shared.extend(back)                             # 失敗的放回佇列，本機會拿去做
                    if done:
                        speed["cloud"].append(max(1.0, (time.time() - ts - CLOUD_OVERHEAD) / done))
                if back:
                    _log(f"[hybrid] 雲端失敗 {len(back)} 支，放回佇列：{' '.join(d.name for d in back)}")
        finally:
            if keep:
                _log("[hybrid] HYBRID_KEEP=1：Colab 不關（閒置約 20 分鐘會被收回；用完記得 colab_h3.py stop）")
            else:
                _log("[hybrid] 背景關閉 Colab（不用等）")
                colab("stop", wait=False)

    th = [threading.Thread(target=local_worker)] + ([threading.Thread(target=cloud_worker)] if cloud_on else [])
    for t in th:
        t.start()
    for t in th:
        t.join()
    local_worker(do_relay=True)                                     # 雲端最後放回來的失敗鏡頭＋接力鏡頭
    miss = [d for d in dirs if not (d / "clip.mp4").exists()]
    _log(f"[hybrid] 完成 {time.time() - t0:.0f} 秒：本機 {stats['local']} 支、雲端 {stats['cloud']} 支、失敗 {len(miss)} 支")
    return miss


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(1 if run_hybrid(sys.argv[1:]) else 0)
