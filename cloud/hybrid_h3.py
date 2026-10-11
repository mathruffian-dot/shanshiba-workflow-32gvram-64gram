"""本機＋Colab 一起跑 H3（H3_BACKEND=both）。⚠ 2026-10-10 加入，尚未實測。

做法：所有鏡頭放進同一個佇列，兩個工人同時拿：
  - 本機：從佇列「前面」一支一支拿，用本機 ComfyUI（h3_shot.py）跑。開跑不用等。
  - 雲端：先開 Colab G4（約 3.5 分鐘，這段時間本機已經在跑），開好後每次從佇列「後面」拿一小批（預設 4 支＝2 個 ComfyUI × 2），
    交給 colab_h3.py batch（上傳 → 跑 → 下載回每個鏡頭的資料夾），做完再拿下一批。
  - 雲端失敗的鏡頭放回佇列給本機重跑；佇列空了就關掉 Colab（HYBRID_KEEP=1 則不關，審片後要重抽可以接著用）。
接力鏡頭（spec 有 first_clip，要用上一鏡的結尾）等兩邊都做完、上一鏡一定已經在了，才由本機照順序跑。
鏡頭太少（< HYBRID_MIN，預設 8）不值得等雲端開機 → 全部本機跑。

用法：python cloud/hybrid_h3.py out/h3/S01 out/h3/S02 …   （每個資料夾要有 spec.json；成品 clip.mp4 寫回同一個資料夾）
      make_film.py 設 H3_BACKEND=both 會自動呼叫 run_hybrid()。
環境變數：HYBRID_CHUNK（雲端每批幾支，預設 4）、HYBRID_MIN（少於幾支就不開雲端，預設 8）、HYBRID_KEEP=1（做完不關 Colab）、
          COLAB_NAME（Colab session 名稱，預設 h3）。"""
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


def _log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def _relay(d):
    try:
        return "first_clip" in json.loads((Path(d) / "spec.json").read_text(encoding="utf-8"))
    except Exception:
        return False


def run_hybrid(dirs, pyh3=None, tools=None):
    """dirs：鏡頭資料夾（各有 spec.json）。回傳沒做出 clip.mp4 的資料夾清單（空＝全部成功）。"""
    pyh3 = str(pyh3 or PYH3_DEFAULT); tools = Path(tools or REPO / "tools")
    dirs = [Path(d) for d in dirs]
    chunk = int(os.environ.get("HYBRID_CHUNK", "4")); nmin = int(os.environ.get("HYBRID_MIN", "8"))
    name = os.environ.get("COLAB_NAME", "h3"); keep = os.environ.get("HYBRID_KEEP") == "1"
    relay = [d for d in dirs if _relay(d)]                          # 最後才由本機照順序跑
    shared = collections.deque(d for d in dirs if d not in relay)
    lock = threading.Lock(); stats = {"local": 0, "cloud": 0}; cloud_on = len(shared) >= nmin
    t0 = time.time()
    _log(f"[hybrid] {len(dirs)} 鏡（接力鏡 {len(relay)} 支只在本機）；" + ("本機＋Colab 一起跑" if cloud_on else f"少於 {nmin} 支，全部本機跑"))

    def local_worker(do_relay=False):
        while True:
            with lock:
                d = shared.popleft() if shared else (relay.pop(0) if do_relay and relay else None)
            if d is None:
                return
            if (d / "clip.mp4").exists():
                continue
            r = subprocess.run([pyh3, str(tools / "h3_shot.py"), str(d / "spec.json"), "--out", str(d)])
            ok = r.returncode == 0 and (d / "clip.mp4").exists()
            with lock:
                stats["local"] += ok
            _log(f"[hybrid] 本機 {d.name}: {'OK' if ok else 'FAIL'}")

    def colab(*args):
        return subprocess.run([sys.executable, str(REPO / "cloud" / "colab_h3.py"), "--name", name, *map(str, args)])

    def cloud_worker():
        _log("[hybrid] 雲端開機中（約 3.5 分鐘，本機先跑）")
        if colab("start").returncode != 0:
            _log("[hybrid] Colab 開不起來 → 剩下的全部本機跑"); return
        try:
            while True:
                with lock:
                    n = min(chunk, len(shared))
                    if n < 2 and len(shared) <= 1:                  # 只剩 0–1 支：本機做比較快（不用上傳下載）
                        return
                    batch = [shared.pop() for _ in range(n)]
                todo = [d for d in batch if not (d / "clip.mp4").exists()]
                if not todo:
                    continue
                _log(f"[hybrid] 雲端拿 {len(todo)} 支：{' '.join(d.name for d in todo)}")
                colab("batch", *[d / "spec.json" for d in todo])
                back = [d for d in todo if not (d / "clip.mp4").exists()]
                with lock:
                    stats["cloud"] += len(todo) - len(back)
                    shared.extend(back)                             # 失敗的放回佇列，本機會拿去做
                if back:
                    _log(f"[hybrid] 雲端失敗 {len(back)} 支，放回佇列：{' '.join(d.name for d in back)}")
        finally:
            if keep:
                _log("[hybrid] HYBRID_KEEP=1：Colab 不關（閒置約 20 分鐘會被收回；用完記得 colab_h3.py stop）")
            else:
                colab("stop")

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
