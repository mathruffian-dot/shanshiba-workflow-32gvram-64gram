r"""交片前檢查總表（第一版：只收成片）。2026-11-24 建立；設計經 Codex gpt-6.2-astra 審過。

為什麼有這支：交片前要跑的檢查散在好幾支工具、各片資料夾、對決範本，結果寫法各不相同（有的回傳碼、有的印 ★、有的只出圖給人看），
全靠記得一支一支跑。這支把「成片層」的檢查收成一張表，並且把「要人看」的項目做成一定要簽核才算完成。

★ 回傳 0 只代表「這一版成片、這支工具目前收進來的檢查與簽核都做完了」，不代表片子沒問題。
  還沒收進來的必跑檢查印在報告最後（逐鏡 flashcheck／blurcheck／stutter、SHAKE、pron_guard、cutpairs、colordrift、handside、手機版…），
  照 docs/04_自審清單.md 與各片自審清單另外跑；等它們一項一項接進來、驗過，才會從那張表拿掉。

用法（任何有 numpy 的 Python；ffmpeg／ffprobe 要在 PATH）：
  python preflight.py check  <成片.mp4> [--orient auto|landscape|portrait] [--lufs -16] [--tol 1.0] [--out <資料夾>]
  python preflight.py sign   <成片.mp4> <項目> --by <誰> --result pass|reject --note "<看了什麼、在哪幾秒>"
  python preflight.py status <成片.mp4>          只讀上次的結果與簽核，不重跑
  python preflight.py selftest                    用 ffmpeg 合成的測試片驗證判定與放行邏輯
輸出：<成片所在資料夾>/preflight/<成片檔名>.md、.json、.signoff.json（--out 可改）。
回傳碼：0＝必跑項全部「通過」或「已簽核通過」；1＝還有不通過／沒跑成功／待簽核／簽核退回；2＝用法錯誤。

項目（每項先標「適用性」，再記「結果」；這一版四項都是必跑）：
  spec      規格      自動  橫式 1920x1080／直式 1088x1904、24 fps、有聲音軌
  loudness  響度      自動  整合響度在 目標(預設 -16 LUFS) ± 容許(預設 1.0)；真峰值 > 0 dBTP 算不通過（數字一律印出來）
  stutter   頓挫篩檢  自動→人  沿用 stutter.py 的判定（_score：每 4 格停一格 dup<0.5 或一格大一格小 alt>0.5，且有動作），
                      逐秒窗掃整支成片；含剪接點的窗略過（剪接本身就是一格大跳）。0 個可疑區段＝通過；
                      有可疑區段＝列出時間碼，人要逐段看過再簽核。⚠ 剪接點前後約 1 秒這一層看不到，逐鏡 stutter.py check 才準。
  playback  整片實播  人    整片開聲音從頭看到尾（畫面、聲音、字幕、節奏），簽核時寫下看到的問題或「沒有」。
結果只有這幾種：通過／不通過／沒跑成功（工具當掉、逾時、輸出看不懂）／缺輸入／待簽核／已簽核通過／已簽核退回。
  「必跑」項只有「通過」「已簽核通過」不擋交片，其餘全部擋。

簽核綁指紋：每一項的指紋＝SHA-256(成片內容雜湊＋這支工具版本＋stutter.py 內容雜湊＋該項門檻)。
  成片重出、工具改版或門檻改了，舊簽核自動失效，回到待簽核。"""
import argparse
import datetime
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.10"
HERE = Path(__file__).resolve().parent
LOCK_WAIT = 20         # 別的程序正在檢查同一支成片時，最多等幾秒
DECODE_TIMEOUT = 1800  # 整支成片解碼的總時限（秒）
MIN_COVERAGE = 0.5   # 有評分的窗蓋不到整支片的一半 → 頓挫篩檢算沒跑成功
CUT_DIFF = 25.0      # 相鄰兩格平均灰階差超過這個＝剪接點（H3 鏡內動作實測 < 15；剪接多在 30 以上）
ORDER = ["spec", "loudness", "stutter", "playback"]
TITLE = {"spec": "規格", "loudness": "響度", "stutter": "頓挫篩檢", "playback": "整片實播"}
OK_STATES = {"通過", "已簽核通過"}
HUMAN_ONLY = {"playback"}     # 這些項目的自動結果只能是「待簽核」
AUTO_STATES = {"通過", "不通過", "沒跑成功", "缺輸入", "待簽核"}
DEFAULT_PARAMS = {"spec": {"orient": "auto"}, "loudness": {"target": -16.0, "tol": 1.0}}
NOT_INTEGRATED = [
    ("逐鏡閃爍", r"tools\flashcheck.py --clips <資料夾>"),
    ("逐鏡頓挫與來回抖（STUTTER／SHAKE 都要 0 支）", r"tools\stutter.py check <各鏡 clip.mp4>"),
    ("動作糊邊", r"tools\blurcheck.py --clips <out>"),
    ("色調漂移", r"tools\colordrift.py <集> --ver N"),
    ("每秒一格審片", r"tools\framecheck.py <成片>"),
    ("逐鏡構圖漂移、H3 自己切鏡", r"tools\clipcheck.py <資料夾>"),
    ("左右手、跳切", "人工逐鏡看（原專案有專用腳本，未收錄）"),
    ("讀音（念錯過的字）", r"tools\pron_guard.py <lines.json> <wav 資料夾> --all-asr"),
    ("整片連續聽寫比對台詞", "各片的 review 腳本（範例 pipeline/example_D-7/review.py）"),
    ("遠景小臉", r"tools\face_refine.cmd --track"),
    ("手機版（≤30 MB、橫式 1280x720／直式 720x1280）", "各片 assemble 腳本"),
    ("首幀重生後的下游（封面、片尾、空景）", "人工清點"),
]


