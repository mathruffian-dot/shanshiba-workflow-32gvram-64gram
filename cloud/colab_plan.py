"""開 Colab 前先算「開幾台最划算」，印出給使用者確認的訊息（agent 開機前一定先跑這支、把結果告訴使用者並等回覆）。

用法：python cloud/colab_plan.py <spec.json｜鏡頭資料夾｜清單.txt …> [--local auto|free|busy] [--homes "default;C:\\colab_home2"] [--no-query]
      [--split 輸出前綴]   ← 只用雲端時，把鏡頭照估計工作量平均分成 k 份清單（<前綴>_vm1.txt…），每台各自 batch

公式（2026-11-06 由實測整理，〈孔子來代課〉第 9 集與主題曲 MV 校正，見 cloud/README.md「大量分鏡要開幾台」）：
  M ＝ 本機全部跑完的分鐘數（每鏡：H3 格數 × 每格秒數 × 畫面面積比 ＋ 5 秒；DMAD 每格約 0.51 秒、14 步約 1.07 秒，1344×768 為 1）
  一台 G4（2 個 ComfyUI）≈ 本機 1.5 倍速；每台開機約 3.7 分、收尾約 1 分；每台約 9 單元／小時
  本機一起跑：T ≈ 3.7 ＋ (M − 3.7) ÷ (1 ＋ 1.5k) ＋ 1；只有雲端：T ≈ 3.7 ＋ M ÷ 1.5k ＋ 1；單元 ≈ k × T × 9 ÷ 60
  建議台數：一台一台往上加，「多開這台每多花 1 單元至少省 5 分鐘」才加（約等於每台至少分到 13 分鐘的工作）
  上限：每個帳號 2 台（2026-11-06 實測同帳號可開兩台），而且帳號餘額要夠。
同一個帳號開兩台：家目錄清單寫兩次，例如 HYBRID_COLAB_HOMES=default;default → session 名 h3、h3_2（hybrid_h3.py／colab_only.py 都照順序取名）。
Standard library only."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FPS = 24
SEC_PER_FRAME = {"draft": 0.51, "full": 1.07}        # 本機 RTX 5090、1344×768：2026-11-05〈孔子來代課〉第 9 集 220 鏡全本機 205.5 分＝每格 0.51 秒；14 步約 DMAD 的 2.1 倍
SHOT_OVERHEAD = 5.0
CLOUD_SPEEDUP, BOOT, TAIL, RATE = 1.5, 3.7, 1.0, 9.0   # G4 兩個 ComfyUI≈本機 1.5 倍（使用者確認；MV 實測 1.6）；開機 205–248 秒；餘額實扣 8.0–9.7 單元／小時
MIN_PER_UNIT = 5.0                                    # 多開一台：每多花 1 單元至少要省 5 分鐘
PER_ACCOUNT = 2


def frames_for(d):
    n = 0
    while 17 * n + 5 < d * FPS:
        n += 1
    return 17 * n + 5


def collect(paths):
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += [p / "spec.json"] if (p / "spec.json").exists() else sorted(p.rglob("spec.json"))
        elif p.suffix.lower() == ".txt":     # 一行一個或空白分隔；相對路徑以清單所在資料夾為準
            for tok in p.read_text(encoding="utf-8").split():
                q = Path(tok) if Path(tok).is_absolute() else p.parent / tok
                out += collect([q])
        else:
            out.append(p)
    return out


def local_sec(spec):
    s = json.loads(spec.read_text(encoding="utf-8"))
    w, h = s.get("size", [1344, 768])
    per = SEC_PER_FRAME["draft" if s.get("draft") or s.get("steps", 14) <= 4 else "full"]
    return frames_for(float(s.get("duration", 4))) * per * (w * h) / (1344 * 768) + SHOT_OVERHEAD


def local_busy():
    """本機忙＝ComfyUI（8188）佇列有東西，或顯卡已用超過 12 GB。查不到就當作有空。"""
    why = []
    try:
        q = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/queue", timeout=3).read())
        n = len(q.get("queue_running", [])) + len(q.get("queue_pending", []))
        if n:
            why.append(f"ComfyUI 佇列 {n} 個工作")
    except Exception:
        pass
    if shutil.which("nvidia-smi"):
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True)
        try:
            used, tot = map(int, r.stdout.split("\n")[0].split(","))
            if used > 12000:
                why.append(f"顯卡已用 {used / 1024:.0f}/{tot / 1024:.0f} GB")
        except ValueError:
            pass
    return why


def account(home):
    """回傳 (餘額, 使用中的機器數)；查不到回 (None, None)。"""
    b = shutil.which("colab")
    if not b:
        return None, None
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if home:
        env.update(USERPROFILE=home, HOME=home)
    try:
        out = subprocess.run([b, "usage"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
        out = out.stdout + out.stderr
    except Exception:
        return None, None
    m = re.search(r"Current balance:\s*([\d.]+)", out); a = re.search(r"Active assignments:\s*(\d+)", out)
    return (float(m.group(1)) if m else None), (int(a.group(1)) if a else None)


def plan(M, k, local):
    if k == 0:
        return M, 0.0
    T = BOOT + max(0.0, M - BOOT * local) / (local + CLOUD_SPEEDUP * k) + TAIL
    return T, k * RATE * T / 60


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--local", default="auto", choices=["auto", "free", "busy"])
    ap.add_argument("--homes", default=os.environ.get("HYBRID_COLAB_HOMES") or os.environ.get("COLAB_HOMES") or "default",
                    help="每個 Colab 帳號的家目錄，用 ; 分隔（default＝目前登入的帳號）；同一帳號只寫一次，台數由本工具決定")
    ap.add_argument("--no-query", action="store_true", help="不查 Colab 餘額（離線估算）")
    ap.add_argument("--split", help="只用雲端時把鏡頭平均分成 k 份清單：<前綴>_vm1.txt …")
    a = ap.parse_args()

    specs = collect(a.paths)
    secs = {s: local_sec(s) for s in specs}
    M = sum(secs.values()) / 60
    why = local_busy() if a.local == "auto" else (["你指定 busy"] if a.local == "busy" else [])
    local = 0 if why else 1
    homes = list(dict.fromkeys(h.strip() for h in a.homes.split(";") if h.strip())) or ["default"]
    accts = []
    for h in homes:
        bal, act = (None, None) if a.no_query else account(None if h == "default" else h)
        accts.append(dict(home=h, balance=bal, active=act))
    cap = PER_ACCOUNT * len(accts)

    print(f"鏡頭 {len(specs)} 支；本機全部跑完約 M＝{M:.0f} 分鐘（每鏡平均 {M * 60 / max(1, len(specs)):.0f} 秒）")
    print("本機：" + ("忙（" + "、".join(why) + "）→ 只用雲端" if why else "有空 → 本機＋雲端一起跑"))
    for x in accts:
        b = "?" if x["balance"] is None else f"{x['balance']:.2f}"
        warn = f"　⚠ 已有 {x['active']} 台在跑（可能是別的工作，不要沿用或關掉）" if x["active"] else ""
        print(f"帳號 {x['home']}：餘額 {b} 單元{warn}")
    print("\n台數  總時間   單元")
    rows = {}
    for k in range(0 if local else 1, cap + 1):
        T, U = plan(M, k, local); rows[k] = (T, U)
        m = ""
        if k - 1 in rows:
            dT, dU = rows[k - 1][0] - T, U - rows[k - 1][1]
            m = f"   {dT / dU:5.1f}" if dU > 0 else ""
        print(f"  {k}   {T:5.1f} 分  {U:5.1f}{m}" + ("　（只用本機）" if k == 0 else ""))
    # 建議台數：從最少的開始加，多開一台每多花 1 單元至少省 MIN_PER_UNIT 分鐘才加；餘額不夠就停
    total_bal = sum(x["balance"] or 0 for x in accts) if not a.no_query and all(x["balance"] is not None for x in accts) else None
    best = min(rows)
    for k in sorted(rows)[1:]:
        dT, dU = rows[k - 1][0] - rows[k][0], rows[k][1] - rows[k - 1][1]
        if dU <= 0 or dT / dU < MIN_PER_UNIT or (total_bal is not None and rows[k][1] > total_bal):
            break
        best = k
    T, U = rows[best]

    # 每個帳號依序配台：先用餘額多的帳號
    order = sorted(accts, key=lambda x: -(x["balance"] or 0))
    seats = []
    for x in order:
        seats += [x["home"]] * PER_ACCOUNT
    seats = seats[:best]
    homes_env = ";".join(seats)
    print(f"\n建議：{'只用本機' if best == 0 else f'開 {best} 台 Colab'}，約 {T:.0f} 分鐘、約 {U:.1f} 單元"
          + (f"（只用本機要 {M:.0f} 分）" if local and best else ""))
    alt = [k for k in (best - 1, best + 1) if k in rows and k != best]
    alts = "；".join(f"{k} 台約 {rows[k][0]:.0f} 分／{rows[k][1]:.1f} 單元" for k in alt)

    print("\n—— 給使用者確認（開機前一定先問，等回覆再開）——")
    print(f"這次 {len(specs)} 鏡，本機{'在忙、只能用雲端' if why else '有空'}。建議開 {best} 台 Colab"
          + (f"（{'、'.join(f'{h} {seats.count(h)} 台' for h in dict.fromkeys(seats))}）" if best else "")
          + f"，約 {T:.0f} 分鐘、花約 {U:.1f} 單元。" + (f"其他選擇：{alts}。" if alts else "") + "要照這樣開嗎？")

    if best:
        print("\n使用者同意後：")
        if local:
            print(f"  set HYBRID_COLAB_HOMES={homes_env}\n  python cloud/hybrid_h3.py <鏡頭資料夾…>")
        else:
            print(f"  對決範本：set COLAB_HOMES={homes_env} → python colab_only.py\n"
                  f"  其他片：每台各一份清單，各自 colab_h3.py --name h3｜h3_2… start --h3-only，再 batch（每批 ≤ 10 鏡，約 96 MB 一次上傳會失敗）")
        if not local and a.split:
            buckets = [[] for _ in range(best)]; load = [0.0] * best
            for s in sorted(specs, key=lambda s: -secs[s]):
                i = load.index(min(load)); buckets[i].append(s); load[i] += secs[s]
            for i, b in enumerate(buckets):
                f = Path(f"{a.split}_vm{i + 1}.txt"); f.write_text("\n".join(str(x) for x in b), encoding="utf-8")
                print(f"  {f}：{len(b)} 鏡，雲端約 {load[i] / 60 / CLOUD_SPEEDUP:.0f} 分（帳號 {seats[i]}，session {'h3' if seats[:i + 1].count(seats[i]) == 1 else 'h3_2'}）")


if __name__ == "__main__":
    main()
