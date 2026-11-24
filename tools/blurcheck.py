"""動作糊邊檢查：有動作的片段，人物的手和身體邊緣整個糊掉（例：觀眾舉手的鏡頭）。審出來就要重拍。
H3 DMAD 4 步在大動作的地方常把手、身體邊緣畫成一團糊。

做法：每一格找「正在動的區域」（跟前兩格比差很多的地方；跟前一格的差只用來補判「其實有在動卻量不到」），比它的銳利度跟同一格「沒在動的區域」的銳利度：
  銳利度＝|Laplacian| 平均 ÷ |Sobel 梯度| 平均（有邊但沒有細節＝糊）；比值 ratio＝動的區域 ÷ 不動的區域。
  正常的動作只會比靜止區稍低；糊掉時會掉很多。每鏡取最糟的 10%（p10）跟平均。

用法（Voice venv）：
  python blurcheck.py a.mp4 b.mp4 ...            每支印 p10 ratio、動態面積；p10 < THR 判 BLUR
  python blurcheck.py --clips <out 資料夾> [鏡號 ...]   掃 <out>/h3/<鏡>/clip.mp4
  python blurcheck.py --sheet out.jpg a.mp4 ...   另外輸出每支最糊那一格的總表（左上角標鏡號與 p10）方便人看
門檻 THR 預設 0.90（環境變數 BLUR_THR）：作者實測被指出糊掉的三個鏡頭（DMAD 4 步）p10 0.75–0.80，正常鏡 ≥ 0.95。
⚠ 抓不到「半透明殘影」（邊緣仍銳利；作者實測一個人群伸手的鏡頭 p10 1.04 過關）→ 群眾伸手鏡改靜態或放大逐格人看。
動態面積 < 1.5% 的格不算（幾乎沒動）；整個畫面都在動（> 60%，例：觀眾大全景）時不動區太少，改跟第 0 格同一區域比。"""
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

THR = float(os.environ.get("BLUR_THR", "0.90"))
if not (0 < THR < 10):      # nan、inf、負數都會讓門檻比較失效
    print(f"BLUR_THR 要是 0–10 之間的數字（現在是 {os.environ.get('BLUR_THR')}）")
    sys.exit(2)
W, H = 640, 360


