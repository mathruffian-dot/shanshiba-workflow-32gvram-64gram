"""Suno 局部重唱（Kie replace-section）：歌已定稿、只有幾個字唱歪時用（同音字當歌詞）。重生一段 ≥10 秒，之後只把那幾個字剪回定稿。
環境變數 SUNO_PROMPT 換掉預設的咬字提示、SUNO_PART 給整段送件歌詞（含段落標籤，換行寫 \n），用在氣音段、段落標籤不是 Verse 的地方。
用法：
  python suno_replace.py submit <A|B> <標籤> <開始秒> <結束秒> <原句> <新句> [<原句2> <新句2> …] → out/suno/tasks_<標籤>.json（每次 2 版）
  python kie_suno.py poll <標籤>                                                                   → out/suno/<歌名>_<標籤>_v1.mp3、_v2.mp3
來源（定稿的送件標籤:第幾版）要指定：環境變數 SUNO_SRC=f1:1，或改下面的 SRC。新句只用在送給 Suno 的歌詞，battle.json 歌詞不改。"""
import json
import os
import sys
import time

import kie_suno as k

SRC = {"A": ("a1", 0), "B": ("b1", 0)}   # 定稿的送件標籤、第幾版


def submit(who, tag, s0, s1, *pairs):
    src = os.environ.get("SUNO_SRC", "").split(":") if os.environ.get("SUNO_SRC") else SRC[who]   # SUNO_SRC=f1:1 指定來源版（定稿本身是重唱版時用）
    t = json.loads((k.OUT / f"tasks_{src[0]}.json").read_text(encoding="utf-8"))
    aid = json.loads(t["raw"]["resultJson"])["data"][int(src[1])]["id"]
    full = t["input"].get("full_lyrics") or t["input"]["lyrics"]; part = []
    for old, new in zip(pairs[::2], pairs[1::2]):
        assert old in full, old
        full = full.replace(old, new); part.append(new)
    inp = {"task_id": t["taskId"], "audio_id": aid, "title": t["input"]["title"],
           "prompt": os.environ.get("SUNO_PROMPT", "Same rapper, same beat, same flow. Every Mandarin syllable bitten off clearly with Taiwanese diction."),
           "tags": t["input"].get("style") or t["input"]["tags"], "negative_tags": t["input"]["negative_tags"], "vocal_gender": "m",
           "infill_start_s": float(s0), "infill_end_s": float(s1),
           "full_lyrics": full, "lyrics": os.environ.get("SUNO_PART", "").replace("\\n", "\n") or "[Verse]\n" + "\n".join(part)}
    res = k.req("/jobs/createTask", {"model": "ai-music-api/replace-section", "input": inp})
    print(tag, str(res)[:120])
    if res.get("code") != 200:
        sys.exit(res)
    (k.OUT / f"tasks_{tag}.json").write_text(json.dumps({"taskId": res["data"]["taskId"], "who": who, "input": inp, "submitted": time.time()},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    submit(*sys.argv[2:]) if sys.argv[1] == "submit" else sys.exit(__doc__)
