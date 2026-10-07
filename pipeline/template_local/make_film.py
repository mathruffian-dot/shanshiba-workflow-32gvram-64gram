"""全本地多鏡短片範本：讀 film.json，從角色定妝照一路做到成片＋自審。做新片只改 film.json，這支程式不用改。
H3 venv 執行（ComfyUI 要先開：同一個 cmd 視窗 call configs\\profile.cmd → C:\\AI\\tools\\start_comfy.cmd）：
  C:\\AI\\H3\\venv\\Scripts\\python.exe make_film.py [stage ...] [--film 別的設定.json]
stage（不給＝全部依序）：chars masters frames voices h3 amb edl music ending cut review
每一步的輸出都在 out/，已存在的檔案會跳過，所以可以中斷後續跑、或刪掉某個檔重做：
  - 重生某一鏡首幀：刪 out/first/<鏡>.png，在 film.json 的 seeds 加 "frame_<鏡>": 新 seed，再跑 frames
  - 重拍某一鏡 H3：刪 out/h3/<鏡>/clip.mp4（或加 "h3_<鏡>": 新 seed），再跑 h3（環境變數 ONLY="S2 S5" 只跑指定鏡）
  - 改了台詞：刪 out/voice/bv 裡那句的檔（或整個 out/voice/bv），再跑 voices
  - 改了剪接（cut_in、tail…）：跑 edl cut review 即可
人工關卡：frames 之後看 out/first/_sheet.jpg；h3 之後看 out/review/clips_*.jpg；review 之後一定要看成片。
2026-10-07 由「一個沒看過本專案的 agent 照 repo 做出〈被狗吃掉的作業〉」時寫的 film.py／post.py 整理而成。"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

for _s in (sys.stdout, sys.stderr):                 # 中文輸出在非 UTF-8 主控台不變亂碼
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:]]
FILM = HERE / (ARGS[ARGS.index("--film") + 1] if "--film" in ARGS else "film.json")
CFG = json.loads(FILM.read_text(encoding="utf-8"))
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
REPO = (HERE / CFG.get("repo_dir", "../..")).resolve()
T = Path(os.environ.get("AI_TOOLS", r"C:\AI\tools"))
PYH3 = os.environ.get("PY_H3", r"C:\AI\H3\venv\Scripts\python.exe")
PYV = os.environ.get("PY_VOICE", r"C:\AI\Voice\venv\Scripts\python.exe")
PYB = os.environ.get("PY_BREEZE", r"C:\AI\BreezeTTS\venv\Scripts\python.exe")
PYBV = os.environ.get("PY_BREEZYVOICE", r"C:\AI\BreezyVoice\venv\Scripts\python.exe")
SEP = str(Path(PYV).parent / "audio-separator.exe")
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
SR, FPS = 48000, 24
CHARS, SHOTS = CFG["chars"], CFG["shots"]
LINES = [(s["id"], s["line"]) for s in SHOTS if s.get("line")]      # (鏡, {who, text, tts?, at})
MIX = CFG.get("mix", {})
TIMING = OUT / "timing.json"
timing = json.loads(TIMING.read_text(encoding="utf-8")) if TIMING.exists() else {}


def seed(key, default):
    return int(CFG.get("seeds", {}).get(key, default))


def comfy_ok():
    try:
        urllib.request.urlopen(HOST + "/system_stats", timeout=5); return True
    except Exception:
        return False


def free_comfy():
    try:
        r = urllib.request.Request(HOST + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r, timeout=30)
    except Exception:
        pass
    time.sleep(5)


def run(cmd, cwd=OUT, check=True, **kw):
    print("$", " ".join(map(str, cmd))[:200], flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}, stdin=subprocess.DEVNULL, **kw)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))[:200]}\n{(r.stdout + r.stderr)[-2500:]}")
    return r


def newest(d, ext=".png"):
    fs = sorted(Path(d).glob(f"*{ext}"), key=lambda f: f.stat().st_mtime)
    return fs[-1] if fs else None


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout)


def frames_for(d):
    n = 0
    while 17 * n + 5 < d * FPS:
        n += 1
    return 17 * n + 5


def stage(name):
    def deco(fn):
        def wrap():
            t0 = time.time(); a = time.strftime("%H:%M:%S"); fn()
            timing[name] = dict(sec=round(time.time() - t0, 1), start=a, end=time.strftime("%H:%M:%S"))
            TIMING.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[stage] {name} {timing[name]['sec']}s", flush=True)
        return wrap
    return deco


def line_index(sid):
    return next(i for i, (s, _) in enumerate(LINES) if s == sid)


# ------------------------------------------------------------------------------------------------ 圖
@stage("chars")
def chars():
    """角色定妝照：單張、灰底、正面半身（docs/07 §1）。不滿意就在 seeds 加 char_<角色> 換 seed、刪檔重跑。"""
    for k, c in CHARS.items():
        dst = OUT / "chars" / f"{k}.png"
        if dst.exists():
            continue
        p = ("Studio character reference photo, single person only, one image (not a collage), medium close-up bust portrait facing the camera, "
             "plain light grey seamless background, soft even studio light, sharp focus, realistic photograph. " + c["look"] + ", gentle natural expression. "
             "No text, no watermark.")
        run([PYH3, T / "gen_image.py", "--prompt", p, "--width", "1024", "--height", "1024", "--seed", seed("char_" + k, 11),
             "--prefix", f"film/char_{k}", "--out", "chars"])
        newest(OUT / "chars").rename(dst)


@stage("masters")
def masters():
    """場景母版（空景 2K），再依每鏡的 scene 框裁成該鏡景別，當首幀的場景參考（docs/07 §4）。"""
    from PIL import Image
    for k, p in CFG.get("masters", {}).items():
        dst = OUT / "masters" / f"{k}.png"
        if not dst.exists():
            run([PYH3, T / "gen_image.py", "--prompt", p, "--seed", seed("master_" + k, 21), "--prefix", f"film/master_{k}", "--out", "masters"])
            newest(OUT / "masters").rename(dst)
    for s in SHOTS:
        if not s.get("scene"):
            continue
        m, box = s["scene"]; im = Image.open(OUT / "masters" / f"{m}.png").convert("RGB"); W, H = im.size
        crop = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
        crop.thumbnail((1344, 1344)); crop.save(OUT / "masters" / f"crop_{s['id']}.png")


@stage("frames")
def frames():
    """首幀：Qwen-Image-Edit 附「角色定妝照（<image1>…）＋場景裁切（最後一張）」。每鏡都照抄角色完整外觀描述，否則會掉眼鏡、換髮型。"""
    for s in SHOTS:
        dst = OUT / "first" / f"{s['id']}.png"
        if dst.exists():
            continue
        keep = " ".join(f"Keep exactly the same person as <image{i}>: same face, hairstyle and clothes ({CHARS[k]['look']})."
                        for i, k in enumerate(s["refs"], 1))
        set_s = (" " + CFG["set_sentence"].format(n=len(s["refs"]) + 1)) if s.get("scene") else ""
        p = keep + set_s + " New photo: " + CFG["cine"] + s["frame"] + CFG.get("frame_suffix", " No text, no watermark, no captions.")
        cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", p,
               "--seed", seed("frame_" + s["id"], 5101), "--prefix", f"film/{s['id']}", "--out", "first"]
        for k in s["refs"]:
            cmd += ["--ref", OUT / "chars" / f"{k}.png"]
        if s.get("scene"):
            cmd += ["--ref", OUT / "masters" / f"crop_{s['id']}.png"]
        run(cmd)
        newest(OUT / "first").rename(dst)
    sheet([OUT / "first" / f"{s['id']}.png" for s in SHOTS], OUT / "first" / "_sheet.jpg")
    print("→ 人工檢查 out/first/_sheet.jpg：臉、服裝、多手多腳、背景有沒有字、窗戶方向", flush=True)


def sheet(files, dst, cols=3):
    from PIL import Image, ImageDraw, ImageFont
    fs = [p for p in files if Path(p).exists()]
    if not fs:
        return
    W, H = 672, 384; rows = (len(fs) + cols - 1) // cols
    im = Image.new("RGB", (W * cols, H * rows)); f = ImageFont.truetype("C:/Windows/Fonts/msjhbd.ttc", 28)
    for i, p in enumerate(fs):
        t = Image.open(p).convert("RGB").resize((W, H)); ImageDraw.Draw(t).text((8, 6), Path(p).stem, font=f, fill=(255, 255, 0), stroke_width=3, stroke_fill=0)
        im.paste(t, ((i % cols) * W, (i // cols) * H))
    Path(dst).parent.mkdir(parents=True, exist_ok=True); im.save(dst, quality=85)


# ------------------------------------------------------------------------------------------------ 聲音
@stage("voices")
def voices():
    """Breeze 設計角色聲音（一次）→ edge-tts 台灣國語答案卷 → BreezyVoice 每句 8 候選 → 自動挑（聽寫拼音聲調全對＋腔調分數，已去頭尾靜音）。"""
    free_comfy()
    vd = OUT / "voice"; vd.mkdir(exist_ok=True)
    jobs = [dict(name=f"ref_{k}", text=c["voice_sample"], instruction=c["voice_design"], seed=seed("voice_" + k, 7)) for k, c in CHARS.items()]
    for i, (sid, ln) in enumerate(LINES):          # 答案卷：只拿來比腔調，不進成片
        w = vd / f"tw_{i}.wav"
        if w.exists():
            continue
        mp3 = vd / f"tw_{i}.mp3"
        r = run([PYV, T / "gen_voice.py", "--engine", "edge", "--text", ln["text"], "--voice", CHARS[ln["who"]].get("edge_voice", "zh-TW-YunJheNeural"),
                 "--out", mp3], check=False)
        if r.returncode == 0 and mp3.exists():
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "48000", "-ac", "1", w])
        else:                                        # 沒網路：改用 Breeze 產生答案卷（可靠度較低）
            jobs.append(dict(name=f"tw_{i}", text=ln["text"], instruction="A clear, neutral standard Taiwanese Mandarin news-reading voice, calm, precise tones.", seed=11))
    (OUT / "breeze.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
    run([PYB, T / "breeze_batch.py", "breeze.json"])
    bv = [dict(name=f"line{i}", text=ln.get("tts", ln["text"]), ref_audio=f"voice/ref_{ln['who']}.wav", ref_text=CHARS[ln["who"]]["voice_sample"],
               tw_ref=f"voice/tw_{i}.wav", seeds=8) for i, (sid, ln) in enumerate(LINES)]
    (OUT / "bv.json").write_text(json.dumps(dict(out_dir="voice/bv", jobs=bv), ensure_ascii=False, indent=1), encoding="utf-8")
    run([PYBV, T / "breezyvoice_batch.py", "bv.json"])
    run([PYV, T / "breezyvoice_pick.py", "bv.json"])
    bp = json.loads((vd / "bv" / "picks.json").read_text(encoding="utf-8"))
    picks, bad = {}, []
    for i, (sid, ln) in enumerate(LINES):
        p = bp[f"line{i}"]; best = next(c for c in p["cands"] if c["file"] == p["pick"])
        if p["needs_review"]:
            bad.append(f"{sid}「{ln['text']}」聽成「{best['asr']}」")
        picks[str(i)] = dict(shot=sid, who=ln["who"], text=ln["text"], file=str(vd / "bv" / f"line{i}.wav"), heard=best["asr"],
                             tw_score=best.get("tw_score"), needs_review=p["needs_review"])
        print("pick", sid, ln["text"], "→", p["pick"], best["asr"], best.get("tw_score"), flush=True)
    (OUT / "voice_picks.json").write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    if bad and os.environ.get("ALLOW_REVIEW") != "1":
        raise SystemExit("這幾句 8 個候選聽寫都不對：" + "；".join(bad) +
                         "\n請在 film.json 該句加 \"tts\"（念不準的字標注音，例：假[:ㄐㄧㄚ4]）或換說法，刪掉 out/voice/bv 再跑 voices；"
                         "確定只是 ASR 聽錯（例如單字喊叫）就用 ALLOW_REVIEW=1 繼續。")


# ------------------------------------------------------------------------------------------------ H3
def shot_secs(s, picks):
    d = s["dur"]
    if s.get("line"):
        d = max(d, s["line"]["at"] + dur(picks[str(line_index(s["id"]))]["file"]) + 0.8)
    return frames_for(d) / FPS


def h3_spec(s, secs, dialogue):
    h = CFG["h3"]
    return dict(duration=round(secs - 0.02, 3), size=[1344, 768], seed=seed("h3_" + s["id"], h.get("default_seed", 20261007)), steps=14, draft=True,
                style=h["style"], setting=h["setting"], first_frame=str(OUT / "first" / f"{s['id']}.png"),
                subjects=[dict(key=k, desc=CHARS[k]["look"], voice=CHARS[k]["h3_voice"]) for k in s["refs"]],
                shots=[dict(camera=s.get("camera", h.get("camera", "The camera holds a static shot on a tripod.")), action=s["action"], dialogue=dialogue)],
                constraints=h.get("constraints", []) + s.get("extra_constraints", []), soundscape=h["soundscape"], music="N/A")


@stage("h3")
def h3():
    """每鏡 H3（DMAD 4 步、只給首幀）。看得到臉的鏡頭一律給固定音軌：有台詞放配音，沒台詞放靜音（否則角色會自己嘟囔）。"""
    picks = json.loads((OUT / "voice_picks.json").read_text(encoding="utf-8")) if LINES else {}
    only = os.environ.get("ONLY", "").split()
    for s in SHOTS:
        if only and s["id"] not in only:
            continue
        od = OUT / "h3" / s["id"]
        if (od / "clip.mp4").exists():
            continue
        od.mkdir(parents=True, exist_ok=True)
        secs = shot_secs(s, picks); buf = bytearray(int(secs * SR) * 2); dlg = []
        if s.get("line"):
            ln = s["line"]; f = picks[str(line_index(s["id"]))]["file"]
            pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", f, "-ar", str(SR), "-ac", "1", "-f", "s16le", "-"], capture_output=True).stdout
            st = int(ln["at"] * SR) * 2; seg = pcm[: len(buf) - st]; buf[st:st + len(seg)] = seg
            dlg = [dict(subject=ln["who"], line=ln["text"], lang="Chinese", after="Right after the line the speaker's lips close and stay closed.")]
        with wave.open(str(od / "guide.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(buf))
        spec = h3_spec(s, secs, dlg); spec["audio"] = {"fixed": {"file": str(od / "guide.wav")}}
        (od / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        run([PYH3, T / "h3_shot.py", od / "spec.json", "--out", od])
    sheet_clips()


def sheet_clips():
    from PIL import Image
    rv = OUT / "review"; rv.mkdir(exist_ok=True)
    for s in SHOTS:
        c = OUT / "h3" / s["id"] / "clip.mp4"
        if not c.exists():
            continue
        d = dur(c); tiles = []
        for q in (0.08, 0.3, 0.5, 0.7, 0.85, 0.97):
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{d * q:.2f}", "-i", str(c), "-frames:v", "1", "-vf", "scale=448:256",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            if len(raw) == 448 * 256 * 3:
                tiles.append(Image.frombytes("RGB", (448, 256), raw))
        im = Image.new("RGB", (448 * 6, 256))
        for i, t in enumerate(tiles):
            im.paste(t, (448 * i, 0))
        im.save(rv / f"clips_{s['id']}.jpg", quality=82)
    print("→ 人工檢查 out/review/clips_*.jpg：換臉、多出人、多手多腳、鏡頭漂移、背景同學亂動", flush=True)


@stage("amb")
def amb():
    """有動作音效的鏡頭（amb: true）：用同一張首幀另拍一支「H3 原生音效」版，聽寫確認沒有人聲後，只取它的音軌當環境音。"""
    res = {}
    picks = json.loads((OUT / "voice_picks.json").read_text(encoding="utf-8")) if LINES else {}
    for s in SHOTS:
        if not s.get("amb"):
            continue
        od = OUT / "h3" / f"{s['id']}_amb"; od.mkdir(parents=True, exist_ok=True)
        if not (od / "clip.mp4").exists():
            spec = h3_spec(s, shot_secs(s, picks), [])
            spec["seed"] = int(s.get("amb_seed", spec["seed"]))      # 不寫 audio 欄位＝H3 原生音效
            (od / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            run([PYH3, T / "h3_shot.py", od / "spec.json", "--out", od])
        run([PYV, T / "stt.py", "--audio", od / "clip.mp4", "--outdir", od / "stt"], check=False)
        heard = (od / "stt" / "transcript.txt").read_text(encoding="utf-8").strip() if (od / "stt" / "transcript.txt").exists() else ""
        speech = len(re.findall(r"[\u4e00-\u9fff]", heard))
        if speech <= 1:
            res[s["id"]] = str(od / "clip.mp4"); print(f"amb {s['id']}: OK（聽寫沒有人聲）", flush=True)
        else:
            print(f"amb {s['id']}: 有人聲「{heard}」→ 不用；換 amb_seed 再跑 amb，或改用 sfx/ 音效", flush=True)
    (OUT / "post").mkdir(exist_ok=True)
    (OUT / "post" / "amb.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------------------------------------ 剪接、配樂、片尾、成片
def ending_secs():
    e = CFG.get("ending")
    return len(e["cards"]) * e.get("card_dur", 3.3) + e.get("title_dur", 7.5) if e else 0.0


@stage("edl")
def edl():
    """時間軸：依配音長度與 cut_in／cut_out／tail 算每鏡在成片中的位置，寫 out/post/edl.json（cut、review 都讀它）。
    cut_in＝裁掉鏡頭開頭幾秒（H3 常晚開口）；cut_out＝"full" 用到鏡尾，不寫＝台詞結束＋tail 秒（反應停頓）。"""
    picks = json.loads((OUT / "voice_picks.json").read_text(encoding="utf-8")) if LINES else {}
    amb_files = json.loads((OUT / "post" / "amb.json").read_text(encoding="utf-8")) if (OUT / "post" / "amb.json").exists() else {}
    lead = MIX.get("say_lead", 0.2); t, rows = 0.0, []
    for s in SHOTS:
        cd = dur(OUT / "h3" / s["id"] / "clip.mp4"); a = float(s.get("cut_in", 0.0)); b = s.get("cut_out"); lines = []
        if s.get("line"):
            i = line_index(s["id"]); ln = s["line"]; d = dur(picks[str(i)]["file"])
            lines.append(dict(id=f"line{i}", who=ln["who"], text=ln["text"], file=picks[str(i)]["file"],
                              film_start=round(t + ln["at"] - a - lead, 3), film_end=round(t + ln["at"] - a - lead + d, 3)))
            if b is None:
                b = ln["at"] + d + s.get("tail", MIX.get("default_tail", 0.55))
        b = cd if b in (None, "full") else min(float(b), cd)
        rows.append(dict(id=s["id"], start=round(t, 3), dur=round(b - a, 3), src_in=a, src_out=round(b, 3), lines=lines, amb=amb_files.get(s["id"])))
        t += b - a
    e = dict(shots=rows, story_end=round(t, 3), total=round(t + ending_secs(), 3))
    (OUT / "post").mkdir(exist_ok=True)
    (OUT / "post" / "edl.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"本片 {t:.2f} 秒＋片尾 {ending_secs():.1f} 秒＝{e['total']:.2f} 秒", flush=True)


def load(p):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-ar", str(SR), "-ac", "1", "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


@stage("music")
def music():
    """配樂：Music 3 純器樂多 seed → BS-RoFormer 分離 → 挑人聲殘留最少、長度夠的那首的純器樂軌。"""
    import numpy as np
    e = json.loads((OUT / "post" / "edl.json").read_text(encoding="utf-8")); secs = int(e["total"] + 4)
    m = CFG["music"]; md = OUT / "music"; md.mkdir(exist_ok=True)
    (md / "cap.txt").write_text(m["caption"], encoding="utf-8")
    (md / "lyr.txt").write_text("[Intro]\n" + "[Instrumental]\n" * 14 + "[Outro]\n[Instrumental]\n", encoding="utf-8")   # 少於 14 個會太短；加 Verse 會冒人聲
    for sd_ in m.get("seeds", [7, 23, 51]):
        sd = md / f"s{sd_}"; sd.mkdir(exist_ok=True)
        if not list(sd.glob("*.flac")):
            run([PYH3, T / "gen_music3.py", "--caption-file", md / "cap.txt", "--lyrics-file", md / "lyr.txt", "--seconds", secs, "--seed", sd_,
                 "--prefix", f"audio/MM3/film_{sd_}", "--out", sd])
    free_comfy(); best = None
    for sd_ in m.get("seeds", [7, 23, 51]):
        sd = md / f"s{sd_}"; src = next(sd.glob("*.flac"))
        if not list(sd.glob("*Instrumental*.wav")):
            run([SEP, src, "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "--model_file_dir", r"C:\AI\Voice\models\separator",
                 "--output_dir", sd, "--output_format", "WAV"])
        voc = load(next(sd.glob("*Vocals*.wav"))); ins = load(next(sd.glob("*Instrumental*.wav")))
        ratio = float(np.sqrt((voc ** 2).mean()) / (np.sqrt((ins ** 2).mean()) + 1e-9)); d = len(ins) / SR
        print(f"music s{sd_}: 人聲殘留 {ratio:.4f}，{d:.1f} 秒", flush=True)
        if d >= e["total"] and (best is None or ratio < best[0]):
            best = (ratio, next(sd.glob("*Instrumental*.wav")))
    if best is None:
        raise SystemExit("沒有一首配樂夠長：把 music.seeds 換掉再跑 music")
    (OUT / "post" / "music_pick.json").write_text(json.dumps(dict(file=str(best[1]), vocal_ratio=best[0]), ensure_ascii=False), encoding="utf-8")


@stage("ending")
def ending():
    """片尾：特寫靜幀＋AI 工具名單＋片名（templates/ending）。MiniMax Music3 授權要求標示、公開內容要標示 AI 生成。"""
    e = CFG.get("ending")
    if not e:
        return
    from PIL import Image
    ed = OUT / "ending"; (ed / "frames").mkdir(parents=True, exist_ok=True)
    cards = []
    for i, tools in enumerate(e["cards"]):
        sid = e["closeups"][i % len(e["closeups"])]
        Image.open(OUT / "first" / f"{sid}.png").convert("RGB").save(ed / "frames" / f"close{i + 1}.png")
        cards.append(dict(image=f"frames/close{i + 1}.png", tools=tools))
    cfg = {"_base": str(ed), "title": e.get("title", CFG["title"]), "header": e.get("header", "本片使用的 AI 工具"), "card_dur": e.get("card_dur", 3.3),
           "title_dur": e.get("title_dur", 7.5), "out": "ending.mp4", "cards": cards}
    (ed / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    run([PYH3, REPO / "templates" / "ending" / "render_ending.py", ed / "config.json"])


def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


@stage("cut")
def cut():
    """RTX VSR 放大 → 依 edl 剪接 → 混音（台詞提前 say_lead 秒、配樂台詞期間壓低）→ 響度 → 1080p 燒字幕 → 手機版。"""
    import numpy as np
    e = json.loads((OUT / "post" / "edl.json").read_text(encoding="utf-8")); post = OUT / "post"
    vsr = post / "vsr"; vsr.mkdir(exist_ok=True); seg = post / "seg"; seg.mkdir(exist_ok=True); parts = []
    for r in e["shots"]:
        src = OUT / "h3" / r["id"] / "clip.mp4"; v = vsr / f"{r['id']}.mp4"
        if v.exists() and v.stat().st_mtime < src.stat().st_mtime:
            v.unlink()                               # 重拍過：重新放大（upscale_vsr.py 不覆寫舊檔）
        if not v.exists():
            run([PYH3, T / "upscale_vsr.py", "--source", src, "--output", v])
        p = seg / f"{r['id']}.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{r['src_in']:.3f}", "-i", v, "-frames:v", str(round(r["dur"] * FPS)), "-an",
             "-vf", "scale=1920:1080:flags=lanczos,fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "medium", p])
        parts.append(p)
    if CFG.get("ending"):
        parts.append(OUT / "ending" / "ending.mp4")
    (post / "list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", post / "list.txt", "-c", "copy", post / "video.mp4"])
    vtotal = dur(post / "video.mp4"); n = int(vtotal * SR) + SR
    voice = np.zeros(n, np.float32); amb_ = np.zeros(n, np.float32); duck = np.ones(n, np.float32)
    under = MIX.get("music_under_lines", 0.30)
    for r in e["shots"]:
        for l in r["lines"]:
            a = load(l["file"]); s0 = int(l["film_start"] * SR); voice[s0:s0 + len(a)] += a[: n - s0]
            duck[max(0, int((l["film_start"] - 0.25) * SR)):int((l["film_end"] + 0.35) * SR)] = under
        if r.get("amb"):                             # amb 階段確認過沒有人聲的 H3 原生音效
            a = load(r["amb"])[int(r["src_in"] * SR):int(r["src_out"] * SR)]
            fade = np.minimum(1, np.minimum(np.arange(len(a)) / (0.15 * SR), (len(a) - np.arange(len(a))) / (0.15 * SR)))
            s0 = int(r["start"] * SR); amb_[s0:s0 + len(a)] += (a * fade * 0.8)[: n - s0]
    k = int(0.12 * SR); duck = np.convolve(duck, np.ones(k) / k, mode="same")
    mus = load(json.loads((post / "music_pick.json").read_text(encoding="utf-8"))["file"])[:n]; mus = np.pad(mus, (0, n - len(mus)))
    mus = mus / (np.sqrt((mus[: int(e["story_end"] * SR)] ** 2).mean()) + 1e-9) * MIX.get("music_bed_rms", 0.035)
    t = np.arange(n) / SR
    mix = voice + amb_ + mus * duck * np.clip((vtotal - t) / 3.0, 0, 1) * np.clip(t / 0.8, 0, 1)
    raw = post / "mix_raw.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(raw)],
                   input=mix[: int(vtotal * SR)].astype(np.float32).tobytes(), check=True)
    # 響度：量 → 固定增益 → 限幅（alimiter 一定要 level=false，預設會把峰值拉到 0 dBFS）→ 再量一次、差太多就補一次
    target = MIX.get("target_lufs", -15.5); gain = 0.0
    for _ in range(3):
        r = subprocess.run(["ffmpeg", "-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.78:level=false:attack=2:release=80,ebur128",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.findall(r"I:\s*(-?[\d.]+) LUFS", r.stderr); got = float(m[-1]) if m else target
        if abs(got - target) <= 0.4:
            break
        gain += target - got
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.78:level=false:attack=2:release=80", "-ar", str(SR),
         post / "mix.wav"])
    # 字幕（ASS，依說話者上色，放大到 1080p 之後才燒）
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
           "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
    for k, c in CHARS.items():
        hdr += f"Style: {k},Microsoft JhengHei,58,{c.get('sub_color', '&H00FFFFFF')},&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,1,0,1,4,1,2,60,60,70,1\n"
    ev = "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    caps = sorted([(l, r) for r in e["shots"] for l in r["lines"]], key=lambda x: x[0]["film_start"])
    for i, (l, r) in enumerate(caps):
        a = l["film_start"] - 0.05; b = l["film_end"] + 0.45
        if i + 1 < len(caps):
            b = min(b, caps[i + 1][0]["film_start"] - 0.1)
        b = min(b, r["start"] + r["dur"] - 0.04)
        ev += f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{l['who']},,0,0,0,,{CHARS[l['who']]['name']}：{l['text']}\n"
    (post / "subs.ass").write_text(hdr + ev, encoding="utf-8")
    (OUT / "cut").mkdir(exist_ok=True)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", "post/video.mp4", "-i", "post/mix.wav", "-vf", "subtitles=post/subs.ass", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest",
         "cut/film_1080p.mp4"])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", OUT / "cut" / "film_1080p.mp4", "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "26",
         "-c:a", "aac", "-b:a", "128k", OUT / "cut" / "film_720p_phone.mp4"])
    print(f"成片 out/cut/film_1080p.mp4（{vtotal:.2f} 秒）", flush=True)


@stage("review")
def review():
    """自審五遍（review.py）：1 逐鏡抽格、2 成片聽寫、3 雜訊、4 黑畫面／定格／響度、5 切點明暗／台詞重疊／台詞被鏡尾切掉。"""
    c = OUT / "cut" / "film_1080p.mp4"
    r1 = run([PYH3, HERE / "review.py", c], check=False); print(r1.stdout[-3000:], flush=True)
    r2 = run([PYV, HERE / "review.py", c, "--asr"], check=False); print(r2.stdout[-2000:], flush=True)
    print("→ 看 out/review/：film_1080p_pass1.jpg、pass5_cuts.jpg、review.json、asr.json；最後一定要人看成片", flush=True)


STAGES = dict(chars=chars, masters=masters, frames=frames, voices=voices, h3=h3, amb=amb, edl=edl, music=music, ending=ending, cut=cut, review=review)

if __name__ == "__main__":
    names = [a for i, a in enumerate(ARGS) if a in STAGES]
    if not comfy_ok():
        sys.exit(f"ComfyUI not running at {HOST}: call configs\\profile.cmd, then C:\\AI\\tools\\start_comfy.cmd")
    for name in (names or list(STAGES)):
        STAGES[name]()
    print("timing", json.dumps({k: v["sec"] for k, v in timing.items()}, ensure_ascii=False), flush=True)