def frames(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(p), "-vf", f"fps=24,scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)      # -xerror：中間有壞格也算失敗
    if r.returncode != 0:      # 檔案不存在、壞檔、解到一半失敗：不拿殘缺的畫面去評分
        raise RuntimeError("ffmpeg 解碼失敗：" + r.stderr.decode("utf-8", "replace").strip()[-160:])
    raw = r.stdout
    F = np.frombuffer(raw[:len(raw) // (W * H) * (W * H)], np.uint8).reshape(-1, H, W)
    if len(F) < 3:
        raise RuntimeError(f"解不出畫面（只有 {len(F)} 格）")
    return F


def sharp(lap, grd, m):
    g = grd[m].mean()
    return lap[m].mean() / (g + 1e-6) if g > 2 else np.nan


def scan(p):
    F = frames(p)
    if len(F) < 3:
        return dict(p10=np.nan, mean=np.nan, area=0.0, worst=None, n=0)
    rows, moving, unmeasured = [], 0, 0
    k = np.ones((9, 9), np.uint8)

    def lg(a):
        gx, gy = cv2.Sobel(a, cv2.CV_32F, 1, 0), cv2.Sobel(a, cv2.CV_32F, 0, 1)
        return np.abs(cv2.Laplacian(a, cv2.CV_32F, ksize=3)), np.sqrt(gx * gx + gy * gy)
    lap0, grd0 = lg(F[0].astype(np.float32))
    for t in range(2, len(F)):
        a, b = F[t].astype(np.float32), F[t - 2].astype(np.float32)
        mv = cv2.dilate((np.abs(a - b) > 10).astype(np.uint8), k) > 0
        area = mv.mean()
        if area < 0.015:
            # 跟前兩格比看不出動作，但跟前一格比有在動（例：兩種畫面一格一格交替）→ 記成「有動作但量不到」，不能當靜止鏡
            if (np.abs(a - F[t - 1].astype(np.float32)) > 10).mean() >= 0.015:
                unmeasured += 1
            continue
        moving += 1
        lap, grd = lg(a)
        ref = sharp(lap, grd, ~mv) if area <= 0.6 else sharp(lap0, grd0, mv)
        r = sharp(lap, grd, mv) / (ref + 1e-6)
        if np.isfinite(r):
            rows.append((t, r, area))
    if unmeasured > max(2, 0.2 * (len(F) - 2)):      # 兩成以上的格是「相鄰格在動、隔一格卻一樣」：這種片這支工具量不準
        raise RuntimeError(f"有 {unmeasured} 格只有相鄰格在動（畫面一格一格交替），這支工具量不到")
    tot = moving + unmeasured      # 有在動的格＝隔一格比看得出動作的，加上只有相鄰格看得出動作的
    if tot >= 5 and len(rows) < 0.5 * tot:      # 算得出比值的不到一半：量測覆蓋不足，剩下幾格的結果不能代表整支
        raise RuntimeError(f"{tot} 格在動，只有 {len(rows)} 格算得出銳利度比值（不到一半），量測不足")
    if not rows:
        if moving:      # 有在動的格，卻沒有一格算得出比值（整片太平、沒有邊可比）：這不是「沒問題」，是量不到
            raise RuntimeError(f"有 {moving} 格在動，但算不出任何有效的銳利度比值")
        return dict(p10=np.nan, mean=np.nan, area=0.0, worst=None, n=0)      # 靜止鏡：沒有動作，不判
    r = np.array([x[1] for x in rows])
    w = rows[int(np.argmin(r))]
    return dict(p10=float(np.percentile(r, 10)), mean=float(r.mean()), area=float(np.mean([x[2] for x in rows])), worst=w[0], n=len(rows), moving=moving, unmeasured=unmeasured)


def main():
    a = sys.argv[1:]
    sheet = None
    if a and a[0] == "--sheet":
        sheet, a = a[1], a[2:]
    if a and a[0] == "--clips":
        base = Path(a[1]) / "h3"
        skipped = []
        if a[2:]:
            ids = a[2:]                                   # 指名的鏡：沒有 clip.mp4 會在下面標 ERROR
        else:
            dirs = sorted(q.name for q in base.iterdir() if q.is_dir()) if base.is_dir() else []
            ids = [i for i in dirs if (base / i / "clip.mp4").exists()]
            skipped = [i for i in dirs if i not in ids]   # 沒指名時：沒有 clip.mp4 的鏡資料夾（生成失敗、舊資料夾）列出來給人看，不算錯
        paths = [base / i / "clip.mp4" for i in ids]
    else:
        paths = [Path(x) for x in a]
    bad, tiles, err = [], [], []
    skipped = locals().get("skipped", [])
    for p in paths:
        try:
            r = scan(p)
        except Exception as e:  # noqa: BLE001  解不出畫面、檔案不存在：不能當成通過
            print(f"{p}  ERROR 沒檢查到：{type(e).__name__} {e}", flush=True)
            err.append(str(p))
            continue
        flag = "BLUR" if np.isfinite(r["p10"]) and r["p10"] < THR else ""
        if flag:
            bad.append(str(p))
        print(f"{p}  p10 {r['p10']:.2f}  mean {r['mean']:.2f}  moving {r['area'] * 100:.0f}%  frames {r['n']}  worst@{(r['worst'] or 0) / 24:.1f}s  {flag}",
              flush=True)
        if sheet and r["worst"] is not None:
            cap = cv2.VideoCapture(str(p)); cap.set(cv2.CAP_PROP_POS_FRAMES, r["worst"]); ok, im = cap.read()
            if ok:
                im = cv2.resize(im, (480, 270)); cv2.putText(im, f"{p.parent.name} {r['p10']:.2f}", (8, 24), 0, 0.7, (0, 255, 255), 2)
                tiles.append(im)
    if sheet and tiles:
        while len(tiles) % 4:
            tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(sheet, np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]))
    print(f"BLUR（p10 < {THR}）：{len(bad)} {bad}" + (f"（⚠ 另有 {len(err)} 支沒檢查到，這個數字不完整）" if err else ""))
    if skipped:
        print(f"沒有 clip.mp4、沒掃的鏡資料夾：{len(skipped)} {skipped}（確認這些鏡沒有用在成片裡）")
    if not paths:
        print("ERROR：一支影片都沒掃到（路徑不對，或資料夾底下沒有 h3/<鏡>/）")
        sys.exit(2)
    if err:
        print(f"ERROR（沒檢查到，不算通過）：{len(err)} {err}")
        sys.exit(2)
    sys.exit(1 if bad else 0)      # 回傳碼：0＝全部沒問題；1＝有 BLUR；2＝有影片沒檢查到


if __name__ == "__main__":
    main()