def _run(cmd, timeout=1800):
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def sha256_file(p, buf=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fingerprint(film_sha, item, params):
    tool = sha256_file(HERE / "stutter.py") if item == "stutter" and (HERE / "stutter.py").exists() else ""
    s = json.dumps({"film": film_sha, "item": item, "preflight": VERSION, "tool": tool, "params": params}, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def tc(sec):
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


# ---------- 各項檢查：回傳 (結果, 摘要, 細節 dict) ----------
def check_spec(film, orient):
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(film)], 120)
    if r.returncode != 0:
        return "沒跑成功", "ffprobe 讀不了這個檔：" + r.stderr.decode("utf-8", "replace").strip()[-200:], {}
    try:
        info = json.loads(r.stdout.decode("utf-8", "replace"))
        v = [s for s in info["streams"] if s.get("codec_type") == "video"]
        a = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        dur = float(info["format"]["duration"])
    except Exception as e:  # noqa: BLE001
        return "沒跑成功", f"ffprobe 輸出看不懂：{e}", {}
    if not v:
        return "不通過", "沒有影像軌", {"duration": dur}
    w, h, fps = int(v[0]["width"]), int(v[0]["height"]), v[0].get("r_frame_rate", "?")
    d = {"width": w, "height": h, "fps": fps, "vcodec": v[0].get("codec_name"), "pix_fmt": v[0].get("pix_fmt"),
         "acodec": a[0].get("codec_name") if a else None, "duration": dur}
    want = {"landscape": (1920, 1080), "portrait": (1088, 1904)}
    o = orient if orient != "auto" else ("landscape" if w >= h else "portrait")
    bad = []
    if (w, h) != want[o]:
        bad.append(f"尺寸 {w}x{h}，{'橫式' if o == 'landscape' else '直式'}應為 {want[o][0]}x{want[o][1]}")
    if fps != "24/1":
        bad.append(f"幀率 {fps}，應為 24/1")
    if not a:
        bad.append("沒有聲音軌")
    summ = f"{w}x{h}、{fps} fps、{d['vcodec']}/{d['acodec']}、{tc(dur)}"
    return ("不通過", summ + "；" + "；".join(bad), d) if bad else ("通過", summ, d)


def check_loudness(film, target, tol):
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(film), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0:
        return "沒跑成功", "ffmpeg 量響度失敗：" + err.strip()[-200:], {}
    tail = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    mi = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    mp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", tail)
    if not mi or not mp:
        return "沒跑成功", "ebur128 的 Summary 看不懂（找不到 I 或 Peak）", {}
    lufs = float(mi.group(1))
    peak = float("-inf") if mp.group(1) == "-inf" else float(mp.group(1))
    return judge_loudness(lufs, peak, target, tol)


def judge_loudness(lufs, peak, target, tol):
    """響度判定（跟量測分開，方便單獨測）：響度在目標 ± 容許內，而且真峰值不超過 0 dBTP，兩個都要成立。"""
    d = {"lufs": lufs, "true_peak": None if peak == float("-inf") else peak, "target": target, "tol": tol}
    summ = f"整合響度 {lufs:.1f} LUFS（目標 {target:g} ± {tol:g}）、真峰值 {'-inf' if peak == float('-inf') else format(peak, '.1f')} dBTP"
    bad = []
    if not (abs(lufs - target) <= tol):      # 寫成「不在範圍內」：量到 nan 也會算不通過
        bad.append(f"響度差目標 {lufs - target:+.1f}")
    if not (peak <= 0):
        bad.append("真峰值超過 0 dBTP（會破音）")
    return ("不通過", summ + "；" + "；".join(bad), d) if bad else ("通過", summ, d)


def _frame_diffs(film):
    """跟 stutter.py 的 _diffs 同一個量（24fps、336x192 灰階、相鄰格平均絕對差），改成邊讀邊算，整支成片也不吃記憶體。"""
    import tempfile
    import threading
    import numpy as np
    # 錯誤訊息寫到暫存檔，不用管線：壞檔的錯誤訊息很多時，管線塞滿會讓 ffmpeg 停住、這邊又在等畫面，兩邊卡死。
    # 另外設總時限，超過就砍掉，當成沒跑成功。
    with tempfile.TemporaryFile() as ef:
        pr = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(film), "-vf", "fps=24,scale=336:192,format=gray", "-f", "rawvideo", "-"],
                              stdout=subprocess.PIPE, stderr=ef)
        timed_out = []
        killer = threading.Timer(DECODE_TIMEOUT, lambda: (timed_out.append(1), pr.kill()))
        killer.start()
        try:
            n, prev, out = 336 * 192, None, []
            while True:
                b = pr.stdout.read(n)
                if len(b) < n:
                    break
                f = np.frombuffer(b, np.uint8).astype(np.float32)
                if prev is not None:
                    out.append(float(np.abs(f - prev).mean()))
                prev = f
            rc = pr.wait()
        finally:
            killer.cancel()
            pr.stdout.close()
        if timed_out:
            raise RuntimeError(f"ffmpeg 解碼超過 {DECODE_TIMEOUT} 秒，已中止")
        if rc != 0:
            ef.seek(0)
            raise RuntimeError("ffmpeg 解碼失敗：" + ef.read().decode("utf-8", "replace").strip()[-200:])
    return np.array(out)


