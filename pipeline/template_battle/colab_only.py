"""只用 Colab 跑 H3（本機 ComfyUI 被別的 session 佔著時用，完全不碰本機佇列）。
開跑前先用 cloud/colab_plan.py 算要開幾台，告訴使用者、等使用者同意（2026-11-06 起）；同一帳號開兩台＝COLAB_HOMES 寫兩次同一個家目錄。
每個帳號開一台 G4（各 2 個 ComfyUI）→ 大家從同一個佇列一批一批拿 → 下載回 out/h3/<鏡>/ → 立刻關機並確認。
失敗的鏡放回佇列，最多重試一輪；還是失敗就列出來。
用法：python colab_only.py [鏡號…]    （不給鏡號＝全部還沒有 clip.mp4、或 spec 比 clip 新的鏡）
環境變數：COLAB_HOMES（用 ; 分隔的家目錄，default＝目前帳號；預設只用目前帳號）、COLAB_NAMES（對應的 session 名，用 ; 分隔；預設 h3、h3_2…）、
COLAB_CHUNK（每批幾支，預設 8）、COLAB_REUSE=1（確定開著的那台是自己開的才設）。
⚠ 2026-11-06 踩坑：開工時發現同名 session 已經開著＝很可能是別的 session 的 VM。colab_h3.py start 會直接沿用、做完的 stop 還會把它關掉 →
這裡預設跳過那個帳號（只在 COLAB_REUSE=1 才沿用）。開機前查過 status 也不夠，隔幾分鐘就可能被別的 session 開走。"""
import collections
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
REPO = (HERE / CFG.get("repo_dir", "../..")).resolve()
TOOL = REPO / "cloud" / "colab_h3.py"
H3 = HERE / "out" / "h3"
only = sys.argv[1:]
CHUNK = int(os.environ.get("COLAB_CHUNK", "8"))
homes = [None if h.strip() in ("", "default") else h.strip() for h in os.environ.get("COLAB_HOMES", "default").split(";")]


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


names = [n.strip() for n in os.environ.get("COLAB_NAMES", "").split(";") if n.strip()] or ["h3" if k == 0 else f"h3_{k + 1}" for k in range(len(homes))]


def need(d):
    sp, cl = d / "spec.json", d / "clip.mp4"
    if not sp.exists() or (only and d.name not in only):
        return False
    return not cl.exists() or cl.stat().st_mtime < sp.stat().st_mtime


def colab(k, *args):
    cmd = [sys.executable, str(TOOL), "--name", names[k], *map(str, args)]
    env = dict(os.environ, USERPROFILE=homes[k], HOME=homes[k]) if homes[k] else dict(os.environ)
    return subprocess.run(cmd, env=env)


q = collections.deque(sorted((d for d in H3.iterdir() if d.is_dir() and need(d)), key=lambda d: d.name))
n0 = len(q)
tries = collections.Counter()
lock = threading.Lock()
t0 = time.time()
log(f"{n0} 鏡，{len(homes)} 台 Colab")


def taken(k):
    """同名 session 已經開著？（別的 session 的 VM 不能沿用、更不能關）"""
    env = dict(os.environ, USERPROFILE=homes[k], HOME=homes[k]) if homes[k] else dict(os.environ)
    code = f"import sys; sys.path.insert(0, {str(TOOL.parent)!r}); sys.argv = ['x']; import colab_h3; print('ALIVE' if colab_h3.alive({names[k]!r}) else 'FREE')"
    return "ALIVE" in subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def worker(k):
    tag = f"雲端{k + 1}"
    if os.environ.get("COLAB_REUSE") != "1" and taken(k):
        log(tag, f"{names[k]} 已經開著（可能是別的 session 的）→ 不用這個帳號")
        return
    log(tag, "開機（只裝 H3，約 4 分鐘）")
    for attempt in range(int(os.environ.get("COLAB_START_TRIES", "8"))):   # G4 常回 503 Service Unavailable（Google 沒機器）：隔 2 分鐘再要
        if colab(k, "start", "--h3-only").returncode == 0:
            break
        log(tag, f"第 {attempt + 1} 次開不起來，2 分鐘後再試")
        time.sleep(120)
    else:
        log(tag, "一直開不起來，放棄（鏡頭留給另一台）")
        colab(k, "stop")
        return
    try:
        while True:
            with lock:
                batch = [q.popleft() for _ in range(min(CHUNK, len(q)))]
            if not batch:
                return
            stamp = time.time(); log(tag, "拿", len(batch), "支：", " ".join(d.name for d in batch))
            colab(k, "batch", *[d / "spec.json" for d in batch])
            bad = [d for d in batch if not ((d / "clip.mp4").exists() and (d / "clip.mp4").stat().st_mtime >= stamp)]
            with lock:
                for d in bad:
                    tries[d.name] += 1
                    if tries[d.name] < 2:
                        q.append(d)
            log(tag, f"這批 {len(batch) - len(bad)}/{len(batch)} 支，{time.time() - stamp:.0f} 秒，總進度剩 {len(q)} 支待拿")
    finally:
        log(tag, "關機"); colab(k, "stop")


th = [threading.Thread(target=worker, args=(k,)) for k in range(len(homes))]
for i, t in enumerate(th):
    t.start()
for t in th:
    t.join()
miss = [d.name for d in sorted(H3.iterdir()) if d.is_dir() and need(d)]
log(f"完成 {time.time() - t0:.0f} 秒；沒做出來：", miss)
for k in range(len(homes)):
    colab(k, "status")
