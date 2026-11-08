"""DJ 口白「句尾斷掉」檢查＋找句尾真正結束的地方（〈Bravo 之戰〉v5 使用者 2026-11-08：3:45–3:59 DJ 每句尾巴都斷掉）。

原因：在句子之間插停頓時，用強制對齊的「字結束時間」當切點；對齊器報的字尾常早 0.1–0.3 秒
（尤其句尾拖長的「贏」「首」「的」），切下去最後一個字被砍掉，剩下的尾巴還被推到停頓後面，聽起來斷斷續續。

- tail_end(x, sr, t)：從對齊的字尾 t 往後找「不再有聲帶振動、音量 < −42 dB 持續 30 ms，而且後面 0.15 秒沒有再冒出聲帶音」的第一個點＝真正的句尾。插停頓一律切這裡。
- 直接執行：python dj_tail_check.py <wav>...  → 列出「有聲音突然變成數位靜音」（句尾被砍）與「停頓之間的小碎片」（被推走的尾巴）。
  make_battle.py review 也會對 out/audio/dj.wav 跑一次。"""
import sys

import numpy as np

HOP = 0.01


def _levels(m, sr):
    h = int(HOP * sr); w = int(0.02 * sr)
    return np.array([20 * np.log10(np.sqrt(np.mean(m[i:i + w] ** 2)) + 1e-9) for i in range(0, max(1, len(m) - w), h)])


def tail_end(x, sr, t, limit=0.5, floor=-42.0):
    """t＝對齊器報的句尾秒數；回傳真正句尾（秒）。找不到就回傳搜尋範圍內最安靜的點。"""
    import librosa
    m = x.mean(1) if x.ndim > 1 else x
    a = max(0, int((t - 0.05) * sr)); b = min(len(m), int((t + limit) * sr))
    seg = m[a:b]
    if len(seg) < int(0.1 * sr):
        return t
    _, vf, _ = librosa.pyin(seg, fmin=70, fmax=500, sr=sr, frame_length=2048, hop_length=int(HOP * sr))
    lv = _levels(seg, sr); n = min(len(vf), len(lv))
    for i in range(n - 3):
        if not vf[i] and all(lv[i + k] < floor for k in range(3)):
            if any(vf[k] and lv[k] > -48 for k in range(i + 3, min(n, i + 16))):
                continue                                     # 後面 0.15 秒內又有聲帶音（「放」「贏」的鼻音尾巴會先掉一下再出來）→ 還沒結束
            return (a + i * HOP * sr) / sr
    return (a + int(np.argmin(lv[:n])) * HOP * sr) / sr


def hard_cuts(m, sr, loud=-44.0, dead=-65.0, frag=(0.05, 0.16), gap=0.2):
    """回傳 [(秒, 說明)]：①有聲音（> loud）10 ms 內掉到數位靜音（< dead）＝句尾被砍；
    ②靜音 ≥ gap 秒後冒出 0.05–0.16 秒、夠大聲（> −36 dB）的一小段，後面又掉下去（< −42 dB ≥ 30 ms）＝被推到停頓後面的句尾。"""
    lv = _levels(m, sr); out = []
    for i in range(len(lv) - 2):
        if lv[i] > loud and lv[i + 1] < dead and lv[i + 2] < dead:
            out.append((round(i * HOP, 2), f"句尾被砍（{lv[i]:.0f} dB → 靜音）"))
    g = int(gap / HOP)
    for i in range(g, len(lv) - 20):
        if lv[i] > -50 and (lv[i - g:i] < -55).all():           # 停頓後第一聲
            j = i
            while j < len(lv) and lv[j] > -42:
                j += 1
            n = j - i
            if frag[0] <= n * HOP <= frag[1] and lv[i:j].max() > -36 and (lv[j:j + 3] < -42).all():
                out.append((round(i * HOP, 2), f"停頓後冒出 {n * HOP:.2f} 秒的小碎片又斷掉（被推走的句尾？）"))
    return out

if __name__ == "__main__":
    import soundfile as sf
    sys.stdout.reconfigure(encoding="utf-8")
    bad = 0
    for p in sys.argv[1:]:
        y, sr = sf.read(p, dtype="float32", always_2d=True)
        r = hard_cuts(y.mean(1), sr)
        print(p, "OK" if not r else "")
        for t, s in r:
            print(f"  ⚠ {t:7.2f} 秒 {s}")
        bad += len(r)
    sys.exit(1 if bad else 0)
