"""〈D-7〉配樂：MiniMax Music 3 純器樂三段 → 去人聲檢查選殘留最低 → 貼合長度＋交叉淡化 → post/music_bed.wav
變身段（S11–S13）刻意不放音樂。需要先跑過一次 assemble.py（產生 post/starts.json）。
C:/AI/H3/venv/Scripts/python.exe music_scenes.py"""
import json, os, subprocess, wave
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; M = HERE / "music3"; M.mkdir(exist_ok=True)
S = json.loads((HERE / "post" / "starts.json").read_text(encoding="utf-8"))
END = S["_total"]
NONE = "Vocal: NONE. No singing, no humming, no choir, no vocal samples, no spoken words.\n"
DRY = ("Every note is short and detached. Absolutely NO choir, NO humming, NO vocal-like or breathy sounds, NO sustained synth pads that sound like voices.")
SC = [("m1", "C1", "C2", "Genre: light playful school comedy underscore, purely instrumental film score. BPM 108, key F major. Emotional arc: a carefree sunny school day, a neat diligent girl starts early, two boys goof off, a cosy evening at home.\n" + NONE + "Arrangement: pizzicato strings, marimba, glockenspiel, ukulele plucks, light brushed snare, upright bass. " + DRY),
      ("m2", "C2", "C3", "Genre: comedic panic underscore, purely instrumental film score. BPM 120, key D minor. Emotional arc: a sudden shock after school, a frantic all-nighter, a ticking clock, a sheepish surprise, then a sleepy quiet night.\n" + NONE + "Arrangement: staccato pizzicato strings, ticking woodblock, bassoon, marimba, muted trumpet stabs, celesta for the night. " + DRY),
      ("m3", "C3", None, "Genre: quirky suspense into warm comedy, purely instrumental film score. BPM 100, key G major. Emotional arc: a quiet exam morning, tension builds as papers are handed out, a comic shock, a funny reveal, then a warm gentle ending theme that resolves for the end credits.\n" + NONE + "Arrangement: pizzicato strings, marimba, celesta, harp, light timpani, bassoon, glockenspiel, upright bass. " + DRY)]
LYR = "[Intro]" + chr(10) + ("[Instrumental]" + chr(10)) * 14 + "[Outro]" + chr(10) + "[Instrumental]" + chr(10)
SR = 44100; env = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def rd(p):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-ar", str(SR), "-ac", "2", "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


picked = {}
for name, a, b, cap in SC:
    need = (S[b] if b else END) - S[a]; cand = []
    for seed in (61, 62, 63):
        d = M / f"M{name}_s{seed}"; d.mkdir(exist_ok=True); flac = d / "gen.flac"
        if not flac.exists():
            (d / "cap.txt").write_text(cap, encoding="utf-8"); (d / "lyr.txt").write_text(LYR, encoding="utf-8")
            subprocess.run([r"C:\AI\H3\venv\Scripts\python.exe", r"C:\AI\tools\gen_music3.py", "--caption-file", str(d / "cap.txt"), "--lyrics-file", str(d / "lyr.txt"),
                            "--seconds", str(min(300, max(need + 8, 40))), "--seed", str(seed), "--prefix", f"audio/MM3/mv_{name}_{seed}", "--out", str(d)], env=env, capture_output=True)
            g = list(d.glob("mv_*.flac"))
            if g: g[0].replace(flac)
        if not flac.exists(): print(name, seed, "失敗", flush=True); continue
        if not list(d.glob("*Instrumental*.wav")):
            subprocess.run([r"C:\AI\Voice\venv\Scripts\audio-separator.exe", str(flac), "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "--model_file_dir", r"C:\AI\Voice\models\separator",
                            "--output_dir", str(d), "--output_format", "WAV"], env=env, capture_output=True)
        inst = list(d.glob("*Instrumental*.wav")); voc = list(d.glob("*Vocals*.wav"))
        if not inst: continue
        xi, xv = rd(flac), rd(voc[0]); dur = len(xi) / SR
        resid = float(np.sqrt((xv ** 2).mean()) / (np.sqrt((rd(inst[0]) ** 2).mean()) + 1e-9))
        print(name, seed, f"需要{need:.0f}s 實際{dur:.0f}s 人聲殘留{resid:.3f}", flush=True)
        cand.append((resid + (0 if dur >= need * 0.6 else 1.0) + (0.0 if dur >= need else 0.03), seed, flac, dur, resid))
    if not cand: print(name, "無候選"); continue
    cand.sort(); picked[name] = (cand[0][2], cand[0][3], need, a, b); print("PICK", name, cand[0][1], f"殘留{cand[0][4]:.3f}", flush=True)

XF = int(2.0 * SR); bed = np.zeros((int(END * SR) + XF, 2), np.float32)
for name, (p, dur, need, a, b) in picked.items():
    x = rd(p); L = int((need + 2.0) * SR)
    if len(x) < L:
        cf = int(3 * SR); out = x.copy()
        while len(out) < L:
            k = min(cf, len(x) // 2); fade = np.linspace(0, 1, k)[:, None]; out = np.concatenate([out[:-k], out[-k:] * (1 - fade) + x[:k] * fade, x[k:]])
        x = out
    x = x[:L].copy(); n = len(x); f = np.ones(n, np.float32); f[:XF] = np.linspace(0, 1, XF); f[-XF:] = np.linspace(1, 0, XF); x *= f[:, None]
    s = int(S[a] * SR); s = max(0, s - (XF // 2 if a != "C1" else 0)); bed[s:s + n] += x[: len(bed) - s]
bed = bed[: int(END * SR)]
win = SR; nwin = len(bed) // win + 1; g = np.ones(nwin, np.float32)
for i in range(nwin):
    seg = bed[i * win:(i + 1) * win]
    if len(seg) > 0: g[i] = np.clip(0.12 / (np.sqrt((seg ** 2).mean()) + 1e-6), 0.5, 14.0)
k = np.ones(5, np.float32) / 5; g = np.convolve(np.pad(g, (2, 2), mode="edge"), k, mode="valid")
gi = np.interp(np.arange(len(bed)) / SR, (np.arange(nwin) + 0.5), g).astype(np.float32); bed = bed * gi[:, None]
bed = bed / max(1e-6, np.abs(bed).max()) * 0.9
out = HERE / "post" / "music_bed.wav"
with wave.open(str(out), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(bed, -1, 1) * 32767).astype(np.int16).tobytes())
print("music_bed written", out, flush=True)
