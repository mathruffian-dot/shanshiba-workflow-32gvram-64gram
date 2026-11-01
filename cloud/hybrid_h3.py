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
          HYBRID_TOOLS（本機 h3_shot.py 所在資料夾，預設 repo 的 tools/）、COLAB_NAME（Colab session 名稱，預設 h3）、
          HYBRID_COLAB_HOMES（兩個以上 Colab 帳號同時跑：每個帳號一個家目錄，用 ; 分隔〔Linux／macOS 用 :〕，default＝目前登入的帳號）。
兩個帳號同時跑（2026-10-29）：Colab CLI 的登入憑證放在家目錄（~/.config/colab-cli/token.json），一個家目錄＝一個帳號。
  第二個帳號：建一個空資料夾（例如 C:\\colab_home2），在 cmd 跑 `set USERPROFILE=C:\\colab_home2` `set HOME=C:\\colab_home2` `colab usage`
  → 瀏覽器登入第二個帳號（只要做一次）。之後 `set HYBRID_COLAB_HOMES=default;C:\\colab_home2`：本機 1 個 ComfyUI＋每台 G4 2 個。
  每台各扣自己帳號的單元；雲端預設保留比例照台數算（兩台約 4/5 給雲端）。
  實測（2026-10-29，38 支 3–4.5 秒短鏡、DMAD 4 步，本機 RTX 5090＋兩個帳號各一台 G4）：16.5 分鐘全部完成（本機 10、雲端 10＋18），
  推算全部本機約 37 分 → 快約 55%；兩個帳號各扣約 2.0 單元。G4 開機看機房：美國 216 秒、荷蘭 8.5 分（下載模型慢），
  開機慢的那台只在後段出力 → 鏡頭少（< 20 支）時第二台不太划算，越長的片越值得。
中途要停：本機要連 h3_shot.py 子程序與 ComfyUI 佇列一起清（POST /queue {"clear": true} 與 POST /interrupt）；
          停掉這支程式後 Colab 上的批次還在算，要另外 python cloud/colab_h3.py stop。
