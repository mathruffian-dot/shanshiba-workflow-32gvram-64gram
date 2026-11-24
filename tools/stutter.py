"""H3 頓挫（看起來像畫面震動）檢查與修補。現象：成片裡動作大的鏡頭看起來像畫面在震。原因：
H3 有時每 4 格有一格幾乎跟前一格一樣（停一下再追上，6Hz 頓挫），動作大的鏡看起來就像在震。4 步 DMAD 與 14 步都會有，換 seed 也常有，
所以用後製修：把停住的格換成前後兩格的光流中間格（OpenCV DIS，雙向各走一半再平均），聲音不動。

用法（Voice venv）：
  python stutter.py check a.mp4 b.mp4 ...        逐秒窗找最差一段；有動作（其他格平均差 ≥2）且 dup<0.5 或 alt>0.5 → STUTTER
  python stutter.py fix in.mp4 out.mp4            修好輸出（不改原檔），之後再 check 一次確認
判讀：dup＝停格相位的跳動 / 其他格（越小越頓）；alt＝一格大一格小的交替程度。
2026-11-17 加「來回抖」（修完頓挫仍在抖的鏡頭：鏡頭其實沒動，是人走動時身體一格往前一格往後）：
jitter p90 > 0.3 → SHAKE。SHAKE 用 fix 修不掉，換 seed（14 步較少）再 fix＋check。"""
import os, subprocess, sys
from pathlib import Path

import numpy as np


class DecodeError(Exception):
    """影片解不出畫面（檔案不存在、壞檔、ffmpeg 失敗、太短）。不能當成「沒有頓挫」。"""


