"""〈D-7〉H3 出片：讀 voice_state.json 建時間軸 → 每鏡 spec（固定音軌：台詞放在指定秒數，其餘靜音）→ h3_shot.py
→ 自動品檢（切鏡／黑格），有問題換 seed 最多 3 次。可續跑。
  C:\\AI\\H3\\venv\\Scripts\\python.exe pipeline_gen.py [--only S05 S07 ...] [--retake S05 ...] [--dry]
狀態 gen_state.json；進度 PROGRESS.md；時間軸 timeline.json；各鏡輸出 h3/<id>_a<k>/，採用版複製到 h3/<id>/clip.mp4"""
import json, os, subprocess, sys, time, wave, shutil, urllib.request
from pathlib import Path
import numpy as np
import plan_h3 as P

HERE = P.HERE; SPEC = HERE / "specs"; H3 = HERE / "h3"; VOICE = HERE / "voice"
for d in (SPEC, H3): d.mkdir(exist_ok=True)
H3SHOT = r"C:\AI\tools\h3_shot.py"; PYH3 = r"C:\AI\H3\venv\Scripts\python.exe"
STATE_F = HERE / "gen_state.json"; PROG = HERE / "PROGRESS.md"
state = json.loads(STATE_F.read_text(encoding="utf-8")) if STATE_F.exists() else {"shots": {}}
VS = json.loads((HERE / "voice_state.json").read_text(encoding="utf-8"))
SPEAKER = {k: v[1] for k, v in {}.items()}


def save(): STATE_F.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
def log(m):
    t = time.strftime("%m-%d %H:%M:%S"); print(t, m, flush=True)
    with open(PROG, "a", encoding="utf-8") as f: f.write(f"- {t} {m}\n")
def run(cmd): return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def frames_for(d):
    n = 0
    while 17 * n + 5 < d * 24: n += 1
    return 17 * n + 5


def timeline():
    tl = {}
    for sh in P.SHOTS:
        ls, end = [], 0.0
        for lid, st in sh["lines"]:
            v = VS[lid]; ls.append(dict(id=lid, speaker=v["speaker"], text=v["text"], start=st, end=round(st + v["dur"], 3)))
            end = max(end, st + v["dur"])
        tl[sh["id"]] = dict(dur=round(max(sh["dur"], end + 0.6), 2), lines=ls)
    (HERE / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    return tl


def guide_wav(sid, t, secs):
    sr = 48000; buf = np.zeros(int(secs * sr) + sr, np.int16)
    for l in t["lines"]:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(VOICE / f"{l['id']}.wav"), "-ar", str(sr), "-ac", "1", "-f", "s16le", "-"], capture_output=True)
        a = np.frombuffer(r.stdout, np.int16); s = int(l["start"] * sr); buf[s:s + len(a)] = a[:len(buf) - s]
    p = SPEC / f"{sid}_guide.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(buf[:int(secs * sr)].tobytes())
    return p


def make_spec(sid, t, seed):
    sh = P.BY_ID[sid]
    secs = frames_for(t["dur"]) / 24
    dlg = [dict(subject=l["speaker"], line=l["text"].replace("……", "").replace("——", "，").replace("～", ""), lang="Chinese",
                offscreen=False, after="Right after the line the speaker's lips close and stay closed.") for l in t["lines"]]
    cons = ["No new people or animals appear that are not already in the first frame; no captions and no readable text.", P.LOCK] + sh["cons"]
    spec = dict(duration=round(secs - 0.02, 3), size=sh["size"], seed=seed, steps=14, style=P.STYLE, setting=sh["setting"],
                first_frame=str(HERE / "first" / f"{sh['frame']}.png"), subjects=[P.SUBJ[k] for k in sh["subs"]],
                shots=[dict(camera="The camera holds a static shot on a tripod.", action=sh["action"], dialogue=dlg)],
                constraints=cons, soundscape=sh["soundscape"] or "Quiet room tone.", music="N/A")
    if not sh["native"]:
        spec["audio"] = {"fixed": {"file": str(guide_wav(sid, t, secs))}}
    if sh["last"]:
        spec["last_frame"] = str(sh["last"])
    p = SPEC / f"{sid}.json"; p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def qc(clip):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(clip), "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    fr = np.frombuffer(r.stdout, np.uint8).reshape(-1, 90, 160).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)) if len(fr) > 1 else np.zeros(1)
    cuts = int((d > max(18.0, 6 * float(np.median(d)))).sum()); black = int((fr.mean(axis=(1, 2)) < 8).sum())
    drift = float(np.abs(fr[-1] - fr[0]).mean())
    return dict(cuts=cuts, black=black, maxdiff=round(float(d.max()), 1), drift=round(drift, 1), frames=len(fr))


def comfy_ok():
    try:
        urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=5); return True
    except Exception:
        return False


def main(only=None, retake=False, dry=False):
    tl = timeline()
    if dry:
        for sid in (only or P.BY_ID):
            r = run([PYH3, H3SHOT, str(make_spec(sid, tl[sid], 1)), "--out", str(H3 / f"_dry_{sid}"), "--dry-run"])
            print(sid, "OK" if r.returncode == 0 else (r.stdout + r.stderr)[-400:])
        return
    if not comfy_ok():
        log("ComfyUI 沒有回應，停止"); return
    ids = [s["id"] for s in P.SHOTS if not only or s["id"] in only]
    for sid in ids:
        st = state["shots"].setdefault(sid, {"status": "todo", "attempts": []}); sh0 = P.BY_ID[sid]
        if st["status"] == "done" and not retake: continue
        best, base = None, len(st["attempts"])
        for k in range(3):
            seed = 20261005 + P.SHOTS.index(sh0) * 10 + 1000 * (k + base)
            out = H3 / f"{sid}_a{k + base}"; t0 = time.time()
            r = run([PYH3, H3SHOT, str(make_spec(sid, tl[sid], seed)), "--out", str(out)])
            clip = out / "clip.mp4"
            if not clip.exists():
                st["attempts"].append(dict(seed=seed, error=(r.stdout + r.stderr)[-300:])); log(f"{sid} 失敗 {(r.stdout + r.stderr)[-200:]}"); save(); continue
            q = qc(clip); q.update(seed=seed, dir=str(out), secs=round(time.time() - t0)); st["attempts"].append(q)
            log(f"{sid} try{k + base} {q}")
            score = q["cuts"] * 10 + q["black"]
            if best is None or score < best[0]: best = (score, out)
            if q["cuts"] == 0 and q["black"] == 0: break
        if best:
            dst = H3 / sid; dst.mkdir(exist_ok=True); shutil.copyfile(best[1] / "clip.mp4", dst / "clip.mp4")
            st["status"] = "done"; st["pick"] = str(best[1])
        else:
            st["status"] = "failed"
        save()
    left = [s for s in ids if state["shots"].get(s, {}).get("status") != "done"]
    log("GEN_DONE" if not left else f"GEN_PARTIAL 未完成 {left}")


if __name__ == "__main__":
    a = sys.argv[1:]
    only = None
    for flag in ("--only", "--retake"):
        if flag in a: only = [x for x in a[a.index(flag) + 1:] if not x.startswith("--")]
    main(only, retake="--retake" in a, dry="--dry" in a)