HYBRID_KEEP=1 做完要手動關：第一台 `colab_h3.py stop`；第二台以後的 session 名稱是 h3_2、h3_3…，而且要在那個帳號的家目錄下關
（set USERPROFILE=<家目錄> 再 `colab_h3.py --name h3_2 stop`），只跑 `colab_h3.py stop` 會回「Session 'h3' not found」、那台照扣。
關完用 `colab_h3.py status` 確認 Active assignments: 0（2026-10-30〈電流之戰〉漏關第二台的教訓）。"""
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


def colab_homes():
    """HYBRID_COLAB_HOMES：每個 Colab 帳號一個家目錄（Colab CLI 的登入憑證在 <家目錄>/.config/colab-cli/），用 os.pathsep 分隔
    （Windows 是 ;）；寫 default 或空字串＝目前登入的帳號。沒設＝只用目前帳號一台。每個帳號開一台 G4、各 2 個 ComfyUI。"""
    v = os.environ.get("HYBRID_COLAB_HOMES")
    if not v:
        return [None]
    return [None if h.strip() in ("", "default") else str(Path(h.strip()).expanduser().resolve()) for h in v.split(os.pathsep)]


def run_hybrid(dirs, pyh3=None, tools=None):
    """dirs：鏡頭資料夾（各有 spec.json）。回傳沒做出 clip.mp4 的資料夾清單（空＝全部成功）。"""
    pyh3 = str(pyh3 or PYH3_DEFAULT); tools = Path(tools or os.environ.get("HYBRID_TOOLS") or REPO / "tools")
    dirs = [Path(d) for d in dirs]
    chunk = int(os.environ.get("HYBRID_CHUNK", "8")); nmin = int(os.environ.get("HYBRID_MIN", "8"))
    name = os.environ.get("COLAB_NAME", "h3"); keep = os.environ.get("HYBRID_KEEP") == "1"
    homes = colab_homes(); nc = len(homes)
    relay = [d for d in dirs if _relay(d)]                          # 最後才由本機照順序跑
    shared = collections.deque(d for d in dirs if d not in relay)
    lock = threading.Lock(); stats = {"local": 0, "cloud": 0}; cloud_on = len(shared) >= nmin
    # 2026-10-25（使用者：「Colab 比較快，要分配比較多的片段給他」）：開跑就照速度比例替雲端保留一份（預設
    # 本機 62 秒／支 vs 雲端 30 秒／支 → 一台雲端約 2/3、兩台約 4/5），本機不能先拿走；本機自己那份做完才去接雲端還沒送出的。
    # 之前是共用佇列，雲端第一批要載模型（〈畢氏定理 MV〉8 支 8.5 分）期間本機一直拿，結果本機分得比雲端多。
    share = float(os.environ.get("HYBRID_CLOUD_SHARE", nc * LOCAL_SEC / (nc * LOCAL_SEC + CLOUD_SEC))) if cloud_on else 0.0
    reserve = collections.deque(shared.pop() for _ in range(int(round(len(shared) * share))))   # 從尾巴拿＝雲端照舊做後段
    speed = {"local": [], "cloud": []}                              # 實測秒數，用來估算尾巴該怎麼分
    t0 = time.time()
    _log(f"[hybrid] {len(dirs)} 鏡（接力鏡 {len(relay)} 支只在本機）；" + (f"本機＋{nc} 台 Colab 一起跑：先保留 {len(reserve)} 支給雲端、"
         f"{len(shared)} 支給本機（HYBRID_CLOUD_SHARE={share:.2f}）" if cloud_on else f"少於 {nmin} 支，全部本機跑"))

    def avg(k, default):
        v = speed[k]
        return sum(v) / len(v) if v else default

    def local_worker(do_relay=False):
        while True:
            with lock:
                if shared:
                    d = shared.popleft()
                elif reserve and not do_relay:              # 自己那份做完 → 接雲端還沒送出的（從前面拿，雲端從後面拿）
                    d = reserve.popleft(); _log(f"[hybrid] 本機做完自己的，接手雲端保留的 {d.name}")
                else:
                    d = relay.pop(0) if do_relay and relay else None
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

    def colab(k, *args, wait=True):
        # 第 k 台：自己的家目錄（＝自己的 Colab 帳號）與 session 名稱（h3、h3_2…）
        cmd = [sys.executable, str(REPO / "cloud" / "colab_h3.py"), "--name", name if k == 0 else f"{name}_{k + 1}", *map(str, args)]
        env = dict(os.environ, USERPROFILE=homes[k], HOME=homes[k]) if homes[k] else None
        return subprocess.run(cmd, env=env) if wait else subprocess.Popen(cmd, env=env)

    def others_sec():
        """收尾估算用：「本機＋其他雲端」合起來每支幾秒（只有一台雲端時就是本機速度）。"""
        loc, cl = avg("local", LOCAL_SEC), avg("cloud", CLOUD_SEC) + CLOUD_OVERHEAD / chunk
        return 1.0 / (1.0 / loc + (nc - 1) / cl)

    def cloud_worker(k):
        tag = f"雲端{k + 1}" if nc > 1 else "雲端"
        _log(f"[hybrid] {tag}開機中（只裝 H3，約 3.5 分鐘，本機先跑）")
        if colab(k, "start", "--h3-only").returncode != 0:
            _log(f"[hybrid] {tag} Colab 開不起來 → 它保留的鏡頭由本機和其他雲端接手"); return
        try:
            first = True
            while True:
                with lock:
                    if reserve:                                     # 先做保留給雲端的那份
                        rem = len(reserve) + len(shared)
                        # 收尾（2026-10-25 高斯 MV：最後一批雲端一次拿 8 支跑 8 分，本機早做完閒了 6 分）：
                        # 剩不到兩批時照實測速度估雲端這批該拿幾支，其餘留在 reserve 讓本機做完自己的之後接手
                        n = min(chunk, len(reserve)) if rem > 2 * chunk * nc else max(2, min(len(reserve), cloud_take(
                            rem, chunk, others_sec(), avg("cloud", CLOUD_SEC))))
                        n = min(n, len(reserve))                    # 2026-10-27：保留只剩 1 支時 max(2,…) 會多拿 → pop 空佇列
                        batch = [reserve.pop() for _ in range(n)]
                    else:
                        rem = len(shared)
                        n = min(chunk, rem) if rem > 2 * chunk * nc else cloud_take(rem, chunk, others_sec(), avg("cloud", CLOUD_SEC))
                        if n < 2:                                   # 剩下的本機做比較快（不用上傳下載、不用等雲端）
                            return
                        batch = [shared.pop() for _ in range(n)]
                todo = [d for d in batch if not (d / "clip.mp4").exists()]
                if not todo:
                    continue
                _log(f"[hybrid] {tag}拿 {len(todo)} 支（佇列剩 {rem - n}）：{' '.join(d.name for d in todo)}")
                ts = time.time()
                colab(k, "batch", *[d / "spec.json" for d in todo])
                back = [d for d in todo if not (d / "clip.mp4").exists()]
                done = len(todo) - len(back)
                with lock:
                    stats["cloud"] += done; stats[tag] = stats.get(tag, 0) + done
                    shared.extend(back)                             # 失敗的放回佇列，本機會拿去做
                    if done and not first:                          # 第一批含載模型暖機，不拿來估速度（會把雲端估得太慢）
                        speed["cloud"].append(max(1.0, (time.time() - ts - CLOUD_OVERHEAD) / done))
                _log(f"[hybrid] {tag}這批 {done} 支 {time.time() - ts:.0f} 秒" + ("（第一批含暖機）" if first else ""))
                first = False
                if back:
                    _log(f"[hybrid] {tag}失敗 {len(back)} 支，放回佇列：{' '.join(d.name for d in back)}")
        finally:
            if keep:
                _log(f"[hybrid] HYBRID_KEEP=1：{tag} Colab 不關（閒置約 20 分鐘會被收回；用完記得 colab_h3.py stop）")
            else:
                _log(f"[hybrid] 背景關閉{tag} Colab（不用等）")
                colab(k, "stop", wait=False)

    th = [threading.Thread(target=local_worker)] + ([threading.Thread(target=cloud_worker, args=(k,)) for k in range(nc)] if cloud_on else [])
    for t in th:
        t.start()
    for t in th:
        t.join()
    local_worker(do_relay=True)                                     # 雲端最後放回來的失敗鏡頭＋接力鏡頭
    miss = [d for d in dirs if not (d / "clip.mp4").exists()]
    per = "".join(f"（{k}：{v}）" for k, v in stats.items() if k.startswith("雲端") and nc > 1)
    _log(f"[hybrid] 完成 {time.time() - t0:.0f} 秒：本機 {stats['local']} 支、雲端 {stats['cloud']} 支{per}、失敗 {len(miss)} 支")
    return miss


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(1 if run_hybrid(sys.argv[1:]) else 0)