def check_stutter(film):
    try:
        import numpy as np
        sys.path.insert(0, str(HERE))
        import stutter  # 判定邏輯只有 stutter.py 一份，這裡不另寫門檻
    except Exception as e:  # noqa: BLE001
        return "沒跑成功", f"載入 numpy 或 stutter.py 失敗：{e}", {}
    try:
        d = _frame_diffs(film)
    except Exception as e:  # noqa: BLE001
        return "沒跑成功", str(e), {}
    if len(d) < 24:
        return "沒跑成功", f"只解出 {len(d) + 1} 格，太短", {}
    cuts = np.where(d > CUT_DIFF)[0]
    hits, skipped, scored = [], 0, 0
    covered = np.zeros(len(d), bool)          # 哪些格至少被一個「有評分的窗」蓋到
    starts = list(range(0, max(1, len(d) - 23), 6))
    if len(d) > 24 and starts[-1] != len(d) - 24:
        starts.append(len(d) - 24)          # 補評貼齊片尾的最後一個視窗（跟 stutter.py 一致）
    for s0 in starts:
        w = d[s0:s0 + 24]
        if len(w) < 12:
            continue
        if ((cuts >= s0) & (cuts < s0 + len(w))).any():
            skipped += 1
            continue
        scored += 1
        covered[s0:s0 + len(w)] = True
        dup, act, alt, _ = stutter._score(w)
        if act >= 2 and (dup < 0.5 or alt > 0.5):
            hits.append((s0 / 24, float(dup), float(alt)))
    iv = []
    for t, dup, alt in hits:
        if iv and t - iv[-1]["end"] <= 1.0:
            iv[-1].update(end=t + 1, dup=min(iv[-1]["dup"], dup), alt=max(iv[-1]["alt"], alt))
        else:
            iv.append({"start": t, "end": t + 1, "dup": dup, "alt": alt})
    gaps, g0 = [], None                         # 沒被任何評分窗蓋到的連續區段（密集剪接的地方）
    for i, c in enumerate(list(covered) + [True]):
        if not c and g0 is None:
            g0 = i
        elif c and g0 is not None:
            gaps.append({"start": g0 / 24, "end": i / 24})
            g0 = None
    unchecked = float(sum(g["end"] - g["start"] for g in gaps))
    det = {"frames": int(len(d) + 1), "cuts": int(len(cuts)), "windows_scored": scored, "windows_skipped_at_cuts": skipped, "intervals": iv,
           "unchecked": gaps, "unchecked_seconds": round(unchecked, 1), "cut_diff": CUT_DIFF}
    if scored == 0:
        return "沒跑成功", f"每個視窗都含剪接點（{len(cuts)} 個剪接點），整支一格都沒評到分，不能當作沒有頓挫", det
    cov = float(covered.mean())
    det["coverage"] = round(cov, 3)
    if cov < MIN_COVERAGE:
        return "沒跑成功", f"有評分的窗只蓋到整支片的 {cov:.0%}（剪接太密），不能當作沒有頓挫；請改用逐鏡 stutter.py check", det
    big = [g for g in gaps if g["end"] - g["start"] >= 1.0]      # 摘要只列 1 秒以上的沒檢區段，全部的在 JSON 的 unchecked
    gtxt = ("，其中 1 秒以上的：" + "、".join(f"{tc(g['start'])}–{tc(g['end'])}" for g in big[:12]) + ("…" if len(big) > 12 else "")) if big else ""
    note = (f"（{len(cuts)} 個剪接點；評分 {scored} 窗；剪接太密而完全沒檢到的共 {unchecked:.1f} 秒{gtxt}"
            "；剪接點前後約 1 秒也看不準，逐鏡 stutter.py check 才準）")
    if not iv and not big:
        return "通過", "沒有可疑區段" + note, det
    if not iv:
        return "待簽核", f"沒有可疑區段，但有 {len(big)} 段 1 秒以上完全沒檢到，要人看那幾段" + note, det
    lst = "、".join(f"{tc(x['start'])}–{tc(x['end'])}" for x in iv[:30]) + ("…" if len(iv) > 30 else "")
    return "待簽核", f"{len(iv)} 個可疑區段要逐段看：{lst}" + note, det


# ---------- 簽核 ----------
def out_paths(film, out):
    d = Path(out) if out else film.parent / "preflight"
    return d, d / (film.stem + ".md"), d / (film.stem + ".json"), d / (film.stem + ".signoff.json")


class SignoffError(Exception):
    pass


def load_signoffs(p):
    """讀簽核檔。檔案壞了要報錯，不能當成「沒有簽核」（那會讓退回紀錄消失）。"""
    if not p.exists():
        return []
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(v, list) and all(isinstance(s, dict) and {"item", "result", "fingerprint"} <= set(s) for s in v)
        return v
    except Exception as e:  # noqa: BLE001
        raise SignoffError(f"簽核檔讀不了（{p}）：{type(e).__name__} {e}。請人看過這個檔再決定，不要直接刪。")


def write_atomic(p, text):
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


class Lock:
    """同一支成片的報告與簽核同一時間只給一個程序寫（多個 session 可能同時跑）。"""

    # 用作業系統的檔案鎖（Windows：msvcrt.locking；其他：fcntl.flock）鎖住 .lock 檔的第一個位元組。
    # 鎖跟著開檔的程序走：程序結束（包括當掉、被砍）系統就自動放掉，所以不用猜「多舊的鎖算過期」，
    # 檢查跑再久也不會被別的程序誤刪。.lock 檔本身留著不刪，裡面沒有東西。

    def __init__(self, d, stem):
        self.p = d / (stem + ".lock")
        self.f = None

    def _try(self):
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __enter__(self):
        self.f = open(self.p, "a+b")
        for _ in range(LOCK_WAIT * 5):
            try:
                self.f.seek(0)
                self._try()
                return self
            except OSError:
                time.sleep(0.2)
        self.f.close()
        self.f = None
        raise SignoffError(f"別的程序正在檢查或簽核這支成片（{self.p}），等了 {LOCK_WAIT} 秒還沒好，稍後再試。")

    def __exit__(self, *a):
        try:
            self.f.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.f.close()


