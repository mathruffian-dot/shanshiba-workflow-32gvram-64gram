"""中文配音「對照標準台灣國語」腔調審核 — 2026-10-04 建立。
pron_check.py 只看每字聲調的升降方向，抓不到「方向對但高低／力道不像台灣國語」的腔調（使用者聽到的港腔）。
這支把候選配音和一段「標準台灣國語參考音」（同一句台詞，例如 zh-TW 標準語音念的）逐字對齊後，比對每個字的音高曲線形狀：

  1. 兩段音檔都用 MMS_FA 逐字對齊（pron_check.align）。
  2. 每段各自換算半音（相對前後 3 字的區域中位數，抵消音域與整句下傾），每字取 10 點曲線。
  3. 逐字距離 = 兩條曲線的 RMS 差（半音）；另比對字長比例（念太急或拖太長）。
  4. 距離 > 門檻 的字標為「腔調偏」，門檻用「兩個台灣口音之間」的自然差距校準（本人真實錄音 vs 標準語音）。

用法（Voice venv）：
  python C:\\AI\\tools\\pron_compare.py <候選.wav> <參考.wav> "台詞"     → 每字距離、偏掉的字、整句分數
  from pron_compare import compare
參考音不放進影片，只當「答案卷」。"""
import sys
import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from pron_check import expected, align, f0_track  # noqa: E402

THRESH = 3.0      # 半音；校準後更新（見 C:\AI\tools\README.md 發音審核段）


def contours(path, base):
    import soundfile as sf, librosa
    x, sr = sf.read(str(path), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
    x16 = librosa.resample(x, orig_sr=sr, target_sr=16000) if sr != 16000 else x
    spans = align(x16, base); t, f = f0_track(path); v = f > 0
    st = np.full_like(f, np.nan); st[v] = 12 * np.log2(f[v] / np.median(f[v]))
    cen = [np.nanmedian(st[(t >= a) & (t <= b) & v]) if ((t >= a) & (t <= b) & v).sum() else np.nan for a, b in spans]
    out = []
    for i, (a, b) in enumerate(spans):
        ref = np.nanmedian([c for c in cen[max(0, i - 3):i + 4] if not np.isnan(c)] or [0])
        pad = (b - a) * 0.06; sel = (t >= a + pad) & (t <= b - pad) & v
        if sel.sum() < 3: sel = (t >= a) & (t <= b) & v          # 短字（如「急」）不要因為切頭尾而被跳過
        y = st[sel] - ref
        out.append((np.interp(np.linspace(0, 1, 10), np.linspace(0, 1, len(y)), y) if len(y) >= 3 else None, b - a))
    return out


def compare(cand, ref, text, thresh=THRESH):
    chars, base, tones, sur = expected(text)
    C, R = contours(cand, base), contours(ref, base)
    tc = sum(d for _, d in C) or 1; tr = sum(d for _, d in R) or 1
    rows, dists = [], []
    for ch, b, tn, (cc, dc), (rc, dr) in zip(chars, base, sur, C, R):
        if tn == 5 or cc is None or rc is None:
            rows.append(dict(char=ch, tone=tn, dist=None, verdict="skip")); continue
        d = float(np.sqrt(np.mean((cc - rc) ** 2))); ratio = (dc / tc) / max(1e-6, dr / tr)
        bad = d > thresh or ratio < 0.45 or ratio > 2.2
        rows.append(dict(char=ch, tone=tn, dist=round(d, 2), dur_ratio=round(ratio, 2), verdict="bad" if bad else "ok")); dists.append(d)
    bad = [r for r in rows if r["verdict"] == "bad"]
    return dict(text=text, mean_dist=round(float(np.mean(dists)), 2) if dists else None, n=len(dists), bad=[f"{r['char']}({r['dist']}半音, 長度比{r['dur_ratio']})" for r in bad],
                score=round(1 - len(bad) / max(1, len(dists)), 3), chars=rows)


if __name__ == "__main__":
    r = compare(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"score {r['score']}  mean_dist {r['mean_dist']}  bad {r['bad']}")