def _probe(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def _decode(p, vf, frame_bytes):
    """ffmpeg 解成灰階原始畫面。回傳碼不是 0（檔案不存在、壞檔、解到一半失敗）一律當失敗，不拿殘缺的畫面去評分。"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(p), "-vf", vf, "-f", "rawvideo", "-"], capture_output=True)   # -xerror：中間有壞格也算失敗
    if r.returncode != 0:
        raise DecodeError("ffmpeg 解碼失敗：" + r.stderr.decode("utf-8", "replace").strip()[-160:])
    return r.stdout[:len(r.stdout) // frame_bytes * frame_bytes]


def _diffs(p):
    raw = _decode(p, "fps=24,scale=336:192,format=gray", 336 * 192)
    f = np.frombuffer(raw, np.uint8).reshape(-1, 192, 336).astype(float)
    return np.abs(np.diff(f, axis=0)).mean((1, 2))


def _score(d):
    best = (9.0, 0.0, 0)
    for ph in range(4):
        idx = np.arange(ph, len(d), 4); oth = np.setdiff1d(np.arange(len(d)), idx)
        act = d[oth].mean(); best = min(best, (d[idx].mean() / max(act, 1e-6), act, ph))
    return best[0], best[1], np.abs(np.diff(d)).mean() / max(d.mean(), 1e-6), best[2]


def check(p):
    d = _diffs(p); worst = None
    if len(d) < 12:      # 一個視窗至少要 12 個相鄰格差（13 格）；更短的片一個視窗都評不到
        raise DecodeError(f"只解出 {len(d) + 1 if len(d) else 0} 格，不到 13 格，沒有可以評分的視窗")
    starts = list(range(0, max(1, len(d) - 23), 6))
    if len(d) > 24 and starts[-1] != len(d) - 24:
        starts.append(len(d) - 24)          # 補評貼齊片尾的最後一個視窗（每次跳 6 格，片尾最多會漏 5 格）
    for s0 in starts:
        w = d[s0:s0 + 24]
        if len(w) < 12:
            continue
        dup, act, alt, _ = _score(w)
        if act < 2:
            continue
        bad = max(0.5 - dup, 0) * 2 + max(alt - 0.5, 0) * 2
        if worst is None or bad > worst[0]:
            worst = (bad, dup, act, alt, s0 / 24)
    if worst is None:
        return False, "no motion"
    flag = worst[1] < 0.5 or worst[3] > 0.5
    return flag, f"worst@{worst[4]:.1f}s dup {worst[1]:.2f} motion {worst[2]:.1f} alt {worst[3]:.2f}"


def shake(p):
    """人／物體前後來回抖（下一格的光流方向跟上一格相反）。逐格算「有在動的像素裡反向的比例」，取第 90 百分位。
    實測：正常鏡 ≤0.03；來回抖的鏡頭各 seed 0.6–0.98（抖在人走動的那 1.5 秒）。"""
    import cv2
    raw = _decode(p, "fps=24,scale=448:256,format=gray", 448 * 256)
    f = np.frombuffer(raw, np.uint8).reshape(-1, 256, 448)
    if len(f) < 4:
        return False, "jitter n/a (too short)"
    fl = np.array([cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0) for a, b in zip(f[:-1], f[1:])])
    mag = np.linalg.norm(fl, axis=3); both = (mag[1:] > 0.4) & (mag[:-1] > 0.4)
    rev = (((fl[1:] * fl[:-1]).sum(3) < 0) & both).sum((1, 2)) / np.maximum(both.sum((1, 2)), 1)
    p90 = float(np.percentile(rev, 90)); bad = [round((i + 1) / 24, 1) for i, v in enumerate(rev) if v > 0.5]
    return p90 > 0.3, f"jitter p90 {p90:.2f}" + (f" at {bad[0]}–{bad[-1]}s" if bad else "")


def fix(src, dst):
    import cv2
    try:
        W, H = _probe(src)
    except Exception:  # noqa: BLE001
        raise SystemExit(f"stutter.py fix：讀不到這支影片（{src}）")
    fps = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate", "-of", "csv=p=0",
                          str(src)], capture_output=True, text=True).stdout.strip()
    if fps != "24/1,24/1":       # 標稱與平均幀率都要是 24/1；平均不是 24＝可變幀率或掉格的檔
        raise SystemExit(f"stutter.py fix 只支援固定 24 fps 的影片（這支的標稱,平均幀率是 {fps or '讀不到'}）：直接補格會變速、聲畫不同步。")
    r0 = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    raw = r0.stdout
    if r0.returncode != 0 or len(raw) < W * H * 3 * 13 or len(raw) % (W * H * 3):
        raise SystemExit(f"stutter.py fix：解碼失敗或畫面不完整（{src}）")
    f = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).copy()
    g = np.stack([cv2.resize(cv2.cvtColor(x, cv2.COLOR_RGB2GRAY), (336, 192)) for x in f]).astype(float)
    d = np.abs(np.diff(g, axis=0)).mean((1, 2))
    ph = _score(d)[3]
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    n = 0
    for i in range(ph, len(d) - 1, 4):
        nb = np.r_[d[max(0, i - 3):i], d[i + 1:i + 4]]
        j = i + 1
        if nb.mean() >= 1.5 and d[i] < 0.6 * nb.mean() and j + 1 < len(f):
            a, b = f[j - 1], f[j + 1]
            ga, gb = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
            fab, fba = dis.calc(ga, gb, None), dis.calc(gb, ga, None)
            wa = cv2.remap(a, gx - 0.5 * fab[..., 0], gy - 0.5 * fab[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            wb = cv2.remap(b, gx - 0.5 * fba[..., 0], gy - 0.5 * fba[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            f[j] = ((wa.astype(np.uint16) + wb) // 2).astype(np.uint8); n += 1
    dst = Path(dst); dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.stem}_stutterfix_{os.getpid()}.v.tmp.mp4")      # 只有畫面
    out = dst.with_name(f"{dst.stem}_stutterfix_{os.getpid()}.out.tmp.mp4")    # 畫面＋原聲音，完成後才換成目的檔
    try:
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "24", "-i", "-",
                              "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
        try:
            p.stdin.write(f.tobytes()); p.stdin.close()
        except OSError:          # 編碼器中途死掉（斷管）
            pass
        if p.wait() != 0:
            raise SystemExit("stutter.py fix：ffmpeg 編碼失敗，沒有輸出，目的檔沒有動")
        m = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c", "copy", str(out)])
        if m.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
            raise SystemExit("stutter.py fix：封裝失敗，沒有輸出，目的檔沒有動")
        os.replace(out, dst)     # 全部成功才換掉目的檔
    finally:
        tmp.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    return n


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd not in ("check", "fix") or (cmd == "check" and not args) or (cmd == "fix" and len(args) != 2):
        print("用法：stutter.py check <影片...>　或　stutter.py fix <輸入.mp4> <輸出.mp4>")
        sys.exit(2)
    if cmd == "check":
        bad, shk, err = [], [], []
        for a in args:
            try:
                flag, msg = check(a); sf, sm = shake(a)
            except Exception as e:  # noqa: BLE001  解不出畫面、檔案不存在：不能當成通過
                print(f"{a}  ERROR 沒檢查到：{type(e).__name__} {e}", flush=True)
                err.append(a)
                continue
            print(f"{a}  {msg}  {'STUTTER' if flag else ''}  | {sm}  {'SHAKE' if sf else ''}", flush=True)
            if flag:
                bad.append(a)
            if sf:
                shk.append(a)
        part = f"（⚠ 另有 {len(err)} 支沒檢查到，這個數字不完整）" if err else ""
        print("STUTTER:", len(bad), bad, part)
        print("SHAKE:", len(shk), shk, "（換 seed 或換鏡，fix 修不掉）" if shk else "", part)
        if err:
            print("ERROR（沒檢查到，不算通過）:", len(err), err)
            sys.exit(2)
        sys.exit(1 if bad or shk else 0)      # 回傳碼：0＝全部沒問題；1＝有 STUTTER 或 SHAKE；2＝有影片沒檢查到
    elif cmd == "fix":
        print("fixed", fix(args[0], args[1]), "frames ->", args[1])