def apply_signoff(item, res, fp, signoffs):
    """待簽核的項目：找指紋相同的最後一筆簽核。回傳 (結果, 簽核紀錄或 None, 失效的舊簽核數)。"""
    mine = [s for s in signoffs if s.get("item") == item]
    cur = [s for s in mine if s.get("fingerprint") == fp]
    stale = len(mine) - len(cur)
    if res != "待簽核" or not cur:
        return res, None, stale
    last = cur[-1]
    return ("已簽核通過" if last.get("result") == "pass" else "已簽核退回"), last, stale


def evaluate(film, data, so):
    """拿「上次 check 的自動結果」＋「現在的成片、現在的工具、現在的簽核檔」重算每一項的結果。
    回傳 (rc, 訊息或 None)。成片不見、成片內容變了、工具或門檻變了 → 上次的結果不算數，rc 1。"""
    if not film.exists():
        return 1, f"找不到成片（{film}）：上次的結果與簽核都不算數。"
    if sha256_file(film) != data.get("film_sha256"):
        return 1, "成片內容跟上次 check 的不一樣（重出過）：上次的結果與簽核都不算數，請重跑 check。"
    got = [str(i.get("item")) if isinstance(i, dict) else "?" for i in data.get("items", [])]
    if sorted(got) != sorted(ORDER):
        return 1, f"上次的報告不完整（項目應為 {'、'.join(ORDER)} 各一次，實際是 {got}）：請重跑 check。"
    if any(i.get("auto_result") not in AUTO_STATES for i in data["items"]):
        return 1, "上次的報告裡有看不懂的結果：請重跑 check。"
    if any(i["auto_result"] != "待簽核" for i in data["items"] if i["item"] in HUMAN_ONLY):
        return 1, "上次的報告裡，只能由人簽核的項目被寫成別的結果：請重跑 check。"
    for i in data["items"]:
        if fingerprint(data["film_sha256"], i["item"], i.get("params", {})) != i["fingerprint"]:
            return 1, f"「{i['title']}」的工具版本或門檻跟上次 check 時不一樣：上次的結果與簽核都不算數，請重跑 check。"
    signoffs = load_signoffs(so)
    for i in data["items"]:
        i["result"], i["signoff"], i["stale_signoffs"] = apply_signoff(i["item"], i["auto_result"], i["fingerprint"], signoffs)
    data["rc"] = 1 if [i for i in data["items"] if i["result"] not in OK_STATES] else 0
    return data["rc"], None


# ---------- 主流程 ----------
def run_check(film, orient="auto", lufs=-16.0, tol=1.0, out=None, quiet=False):
    film = Path(film).resolve()
    d, md, js, so = out_paths(film, out)
    if not film.exists():
        print(f"找不到成片：{film}")
        return 2, None
    if not (math.isfinite(lufs) and math.isfinite(tol) and tol >= 0):
        print("--lufs、--tol 要是有限的數字，--tol 不能是負的。")
        return 2, None
    d.mkdir(parents=True, exist_ok=True)
    try:
        with Lock(d, film.stem):
            return _check_locked(film, orient, lufs, tol, d, md, js, so, quiet)
    except SignoffError as e:
        print(str(e))
        return 1, None


def _check_locked(film, orient, lufs, tol, d, md, js, so, quiet):
    film_sha = sha256_file(film)
    params = {"spec": {"orient": orient}, "loudness": {"target": lufs, "tol": tol}, "stutter": {"cut_diff": CUT_DIFF}, "playback": {}}
    raw = {}
    for item, fn in (("spec", lambda: check_spec(film, orient)), ("loudness", lambda: check_loudness(film, lufs, tol)),
                     ("stutter", lambda: check_stutter(film))):
        try:
            raw[item] = fn()
        except subprocess.TimeoutExpired:
            raw[item] = ("沒跑成功", "逾時", {})
        except Exception as e:  # noqa: BLE001
            raw[item] = ("沒跑成功", f"{type(e).__name__}: {e}", {})
    raw["playback"] = ("待簽核", "整片開聲音從頭看到尾，簽核時寫下看到的問題或「沒有」", {})
    # 檢查跑了一段時間：寫報告前再算一次成片雜湊。檢查途中成片被換掉（重新出片蓋過去）的話，剛才量的是哪一版說不準，
    # 不寫報告、不套用舊簽核，請人重跑
    if sha256_file(film) != film_sha:
        print("檢查途中成片的內容變了（被重新出片蓋過去？）：這次的結果不算數，沒有寫報告，請重跑 check。")
        return 1, None
    signoffs = load_signoffs(so)
    items = []
    for item in ORDER:
        res, summ, det = raw[item]
        fp = fingerprint(film_sha, item, params[item])
        res2, sig, stale = apply_signoff(item, res, fp, signoffs)
        items.append({"item": item, "title": TITLE[item], "applies": "必跑", "auto_result": res, "result": res2, "summary": summ,
                      "detail": det, "params": params[item], "fingerprint": fp, "signoff": sig, "stale_signoffs": stale})
    blocking = [x for x in items if x["result"] not in OK_STATES]
    rc = 1 if blocking else 0
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data = {"film": str(film), "film_sha256": film_sha, "checked_at": now, "preflight_version": VERSION, "rc": rc, "items": items,
            "not_integrated": [a for a, _ in NOT_INTEGRATED]}
    write_atomic(js, json.dumps(data, ensure_ascii=False, indent=1))
    write_atomic(md, render(data))
    if not quiet:
        print(render(data, short=True))
        print(f"\n報告：{md}")
    return rc, data


