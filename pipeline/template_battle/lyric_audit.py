"""全曲逐字聽寫稽核（〈向日葵之戰〉使用者 2026-11-04 抓到「吵到你」唱成「好當你」，對齊分數卻有 0.85）。
對齊分數只代表時間對得上，不代表字唱對。每句人聲、混音各聽寫一次（不給提示），用拼音比（同音字不算錯），列出兩邊都對不上的字。
用法：Voice venv python lyric_audit.py [A B]     輸出 out/song/lyric_audit_<A|B>.md"""
import json
import os
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import opencc
from faster_whisper import WhisperModel
from pypinyin import lazy_pinyin

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
cc = opencc.OpenCC("s2twp")
m = WhisperModel("large-v3", device="cpu", compute_type="int8", download_root=os.environ.get("AI_ROOT", "C:/AI") + "/Voice/models/whisper")
NOTCH = re.compile(r"[^\u4e00-\u9fff0-9]")


def hear(x):
    seg, _ = m.transcribe(x, language="zh", vad_filter=False, condition_on_previous_text=False, temperature=0.0)
    return NOTCH.sub("", cc.convert("".join(s.text for s in seg)))


def score(want, got):
    """逐字拼音做最長共同子序列：回傳沒聽到的字。"""
    a, b = lazy_pinyin(want), lazy_pinyin(got)
    d = np.zeros((len(a) + 1, len(b) + 1), int)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            d[i + 1, j + 1] = d[i, j] + 1 if x == y else max(d[i, j + 1], d[i + 1, j])
    i, j = len(a), len(b); miss = []
    while i and j:
        if a[i - 1] == b[j - 1]:
            i -= 1; j -= 1
        elif d[i - 1, j] >= d[i, j - 1]:
            i -= 1; miss.append(want[i])
        else:
            j -= 1
    miss += list(want[:i])
    return miss[::-1]


for who in sys.argv[1:] or ["A", "B"]:
    al = json.loads((HERE / "out" / "song" / f"align_{who}.json").read_text(encoding="utf-8"))
    mix, _ = librosa.load(al["song"], sr=16000, mono=True)
    voc, _ = librosa.load(al["vocals"], sr=16000, mono=True)
    out = [f"# {who} 逐字聽寫稽核", "", "| 句 | 秒 | 歌詞 | 人聲聽寫 | 混音聽寫 | 兩邊都沒聽到的字 |", "|:--|:--|:--|:--|:--|:--|"]
    bad = 0
    for i, r in enumerate(al["rows"]):
        want = NOTCH.sub("", cc.convert(r.get("text") or "".join(w.get("w", "") for w in r.get("words", []))))
        t0, t1 = max(0, r["start"] - 0.25), r["end"] + 0.3
        hv, hm = hear(voc[int(t0 * 16000):int(t1 * 16000)]), hear(mix[int(t0 * 16000):int(t1 * 16000)])
        mv, mm = score(want, hv), score(want, hm)
        both = [c for c in mv if c in mm]
        bad += bool(both)
        out.append(f"| {i} | {r['start']:.1f} | {want} | {hv} | {hm} | {'**' + ''.join(both) + '**' if both else ''} |")
        print(i, round(r["start"], 1), want, "|", hv, "|", hm, "|", "".join(both), flush=True)
    (HERE / "out" / "song" / f"lyric_audit_{who}.md").write_text("\n".join(out) + f"\n\n有疑問 {bad} 句。\n", encoding="utf-8")
