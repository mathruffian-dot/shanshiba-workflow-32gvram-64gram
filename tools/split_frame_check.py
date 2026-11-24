"""首幀「拼成兩格」檢查（2026-11-18 作者實測：提示詞寫了前後兩個時間點的動作，例如「拍攝中，然後放下相機」，Image 2.5 畫成上下兩格的對照圖，H3 照著拍成分割畫面）。
做法：找畫面中段（35%–65%）最強的一條水平／垂直接縫，跟整張圖的中位數比；比值 ≥ 8 幾乎一定是拼圖（正常照片 ≤ 5）。
用法：python split_frame_check.py <首幀資料夾或圖檔...> [--thr 8]
回傳碼 1＝有疑似拼圖的首幀。修法：首幀提示詞只寫「動作開始前」的一個姿勢，加「One single continuous photograph, NOT a split image」，重生首幀再拍。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def seam(p):
    a = np.asarray(Image.open(p).convert("L").resize((672, 384)), np.float32)
    out = []
    for axis, n in ((0, 384), (1, 672)):
        d = np.abs(np.diff(a, axis=axis)).mean(1 - axis)
        lo, hi = int(n * 0.35), int(n * 0.65)
        i = int(d[lo:hi].argmax()) + lo
        out.append((float(d[i] / (np.median(d) + 1e-3)), "水平" if axis == 0 else "垂直", round(i / n, 2)))
    return max(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="首幀拼成兩格檢查")
    ap.add_argument("paths", nargs="+", help="首幀資料夾或圖檔")
    ap.add_argument("--thr", type=float, default=8.0)
    a = ap.parse_args()
    if not (0 < a.thr < 1000):      # nan、inf、負數都會讓門檻比較失效
        ap.error("--thr 要是正的有限數字")
    thr, files, err = a.thr, [], []
    for x in a.paths:
        q = Path(x)
        if q.is_dir():
            got = sorted(f for f in q.glob("*.png") if not f.name.startswith("_")) + sorted(q.glob("*.jpg"))
            files += got
            if not got:
                err.append(f"{x}（資料夾裡沒有 png／jpg）")
        elif q.is_file():
            files.append(q)
        else:
            err.append(f"{x}（找不到）")
    bad = []
    for f in files:
        try:
            r, kind, pos = seam(f)
        except Exception as e:  # noqa: BLE001  圖讀不了：不能當成通過
            err.append(f"{f.name}（{type(e).__name__}）")
            continue
        if r >= thr:
            bad.append(f); print(f"疑似拼圖  {f.name}  {kind}接縫 位置 {pos:.0%}  比值 {r:.1f}")
    print(f"{len(files)} 張，疑似拼圖 {len(bad)} 張" + (f"（⚠ 另有 {len(err)} 個沒檢查到，這個數字不完整）" if err else ""))
    if err:
        print(f"ERROR（沒檢查到，不算通過）：{len(err)} {err}")
        sys.exit(2)
    sys.exit(1 if bad else 0)
