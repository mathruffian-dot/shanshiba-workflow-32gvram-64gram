"""DJ 口白逐字對齊：out/voice/ming/dj_<key>.wav ＋ battle.json 文字 → out/voice/ming/dj_align.json（{key: [[字, 開始, 結束], …]}）。
鏡頭切點（setup_shots.py 的 djt）與 DJ 字幕都用它；換了口白檔要重跑（使用者 2026-11-04：插入鏡要對到口白正在講的事）。
用法（Voice venv）：python dj_align.py"""
import json
import os
import re
from pathlib import Path

import stable_whisper

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
M = HERE / "out" / "voice" / "ming"
m = stable_whisper.load_faster_whisper("large-v3", device="cpu", compute_type="int8", download_root=os.environ.get("AI_ROOT", "C:/AI") + "/Voice/models/whisper")
out = {}
for key, text in CFG["dj"]["lines"].items():
    clean = re.sub(r"[，。！？；：、《》「」\s]", " ", text)
    res = m.align(str(M / f"dj_{key}.wav"), clean, language="zh", original_split=False)
    out[key] = [[w.word, round(w.start, 2), round(w.end, 2)] for s in res.segments for w in s.words]
    print(key, len(out[key]), out[key][-1], flush=True)
(M / "dj_align.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
