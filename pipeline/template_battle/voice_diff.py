"""人聲不重複檢查（使用者 2026-11-02：不要老是用同類的幾個人聲）：候選的聲紋和音高，比對前面每一場用過的人聲。
用法（Voice venv）：python voice_diff.py 檔案或分軌 [檔案…]   → 每個候選列出最像的 3 個前場人聲、F0、跟同場另一人的相似度
前場人聲：短片/**/battle/out/song/align_<A|B>.json 的 vocals（有 battle.json 的資料夾）。"""
import glob
import json
import os
import sys
from pathlib import Path

AI = os.environ.get("AI_ROOT", r"C:\AI")
for d in glob.glob(AI + "/Voice/venv/Lib/site-packages/nvidia/*/bin"):
    os.add_dll_directory(d); os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
import librosa
import numpy as np
import onnxruntime as ort
import parselmouth
import torch
import torchaudio

HERE = Path(__file__).resolve().parent
FILMS = Path(os.environ.get("BATTLE_FILMS") or HERE.parents[1])   # 放各場對決的資料夾
sess = ort.InferenceSession(glob.glob(AI + r"\**\campplus.onnx", recursive=True)[0], providers=["CPUExecutionProvider"])


def embed(x):
    feat = torchaudio.compliance.kaldi.fbank(torch.from_numpy(x).unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000)
    feat = feat - feat.mean(dim=0, keepdim=True)
    e = sess.run(None, {sess.get_inputs()[0].name: feat.unsqueeze(0).numpy()})[0].flatten()
    return e / np.linalg.norm(e)


def voiced(path, rows=None):
    v, _ = librosa.load(path, sr=16000)
    if rows:
        r = [x for x in rows if x["ok"] >= 0.6 and x["end"] - x["start"] < 6] or rows
        v = np.concatenate([v[int(a["start"] * 16000):int(a["end"] * 16000)] for a in r])
    else:                                    # 沒對齊：只取人聲能量夠的段落
        hop = 1600
        e = np.array([np.sqrt(np.mean(v[i:i + hop] ** 2)) for i in range(0, len(v) - hop, hop)])
        keep = e > 0.02
        v = np.concatenate([v[i * hop:(i + 1) * hop] for i in np.nonzero(keep)[0]]) if keep.any() else v
    return v[:16000 * 40].astype(np.float32)


def f0(x):
    p = parselmouth.Sound(x.astype(np.float64), 16000).to_pitch(pitch_floor=60, pitch_ceiling=600).selected_array["frequency"]
    return round(float(np.median(p[p > 0])), 1)


hist = {}
for cfg in FILMS.glob("*/battle/battle.json"):
    if cfg.parent == HERE:
        continue
    d = json.loads(cfg.read_text(encoding="utf-8"))
    for k, r in d.get("rappers", {}).items():
        al = cfg.parent / "out" / "song" / f"align_{k}.json"
        if not al.exists():
            continue
        j = json.loads(al.read_text(encoding="utf-8"))
        if Path(j.get("vocals", "")).exists():
            x = voiced(j["vocals"], j.get("rows"))
            hist[f"{d.get('title')}/{r.get('name')}"] = (embed(x), f0(x))
print("前場人聲", {k: v[1] for k, v in hist.items()})
out = {}
for f in sys.argv[1:]:
    a = None
    x = voiced(f, a)
    e = embed(x)
    top = sorted(((float(e @ v[0]), k) for k, v in hist.items()), reverse=True)[:3]
    out[f] = e
    print(Path(f).name[:44], "F0", f0(x), "最像", [(round(s, 2), k) for s, k in top])
names = list(out)
if len(names) > 1:
    print("候選之間：")
    for a in names:
        print(Path(a).name[:30], [round(float(out[a] @ out[b]), 2) for b in names])
