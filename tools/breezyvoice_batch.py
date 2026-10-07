"""BreezyVoice（聯發科＋台大，Apache-2.0 可商用台灣國語 TTS）批次生成：模型只載一次，每句抽多個 seed 當候選。2026-10-07 建立。
挑選用 breezyvoice_pick.py（Voice venv：ASR 必須全對＋對照 edge-tts 台灣國語參考音的腔調分數）。一鍵：make_breezyvoice.cmd jobs.json

執行（BreezyVoice venv，Python 3.10）：
  set PYTHONUTF8=1
  set PYTHONPATH=C:\\AI\\BreezyVoice\\winstub;C:\\AI\\BreezyVoice\\code;C:\\AI\\BreezyVoice\\code\\third_party\\Matcha-TTS
  C:\\AI\\BreezyVoice\\venv\\Scripts\\python.exe C:\\AI\\tools\\breezyvoice_batch.py jobs.json

jobs.json（相對路徑以 jobs.json 所在資料夾為準）：
{"out_dir": "bv", "seeds": 8,
 "jobs": [{"name": "A_V01", "text": "這是阿禾。", "ref_audio": "ref.wav", "ref_text": "參考音逐字稿", "seeds": 8 (選填), "edge_voice": "zh-TW-YunJheNeural" (給挑選用)}]}
輸出 <out_dir>/cand/<name>_s<seed>.wav（22.05 kHz），已存在就跳過；紀錄 <out_dir>/bv_log.jsonl。

念不準的字：直接在文字裡標注音，例如「連假[:ㄐㄧㄚ4]」（標在該字後面），不必再找同音字；下方 TW_BOPO 會自動補常見的台灣讀音。
數字：Windows 版沒有文字正規化（pynini 裝不了），阿拉伯數字會自動轉成國字（只處理整數）。
Windows 的坑：g2pw 的多程序 DataLoader 會卡死 → 建立後設 num_workers=0（已處理）。"""
import json
import os
import re
import sys
import time
from pathlib import Path

BV = Path(r"C:\AI\BreezyVoice")
SPEC = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None   # resolve before chdir
os.chdir(BV / "code")
for p in (BV / "winstub", BV / "code", BV / "code" / "third_party" / "Matcha-TTS"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import torch  # noqa: E402
import torchaudio  # noqa: E402
from g2pw import G2PWConverter  # noqa: E402
from single_inference import CustomCosyVoice, get_bopomofo_rare  # noqa: E402
from cosyvoice.utils.file_utils import load_wav  # noqa: E402

# 台灣讀音強制表（g2pw 判錯過的才放；詞 → 加注音的寫法）
TW_BOPO = {
    "連假": "連假[:ㄐㄧㄚ4]", "放假": "放假[:ㄐㄧㄚ4]", "請假": "請假[:ㄐㄧㄚ4]", "暑假": "暑假[:ㄐㄧㄚ4]", "寒假": "寒假[:ㄐㄧㄚ4]",
    "假期": "假[:ㄐㄧㄚ4]期", "假日": "假[:ㄐㄧㄚ4]日",
}
DIG = "零一二三四五六七八九"


def int_zh(n):
    if n < 10:
        return DIG[n]
    if n < 100:
        t, o = divmod(n, 10)
        return ("" if t == 1 else DIG[t]) + "十" + (DIG[o] if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return DIG[h] + "百" + ("" if r == 0 else ("零" + DIG[r] if r < 10 else ("一" + int_zh(r) if r < 20 else int_zh(r))))
    return "".join(DIG[int(c)] for c in str(n))      # 年份等大數：逐字念


def prep(text):
    text = re.sub(r"\[:[^\]]*\]|\d+", lambda m: m.group() if m.group().startswith("[") else int_zh(int(m.group())), text)   # 注音標記裡的聲調數字不轉
    for k, v in TW_BOPO.items():
        if v not in text:
            text = text.replace(k, v)
    return text.replace("……", "，").replace("——", "，").replace("～", "！").strip()


def main():
    spec_path = SPEC
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    base = spec_path.parent
    out = (base / spec.get("out_dir", "bv")).resolve()
    (out / "cand").mkdir(parents=True, exist_ok=True)
    rp = lambda p: str(Path(p) if Path(p).is_absolute() else (base / p).resolve())
    t0 = time.time()
    cv = CustomCosyVoice(str(BV / "model"))
    conv = G2PWConverter()
    conv.num_workers = 0
    print(f"[load] {time.time() - t0:.1f}s", flush=True)
    prompts = {}
    for j in spec["jobs"]:
        key = (rp(j["ref_audio"]), j["ref_text"])
        if key not in prompts:
            prompts[key] = (load_wav(key[0], 16000), get_bopomofo_rare(cv.frontend.text_normalize_new(key[1], split=False), conv))
        ps, pt = prompts[key]
        text = prep(j["text"])
        ct = get_bopomofo_rare(text if "[" in text else cv.frontend.text_normalize_new(text, split=False), conv)
        for seed in range(1, int(j.get("seeds", spec.get("seeds", 8))) + 1):
            dst = out / "cand" / f"{j['name']}_s{seed}.wav"
            if dst.exists():
                continue
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            t = time.time()
            o = cv.inference_zero_shot_no_normalize(ct, pt, ps)
            torchaudio.save(str(dst), o["tts_speech"], 22050)
            rec = {"name": j["name"], "seed": seed, "file": dst.name, "text": j["text"], "tts_input": ct,
                   "gen_s": round(time.time() - t, 2), "audio_s": round(o["tts_speech"].shape[1] / 22050, 2)}
            with open(out / "bv_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[ok] {dst.name} {rec['gen_s']}s", flush=True)
    print(f"[done] total {time.time() - t0:.0f}s peak_vram {torch.cuda.max_memory_allocated() / 2**30:.2f}GB", flush=True)


if __name__ == "__main__":
    main()
