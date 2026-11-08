"""把 Suno 局部重唱（suno_replace.py）的候選接回定稿：人聲連音樂整段換，接點自動找好。
〈Bravo 之戰〉v3（2026-11-08）使用者聽出 2:51、2:55「音樂跳接」：舊做法固定接點＋固定時間差，接點落在字中間（「張揚」的「揚」切一半），
候選的拍子在窗裡慢慢漂（窗頭對齊、窗尾差 16 ms）。這支改成：
  1. 每個版本先分人聲（BS-RoFormer，存 out/song/sep_takes/，只做一次）；
  2. 接點在原訂位置 ±0.35 秒內找「兩個版本都沒在唱」的空隙（比原位置安靜 5 dB 以上才搬）；
  3. 窗頭、窗尾各自量拍子差（伴奏＝原曲減人聲，起音包絡相關，1 ms 精度），窗內照兩端線性對齊（FFT 重取樣，最多差零點幾 %，聽不出來）；
  4. 窗頭、窗尾各自量伴奏音量，窗內線性補（最多 ±3 dB）；
  5. 相鄰兩個窗直接互接（不經過定稿），等功率交叉 40 ms；
  6. 報告每個接點：搬到哪、人聲音量、兩端拍子差；接完再量一次跟定稿的拍子差（要 ≤3 ms）；
     兩版同一個字時間不一樣（一版接點後才開口、另一版接點前就唱完）會警告「可能少一個字」——〈Bravo 之戰〉v4「張揚」的「揚」就是這樣被切掉，
     這種要只剪人聲（用分好的人聲，在同一個母音的長音裡剪掉多出來的長度、交叉 30 ms，再疊回原版伴奏），音樂不剪。
用法（Voice venv）：python splice_resing.py plan.json
plan.json：{"base": "out/suno/<歌>_s2_v1.mp3", "out": "song/B.wav",
            "windows": [{"take": "out/suno/<歌>_rb1_v1.mp3", "t0": 28.1, "t1": 38.9, "lag_ms": -22}, …]}
  t0／t1＝歌曲時間（定稿的秒數），lag_ms＝大約的時間差（候選比定稿晚為正；不知道就給 0，會在 ±60 ms 內找）。路徑相對於 plan.json。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import resample

SR = 44100
HOP = 44                     # 起音包絡 1 ms 一格
XF = 0.04                    # 接點交叉淡化秒數
SEARCH = 0.35                # 接點往前後找空隙的範圍
SEP = os.environ.get("SEP_EXE") or str(Path(sys.executable).parent / ("audio-separator.exe" if os.name == "nt" else "audio-separator"))
SEP_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
SEP_DIR = os.environ.get("SEP_MODEL_DIR") or str(Path(os.environ.get("AI_ROOT", r"C:\AI")) / "Voice" / "models" / "separator")


def load(p):
    y, _ = librosa.load(str(p), sr=SR, mono=False)
    return np.atleast_2d(y).T.astype(np.float32)          # (n, 2)


def vocals(p, d):
    d.mkdir(parents=True, exist_ok=True)
    v = next(d.glob(f"{p.stem}_(Vocals)*"), None)
    if v is None:
        subprocess.run([SEP, str(p), "--model_filename", SEP_MODEL, "--model_file_dir", SEP_DIR, "--output_dir", str(d),
                        "--output_format", "FLAC", "--single_stem", "Vocals"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        v = next(d.glob(f"{p.stem}_(Vocals)*"))
    return load(v)


def fit(a, n):
    return a[:n] if len(a) >= n else np.concatenate([a, np.zeros((n - len(a), a.shape[1]), np.float32)])


class Src:
    def __init__(self, path, d):
        self.mix = load(path); self.voc = fit(vocals(path, d), len(self.mix))
        self.inst = self.mix - self.voc
        self.ons = librosa.onset.onset_strength(y=self.inst.mean(1), sr=SR, hop_length=HOP)
        h = int(0.02 * SR); v = self.voc.mean(1)
        self.venv = 20 * np.log10(np.sqrt(np.convolve(v ** 2, np.ones(3 * h) / (3 * h), "same"))[::h] + 1e-9)   # 人聲音量，20 ms 一格

    def vdb(self, t):
        return float(self.venv[min(len(self.venv) - 1, max(0, int(round(t / 0.02))))])


def lag_at(base, take, a, b, hint):
    """[a, b] 這段（歌曲時間）候選比定稿晚幾 ms：伴奏起音包絡相關最高的位移。"""
    i0, i1 = int(a * SR / HOP), int(b * SR / HOP); x = base.ons[i0:i1]; best = (hint, -1.0)
    for L in range(int(hint) - 60, int(hint) + 61):
        j = i0 + int(round(L * SR / 1000 / HOP)); y = take.ons[j:j + len(x)]
        if j < 0 or len(y) < len(x):
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best[1]:
            best = (L, r)
    return best


def rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-9)


def main():
    plan_p = Path(sys.argv[1]).resolve(); root = plan_p.parent; P = json.loads(plan_p.read_text(encoding="utf-8"))
    sep_d = root / "out" / "song" / "sep_takes"
    base_p = root / P["base"]; base = Src(base_p, sep_d); n = len(base.mix)
    W = sorted(P["windows"], key=lambda w: w["t0"]); takes = {}
    for w in W:
        takes.setdefault(w["take"], Src(root / w["take"], sep_d))
    # 1. 兩端拍子差、伴奏音量差（窗內靠接點那 2.5 秒）
    for w in W:
        tk = takes[w["take"]]; ln = min(2.5, (w["t1"] - w["t0"]) / 2)
        w["La"], w["ra"] = lag_at(base, tk, w["t0"], w["t0"] + ln, w.get("lag_ms", 0))
        w["Le"], w["re"] = lag_at(base, tk, w["t1"] - ln, w["t1"], w.get("lag_ms", 0))
        for e in ("a", "e"):                                  # 相關太低（人聲蓋過伴奏、兩版編曲不同）量不準 → 用另一端或給的值
            if w["r" + e] < 0.75:
                o = "e" if e == "a" else "a"
                w["L" + e] = w["L" + o] if w["r" + o] >= 0.75 else w.get("lag_ms", 0)
        seg = lambda s, a, b, L: s.inst[int((a + L / 1000) * SR):int((b + L / 1000) * SR)]
        w["ga"] = float(np.clip(rms_db(seg(base, w["t0"], w["t0"] + ln, 0)) - rms_db(seg(tk, w["t0"], w["t0"] + ln, w["La"])), -3, 3))
        w["ge"] = float(np.clip(rms_db(seg(base, w["t1"] - ln, w["t1"], 0)) - rms_db(seg(tk, w["t1"] - ln, w["t1"], w["Le"])), -3, 3))
    # 2. 段落表：定稿／候選交替；相鄰窗直接接
    segs = []; cur = 0.0
    for w in W:
        if w["t0"] > cur + 1e-3:
            segs.append(dict(src=base, name="定稿", a=cur, b=w["t0"], w=None))
        segs.append(dict(src=takes[w["take"]], name=Path(w["take"]).stem, a=w["t0"], b=w["t1"], w=w)); cur = w["t1"]
    segs.append(dict(src=base, name="定稿", a=cur, b=n / SR, w=None))

    def lag_of(s, t):                                       # 段落 s 在歌曲時間 t 的時間差（秒）
        w = s["w"]
        if w is None:
            return 0.0
        f = (t - w["t0"]) / max(1e-6, w["t1"] - w["t0"])
        return (w["La"] + (w["Le"] - w["La"]) * f) / 1000

    # 3. 接點搬到兩邊都沒在唱的空隙
    rep = []
    for k in range(len(segs) - 1):
        L, R = segs[k], segs[k + 1]; t = L["b"]
        # 只能往窗外搬（多用候選），不能往窗裡搬：窗裡的定稿是舊歌詞（〈Bravo 之戰〉搬進窗裡的接點聽寫變差）；兩個窗相接時前後都可以
        lo_t = t - (0.04 if R["w"] is None else SEARCH)      # 定稿→候選：只能提早；候選→定稿：只能延後
        hi_t = t + (0.04 if L["w"] is None else SEARCH)
        grid = np.arange(lo_t, hi_t + 1e-9, 0.02)
        lo, hi = L["a"] + 0.3, R["b"] - 0.3
        score = [max(L["src"].vdb(g + lag_of(L, g)), R["src"].vdb(g + lag_of(R, g))) if lo < g < hi else 99 for g in grid]
        here = max(L["src"].vdb(t + lag_of(L, t)), R["src"].vdb(t + lag_of(R, t)))
        g = float(grid[int(np.argmin(score))]); new = g if min(score) <= here - 5 else t
        L["b"] = R["a"] = new
        # 字的時間兩版不一樣（〈Bravo 之戰〉v4：rb9a 的「揚」在接點後 0.08 秒才開口 → 被切掉）
        # 判斷法：接點前後 0.4 秒兩版的音高曲線，兩版都有聲的格子音高差的中位數 > 1.5 半音＝兩版這裡唱的不是同一個字（或時間錯開）
        def pitch(S, seg):
            a = new - 0.4 + lag_of(seg, new); y = S.voc[max(0, int(a * SR)):int((a + 0.8) * SR)].mean(1)
            f0, _, _ = librosa.pyin(librosa.resample(y, orig_sr=SR, target_sr=22050), fmin=70, fmax=800, sr=22050, frame_length=1024, hop_length=441)
            return 12 * np.log2(f0 / 100)
        pa, pb = pitch(L["src"], L), pitch(R["src"], R); m_ = min(len(pa), len(pb)); both = ~np.isnan(pa[:m_]) & ~np.isnan(pb[:m_])
        dp = float(np.median(np.abs(pa[:m_][both] - pb[:m_][both]))) if both.sum() >= 5 else 0.0
        rep.append(dict(seam=f"{L['name']}→{R['name']}", old=round(t, 2), new=round(new, 2), voc_old=round(here), voc_new=round(min(min(score), here)),
                        word_risk=dp > 1.5, pitch_diff=round(dp, 1)))
    # 4. 依段落表重組，等功率交叉
    out = np.zeros((n, 2), np.float32); out_i = np.zeros((n, 2), np.float32); x = int(XF * SR); hx = x // 2
    for k, s in enumerate(segs):
        a, b = int(round(s["a"] * SR)) - (hx if k else 0), min(n, int(round(s["b"] * SR)) + (hx if k < len(segs) - 1 else 0))
        def take(arr):
            if s["w"] is None:
                return arr[a:b].copy()
            ta, tb = a / SR, b / SR; pad = int(0.25 * SR)
            sa, sb = int(round((ta + lag_of(s, ta)) * SR)), int(round((tb + lag_of(s, tb)) * SR))
            src = arr[max(0, sa - pad):sb + pad]
            m = int(round((b - a) * len(src) / (sb - sa)))
            r = resample(src, m, axis=0).astype(np.float32); p0 = int(round((sa - max(0, sa - pad)) * (b - a) / (sb - sa)))
            gdb = np.linspace(s["w"]["ga"], s["w"]["ge"], b - a)
            return fit(r[p0:p0 + (b - a)], b - a) * (10 ** (gdb / 20))[:, None]
        piece, piece_i = take(s["src"].mix), take(s["src"].inst)
        env = np.ones(len(piece), np.float32)
        if k:
            env[:x] = np.sin(np.linspace(0, np.pi / 2, x)) ** 1
        if k < len(segs) - 1:
            env[-x:] = np.cos(np.linspace(0, np.pi / 2, x)) ** 1
        out[a:a + len(piece)] += piece * env[:, None]; out_i[a:a + len(piece)] += piece_i * env[:, None]
    pk = np.abs(out).max()
    if pk > 0.999:
        out *= 0.999 / pk
    dst = root / P["out"]; sf.write(str(dst), out, SR, subtype="PCM_16")
    # 5. 驗收：接完的歌跟定稿的拍子差（每個接點前後 2 秒）
    chk = librosa.onset.onset_strength(y=out_i.mean(1), sr=SR, hop_length=HOP)

    class O:
        ons = chk
    print(f"→ {dst}")
    for w in W:
        print(f"  {Path(w['take']).stem}: {w['t0']:.2f}–{w['t1']:.2f}  拍子差 頭 {w['La']} ms(r {w['ra']:.2f}) 尾 {w['Le']} ms(r {w['re']:.2f})"
              f"  伴奏補 {w['ga']:+.1f}/{w['ge']:+.1f} dB")
    for r_ in rep:
        t = r_["new"]; lb = lag_at(base, O, t - 2.0, t - 0.05, 0); la = lag_at(base, O, t + 0.05, t + 2.0, 0)
        r_.update(after_lag_ms=[lb[0], la[0]])
        print(f"  接點 {r_['seam']}：{r_['old']:.2f} → {r_['new']:.2f} 秒，人聲 {r_['voc_old']} → {r_['voc_new']} dB；接完拍子差 前 {lb[0]} ms／後 {la[0]} ms"
              + ("  ⚠ 拍子沒對齊" if max(abs(lb[0]), abs(la[0])) > 3 else "") + ("  ⚠ 接點還在字上，要人聽" if r_["voc_new"] > -30 else "")
              + (f"  ⚠ 接點前後兩版唱的不一樣（音高差 {r_['pitch_diff']} 半音）：可能少一個字或重複一個字，逐字對" if r_["word_risk"] else ""))
    (dst.parent / f"{dst.stem}_splice.json").write_text(json.dumps(dict(windows=[{k: v for k, v in w.items()} for w in W], seams=rep),
                                                                  ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