def render(data, short=False):
    it = data["items"]
    auto_bad = [x for x in it if x["result"] in ("不通過", "沒跑成功", "缺輸入")]
    wait = [x for x in it if x["result"] == "待簽核"]
    signed = [x for x in it if x["signoff"]]
    L = [f"# 交片前檢查：{Path(data['film']).name}", "",
         f"- 檢查時間 {data['checked_at']}｜preflight {data['preflight_version']}｜成片 SHA-256 `{data['film_sha256'][:16]}…`",
         *([f"- ⚠ 這份報告用的不是預設門檻：" + "；".join(f"{TITLE[x['item']]} {x.get('params')}" for x in it
                                              if x["item"] in DEFAULT_PARAMS and x.get("params") != DEFAULT_PARAMS[x["item"]])]
           if any(x["item"] in DEFAULT_PARAMS and x.get("params") != DEFAULT_PARAMS[x["item"]] for x in it) else []),
         "- **結論：" + ("這一版指定的檢查與簽核都完成了（回傳 0）。這只是成片層的輔助依據，不代表片子沒問題——下面「還沒收進來的必跑檢查」要另外跑。"
                       if data["rc"] == 0 else f"還不能交片（回傳 1）：{len(auto_bad)} 項自動異常、{len(wait)} 項待簽核、"
                       f"{sum(1 for x in it if x['result'] == '已簽核退回')} 項簽核退回。") + "**", "",
         "## 一、自動異常（要修）", ""]
    L += [f"- **{x['title']}**｜{x['result']}｜{x['summary']}" for x in auto_bad] or ["- 沒有"]
    L += ["", "## 二、待看、待簽核", ""]
    for x in wait:
        L.append(f"- **{x['title']}**｜{x['summary']}")
        if x["stale_signoffs"]:
            L.append(f"  - 之前有 {x['stale_signoffs']} 筆簽核，因為成片、工具或門檻變了已經失效，要重看。")
        L.append(f"  - 看完後：`python tools\\preflight.py sign \"{data['film']}\" {x['item']} --by <誰> --result pass|reject --note \"<看了什麼>\"`")
        if x["item"] == "stutter" and not short:
            L += [f"  - {tc(v['start'])}–{tc(v['end'])}　dup {v['dup']:.2f}　alt {v['alt']:.2f}" for v in x["detail"].get("intervals", [])]
    if not wait:
        L.append("- 沒有")
    L += ["", "## 三、人工結論（已簽核）", ""]
    L += [f"- **{x['title']}**｜{x['result']}｜{x['signoff']['by']}　{x['signoff']['time']}｜{x['signoff']['note']}" for x in signed] or ["- 還沒有"]
    L += ["", "## 全部項目", "", "| 項目 | 適用性 | 結果 | 摘要 |", "|:---|:---|:---|:---|"]
    L += [f"| {x['title']} | {x['applies']} | {x['result']} | {x['summary'].replace('|', '／')} |" for x in it]
    L += ["", "## 還沒收進來的必跑檢查（照 docs/04_自審清單.md 與各片自審清單另外跑）", ""]
    if short:
        L.append("- " + "、".join(a for a, _ in NOT_INTEGRATED))
    else:
        L += [f"- {a}：`{b}`" for a, b in NOT_INTEGRATED]
    return "\n".join(L) + "\n"


def run_sign(film, item, by, result, note, out=None):
    film = Path(film).resolve()
    d, md, js, so = out_paths(film, out)
    if item not in ORDER:
        print(f"沒有這個項目：{item}（有：{'、'.join(ORDER)}）")
        return 2
    if not note.strip() or not by.strip():
        print("簽核一定要寫 --by 和 --note（看了什麼、在哪幾秒、結論）")
        return 2
    if not js.exists():
        print("還沒跑過 check，先跑：preflight.py check <成片>")
        return 2
    try:
        with Lock(d, film.stem):
            data = json.loads(js.read_text(encoding="utf-8"))
            rc, msg = evaluate(film, data, so)          # 先確認成片、工具、門檻都跟上次 check 一樣
            if msg:
                print(msg)
                return 2
            x = next(i for i in data["items"] if i["item"] == item)
            if x["auto_result"] != "待簽核":
                print(f"「{x['title']}」的自動結果是「{x['auto_result']}」，不是要人簽核的項目；不通過／沒跑成功不能用簽核蓋過去。")
                return 2
            signoffs = load_signoffs(so)
            signoffs.append({"item": item, "result": result, "by": by, "note": note,
                             "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "fingerprint": x["fingerprint"]})
            write_atomic(so, json.dumps(signoffs, ensure_ascii=False, indent=1))   # 簽核檔先落地；報告之後寫壞了，status 也會照簽核檔重算
            rc, msg = evaluate(film, data, so)
            if msg:      # 簽核寫進去之後成片又被換掉（或工具被改了）：舊的結果不能再寫回報告，印原因就停
                print(msg)
                print("這筆簽核已記在簽核檔，但成片跟檢查時不一樣了，簽核不算數；請重跑 check。")
                return 1
            write_atomic(js, json.dumps(data, ensure_ascii=False, indent=1))
            write_atomic(md, render(data))
    except SignoffError as e:
        print(str(e))
        return 1
    print(f"已記錄：{x['title']}＝{'通過' if result == 'pass' else '退回'}（{by}）。目前回傳碼 {rc}。報告：{md}")
    return rc


def run_status(film, out=None):
    """不重跑自動檢查，但成片雜湊、工具指紋、簽核檔都重新核對；任何一樣對不上就不回 0。"""
    film = Path(film).resolve()
    d, md, js, so = out_paths(film, out)
    if not js.exists():
        print("還沒跑過 check。")
        return 2
    try:
        data = json.loads(js.read_text(encoding="utf-8"))
        rc, msg = evaluate(film, data, so)
    except SignoffError as e:
        print(str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"上次的報告讀不了（{js}）：{type(e).__name__} {e}。請重跑 check。")
        return 1
    if msg:
        print("⚠ " + msg)
        return 1
    print(render(data, short=True))
    return rc


# ---------- 自我測試 ----------
def selftest():
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="preflight_selftest_"))
    ok = True

    def mk(name, vf, af="volume=1", size="1920x1080", rate="24", audio=True, dur=6):
        p = tmp / name
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={dur}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-af", af]
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
        cmd += (["-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]) + [str(p)]
        r = subprocess.run(cmd, capture_output=True)
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]
        return p

    def expect(label, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(("  OK  " if good else "  FAIL") + f" {label}：{got}" + ("" if good else f"（應為 {want}）"))

    def res(data, item):
        return next(x["result"] for x in data["items"] if x["item"] == item)

    try:
        # 1 正常片：規格、響度通過；頓挫沒有可疑區段；整片實播待簽核 → rc 1；簽核後 rc 0
        good = mk("good.mp4", "null", "loudnorm=I=-16:TP=-2:LRA=7")
        rc, d = run_check(good, quiet=True)
        expect("正常片 規格", res(d, "spec"), "通過")
        expect("正常片 響度", res(d, "loudness"), "通過")
        expect("正常片 頓挫", res(d, "stutter"), "通過")
        expect("正常片 整片實播（還沒簽）", res(d, "playback"), "待簽核")
        expect("正常片 沒簽核的回傳碼", rc, 1)
        expect("簽核沒寫 note 被擋", run_sign(good, "playback", "測試", "pass", " "), 2)
        expect("自動通過的項目不能簽核", run_sign(good, "spec", "測試", "pass", "x"), 2)
        expect("簽核通過後的回傳碼", run_sign(good, "playback", "測試", "pass", "從頭看到尾，沒有問題"), 0)
        rc, d = run_check(good, quiet=True)
        expect("重跑 check 簽核還在", res(d, "playback"), "已簽核通過")
        # 2 成片重出（內容變了）→ 舊簽核失效
        shutil.copy(mk("good2.mp4", "hue=h=20", "loudnorm=I=-16:TP=-2:LRA=7"), good)
        expect("成片重出後 status 回傳碼", run_status(good), 1)
        rc, d = run_check(good, quiet=True)
        expect("成片重出後 整片實播回到", res(d, "playback"), "待簽核")
        expect("成片重出後 失效簽核數", next(x["stale_signoffs"] for x in d["items"] if x["item"] == "playback"), 1)
        expect("簽核退回的回傳碼", run_sign(good, "playback", "測試", "reject", "0:03 字幕壓到臉"), 1)
        # 3 頓挫片：每 4 格停一格 → 有可疑區段、待簽核；簽核後才通過
        st = mk("stutter.mp4", "select='mod(n\\,4)',setpts=N/18/TB,fps=24", "loudnorm=I=-16:TP=-2:LRA=7", dur=8)
        rc, d = run_check(st, quiet=True)
        expect("頓挫片 頓挫", res(d, "stutter"), "待簽核")
        expect("頓挫片 有列出可疑區段", len(next(x["detail"]["intervals"] for x in d["items"] if x["item"] == "stutter")) > 0, True)
        # 4 規格不對、太大聲、沒聲音
        bad = mk("bad.mp4", "null", "volume=1", size="1280x720", rate="30")
        rc, d = run_check(bad, quiet=True)
        expect("1280x720/30fps 規格", res(d, "spec"), "不通過")
        expect("沒壓響度的 sine 響度", res(d, "loudness"), "不通過")
        expect("不通過的項目不能用簽核蓋過", run_sign(bad, "spec", "測試", "pass", "x"), 2)
        mute = mk("mute.mp4", "null", audio=False)
        rc, d = run_check(mute, quiet=True)
        expect("沒聲音軌 規格", res(d, "spec"), "不通過")
        expect("沒聲音軌 響度", res(d, "loudness"), "沒跑成功")
        # 5 壞檔 → 沒跑成功，不能當通過
        junk = tmp / "junk.mp4"
        junk.write_bytes(b"not a video" * 100)
        rc, d = run_check(junk, quiet=True)
        expect("壞檔 規格", res(d, "spec"), "沒跑成功")
        expect("壞檔 頓挫", res(d, "stutter"), "沒跑成功")
        expect("壞檔 回傳碼", rc, 1)
        # 6 只簽整片實播還是被頓挫擋住；兩項都簽才回 0
        expect("頓挫片 只簽整片實播", run_sign(st, "playback", "測試", "pass", "看過，沒有其他問題"), 1)
        expect("頓挫片 兩項都簽", run_sign(st, "stutter", "測試", "pass", "0:00–0:08 是測試片故意做的頓挫"), 0)
        expect("頓挫片 status", run_status(st), 0)
        # 7 放行之後：簽核檔多了一筆退回（模擬「退回已寫入、報告來不及更新就中斷」）→ status 不能回 0
        d7, md7, js7, so7 = out_paths(st.resolve(), None)
        sg = json.loads(so7.read_text(encoding="utf-8"))
        so7.write_text(json.dumps(sg + [dict(sg[-1], result="reject", note="模擬中斷")], ensure_ascii=False), encoding="utf-8")
        expect("退回已寫入但報告沒更新 status", run_status(st), 1)
        so7.write_text(json.dumps(sg, ensure_ascii=False), encoding="utf-8")
        expect("還原後 status", run_status(st), 0)
        # 8 放行之後：簽核檔壞掉 → 報錯，不能當成沒簽或已簽
        so7.write_text("{壞掉", encoding="utf-8")
        expect("簽核檔損壞 status", run_status(st), 1)
        expect("簽核檔損壞 check", run_check(st, quiet=True)[0], 1)
        so7.write_text(json.dumps(sg, ensure_ascii=False), encoding="utf-8")
        # 9 放行之後：工具改版 → 舊結果與簽核不算數
        global VERSION
        old = VERSION
        VERSION = old + "-test"
        expect("工具改版後 status", run_status(st), 1)
        expect("工具改版後 sign 被擋", run_sign(st, "playback", "測試", "pass", "x"), 2)
        rc, d = run_check(st, quiet=True)
        expect("工具改版後重跑 整片實播回到", res(d, "playback"), "待簽核")
        VERSION = old
        # 10 放行之後：成片被刪 → status 不能回 0
        rc, d = run_check(st, quiet=True)
        expect("改回版本後簽核恢復", rc, 0)
        st.unlink()
        expect("成片刪掉後 status", run_status(st), 1)
        # 10b 報告被動過：項目清空、漏掉待簽項、項目重複 → status 都不能回 0
        rc, d = run_check(good, quiet=True)
        run_sign(good, "playback", "測試", "pass", "看過")
        d10, md10, js10, so10 = out_paths(good.resolve(), None)
        full = json.loads(js10.read_text(encoding="utf-8"))
        expect("完整報告 status", run_status(good), 0)
        for label, items in (("項目清空", []), ("漏掉待簽項", [i for i in full["items"] if i["item"] != "playback"]),
                             ("項目重複", full["items"] + [full["items"][0]])):
            js10.write_text(json.dumps(dict(full, items=items), ensure_ascii=False), encoding="utf-8")
            expect(f"報告{label} status", run_status(good), 1)
        tam = json.loads(json.dumps(full))
        next(i for i in tam["items"] if i["item"] == "playback")["auto_result"] = "通過"
        js10.write_text(json.dumps(tam, ensure_ascii=False), encoding="utf-8")
        so10.unlink()
        expect("整片實播被改成自動通過、又沒有簽核 status", run_status(good), 1)
        tam2 = json.loads(json.dumps(full))
        del tam2["items"][0]["item"]
        js10.write_text(json.dumps(tam2, ensure_ascii=False), encoding="utf-8")
        expect("項目缺 item 鍵 status", run_status(good), 1)
        old_fp = json.loads(json.dumps(full))
        for i in old_fp["items"]:
            i["fingerprint"] = fingerprint(old_fp["film_sha256"], i["item"], i["params"]).replace("a", "b")   # 模擬舊版工具寫的報告
        js10.write_text(json.dumps(old_fp, ensure_ascii=False), encoding="utf-8")
        expect("舊版工具留下的報告 status", run_status(good), 1)
        js10.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
        # 10c 非預設門檻的報告要標出來
        rc, d = run_check(good, tol=5, quiet=True)
        expect("非預設門檻有標示", "不是預設門檻" in render(d), True)
        rc, d = run_check(good, quiet=True)
        expect("預設門檻不標示", "不是預設門檻" in render(d), False)
        # 11 剪接太密：每個視窗都含剪接點 → 沒跑成功，不能當通過
        dense = mk("dense.mp4", "geq=lum='255*mod(floor(N/8)\\,2)':cb=128:cr=128", "loudnorm=I=-16:TP=-2:LRA=7", size="320x180")
        rc, d = run_check(dense, quiet=True)
        expect("每 8 格一個剪接 頓挫", res(d, "stutter"), "沒跑成功")
        # 11b 前 2 秒剪接很密、後面正常 → 有 1 秒以上沒檢到 → 不能自動通過，要人看
        half = mk("half.mp4", "geq=lum='if(lt(N\\,48)\\,255*mod(floor(N/8)\\,2)\\,128+100*sin(N/7+X/40))':cb=128:cr=128",
                  "loudnorm=I=-16:TP=-2:LRA=7", size="320x180", dur=8)
        rc, d = run_check(half, quiet=True)
        expect("前段剪接太密 頓挫", res(d, "stutter"), "待簽核")
        expect("前段剪接太密 有列沒檢到的區段", len(next(x["detail"]["unchecked"] for x in d["items"] if x["item"] == "stutter")) > 0, True)
        # 12 門檻不是有限數字
        expect("--tol nan 被擋", run_check(good, tol=float("nan"), quiet=True)[0], 2)
        expect("--tol inf 被擋", run_check(good, tol=float("inf"), quiet=True)[0], 2)
        expect("--tol 負數被擋", run_check(good, tol=-1, quiet=True)[0], 2)
        # 13 響度判定：響度合格但真峰值超過 0 → 不通過；量到 nan → 不通過
        expect("響度 -16.0、真峰值 +0.3", judge_loudness(-16.0, 0.3, -16, 1)[0], "不通過")
        expect("響度 -16.0、真峰值 -1.0", judge_loudness(-16.0, -1.0, -16, 1)[0], "通過")
        expect("響度 -17.1、真峰值 -1.0", judge_loudness(-17.1, -1.0, -16, 1)[0], "不通過")
        expect("響度 nan", judge_loudness(float("nan"), -1.0, -16, 1)[0], "不通過")
        expect("靜音（真峰值 -inf、響度 -70）", judge_loudness(-70.0, float("-inf"), -16, 1)[0], "不通過")
        # 13b 檢查途中成片被換掉：不寫報告、回傳 1（把雜湊函式換成「第二次回不同的值」來模擬）
        real_sha, calls = sha256_file, []
        globals()["sha256_file"] = lambda p, buf=1 << 22: (calls.append(1), real_sha(p, buf) if len(calls) == 1 else "changed")[1]
        try:
            rc, d = run_check(good, out=tmp / "swap", quiet=True)
        finally:
            globals()["sha256_file"] = real_sha
        expect("檢查途中成片被換掉 回傳碼", rc, 1)
        expect("檢查途中成片被換掉 沒有寫報告", (tmp / "swap" / "good.json").exists(), False)
        # 13b2 已經簽核通過的成片，改簽「退回」的那一刻成片被換掉：回傳 1，而且不能把舊的「通過」寫回報告
        sw = mk("signswap.mp4", "null", "loudnorm=I=-16:TP=-2:LRA=7")
        run_check(sw, quiet=True)
        expect("換片簽核測試：先簽通過", run_sign(sw, "playback", "測試", "pass", "看過"), 0)
        sw_js = out_paths(sw.resolve(), None)[2]
        before = sw_js.read_text(encoding="utf-8")
        calls2 = []

        def fake_sha(p, buf=1 << 22):      # 只有「成片」第二次以後算出來不一樣；其他檔（例 stutter.py）照常算
            if Path(p).resolve() != sw.resolve():
                return real_sha(p, buf)
            calls2.append(1)
            return real_sha(p, buf) if len(calls2) == 1 else "changed"
        globals()["sha256_file"] = fake_sha
        real_write, written = write_atomic, []
        globals()["write_atomic"] = lambda p, text: (written.append(Path(p).name), real_write(p, text))[1]
        try:
            rc = run_sign(sw, "playback", "測試", "reject", "這時成片被換掉了")
        finally:
            globals()["sha256_file"] = real_sha
            globals()["write_atomic"] = real_write
        expect("改簽退回時成片被換掉 回傳碼", rc, 1)
        expect("改簽退回時成片被換掉 只寫了簽核檔（報告的 json、md 都沒寫）", written, ["signswap.signoff.json"])
        expect("改簽退回時成片被換掉 報告沒有被改寫", sw_js.read_text(encoding="utf-8") == before, True)
        expect("之後 status（簽核檔裡已有退回）", run_status(sw), 1)
        # 13c 兩個程序搶同一支成片的鎖：另一個程序持鎖時這邊拿不到；那個程序被砍掉後就拿得到
        global LOCK_WAIT
        old_wait, LOCK_WAIT = LOCK_WAIT, 2
        ld = tmp / "locktest"
        ld.mkdir()
        code = ("import sys, time; sys.path.insert(0, sys.argv[2]); import preflight; from pathlib import Path; "
                "L = preflight.Lock(Path(sys.argv[1]), 'film'); L.__enter__(); print('locked', flush=True); time.sleep(120)")
        holder = subprocess.Popen([sys.executable, "-c", code, str(ld), str(HERE)], stdout=subprocess.PIPE)
        try:
            holder.stdout.readline()
            try:
                with Lock(ld, "film"):
                    got = True
            except SignoffError:
                got = False
            expect("別的程序持鎖時拿不到鎖", got, False)
            holder.kill()
            holder.wait()
            time.sleep(0.5)
            try:
                with Lock(ld, "film"):
                    got = True
            except SignoffError:
                got = False
            expect("持鎖的程序被砍掉後拿得到鎖", got, True)
        finally:
            holder.kill()
            LOCK_WAIT = old_wait
        # 14 直式
        pt = mk("portrait.mp4", "null", "loudnorm=I=-16:TP=-2:LRA=7", size="1088x1904")
        rc, d = run_check(pt, quiet=True)
        expect("直式 1088x1904 規格", res(d, "spec"), "通過")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest " + ("全部通過" if ok else "有失敗"))
    return 0 if ok else 1


def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="交片前檢查總表（成片層）")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("film")
    c.add_argument("--orient", default="auto", choices=["auto", "landscape", "portrait"])
    c.add_argument("--lufs", type=float, default=-16.0)
    c.add_argument("--tol", type=float, default=1.0)
    c.add_argument("--out")
    s = sp.add_parser("sign")
    s.add_argument("film")
    s.add_argument("item")
    s.add_argument("--by", required=True)
    s.add_argument("--result", required=True, choices=["pass", "reject"])
    s.add_argument("--note", required=True)
    s.add_argument("--out")
    t = sp.add_parser("status")
    t.add_argument("film")
    t.add_argument("--out")
    sp.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "check":
        return run_check(a.film, a.orient, a.lufs, a.tol, a.out)[0]
    if a.cmd == "sign":
        return run_sign(a.film, a.item, a.by, a.result, a.note, a.out)
    if a.cmd == "status":
        return run_status(a.film, a.out)
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
