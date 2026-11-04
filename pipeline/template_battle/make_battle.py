"""饒舌對決範本（橫式 1920x1080、24 fps）：讀 battle.json，從兩首歌一路做到成片＋自審。做新的一場只改 battle.json。
Voice venv 執行（librosa、stable-ts 在這個環境；生圖、H3、放大會自己叫 H3 venv）。ComfyUI 要先開（tools/start_comfy.cmd）：
  <Voice venv>/python make_battle.py [stage ...] [--battle 別的設定.json] [--ver 1]
stage（不給＝全部依序；songtext、yue 不在預設順序裡）：
  songtext  把歌詞、風格寫成 Suno／YuE2 可直接貼的文字檔（out/songtext/）→ 去生歌，挑好的放 song/A.mp3、song/B.mp3
  yue       （沒有 Suno 時）YuE2 14 版每人抽 YUE_SEEDS 首（預設 10）→ 只留目標 BPM、逐句聽寫排序 → 第一名放到 song/（一定要人聽）
  songs     兩首歌：分人聲 → 歌詞強制對齊 → 逐句聽寫、BPM、最後一個字唱完的時間 → out/song/
  dj        DJ 聲音：Breeze 設計參考音 → Ming-3.0-TTS 每句 4 候選（不合格句尾改「……」再抽 4）聽寫自動挑 → out/voice/ming/
            （DJ_TTS=breezyvoice＝舊做法：BreezyVoice 每句 8 候選 → out/voice/bv/）
  audio     全片音軌：A 整首 → 停在拍上 → 1 小節 → B 整首 → 收尾淡出；DJ 口白插進前奏與片尾 → out/audio/
  chars     角色參考照（兩位饒舌手、DJ、麥克風）→ out/chars/
  scenes    擂台母版（空景）→ out/scenes/arena.png
  frames    每鏡首幀 → out/first/<鏡>.png＋接觸表 out/first/_sheet.jpg（人工關卡 1）
  specs     每鏡 H3 spec（對嘴音軌、限制句）→ out/h3/<鏡>/
  h3        跑 H3（本機／Colab／兩邊一起，同 template_local）→ out/h3/<鏡>/clip.mp4＋out/review/clips_*.jpg（人工關卡 2）
  cut       放大 → 剪接 → 字卡 → 音軌 −16 LUFS＋觀眾聲 → 字幕攻擊特效 → out/cut/<片名>_v<N>_1920x1080.mp4＋手機版
  review    每秒一格接觸表、H3 自己切鏡偵測、響度 → out/review/（人工關卡 3：一定要人看完整成片）
  srt       YouTube 字幕檔 → out/cut/<片名>_v<N>.srt
已存在的輸出會跳過（中斷後重跑會接著做）。重做某一鏡：刪 out/first/<鏡>.png 或 out/h3/<鏡>/clip.mp4，或在 battle.json 那鏡加 seed_bump。
還沒跑 H3 的鏡，cut 會用首幀靜態圖代替（沒有首幀就用灰底鏡號），可以先看節奏（animatic）。
由原頻道四場對決（〈圓周率之戰〉〈以吏為師之戰〉〈微積分之戰〉〈正名之戰〉，2026-10-26～28）的腳本整理而成。"""
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ARGS = sys.argv[1:]
CFG_FILE = HERE / (ARGS[ARGS.index("--battle") + 1] if "--battle" in ARGS else "battle.json")
CFG = json.loads(CFG_FILE.read_text(encoding="utf-8"))
VER = ARGS[ARGS.index("--ver") + 1] if "--ver" in ARGS else "1"
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
REPO = (HERE / CFG.get("repo_dir", "../..")).resolve()
AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
T = Path(os.environ.get("AI_TOOLS", str(AI / "tools")))
_EXE = "Scripts/python.exe" if os.name == "nt" else "bin/python"
PYH3 = os.environ.get("PY_H3", str(AI / "H3" / "venv" / _EXE))
PYV = os.environ.get("PY_VOICE", str(AI / "Voice" / "venv" / _EXE))
PYB = os.environ.get("PY_BREEZE", str(AI / "BreezeTTS" / "venv" / _EXE))
PYBV = os.environ.get("PY_BREEZYVOICE", str(AI / "BreezyVoice" / "venv" / _EXE))
SEP = str(Path(PYV).parent / ("audio-separator.exe" if os.name == "nt" else "audio-separator"))
SEP_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
DJ_TTS = os.environ.get("DJ_TTS", "ming")    # ming（預設：MIT 可營利、台灣腔）｜breezyvoice（2026-10-28 以前的做法）
UPSCALE = os.environ.get("UPSCALE", "rtxvsr" if os.name == "nt" else "lanczos")   # rtxvsr（只有 Windows）｜lanczos
SR, FPS, W, H = 48000, 24, 1920, 1080
R, DJ = CFG["rappers"], CFG["dj"]
LANG = CFG.get("lang", "zh")                # zh｜en（英文對決：對齊、聽寫、字幕、H3 台詞語言）
DIST = {"ECU": "an extreme close-up of the face", "CU": "a close-up from the chest up", "MCU": "a medium close-up from the waist up",
        "MS": "a medium shot from the knees up", "WIDE": "a wide shot"}
CLOSE = ("ECU", "CU", "MCU")
HOLD, REL = 0.25, 0.6                        # A 的收尾：最後一拍留 0.25 秒原音＋0.6 秒短衰減（停在拍上，不淡出）
TIMING = OUT / "timing.json"
timing = json.loads(TIMING.read_text(encoding="utf-8")) if TIMING.exists() else {}


# ------------------------------------------------------------------------------------------------ 共用
def run(cmd, cwd=HERE, check=True, **kw):
    print("$", " ".join(map(str, cmd))[:220], flush=True)
    env = {**os.environ, **kw.pop("env", {}), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, stdin=subprocess.DEVNULL, **kw)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))[:220]}\n{(r.stdout + r.stderr)[-2500:]}")
    return r


def stage(name):
    def deco(fn):
        def wrap():
            t0 = time.time(); a = time.strftime("%H:%M:%S"); fn()
            timing[name] = dict(sec=round(time.time() - t0, 1), start=a, end=time.strftime("%H:%M:%S"))
            TIMING.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[stage] {name} {timing[name]['sec']}s", flush=True)
        wrap.__name__ = name
        return wrap
    return deco


def free_comfy():
    try:
        r = urllib.request.Request(HOST + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r, timeout=30); time.sleep(5)
    except Exception:
        pass


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def newest(d, ext=".png"):
    fs = sorted(Path(d).glob(f"*{ext}"), key=lambda f: f.stat().st_mtime)
    return fs[-1] if fs else None


def load_audio(p, sr=SR):
    import librosa
    import numpy as np
    a, _ = librosa.load(str(p), sr=sr, mono=False)
    return (a.T if a.ndim > 1 else np.stack([a, a], 1)).astype(np.float32)


def lines_of(k):
    """一位饒舌手的所有歌詞句（照順序）：sing＝送給歌曲模型的寫法（可用同音字修讀音），show＝字幕寫法。"""
    out = []
    for sec in R[k]["lyrics"]:
        for ln in sec["lines"]:
            out.append(dict(ln, section=sec["sec"]))
    return out


def show_text(ln):
    if ln.get("show"):
        return ln["show"]
    t = ln["sing"]
    for a, b in CFG.get("show_replace", []):
        t = t.replace(a, b)
    return re.sub(r"\s+", "", t)


def rhyme_show(ln):
    t = ln.get("rhyme", "")
    for a, b in CFG.get("show_replace", []):
        t = t.replace(a, b)
    return ln.get("rhyme_show", t)


# ------------------------------------------------------------------------------------------------ 歌
YUE_SEC = [("pre", "PRE-CHORUS"), ("hook", "CHORUS"), ("chorus", "CHORUS"), ("final", "CHORUS"), ("climax", "CHORUS"),
           ("bridge", "BRIDGE"), ("verse", "VERSE"), ("outro", "OUTRO")]


@stage("songtext")
def songtext():
    """Suno（網頁 Custom 模式或 Kie API）與 YuE2 14 版可以直接用的歌詞、風格文字檔。"""
    d = OUT / "songtext"; d.mkdir(exist_ok=True)
    for k, r in R.items():
        su = "\n\n".join(f"[{s['sec']}]" + "".join("\n" + ln["sing"] for ln in s["lines"]) for s in r["lyrics"]) + "\n\n[End]\n"
        (d / f"suno_{k}_lyrics.txt").write_text(su, encoding="utf-8")
        (d / f"suno_{k}_style.txt").write_text(r.get("suno_style", ""), encoding="utf-8")
        yue = []
        for s in r["lyrics"]:
            if not s["lines"]:
                continue                                       # YuE2 不要空段落（14 版範本：空的 Intro／Interlude 會變差）
            tag = next((v for key, v in YUE_SEC if key in s["sec"].lower()), "VERSE")
            for i in range(0, len(s["lines"]), 4):             # 每段 4 句
                yue.append(f"[{tag}]\n" + "\n".join(ln["sing"] for ln in s["lines"][i:i + 4]))
        (d / f"yue_{k}_lyrics.txt").write_text("\n\n".join(yue) + "\n", encoding="utf-8")
        (d / f"yue_{k}_style.txt").write_text(r.get("yue_style", ""), encoding="utf-8")
        n = len(r.get("suno_style", ""))
        print(f"{k} {r['name']}：Suno 風格 {n} 字元" + ("（⚠ 超過 1000，Suno 會擋）" if n > 1000 else ""), flush=True)
    print(f"→ {d}\n"
          "  Suno 網頁：Create → Custom，Lyrics 貼 suno_<A|B>_lyrics.txt、Styles 貼 suno_<A|B>_style.txt，每人各生一首（同一首歌分兩人＝同一個聲音）\n"
          "  Kie API：python kie_suno.py submit A／poll A（環境變數 KIE_API_KEY）\n"
          "  YuE2（沒有 Suno 時）：tools/yue_song.py …--style yue_A_style.txt --lyrics yue_A_lyrics.txt → tools/pick_song.py 挑\n"
          "  挑好的歌放到 battle.json 的 rappers.<A|B>.song（預設 song/A.mp3、song/B.mp3）", flush=True)


@stage("yue")
def yue():
    """沒有 Suno 時：YuE2 14 版（templates/song_yue2_v14）每人抽 YUE_SEEDS 首 → pick_song.py 只留目標 BPM（YuE2 約一半會跑掉）、逐句聽寫排序
    → 第一名轉成 rappers.<A|B>.song。目標 BPM＝rappers.<A|B>.yue_bpm，沒填就讀 yue_style 裡的「NNN BPM」。ComfyUI 要開著（Colab 上也能跑）。
    ⚠ 聽寫排序只是初篩，一定要人聽 out/yue/<A|B>/ 的候選；要換就把那首轉檔覆蓋 song/ 裡的檔，再跑 songs。"""
    if not (OUT / "songtext" / "yue_A_lyrics.txt").exists():
        songtext()
    seeds = os.environ.get("YUE_SEEDS", ",".join(map(str, range(1, 11))))
    for k, r in R.items():
        dst = (HERE / r["song"]).resolve()
        if dst.exists():
            print(f"{k}：{dst} 已經有了，跳過（要重生就刪掉它）", flush=True)
            continue
        d = OUT / "yue" / k; lyr = OUT / "songtext" / f"yue_{k}_lyrics.txt"
        run([PYV, T / "yue_song.py", "battle", k, "--style", OUT / "songtext" / f"yue_{k}_style.txt", "--lyrics", lyr, "--out", d, "--seeds", seeds])
        free_comfy()                                           # 讓聽寫模型有顯存
        m = re.search(r"(\d+(?:\.\d+)?)\s*BPM", r.get("yue_style", ""))
        bpm = r.get("yue_bpm") or (float(m.group(1)) if m else None)
        run([PYV, T / "pick_song.py", d, lyr] + (["--bpm", bpm] if bpm else []))
        pick = json.loads((d / "pick.json").read_text(encoding="utf-8"))
        if not pick:
            raise SystemExit(f"{k}：{seeds} 這幾首都不是目標 BPM（{bpm}）→ 多抽幾個 seed（YUE_SEEDS=11,12,...,20）"
                             f"或在 battle.json 填 rappers.{k}.yue_bpm（librosa 實際量到的值）")
        best = next(iter(pick))
        dst.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", d / best, dst])
        print(f"{k} {r['name']}：{len(pick)} 首拍速對，第一名 {best} {pick[best]} → {dst}", flush=True)
    print("→ 一定要人聽 out/yue/<A|B>/ 的候選（排序在 pick.json）：唱錯字、聲音不像角色就換一首或多抽", flush=True)


def sep_stems(src, d):
    """BS-RoFormer 分出人聲與伴奏（只做一次）。"""
    d.mkdir(parents=True, exist_ok=True)
    voc = next(d.glob(f"{src.stem}_(Vocals)*"), None); ins = next(d.glob(f"{src.stem}_(Instrumental)*"), None)
    if voc is None or ins is None:
        run([SEP, src, "--model_filename", SEP_MODEL, "--model_file_dir", AI / "Voice" / "models" / "separator", "--output_dir", d,
             "--output_format", "FLAC"])
        voc = next(d.glob(f"{src.stem}_(Vocals)*")); ins = next(d.glob(f"{src.stem}_(Instrumental)*"))
    return voc, ins


def vocal_gaps(voc, rows, min_gap=3.0):
    """逐句之間有沒有「人聲還在唱、歌詞卻沒對到」的空檔（Suno 常自己把副歌多唱一遍；〈瑜亮之戰〉v1 誤當器樂段，字幕和唱的人都漏了）。"""
    import librosa
    import numpy as np
    v, sr = librosa.load(str(voc), sr=16000)
    rms = lambda a, b: float(np.sqrt(np.mean(v[int(a * sr):int(b * sr)] ** 2)))
    sung = float(np.median([rms(x["start"], x["end"]) for x in rows if x["end"] - x["start"] > 0.3]))
    return [(round(x["end"], 1), round(n["start"], 1)) for x, n in zip(rows, rows[1:]) if n["start"] - x["end"] >= min_gap and rms(x["end"] + 0.2, n["start"] - 0.2) > sung * 0.4]


def last_word_end(voc, word_end):
    """最後一個字唱完：強制對齊的最後一個詞結束時間（實測跟人工標的差 0–0.07 秒），人聲還很大聲就往後延，最多 0.3 秒。
    不用「人聲變小的時刻」：Suno 常在最後一句後面自己加觀眾喊聲、ad-lib，會被當成還在唱（實測晚 14 秒）。"""
    import numpy as np
    import soundfile as sf
    a, sr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
    hop = int(0.05 * sr); n = len(a) // hop
    rms = np.sqrt(np.mean(a[:n * hop].reshape(n, hop) ** 2, 1)); ref = np.sqrt(np.mean(rms[rms > 0] ** 2))
    i = int(word_end / 0.05)
    while i < min(n, int((word_end + 0.3) / 0.05)) and rms[i] >= 0.25 * ref:
        i += 1
    return round(max(word_end, i * 0.05), 3)


@stage("songs")
def songs():
    """兩首歌：分人聲 → 歌詞強制對齊（stable-ts）→ 逐句聽寫分數、BPM、最後一個字唱完的時間。
    整首直接聽寫會幻覺（「中文字幕志願者」），所以只做「對齊後逐句」聽寫；rap 的分數天生偏低（人工確認全對也只有 0.63–0.80），最後要人聽。"""
    import difflib
    import librosa
    import numpy as np
    import soundfile as sf
    sys.path.insert(0, str(T)); import stt; stt._add_cuda_dll_dirs()   # noqa: E401
    import opencc
    import stable_whisper
    free_comfy()
    d = OUT / "song"; d.mkdir(exist_ok=True)
    cc = opencc.OpenCC("s2twp")
    if LANG == "en":
        cc = type("NoCC", (), {"convert": staticmethod(lambda s: s)})()
    norm = (lambda s: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower().replace("\u00e9", "e"))).strip()) if LANG == "en" else \
        (lambda s: re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", cc.convert(s)).upper())
    m = stable_whisper.load_faster_whisper("large-v3", device="cuda", compute_type="float16", download_root=str(AI / "Voice" / "models" / "whisper"))
    rep = {}
    for k, r in R.items():
        src = (HERE / r["song"]).resolve()
        if not src.exists():
            raise SystemExit(f"找不到 {k} 的歌：{src}（先跑 songtext、生歌，挑好的放到這個路徑）")
        voc, ins = sep_stems(src, d / "sep")
        lines = lines_of(k)
        strip = (lambda t: re.sub(r"[\"“”]", "", t)) if LANG == "en" else (lambda t: re.sub(r"[：，、。！？「」『』（）—…]", " ", t))
        avoc = voc
        if r.get("align_from"):                                # 前奏有 Suno 自己加的喊話會把前幾句對齊拉走 → 對齊時把這秒數之前靜音
            a0, sr0 = sf.read(str(voc), dtype="float32", always_2d=True); a0[:int(float(r["align_from"]) * sr0)] = 0
            avoc = d / "sep" / f"{k}_align_input.wav"; sf.write(str(avoc), a0, sr0)
        res = m.align(str(avoc), "\n".join(strip(x["sing"]) for x in lines), language=LANG, original_split=True)
        if len(res.segments) != len(lines):
            raise SystemExit(f"{k}：對齊出 {len(res.segments)} 段、歌詞有 {len(lines)} 句（歌詞要跟送去生歌的一字不差）")
        a, sr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
        rows = []
        for ln, s in zip(lines, res.segments):
            x = librosa.resample(a[int(max(0, s.start - 0.1) * sr):int((s.end + 0.15) * sr)], orig_sr=sr, target_sr=16000)
            t = cc.convert((" " if LANG == "en" else "").join(z.text.strip() for z in m.transcribe(x, language=LANG, vad=False).segments))
            rows.append({"section": ln["section"], "text": ln["sing"], "start": round(s.start, 3), "end": round(s.end, 3),
                         "words": [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3)} for w in s.words],
                         "asr": t, "ok": round(difflib.SequenceMatcher(None, norm(ln["sing"]), norm(t)).ratio(), 2)})
        lw = r.get("last_word_end") or last_word_end(voc, rows[-1]["words"][-1]["e"] if rows[-1]["words"] else rows[-1]["end"])
        y, s2 = librosa.load(str(src), sr=22050); bpm = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=s2, start_bpm=float(CFG.get("bpm", 120)))[0])[0])
        info = {"song": str(src), "vocals": str(voc), "instrumental": str(ins), "bpm": round(bpm, 1), "last_word_end": lw, "rows": rows}
        (d / f"align_{k}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        rep[k] = {"bpm": round(bpm, 1), "char_ok": round(float(np.mean([x["ok"] for x in rows])), 2), "first": rows[0]["start"],
                  "last_word_end": lw, "low": [(x["text"][:16], x["ok"], x["asr"][:20]) for x in rows if x["ok"] < 0.5]}
        print(k, r["name"], json.dumps({q: v for q, v in rep[k].items() if q != "low"}, ensure_ascii=False), flush=True)
        for b in rep[k]["low"]:
            print("   低分句（去聽這句有沒有唱錯）：", b, flush=True)
        for g in vocal_gaps(voc, rows):
            print(f"   ⚠ {g[0]}–{g[1]} 秒人聲還在唱，但歌詞沒對到（Suno 多唱一遍？）→ 把那幾句補進歌詞，字幕和鏡頭才不會漏", flush=True)
    if abs(rep["A"]["bpm"] - rep["B"]["bpm"]) > 2:
        print(f"⚠ 兩首 BPM 不同（{rep['A']['bpm']} / {rep['B']['bpm']}）：A 停在拍上→1 小節→B 會接不準，建議重生成同一個 BPM", flush=True)
    (d / "songs_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ 最後一個字唱完的時間不對（例如尾巴有 Suno 自己加的喊聲）就在 battle.json 的 rappers.<A|B>.last_word_end 填秒數再跑 songs", flush=True)


# ------------------------------------------------------------------------------------------------ DJ 聲音
@stage("dj")
def dj():
    """Breeze 依文字設計 DJ 參考音（也可以放自己錄的 out/voice/ref_K.wav＋voice_sample 逐字稿）→ Ming-3.0-TTS 每句 4 候選、不合格的句尾改「……」
    再抽 4 → 聽寫自動挑（tools/make_ming.py）。原專案 2026-10-28 試聽 Ming「聲音非常的好，也沒有大陸腔」，MIT 可營利。
    DJ_TTS=breezyvoice＝舊做法（BreezyVoice 每句 8 候選，聽寫＋台灣國語答案卷比腔調）。"""
    free_comfy()
    vd = OUT / "voice"; vd.mkdir(exist_ok=True)
    jobs = [] if (vd / "ref_K.wav").exists() else [dict(name="ref_K", text=DJ["voice_sample"], instruction=DJ["voice_design"],
                                                        seed=int(DJ.get("voice_seed", 7)))]
    if DJ_TTS == "ming":
        if jobs:
            (OUT / "breeze.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
            run([PYB, T / "breeze_batch.py", "breeze.json"], cwd=OUT)
        mj = [dict(name=f"dj_{key}", text=DJ.get("tts", {}).get(key, text), ref_audio="voice/ref_K.wav", ref_text=DJ["voice_sample"])
              for key, text in DJ["lines"].items() if not (vd / "ming" / f"dj_{key}.wav").exists()]
        if not mj:
            return
        (OUT / "ming.json").write_text(json.dumps(dict(out_dir="voice/ming", seeds=4, extra_seeds=4, jobs=mj), ensure_ascii=False, indent=1),
                                       encoding="utf-8")
        run([PYV, T / "make_ming.py", "ming.json"], cwd=OUT)
        mp = json.loads((vd / "ming" / "asr_picks.json").read_text(encoding="utf-8"))
        bad = []
        for j in mj:
            p = mp.get(j["name"], {})
            best = next((c for c in p.get("cands", []) if c["file"] == p.get("pick")), {})
            print("pick", j["name"], j["text"], "→", p.get("pick"), best.get("asr", ""), flush=True)
            if p.get("needs_review"):
                bad.append(f"{j['name']}「{j['text']}」聽成「{best.get('asr', '')}」")
        if bad and os.environ.get("ALLOW_REVIEW") != "1":
            raise SystemExit("這幾句 Ming 候選聽寫都不對：" + "；".join(bad) + "\n在 battle.json 的 dj.tts 換這句的寫法（念錯的字換同音字、"
                             "逗號後別放太短的句子）或換說法，刪 out/voice/ming 裡那句的 cand 再跑 dj；確定只是 ASR 聽錯就用 ALLOW_REVIEW=1 繼續。")
        return
    for key, text in DJ["lines"].items():
        w = vd / f"tw_{key}.wav"
        if w.exists():
            continue
        mp3 = vd / f"tw_{key}.mp3"
        r = run([PYV, T / "gen_voice.py", "--engine", "edge", "--text", text, "--voice", DJ.get("edge_voice", "zh-TW-HsiaoChenNeural"),
                 "--out", mp3], cwd=OUT, check=False)
        if r.returncode == 0 and mp3.exists():
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "48000", "-ac", "1", w])
        else:                                              # 沒網路：改用 Breeze 產生答案卷（可靠度較低）
            jobs.append(dict(name=f"tw_{key}", text=text, instruction="A clear, neutral standard Taiwanese Mandarin news-reading voice, calm, precise tones.", seed=11))
    if jobs:
        (OUT / "breeze.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
        run([PYB, T / "breeze_batch.py", "breeze.json"], cwd=OUT)
    bv = [dict(name=f"dj_{key}", text=DJ.get("tts", {}).get(key, text), ref_audio="voice/ref_K.wav", ref_text=DJ["voice_sample"],
               tw_ref=f"voice/tw_{key}.wav", seeds=8) for key, text in DJ["lines"].items() if not (vd / "bv" / f"dj_{key}.wav").exists()]
    if bv:
        (OUT / "bv.json").write_text(json.dumps(dict(out_dir="voice/bv", jobs=bv), ensure_ascii=False, indent=1), encoding="utf-8")
        run([PYBV, T / "breezyvoice_batch.py", "bv.json"], cwd=OUT)
        run([PYV, T / "breezyvoice_pick.py", "bv.json"], cwd=OUT)
        bp = json.loads((vd / "bv" / "picks.json").read_text(encoding="utf-8"))
        bad = []
        for j in bv:
            p = bp[j["name"]]; best = next(c for c in p["cands"] if c["file"] == p["pick"])
            print("pick", j["name"], j["text"], "→", p["pick"], best["asr"], flush=True)
            if p["needs_review"]:
                bad.append(f"{j['name']}「{j['text']}」聽成「{best['asr']}」")
        if bad and os.environ.get("ALLOW_REVIEW") != "1":
            raise SystemExit("這幾句 8 個候選聽寫都不對：" + "；".join(bad) + "\n在 battle.json 的 dj.tts 加這句的寫法（念不準的字標注音，例："
                             "假[:ㄐㄧㄚ4]）或換說法，刪 out/voice/bv 再跑 dj；確定只是 ASR 聽錯就用 ALLOW_REVIEW=1 繼續。")


# ------------------------------------------------------------------------------------------------ 全片音軌
@stage("audio")
def audio():
    """A 整首（前奏改伴奏分軌，壓 DJ 開場）→ 最後一個字後的第一拍收 → 正好 1 小節後 B 的第一拍 → B 整首（前奏壓 DJ 換場）
    → B 最後一個字後換伴奏分軌，走到「最後一句小節線＋8 小節」、最後 2 小節淡出 →（DJ 定論）→ DJ 片尾 → 片尾卡。口白期間音樂壓 −5 dB。"""
    import librosa
    import numpy as np
    import soundfile as sf
    d = OUT / "audio"; d.mkdir(exist_ok=True)
    D = {}
    for k in R:
        al = json.loads((OUT / "song" / f"align_{k}.json").read_text(encoding="utf-8"))
        mix, voc, ins = load_audio(al["song"]), load_audio(al["vocals"]), load_audio(al["instrumental"])
        n = min(len(mix), len(voc), len(ins))
        _, b = librosa.beat.beat_track(y=librosa.to_mono(mix[:n].T), sr=SR, units="time", start_bpm=float(CFG.get("bpm", 120)))   # 慢歌要給 BPM 先驗，不然會抓成兩倍速
        rows = al["rows"]; period = float(np.median(np.diff(b)))
        D[k] = dict(mix=mix[:n], voc=voc[:n], inst=ins[:n], rows=rows, beats=b, period=period, lw=float(al["last_word_end"]),
                    one=float(b[np.argmin(np.abs(b - rows[0]["start"]))]))

    def beat_after(k, t):
        b = D[k]["beats"]; return float(b[b > t + 0.02][0])

    def bar_line(k, t):
        q = D[k]; bar = 4 * q["period"]; return q["one"] + bar * np.floor((t - q["one"]) / bar + 1e-6)

    def intro_inst(k):
        """前奏（開口前 0.3 秒以前）改用伴奏分軌：拿掉歌曲前奏裡的含糊喊話，免得跟 DJ 口白打架。"""
        q = D[k]; m = q["mix"].copy(); cut = int((q["rows"][0]["start"] - 0.3) * SR); x = int(0.12 * SR)
        if cut <= x + SR:
            return m
        w0 = max(0, cut - 4 * SR)
        g = np.sqrt(np.mean(q["mix"][w0:cut] ** 2)) / (np.sqrt(np.mean(q["inst"][w0:cut] ** 2)) + 1e-9)
        m[:cut - x] = q["inst"][:cut - x] * g
        m[cut - x:cut] = q["inst"][cut - x:cut] * g * np.linspace(1, 0, x)[:, None] + q["mix"][cut - x:cut] * np.linspace(0, 1, x)[:, None]
        return m

    A, B = D["A"], D["B"]
    barA, barB = 4 * A["period"], 4 * B["period"]
    mA, mB = intro_inst("A"), intro_inst("B")
    a_stop = beat_after("A", A["lw"]); ia = int(a_stop * SR)
    btn = mA[ia:ia + int((HOLD + REL) * SR)].copy(); n0 = int(HOLD * SR)
    btn[n0:] *= np.exp(-np.linspace(0, 6.5, len(btn) - n0))[:, None]
    a_part = np.concatenate([mA[:ia], btn])
    b_hit = float(B["beats"][0])
    pause = barA - (HOLD + REL) - b_hit                       # A 收尾拍＋1 小節＝B 那首的第一拍

    # DJ 口白（dj 階段挑好的檔）
    vb = OUT / "voice" / ("ming" if DJ_TTS == "ming" else "bv")
    ref_rms = float(np.sqrt(np.mean(A["voc"][int(A["rows"][0]["start"] * SR):ia] ** 2)))
    clips = {}
    for key in DJ["lines"]:
        v = load_audio(vb / f"dj_{key}.wav"); e = np.abs(v).max(1); nz = np.where(e > 0.01)[0]
        v = v[max(0, nz[0] - 480):nz[-1] + 2400]
        clips[key] = v / (np.sqrt(np.mean(v ** 2)) + 1e-9) * ref_rms * 1.3
    b_first = B["rows"][0]["start"]
    need = (len(clips["switch"]) / SR + 1.2 + 1.0) if "switch" in clips else 0
    if need > b_first:                                        # B 的前奏太短塞不下換場口白 → 多停整數小節（觀眾聲墊著）
        extra = math.ceil((need - b_first) / barA); pause += extra * barA
        print(f"B 前奏 {b_first:.1f} 秒塞不下換場口白 → 多停 {extra} 小節", flush=True)
    D1_AT = 1.0
    open_len = len(clips["open"]) / SR if "open" in clips else 0
    PRE = round(max(0.0, D1_AT + open_len + 0.5 - (A["rows"][0]["start"] - 0.3)), 2) if open_len else 0.0
    sw = int((B["lw"] + 0.1) * SR)
    b_end = int((bar_line("B", B["rows"][-1]["start"]) + 8 * barB) * SR)
    hold = R["B"].get("end_on_hold")                          # Suno 在最後一句後面有長音、自己收掉：唱到底就結束，不換伴奏分軌（〈向日葵之戰〉v3）
    b_part = mB[:sw].copy() if hold else np.concatenate([mB[:sw], B["inst"][sw:b_end]])
    keep_stop = R["B"].get("keep_stop")                       # 最後一個音跟音樂一起停、停一下再進器樂收尾：人聲慢一點收，那個空檔不補（〈向日葵之戰〉v4）
    x = int((0.12 if keep_stop else 0.05) * SR)
    if hold:
        b_part[-x:] *= np.linspace(1, 0, x)[:, None]
    else:
        b_part[sw - x:sw] = mB[sw - x:sw] * np.linspace(1, 0, x)[:, None] + B["inst"][sw - x:sw] * np.linspace(0, 1, x)[:, None]
    if CFG.get("tail_ring", True) and not hold and not keep_stop:
        from scipy.signal import butter, sosfilt
        h_ = sosfilt(butter(2, 300, "hp", fs=SR, output="sos"), b_part[sw:].mean(1))
        hop = int(0.05 * SR); e_ = np.sqrt(np.convolve(h_ ** 2, np.ones(hop) / hop, "same"))[::hop]
        low = np.flatnonzero(e_ < np.median(e_) * 0.12)
        for i in low:                                          # 每個破洞格用前一小節（再不行前兩小節）同拍位補，交叉 20 ms
            i0 = sw + i * hop - hop; i1 = i0 + 2 * hop; x_ = int(0.02 * SR)
            for k_ in (1, 2):
                j0 = i0 - int(k_ * barB * SR)
                if j0 > sw and e_[max(0, (j0 - sw) // hop)] >= np.median(e_) * 0.3:
                    w_ = np.ones((i1 - i0, 1), np.float32); w_[:x_] = np.linspace(0, 1, x_)[:, None]; w_[-x_:] = np.linspace(1, 0, x_)[:, None]
                    b_part[i0:i1] = b_part[i0:i1] * (1 - w_) + b_part[j0:j0 + i1 - i0] * w_
                    break
        if len(low):
            print(f"伴奏破洞補了 {len(low)} 格（50 ms）", flush=True)
    if not hold:
        f = int(2 * barB * SR); b_part[-f:] *= np.linspace(1, 0, f)[:, None] ** 1.3
    ga = np.sqrt(np.mean(A["mix"][int(A["rows"][0]["start"] * SR):ia] ** 2))
    gb = np.sqrt(np.mean(B["mix"][int(b_first * SR):sw] ** 2))
    g = float(ga / gb)                                        # 兩人饒舌段一樣大聲
    t_a = PRE
    t_b = t_a + (len(a_part) + int(pause * SR)) / SR
    if CFG.get("tail_ring", True):                             # B 前奏淡入，不要在 A 的殘響上突然進來
        f = int(1.2 * SR); b_part[:f] *= np.linspace(0.1, 1, f)[:, None]
    music = np.concatenate([np.zeros((int(PRE * SR), 2), np.float32), a_part, np.zeros((int(pause * SR), 2), np.float32), b_part * g])
    music_end = len(music) / SR
    mix = np.concatenate([music, np.zeros((int(14 * SR), 2), np.float32)])
    if CFG.get("tail_ring", True):                             # 殺句後不准突然切斷（使用者 2026-11-03）：最後一個字和收尾拍留殘響，蓋過硬停和換伴奏的落差；時間軸不動
        from scipy.signal import fftconvolve
        rng = np.random.default_rng(7)

        def ring(seg, sec, wet):
            n = int(sec * SR); tt = np.arange(n) / SR
            out = []
            for c in range(2):
                ir = rng.standard_normal(n) * np.exp(-6.9 * tt / sec)
                ir = np.convolve(ir, np.ones(9) / 9, "same")   # 去掉刺耳的高頻
                out.append(fftconvolve(seg[:, c], ir / np.sqrt(np.sum(ir ** 2))))
            return np.stack(out, 1).astype(np.float32) * wet

        for t0, src, sec, wet in ((t_a + a_stop - 0.35, mA[ia - int(0.35 * SR):ia + int(HOLD * SR)], 3.4, 0.6),
                                  (t_b + B["lw"] + 0.1 - 0.5, mB[sw - int(0.5 * SR):sw] * g, 3.0, 0.6)):
            r = ring(src, sec, wet); i0 = int(t0 * SR); f = int(0.03 * SR); r[:f] *= np.linspace(0, 1, f)[:, None]
            mix[i0:i0 + len(r)] += r[:max(0, len(mix) - i0)]
    voc = np.zeros_like(mix)
    voc[int(t_a * SR):int(t_a * SR) + ia] = A["voc"][:ia]
    vbb = B["voc"][:sw] * g; i0 = int(t_b * SR); voc[i0:i0 + len(vbb)] = vbb[:len(voc) - i0]
    place = {"open": D1_AT, "switch": t_b + b_first - 1.2 - len(clips.get("switch", [])) / SR,
             "verdict": t_b + B["lw"] + 3.2}
    djw = np.zeros_like(mix); pos = {}
    for key in ("open", "switch", "verdict", "end"):
        if key not in clips:
            continue
        v = clips[key]
        st = place.get(key) if key != "end" else max(music_end + 0.3, pos.get("verdict", [0, 0])[1] + 0.9)
        e1 = int(st * SR) + len(v)
        if e1 > len(mix):
            pad = e1 - len(mix) + SR
            mix, voc, djw = (np.concatenate([z, np.zeros((pad, 2), np.float32)]) for z in (mix, voc, djw))
        i0 = int(st * SR); djw[i0:i0 + len(v)] += v
        pos[key] = [round(st, 3), round(st + len(v) / SR, 3)]
        r = int(0.15 * SR); a0, a1 = max(0, i0 - r), min(len(mix), i0 + len(v) + r)
        env = np.ones(a1 - a0, np.float32) * 0.56; env[:r] = np.linspace(1, 0.56, r); env[-r:] = np.linspace(0.56, 1, r)
        mix[a0:a1] *= env[:, None]
    if "verdict" in pos and CFG.get("verdict_bed", True):    # 定論口白很長：B 的尾奏淡出後墊 A 前奏的伴奏（鬼魅管風琴）當底，−14 dB
        bed_src = A["inst"][:max(int(4 * SR), int((A["rows"][0]["start"] - 0.5) * SR))]
        v0, v1 = int(max(music_end - 3.0, pos["verdict"][0]) * SR), int((pos["verdict"][1] + 0.8) * SR)
        if v1 > v0:
            bed = np.resize(bed_src, (v1 - v0, 2)) * 0.2
            f = int(2.0 * SR); bed[:f] *= np.linspace(0, 1, f)[:, None]; bed[-f:] *= np.linspace(1, 0, f)[:, None]
            if v1 > len(mix):
                pad = v1 - len(mix) + SR
                mix, voc, djw = (np.concatenate([z, np.zeros((pad, 2), np.float32)]) for z in (mix, voc, djw))
            mix[v0:v1] += bed
    if "open" in pos and pos["open"][1] > t_a + A["rows"][0]["start"] - 0.2:
        print("⚠ DJ 開場口白壓到 A 第一句", pos["open"], flush=True)
    end_at = (pos["end"][1] if "end" in pos else music_end) + 8.0      # 片尾卡至少 8 秒
    if end_at * SR > len(mix):
        pad = int(end_at * SR) - len(mix)
        mix, voc, djw = (np.concatenate([z, np.zeros((pad, 2), np.float32)]) for z in (mix, voc, djw))
    else:
        mix, voc, djw = mix[:int(end_at * SR)], voc[:int(end_at * SR)], djw[:int(end_at * SR)]
    mix = mix + djw
    pk = max(1.0, np.abs(mix).max() / 0.97); mix /= pk
    sf.write(d / "mix.wav", mix, SR, subtype="PCM_16"); sf.write(d / "vocals.wav", voc / pk, SR, subtype="PCM_16")
    sf.write(d / "dj.wav", djw, SR, subtype="PCM_16")

    def lines(k, off):
        cap = D[k]["lw"]; out = []
        for ln, r in zip(lines_of(k), D[k]["rows"]):
            out.append({"who": k, "section": r["section"], "text": r["text"], "show": show_text(ln), "zh": ln.get("zh", ""), "rhyme": ln.get("rhyme", ""),
                        "combo": ln.get("combo"),
                        "rhyme_show": rhyme_show(ln), "atk": ln.get("atk"), "start": round(r["start"] + off, 3),
                        **({"show_start": round(r["show_start"] + off, 3)} if r.get("show_start") else {}),
                        "end": round(min(r["end"], cap) + off, 3),
                        "words": [{"w": w["w"], "s": round(w["s"] + off, 3), "e": round(min(w["e"], cap) + off, 3)} for w in r["words"]]})
        return out
    la, lb = lines("A", t_a), lines("B", t_b)
    total = round(len(mix) / SR, 3)
    marks = {"a_first": la[0]["start"], "a_stop": round(t_a + a_stop, 3), "a_end": round(t_a + a_stop + HOLD + REL, 3), "b_zero": round(t_b, 3),
             "b_first": lb[0]["start"], "b_last": lb[-1]["end"], "music_end": round(music_end, 3), "total": total}
    tl = {"A": la, "B": lb, "marks": marks, "dj": {"pos": pos, "text": DJ["lines"]}, "pre": PRE, "b_gain": round(g, 3)}
    (d / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PRE", PRE, "| A stop", marks["a_stop"], "| B zero", marks["b_zero"], "| B first", marks["b_first"], "| B last", marks["b_last"],
          "| music end", marks["music_end"], "| total", total, "| B gain", round(g, 2), "| dj", pos, flush=True)


# ------------------------------------------------------------------------------------------------ 鏡表
def timeline():
    return json.loads((OUT / "audio" / "timeline.json").read_text(encoding="utf-8"))


def resolve_shots():
    """battle.json 的 shots（at＝開始時間的寫法）→ 每鏡 start／end（下一鏡的開始）。at 可以是：
    秒數｜["A", i]＝A 第 i 句開口前 0.12 秒（i＝-1：前 4 秒、-2：前 2.5 秒）｜["B", i]｜["dj", "open|switch|verdict|end", 偏移秒]
    ｜["mark", "a_first|a_stop|a_end|b_zero|b_first|b_last|music_end", 偏移秒]。"""
    tl = timeline(); mk = tl["marks"]; pos = tl["dj"]["pos"]

    def t_of(at):
        if isinstance(at, (int, float)):
            return float(at)
        if at[0] in ("A", "B"):
            ln = tl[at[0]]; i = at[1]
            return round(ln[0]["start"] - (4.0 if i == -1 else 2.5), 3) if i < 0 else round(ln[i]["start"] - 0.12, 3)
        if at[0] == "dj":
            return round(pos[at[1]][0] + at[2], 3)
        if at[0] == "djs":                                    # ["djs", key, 第幾句, 偏移]：DJ 口白某一句開口（ming_en.py 的 dj_<key>.json）
            mk_ = json.loads((OUT / "voice" / "ming" / f"dj_{at[1]}.json").read_text(encoding="utf-8"))
            return round(pos[at[1]][0] + mk_[at[2]]["start"] + at[3], 3)
        return round(mk[at[1]] + at[2], 3)
    end_still = round(pos["end"][1] + 0.4, 3) if "end" in pos else mk["music_end"]
    err = []
    for s in CFG["shots"]:
        err += [f"{s['id']} gfx {g}" for g in s.get("gfx", []) if g not in CFG.get("cards", {}) and g not in ("title", "vs")]
        err += [f"{s['id']} card {s['card']}（要 A／B／K）" for _ in [0] if s.get("card") and s["card"] not in ("A", "B", "K")]
        err += [f"{s['id']} subj {k}（要 A／B／K／T）" for k in s["subj"] if k not in ("A", "B", "K", "T")]
        err += [f"{s['id']} scene {s['scene']}（不在 places）" for _ in [0] if s["scene"] != "arena" and s["scene"] not in CFG.get("places", {})]
    if err:
        raise SystemExit("battle.json 有對不上的代號：" + "；".join(err))
    out = []
    for i, s in enumerate(CFG["shots"]):
        st = t_of(s["at"]); en = t_of(CFG["shots"][i + 1]["at"]) if i + 1 < len(CFG["shots"]) else end_still
        out.append(dict(s, start=st, end=en))
    bad = [(a["id"], b["id"], a["start"], b["start"]) for a, b in zip(out, out[1:]) if b["start"] <= a["start"] + 0.8]
    if bad:
        raise SystemExit(f"鏡頭太短（< 0.8 秒）或順序錯：{bad}（改 battle.json 這幾鏡的 at）")
    return out, (end_still, mk["total"])


def seed_for(s):
    return int(CFG.get("seed0", 8500)) + zlib.crc32(s["id"].encode()) % 900 + int(s.get("seed_bump", 0))


# ------------------------------------------------------------------------------------------------ 圖
IMG = CFG.get("image_backend", "qwen")       # qwen＝本機 Qwen-Image（gen_image.py）｜img25＝OpenAI Image 2.5（tools/img25.py，要金鑰）


def img_generate(prompt, dst, w, h, seed):
    dst = Path(dst); dst.parent.mkdir(parents=True, exist_ok=True)
    if IMG == "img25":
        sys.path.insert(0, os.environ.get("IMG25_DIR", str(T))); import img25   # noqa: E401  IMG25_DIR＝img25.py 所在資料夾（預設 tools/）
        f = img25.generate(prompt, dst.with_suffix(""), n=1, size="1536x864" if w > h else "1024x1024")[0]
        Path(f).replace(dst); return
    tmp = OUT / "_img"; tmp.mkdir(exist_ok=True)
    run([PYH3, T / "gen_image.py", "--prompt", prompt, "--width", w, "--height", h, "--seed", seed, "--prefix", f"battle/{dst.stem}",
         "--out", tmp])
    newest(tmp).replace(dst)


def img_edit(prompt, refs, dst, seed):
    dst = Path(dst); dst.parent.mkdir(parents=True, exist_ok=True)
    if IMG == "img25":
        sys.path.insert(0, os.environ.get("IMG25_DIR", str(T))); import img25   # noqa: E401  IMG25_DIR＝img25.py 所在資料夾（預設 tools/）
        f = img25.edit(prompt, [Path(r) for r in refs], dst.with_suffix(""), n=1, size="1536x864")[0]
        Path(f).replace(dst); return
    tmp = OUT / "_img"; tmp.mkdir(exist_ok=True)
    cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", prompt, "--seed", seed,
           "--prefix", f"battle/{dst.stem}", "--out", tmp]
    for r in refs:
        cmd += ["--ref", r]
    run(cmd); newest(tmp).replace(dst)


def who(k):
    return R[k] if k in R else DJ


def ref_word(i):
    return f"<image{i}>" if IMG == "qwen" else f"Image {i}"


@stage("chars")
def chars():
    """角色參考照：單人、灰底、腰上半身（docs/07 §1），外觀照 battle.json 的 look。不滿意：刪 out/chars/<A|B|K>.png、改 chars_seed 再跑。"""
    for k in ("A", "B", "K"):
        dst = OUT / "chars" / f"{k}.png"
        if dst.exists():
            continue
        c = who(k)
        p = ("Studio character reference photo for a historical film, single person only, one image (not a collage), medium close-up "
             "portrait from the waist up facing the camera, plain light grey seamless background, soft even studio light, sharp focus, "
             "realistic photograph with real skin texture. " + c["look"] + " A confident, charismatic expression. No text, no watermark, "
             "no microphone.")
        img_generate(p, dst, 1024, 1024, int(c.get("chars_seed", 11)))
    mic = OUT / "chars" / "MIC.png"
    if not mic.exists():
        img_generate("Product photo of one modern polished chrome vintage stand microphone on a tall chrome stand, plain light grey seamless "
                     "background, soft studio light, sharp focus, no logo, no text.", mic, 1024, 1024, 31)
    print("→ 看 out/chars/：臉、服裝、髮型要符合設定；兩位饒舌手要一眼分得出來（臉型、鬍型、頭飾都不同）", flush=True)


@stage("scenes")
def scenes():
    dst = OUT / "scenes" / "arena.png"
    if not dst.exists():
        if IMG == "img25":
            img_generate(CFG["arena"]["master"], dst, 1536, 864, 21)
        else:
            img_generate(CFG["arena"]["master"], dst, 2688, 1536, int(CFG["arena"].get("seed", 21)))
    print("→ 看 out/scenes/arena.png：左右兩半配色要跟上一場不一樣；不要有字、旗子、地板圖騰", flush=True)


def frame_prompt(s):
    """首幀提示詞＋參考圖。參考圖順序：畫面裡的人 → 擂台 → 麥克風（Qwen-Edit 最多 3 張，Image 2.5 最多 5 張）。"""
    cap = 3 if IMG == "qwen" else 5
    refs = [(k, OUT / "chars" / f"{k}.png") for k in s["subj"] if k in ("A", "B", "K")]
    if s["scene"] == "arena":
        if IMG == "qwen":                                  # Qwen-Edit 把第一張當底圖：擂台放第一張，否則雙人鏡會沿用定妝照的灰底（2026-10-28 實測）
            refs.insert(0, ("arena", OUT / "scenes" / "arena.png"))
        else:
            refs.append(("arena", OUT / "scenes" / "arena.png"))
        if any(k in s["subj"] for k in ("A", "B")):
            refs.append(("MIC", OUT / "chars" / "MIC.png"))
    refs = refs[:cap]
    keep = ""
    for i, (k, _) in enumerate(refs, 1):
        if k in ("A", "B", "K"):
            c = who(k)
            keep += f"Keep EXACTLY the same {c.get('person', 'man')} as {ref_word(i)}: same real face, hair and costume ({c['look']}). "
        elif k == "arena":
            keep += CFG["arena"]["keep"].replace("{ref}", ref_word(i)) + " "
        else:
            keep += f"Each rapper's microphone is EXACTLY the modern polished chrome vintage stand microphone of {ref_word(i)} (no logo). "
    text = s["frame"] + " " + (CFG.get("audience", "") if "T" in s["subj"] else "")
    if s["dist"] in CLOSE:
        text += f"CAMERA DISTANCE: {DIST[s['dist']]} - the subject fills most of the frame, faces large and sharp, nothing between subject and camera. "
    if s["scene"] != "arena":
        text += "Here there is NO microphone, no DJ equipment and no stage light. "
    light = CFG["arena"]["light"] if s["scene"] == "arena" else CFG["places"][s["scene"]]["light"]
    insert = s["scene"] != "arena"                             # 插入鏡：film_look 提到饒舌手會在空景畫人、提到舞台地板會多一圈漆（〈向日葵之戰〉F02、F07、F34）
    film = CFG.get("film_look_insert", CFG["film_look"]) if insert else CFG["film_look"]
    no_text = CFG["no_text"].replace(CFG["arena_only"], "") if insert and CFG.get("arena_only") else CFG["no_text"]
    look = (film + f", {light}. HORIZONTAL 16:9 widescreen frame, the picture fills the ENTIRE frame edge to edge - NO black bars, "
            "NO borders. ")
    p = (keep + "New photo: " + text + look + no_text) if IMG == "qwen" else (text + look + no_text + keep)
    return p, [r for _, r in refs]


def sheet(files, dst, cols=4, label=None):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    fs = [p for p in files if Path(p).exists()]
    if not fs:
        return
    tw, th = 480, 270; rows = (len(fs) + cols - 1) // cols
    im = Image.new("RGB", (cols * tw, rows * (th + 30)), (30, 30, 30)); f = ImageFont.truetype(font("jhbd"), 22)
    for i, p in enumerate(fs):
        x, y = (i % cols) * tw, (i // cols) * (th + 30)
        im.paste(Image.open(p).convert("RGB").resize((tw, th)), (x, y + 30))
        ImageDraw.Draw(im).text((x + 6, y + 3), label(p) if label else Path(p).stem, font=f, fill=(255, 220, 0))
    Path(dst).parent.mkdir(parents=True, exist_ok=True); im.save(dst, quality=85)


@stage("frames")
def frames():
    """每鏡首幀（still／custom 的鏡也要首幀，cut 會用）。動作鏡畫「動作開始前」的姿勢；擂台地板只有金圓環；不要字、旗子。"""
    shots, _ = resolve_shots()
    only = os.environ.get("ONLY", "").split()
    for s in shots:
        dst = OUT / "first" / f"{s['id']}.png"
        if dst.exists() or (only and s["id"] not in only) or s.get("custom"):
            continue
        p, refs = frame_prompt(s)
        (OUT / "first").mkdir(exist_ok=True); (OUT / "first" / f"{s['id']}.prompt.txt").write_text(p, encoding="utf-8")
        seed = 5101 + zlib.crc32(s["id"].encode()) % 900 + int(s.get("frame_seed_bump", 0))
        img_edit(p, refs, dst, seed) if refs else img_generate(p, dst, 1344, 768, seed)
        print("frame", s["id"], flush=True)
    sheet([OUT / "first" / f"{s['id']}.png" for s in shots], OUT / "first" / "_sheet.jpg")
    try:                                                       # 多出來的人：Qwen 常在單人鏡多畫一個人（驗證時 N05、L08）
        import cv2
        import numpy as np
        import battle_gfx as gfx
        extra = []
        for s in shots:
            p = OUT / "first" / f"{s['id']}.png"; subj = s.get("subj") or []
            if not p.exists() or not subj or any(k not in ("A", "B", "K") for k in subj):
                continue                                       # 群眾鏡、空景不查
            im = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)   # imread 讀不了中文路徑
            n = len([f for f in gfx.faces(im) if f[3] >= im.shape[0] * 0.08])
            if n > len(subj):
                extra.append(f"{s['id']}（{n} 張臉／{len(subj)} 位角色）")
        if extra:
            print("⚠ 首幀臉比角色多（可能多畫了人，也可能是劇情本來就有旁人，要看）：", "、".join(extra), flush=True)
    except Exception as e:
        print("（略過多人檢查：", e, "）", flush=True)
    print("→ 人工關卡 1：看 out/first/_sheet.jpg（臉、服裝、多手多腳、背景字、旗子；雙人鏡兩人要分得清）。重畫：刪該鏡 png，"
          "battle.json 那鏡加 frame_seed_bump 或改 frame，再跑 frames", flush=True)


# ------------------------------------------------------------------------------------------------ H3
CLEAN = ("One continuous shot with no cuts and no change of scene. No flags, no banners, no pennants, no coats of arms and no national "
         "emblems anywhere. Hands with correct anatomy, no extra people appear, no captions, no new text appears.")
KEEP_OLD = "The place stays exactly as in <Picture 1> for the whole shot: no stage lights, no microphones, no rappers, no DJ."
MIC_KEEP = "The chrome stand microphones keep exactly their shape and position."


def frames_for(sec):
    n = 0
    while 17 * n + 5 < sec * FPS:
        n += 1
    return max(17 * n + 5, 73)


def pron(k):
    return (who(k).get("pronoun", "he") if k in ("A", "B", "K") else "they")


@stage("specs")
def need_fresh_audio():
    """換了歌卻忘了跑 audio，specs、cut 會默默用舊混音（〈向日葵之戰〉v5 差點把舊音軌當新版交出去）。"""
    mix = OUT / "audio" / "mix.wav"
    newer = [r["song"] for r in R.values() if mix.exists() and (HERE / r["song"]).stat().st_mtime > mix.stat().st_mtime]
    if newer or not mix.exists():
        sys.exit(f"歌比 out/audio/mix.wav 新（{newer}）：先跑 audio，再跑 specs、cut")


def specs():
    """shots → out/h3/<鏡>/{spec.json, first.png, guide.wav, gen.json}。演唱鏡：對嘴音軌＝兩人人聲分軌（或 DJ 口白）那一段（audio.fixed）；
    無聲鏡：靜音、閉嘴。每鏡生成範圍＝[start−0.25, end+0.25]，17n+5 格、至少 73 格；預設 DMAD 4 步（draft）。雙人鏡只有第一位唱。"""
    need_fresh_audio()
    import librosa
    import numpy as np
    import shutil
    import soundfile as sf
    shots, _ = resolve_shots(); tl = timeline()
    lines = tl["A"] + tl["B"]
    src = {"song": OUT / "audio" / "vocals.wav", "dj": OUT / "audio" / "dj.wav"}
    locked = set(CFG.get("locked", []))
    rows = []
    for s in shots:
        sid, st, en, kind = s["id"], s["start"], s["end"], s["kind"]
        cs = 0.0 if st == 0 else round(st - 0.25, 3)
        nf = frames_for(en + 0.25 - cs)
        rows.append({"id": sid, "start": st, "end": en, "kind": kind, "clip_start": cs, "frames": nf})
        if s.get("still") or s.get("custom"):
            continue
        if not (OUT / "first" / f"{sid}.png").exists():
            print("skip（沒有首幀）", sid); continue
        d = OUT / "h3" / sid; d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT / "first" / f"{sid}.png", d / "first.png")
        is_dj = s.get("voice") == "dj"
        n = int(round(nf / FPS * SR)); g = np.zeros(n, np.float32)
        if kind == "sing":
            f = src["dj" if is_dj else "song"]; sr0 = sf.info(str(f)).samplerate
            a, _ = sf.read(str(f), dtype="float32", start=int(cs * sr0), frames=int(nf / FPS * sr0) + 10)
            a = a.mean(1) if a.ndim > 1 else a
            a = librosa.resample(a, orig_sr=sr0, target_sr=SR) if sr0 != SR else a
            a = np.pad(a, (0, max(0, n - len(a))))[:n]
            pre, fd = int((st - cs) * SR), int(0.06 * SR)
            if pre > fd:
                a[:pre - fd] = 0; a[pre - fd:pre] *= np.linspace(0, 1, fd)
            g = a / max(1e-6, np.abs(a).max()) * 0.89
        sf.write(d / "guide.wav", g, SR, subtype="PCM_16")
        subs = [{"key": k, "desc": who(k)["desc"] if k in ("A", "B", "K") else CFG.get("audience_desc", "the audience")} for k in s["subj"]]
        perf = [k for k in s["subj"] if k in ("A", "B", "K")]
        P = pron(perf[0]).capitalize() if perf else "They"
        if not perf:
            more = " The motion stays smooth and natural."
        elif s.get("calm"):
            more = (f" {P} moves slowly and deliberately: the head nods on the beat and the hands move slowly and stay sharp and clearly shaped; "
                    "no fast gestures, no flapping, no motion blur.")
        elif is_dj:
            more = f" {P} moves with big, warm, energetic host gestures; the clothes move too."
        elif kind == "sing":
            more = (f" Throughout the shot {pron(perf[0])} keeps performing like a battle rapper: the head moves on the beat, the shoulders move, "
                    "and the free hand gestures in rhythm at chest height.")
        else:
            more = " Meanwhile everyone breathes naturally, eyes blink, hair and fabric move slightly, and the light flickers softly."
        sh = {"camera": "The camera holds a static shot on a tripod.", "action": s["action"] + more}
        cons = [CLEAN]
        if kind == "sing":
            if is_dj:
                txt = " ".join(t for key, t in tl["dj"]["text"].items() if key in tl["dj"]["pos"] and
                               min(en, tl["dj"]["pos"][key][1]) - max(st, tl["dj"]["pos"][key][0]) >= 0.3) or "（主持人喊話）"
                cons.insert(0, f"{P} speaks the words heard in <Audio 1> like a lively host: lips, jaw and breathing follow every syllable of <Audio 1> exactly.")
            else:
                txt = " ".join(l["text"] for l in lines if min(en, l["end"]) - max(st, l["start"]) >= 0.3) or "（跟著節奏喊）"
                cons.insert(0, ("Only <Subject 1>" if len(perf) > 1 else P) + " raps the words heard in <Audio 1>: lips, jaw and breathing "
                            "follow every syllable and rhythm of <Audio 1> exactly.")
            sh["dialogue"] = [{"subject": perf[0], "line": txt, "lang": "English" if LANG == "en" else "Chinese"}]
            if len(perf) > 1:
                cons.insert(1, "<Subject 2> never speaks or raps: the mouth stays closed for the whole shot, only reacting with eyes and head.")
        elif perf:
            cons.insert(0, "Nobody speaks or sings; every mouth stays closed.")
        cons.append(CFG["arena"]["keep_h3"] if s["scene"] == "arena" else KEEP_OLD)
        if s["scene"] == "arena" and any(k in perf for k in ("A", "B")):
            cons.append(MIC_KEEP)
        if sid in locked:
            sh["camera"] = "The camera is locked on a tripod: no zoom, no push-in, no dolly; the framing stays exactly as in <Picture 1>."
            cons.append("The camera never moves closer: everyone stays fully in frame from the first to the last frame.")
        if s["scene"] != "arena" and CFG["places"][s["scene"]].get("text"):
            cons.append("Any text on paper, boards or screens stays exactly as in <Picture 1> and does not change.")
        cons += s.get("cons", [])
        era = "arena" if s["scene"] == "arena" else CFG["places"][s["scene"]].get("era", "period")
        style = CFG["arena"]["style"] if era == "arena" else CFG["style_modern"] if era == "modern" else CFG["style_period"]
        setting = CFG["arena"]["setting"] if s["scene"] == "arena" else CFG["places"][s["scene"]]["setting"]
        spec = {"duration": round(nf / FPS, 3), "size": [1344, 768], "seed": seed_for(s), "draft": s.get("draft", True),
                "style": style, "setting": setting, "first_frame": "first.png", "subjects": subs,
                "audio": {"fixed": {"file": "guide.wav"}}, "shots": [sh], "constraints": cons,
                "soundscape": "Only the voice from <Audio 1>." if kind == "sing" else "Quiet room tone only, no speech, no music.",
                "music": "N/A"}
        if s.get("veda") is not None:
            spec["veda"] = s["veda"]                           # 長鏡 Veda 會在約 5 秒處留下構圖跳動 → 該鏡設 false 重拍
        if s.get("last_first"):
            spec["last_frame"] = "first.png"                   # 尾幀＝首幀：防自己切鏡、冒旗子、冒道具（人會被鎖住不太動）
        (d / "gen.json").write_text(json.dumps({"clip_start": cs, "start": st, "end": en}), encoding="utf-8")
        new = json.dumps(spec, ensure_ascii=False, indent=1)
        if not (d / "spec.json").exists() or (d / "spec.json").read_text(encoding="utf-8") != new:   # 內容沒變就不重寫（不然已做好的鏡會被重跑）
            (d / "spec.json").write_text(new, encoding="utf-8")
    (OUT / "h3").mkdir(exist_ok=True)
    (OUT / "h3" / "timeline.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "shots; H3 frames", sum(r["frames"] for r in rows), flush=True)


def local_h3_ok():
    try:
        vram = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=20).stdout.split()[0]) / 1024
        return vram >= 15
    except Exception:
        return False


H3_BACKEND = os.environ.get("H3_BACKEND") or ("local" if local_h3_ok() else "colab")


@stage("h3")
def h3():
    """有 spec、還沒有 clip（或 spec 比 clip 新）的鏡都跑。H3_BACKEND＝local｜colab｜both（同 template_local）。"""
    only = os.environ.get("ONLY", "").split(); todo = []
    for d in sorted((OUT / "h3").iterdir()):
        sp, cl = d / "spec.json", d / "clip.mp4"
        if not sp.exists() or (only and d.name not in only):
            continue
        if not cl.exists() or cl.stat().st_mtime < sp.stat().st_mtime:
            todo.append(d)
    print(f"[h3] {len(todo)} 鏡（{H3_BACKEND}）", flush=True)
    if H3_BACKEND == "both":
        sys.path.insert(0, str(REPO / "cloud")); from hybrid_h3 import run_hybrid   # noqa: E402
        miss = run_hybrid(todo, PYH3, T)
        if miss:
            print("沒做出來：", " ".join(d.name for d in miss), flush=True)
    elif H3_BACKEND == "colab":
        run([sys.executable, REPO / "cloud" / "colab_h3.py", "batch"] + [d / "spec.json" for d in todo])
    elif os.environ.get("H3_PARALLEL") == "2" and todo:  # 全雲端模式（colab_h3.py film 設定）：2 個 ComfyUI、第二個晚 30 秒開跑（同 template_local）
        t0 = time.time(); r = run([PYH3, REPO / "cloud" / "vm" / "parallel_h3.py"] + todo, check=False)
        print((r.stdout + r.stderr)[-4000:], flush=True)
        fails = [d.name for d in todo if not ((d / "clip.mp4").exists() and (d / "clip.mp4").stat().st_mtime > t0)]
        if fails:
            print("失敗：", fails, "（上面 [parallel_h3] 有錯誤訊息）", flush=True)
    else:
        fails = []
        for d in todo:
            t0 = time.time(); r = run([PYH3, T / "h3_shot.py", d / "spec.json", "--out", d], check=False)
            ok = (d / "clip.mp4").exists() and (d / "clip.mp4").stat().st_mtime > t0
            print(time.strftime("[%H:%M:%S]"), d.name, "OK" if ok else "FAIL", f"{time.time() - t0:.0f}s", flush=True)
            if not ok:
                fails.append(d.name); (d / "run_err.txt").write_text((r.stdout + r.stderr)[-6000:], encoding="utf-8")
        if fails:
            print("失敗：", fails, "（看 out/h3/<鏡>/run_err.txt）", flush=True)
    clipsheet()


def used_range(s):
    g = OUT / "h3" / s["id"] / "gen.json"
    cs = json.loads(g.read_text(encoding="utf-8"))["clip_start"] if g.exists() else s["start"] - 0.25
    a = 0.25 if s["kind"] != "sing" else s["start"] - cs
    return a, a + (s["end"] - s["start"])


def clipsheet():
    """每鏡成片用到範圍的開頭／1/3／2/3／結尾 4 格 → out/review/clips_<n>.jpg（人工關卡 2：換臉、多出人、旗子、自己切鏡）。"""
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    shots, _ = resolve_shots(); rv = OUT / "review"; rv.mkdir(exist_ok=True)
    f = ImageFont.truetype(font("jhbd"), 20); rows = []
    for s in shots:
        c = OUT / "h3" / s["id"] / "clip.mp4"
        if not c.exists():
            continue
        a, b = used_range(s); tiles = []
        for t in (a + 0.05, a + (b - a) / 3, a + 2 * (b - a) / 3, b - 0.1):
            p = rv / "_t.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(c), "-frames:v", "1", "-vf", "scale=384:220", str(p)])
            tiles.append(Image.open(p).convert("RGB"))
        row = Image.new("RGB", (384 * 4 + 160, 220), (25, 25, 25)); ImageDraw.Draw(row).text((6, 90), s["id"] + "\n" + s["kind"], font=f, fill=(255, 220, 0))
        for i, t in enumerate(tiles):
            row.paste(t, (160 + i * 384, 0))
        rows.append(row)
    for k in range(0, len(rows), 8):
        part = rows[k:k + 8]; im = Image.new("RGB", (part[0].width, 224 * len(part)), (0, 0, 0))
        for i, r_ in enumerate(part):
            im.paste(r_, (0, i * 224))
        im.save(rv / f"clips_{k // 8}.jpg", quality=82)
    (rv / "_t.jpg").unlink(missing_ok=True)
    print(f"→ 人工關卡 2：out/review/clips_*.jpg（{len(rows)} 鏡）。重拍：battle.json 那鏡加 seed_bump（會自己切鏡／冒旗子的再加 last_first），"
          "跑 specs h3", flush=True)


# ------------------------------------------------------------------------------------------------ 成片
def sh_(cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True)


FIT = "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080"


def segment(s, seg_dir, vsr_dir):
    k = s["id"]; out = seg_dir / f"{k}.mp4"
    n = int(round(s["end"] * FPS)) - int(round(s["start"] * FPS))
    clip, first = OUT / "h3" / k / "clip.mp4", OUT / "first" / f"{k}.png"
    if s.get("custom"):
        src, mode = HERE / s["custom"], "custom"
    elif not s.get("still") and clip.exists():
        src, mode = clip, "clip"
    elif first.exists():
        src, mode = first, "still" if s.get("still") else "stand-in"
    else:
        src, mode = None, "slate"
    if src is not None and out.exists() and out.stat().st_mtime > src.stat().st_mtime and abs(dur(out) - n / FPS) < 0.5 / FPS:   # 差 1 格就重做：容許 0.05 秒時舊片段少 1 格沒重剪，累積到畫面比聲音早 3 格（〈瑜亮之戰〉v2 抓到）
        return out, mode
    if mode == "slate":
        sh_(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x303030:s=1920x1080:r=24", "-vf",
             f"drawtext=text='{k}':fontcolor=white:fontsize=120:x=(w-text_w)/2:y=(h-text_h)/2", "-frames:v", str(n), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", out])
    elif mode == "custom":
        sh_(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", f"{FIT},fps={FPS},setsar=1,tpad=stop_mode=clone:stop=-1", "-frames:v", str(n),
             "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", out])
    elif mode in ("still", "stand-in"):
        sh_(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", src, "-vf",
             f"{FIT},zoompan=z='1+{0.0003 if s.get('painting') else 0.0009}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,format=yuv420p",   # 名畫慢推小一點，不切到畫邊
             "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", out])
    else:
        v = clip
        if UPSCALE == "rtxvsr":
            v = vsr_dir / f"{k}.mp4"
            if v.exists() and v.stat().st_mtime < clip.stat().st_mtime:
                v.unlink()                                      # 重拍過：重新放大（upscale_vsr.py 不覆寫舊檔）
            if not v.exists():
                run([PYH3, T / "upscale_vsr.py", "--source", clip, "--output", v])
        a, _ = used_range(s)
        sh_(["ffmpeg", "-y", "-v", "error", "-ss", f"{round(a * FPS) / FPS:.4f}", "-i", v, "-an", "-vf", f"{FIT},fps={FPS},setsar=1",
             "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", out])
    return out, mode


def crowd_audio(total, attacks, end_still, roars=()):
    """觀眾聲：每次押韻攻擊後一聲歡呼、片尾墊歡呼（repo 的 sfx/歡呼，CC0）。H3 無聲鏡給的是靜音固定音軌，所以沒有原生人群聲。"""
    import numpy as np
    import soundfile as sf
    out = np.zeros((int(total * SR), 2), np.float32); srcs = []
    for f in sorted((REPO / CFG.get("crowd_sfx", "sfx/歡呼")).glob("*.mp3")):
        w = OUT / "post" / f"crowd_{len(srcs)}.wav"
        sh_(["ffmpeg", "-y", "-v", "error", "-i", f, "-vn", "-ac", "2", "-ar", str(SR), w])
        a, _ = sf.read(str(w), dtype="float32", always_2d=True)
        if len(a) > 2.5 * SR and np.abs(a).max() > 1e-3:
            a = a / (np.sqrt(np.mean(a ** 2)) + 1e-9)
            srcs.append(4 * np.tanh(a / 4))      # 拍手尖峰可達 RMS 的 13 倍 → 軟壓到 4 倍，否則 AAC 後真峰值衝到 +4 dBTP
    if not srcs:
        print("⚠ 沒有觀眾音效（sfx/歡呼）", flush=True); return out
    g = 10 ** (-24 / 20)
    for i, a in enumerate(attacks):
        s = srcs[i % len(srcs)]; seg = s[int(0.3 * SR):int(2.3 * SR)].copy()
        f = int(0.4 * SR); seg[-f:] *= np.linspace(1, 0, f)[:, None]; g0 = int(0.05 * SR); seg[:g0] *= np.linspace(0, 1, g0)[:, None]
        i0 = int((a["t"] + 0.12) * SR); out[i0:i0 + len(seg)] += seg[:max(0, len(out) - i0)] * g
    for r0, r1 in roars:                                       # 殺句後全場炸開：跟殘響一起接住硬停（DJ 開口前淡掉）
        i0, i1 = int(r0 * SR), min(int(r1 * SR), len(out)); s = sum(np.resize(np.roll(q, int(q_i * 0.37 * SR), axis=0), (i1 - i0, 2)) for q_i, q in enumerate(srcs)) / np.sqrt(len(srcs)) * 10 ** (-17 / 20)   # 單一段歡呼斷斷續續（4:01 有空洞）→ 幾段疊起來才連續
        f = int(0.2 * SR); s[:f] *= np.linspace(0, 1, f)[:, None]; f = int(1.6 * SR); s[-f:] *= np.linspace(1, 0, f)[:, None]
        out[i0:i1] += s
    e0, e1 = max(0, int(end_still[0] * SR) - int(0.2 * SR)), int(end_still[1] * SR)   # DJ 片尾口白講完才進歡呼（提早 4 秒會蓋掉「type PROVE」，2026-10-30）
    b = np.resize(np.concatenate(srcs), (e1 - e0, 2)) * 10 ** (-20 / 20)
    f = int(1.5 * SR); b[:f] *= np.linspace(0, 1, f)[:, None]; b[-f:] *= np.linspace(1, 0, f)[:, None]
    out[e0:e1] += b[:len(out) - e0]
    return out


@stage("cut")
def cut():
    need_fresh_audio()
    import numpy as np
    import soundfile as sf
    import battle_gfx as gfx
    shots, end_still = resolve_shots()
    post = OUT / "post"; seg_dir = post / "seg"; vsr_dir = post / "vsr"; spr = post / "sprites"; cutd = OUT / "cut"
    for d in (post, seg_dir, vsr_dir, spr, cutd):
        d.mkdir(parents=True, exist_ok=True)
    segs, modes = [], {}
    for s in shots:
        p, m = segment(s, seg_dir, vsr_dir); segs.append(p); modes[s["id"]] = m
    stand = [k for k, m in modes.items() if m in ("stand-in", "slate")]
    if stand:
        print(f"⚠ 這 {len(stand)} 鏡還沒有 H3，用首幀／鏡號代替：{' '.join(stand)}", flush=True)
    last = post / "last.png"                                   # 片尾：最後一鏡最後一格慢推＋投票卡
    sh_(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.05", "-i", segs[-1], "-frames:v", "1", "-update", "1", last])
    n = int(round(end_still[1] * FPS)) - int(round(end_still[0] * FPS))
    endp = seg_dir / "END.mp4"
    sh_(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", last, "-vf",
         f"{FIT},zoompan=z='1+0.0004*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,eq=brightness=-0.08,"
         f"fade=t=out:st={n / FPS - 1.2:.2f}:d=1.2,format=yuv420p", "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", endp])
    segs.append(endp)
    lst = seg_dir / "list.txt"; lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in segs), encoding="utf-8")
    vid = post / "video_raw.mp4"
    sh_(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])
    total = end_still[1]

    mix = OUT / "audio" / "mix.wav"; ln = post / "mix_ln.wav"          # 兩段式 −16 LUFS
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mix), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    js = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    sh_(["ffmpeg", "-y", "-v", "error", "-i", mix, "-af",
         f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
         f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,apad=whole_dur={total:.3f}",
         "-ar", str(SR), "-ac", "2", "-t", f"{total:.3f}", ln])
    m, _ = sf.read(str(ln), dtype="float32", always_2d=True); m = m[:int(total * SR)]
    ev = gfx.build_events(CFG, timeline())
    mk = timeline()["marks"]
    m = m + crowd_audio(total, ev["attacks"], end_still, roars=[(mk["a_stop"], mk["a_stop"] + 3.6), (mk["b_last"], mk["b_last"] + 3.2)])[:len(m)]
    raw = post / "final_raw.wav"; sf.write(raw, m, SR, subtype="FLOAT")
    # 加了觀眾聲之後再對一次響度：量 → 固定增益 → 限幅（alimiter 一定要 level=false；0.70≈−3.1 dBFS，AAC 之後真峰值才會 ≤ −1）
    gain = 0.0
    for _ in range(4):
        r = subprocess.run(["ffmpeg", "-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.70:level=false:attack=2:release=80,ebur128",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        got = re.findall(r"I:\s*(-?[\d.]+) LUFS", r.stderr)
        got = float(got[-1]) if got else -16.0
        if abs(got + 16.0) <= 0.3:
            break
        gain += -16.0 - got
    final_wav = post / "final_audio.wav"
    sh_(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.70:level=false:attack=2:release=80",
         "-ar", str(SR), "-c:a", "pcm_s16le", final_wav])

    ov, spans = [], []                                         # 字卡（字幕交給 battle_gfx.render_fx）
    for s in shots:
        for g in list(s.get("gfx") or []) + ([s["card"]] if s.get("card") else []):
            lastsp = next((sp for sp in reversed(spans) if sp["key"] == g), None)
            if lastsp and abs(lastsp["end"] - s["start"]) < 0.01:
                lastsp["end"] = s["end"]; lastsp["shots"].append(s)
            else:
                spans.append(dict(key=g, start=s["start"], end=s["end"], shots=[s]))
    report = []
    for sp in spans:
        p, size = gfx.card(CFG, sp["key"], spr / f"gfx_{sp['key']}.png")
        if sp["key"] in ("title", "vs"):
            x, y = (W - size[0]) // 2, (120 if sp["key"] == "title" else 760)
        else:
            boxes = sum((gfx.seg_faces(seg_dir / f"{s['id']}.mp4") for s in sp["shots"]), [])
            x, y = gfx.place(size, boxes)
            if any(s.get("painting") for s in sp["shots"]):       # 名畫靠右，字卡放左邊空位（ROUND 角標下面），不蓋畫
                x, y = 40, 150
        ov.append((p, sp["start"] + 0.15, sp["end"], int(x), int(y)))
        report.append(dict(card=sp["key"], start=sp["start"], end=sp["end"], xy=[int(x), int(y)], size=list(size)))
    (post / "card_layout.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    p, size = gfx.card(CFG, "end_vote", spr / "gfx_end_vote.png")
    ov.append((p, end_still[0] + 0.3, total, (W - size[0]) // 2, H - size[1] - 60))
    inputs = ["-i", vid]; fc, lastv = [], "0:v"
    for i, (p, a, b, x, y) in enumerate(ov):
        inputs += ["-i", p]
        fc.append(f"[{lastv}][{i + 1}:v]overlay={x}:{y}:enable='between(t,{a:.3f},{b:.3f})'[v{i}]"); lastv = f"v{i}"
    cards = post / "video_cards.mp4"
    sh_(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{lastv}]", "-c:v", "libx264", "-crf", "14",
         "-preset", "medium", "-pix_fmt", "yuv420p", cards])
    out = cutd / f"{CFG['title']}_v{VER}_1920x1080.mp4"
    gfx.render_fx(CFG, shots, ev, cards, out, final_wav, post)
    phone = cutd / f"{CFG['title']}_v{VER}_phone.mp4"; kbps = int(27e6 * 8 / total / 1000) - 96   # 手機版：兩段式定碼率約 27 MB
    for ps in (1, 2):
        sh_(["ffmpeg", "-y", "-v", "error", "-i", out, "-vf", "scale=1280:720", "-c:v", "libx264", "-b:v", f"{kbps}k", "-pass", str(ps),
             "-passlogfile", str(post / "phone2pass"), "-preset", "slow"] +
            (["-an", "-f", "null", "NUL" if os.name == "nt" else "/dev/null"] if ps == 1 else ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", phone]))
    print("成片", out, f"{total:.1f}s", f"手機版 {phone.stat().st_size / 1e6:.1f}MB", flush=True)


# ------------------------------------------------------------------------------------------------ 自審
def audio_checks():
    """使用者抓過的聲音問題自動查（review 會印）：濾掉 300 Hz 以下（手機喇叭放不出來）的單聲道音量破洞、突然掉音；最後一句之後人聲還在唱；對齊低分句。"""
    import librosa
    import numpy as np
    from scipy.signal import butter, sosfilt
    sr = 16000; m = timeline()["marks"]
    y = sosfilt(butter(4, 300, "hp", fs=sr, output="sos"), librosa.load(str(OUT / "audio" / "mix.wav"), sr=sr, mono=True)[0])
    db = lambda a: 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-7)
    h = int(0.05 * sr); end = int(m["music_end"] * sr)
    low = [db(y[i:i + h]) < -42 for i in range(0, end, h)]; holes = []; i = 0
    while i < len(low):
        j = i
        while j < len(low) and low[j]:
            j += 1
        if (j - i) * 0.05 >= 0.1 and i > 0:
            holes.append((round(i * 0.05, 2), round(j * 0.05, 2)))
        i = max(j, i + 1)
    e = [db(y[int(t * sr):int((t + 0.5) * sr)]) for t in np.arange(0, m["music_end"], 0.5)]
    drops = [(round(k * 0.5, 1), round(e[k - 1] - e[k], 1)) for k in range(1, len(e)) if e[k - 1] - e[k] >= 8]
    rep = dict(holes=holes, drops=drops, tail={}, low_ok={})
    for k in R:
        al = json.loads((OUT / "song" / f"align_{k}.json").read_text(encoding="utf-8")); rows = al["rows"]
        v = librosa.load(al["vocals"], sr=sr, mono=True)[0]
        sung = np.median([db(v[int(x["start"] * sr):int(x["end"] * sr)]) for x in rows if x["end"] - x["start"] > 0.3])
        t0 = rows[-1]["end"] + 0.3; on = [t for t in np.arange(t0, len(v) / sr - 1, 1.0) if db(v[int(t * sr):int((t + 1) * sr)]) > sung - 8]
        if len(on) >= 2:
            rep["tail"][k] = (round(float(on[0]), 1), round(float(on[-1]) + 1, 1))
        rep["low_ok"][k] = [(round(x["start"], 1), x["text"]) for x in rows if 0 <= x.get("ok", 1) < 0.3]
    (OUT / "review" / "audio_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("⚠ 音量／人聲檢查（每一條都要交代，見 review-checklist 第 H 節）：", flush=True)
    print("  音量破洞（300 Hz 以上，秒）：", holes, flush=True)
    print("  突然掉音（秒，掉幾 dB）：", drops, flush=True)
    print("  最後一句之後人聲還在唱（歌曲時間）：", rep["tail"], flush=True)
    print("  對齊低分句（一定要查，不准當成聽寫不準）：", rep["low_ok"], flush=True)


@stage("review")
def review():
    """每秒一格接觸表（時間碼・鏡號・當下歌詞）＋H3 自己切鏡偵測（用到的範圍內）＋響度。最後一定要人看完整成片。"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    audio_checks()
    shots, end_still = resolve_shots(); tl = timeline()
    video = OUT / "cut" / f"{CFG['title']}_v{VER}_1920x1080.mp4"
    rv = OUT / "review" / f"fc_v{VER}"; rv.mkdir(parents=True, exist_ok=True)
    F = ImageFont.truetype(font("jhbd"), 22); tiles = []
    allines = tl["A"] + tl["B"]
    for i in range(int(dur(video))):
        t = i + 0.5; p = rv / f"f_{i:03d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=640:360", str(p)])
        sid = next((s["id"] for s in shots if s["start"] <= t < s["end"]), "END")
        lyr = next((l["show"][:22] for l in allines if l["start"] - 0.05 <= t <= l["end"] + 0.25), "")
        im = Image.open(p).convert("RGB"); tile = Image.new("RGB", (640, 394)); tile.paste(im, (0, 34))
        ImageDraw.Draw(tile).text((6, 4), f"{int(t // 60)}:{t % 60:04.1f}  {sid}  {lyr}", font=F, fill=(255, 230, 0))
        tiles.append(tile)
    for k in range(0, len(tiles), 12):
        im = Image.new("RGB", (640 * 4 + 12, 394 * 3 + 8), (40, 40, 40))
        for j, tile in enumerate(tiles[k:k + 12]):
            im.paste(tile, ((j % 4) * 644, (j // 4) * 398))
        im.save(rv / f"sheet_{k // 12:02d}.jpg", quality=86)
    cc = {}                                                   # 自己切鏡：相鄰格平均差 > max(18, 6×中位數)；構圖漂走：跟第一格相關係數 < 0.7
    for s in shots:
        v = OUT / "h3" / s["id"] / "clip.mp4"
        if not v.exists() or s.get("still") or s.get("custom"):
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-vf", "scale=168:96,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        f = np.frombuffer(raw, np.uint8).reshape(-1, 96, 168).astype(np.float32)
        d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2)); thr = max(18.0, 6 * float(np.median(d)))
        a0 = f[0] - f[0].mean()
        corr = [float((a0 * (g - g.mean())).sum() / (np.linalg.norm(a0) * np.linalg.norm(g - g.mean()) + 1e-6)) for g in f]
        u0, u1 = used_range(s)
        bad = [round((i + 1) / FPS, 2) for i, x in enumerate(d) if x > thr and u0 <= (i + 1) / FPS <= u1]
        drift = next((round(i / FPS, 2) for i, c in enumerate(corr) if c < 0.7 and u0 <= i / FPS <= u1), None)
        if bad or drift is not None:
            cc[s["id"]] = dict(cuts=bad, drift=drift, used=[round(u0, 2), round(u1, 2)])
    (OUT / "review" / "cutcheck.json").write_text(json.dumps(cc, ensure_ascii=False, indent=1), encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace").stderr
    lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", r); tp = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", r)
    print(f"接觸表 {(len(tiles) + 11) // 12} 張 → {rv}", flush=True)
    print(f"響度 {lufs[-1] if lufs else '?'} LUFS、真峰值 {tp[-1] if tp else '?'} dBTP（目標 −16、≤ −1）", flush=True)
    print("可能自己切鏡／構圖漂走（走位多的鏡會誤報，要人看）：", {k: v for k, v in cc.items()} or "無", flush=True)
    print("→ 人工關卡 3：照 agent/skills/rap-battle/references/review-checklist.md 一張張看接觸表，最後一定要人看完整成片", flush=True)


@stage("srt")
def srt():
    import battle_gfx as gfx
    ev = gfx.build_events(CFG, timeline())
    names = {k: R[k]["name"] for k in R} | {"J": DJ.get("short", DJ["name"])}

    def ts(t):
        t = max(0.0, t); h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
    rows = [(l["start"], l["end"], f"{names[l['who']]}：{l['text'].replace('　', '，').replace('？，', '？').replace('！，', '！')}") for l in ev["lines"]]
    if ev["beats3"]:
        rows.append((ev["beats3"][0]["t"], ev["beats3"][-1]["t"] + 2.0, f"{names['J']}：" + timeline()["dj"]["text"]["end"]))   # 字幕檔照實際念的（end_beats 只是畫面大字）
    rows.sort()
    p = OUT / "cut" / f"{CFG['title']}_v{VER}.srt"; p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(rows, 1)), encoding="utf-8")
    print(p, len(rows), flush=True)


ORDER = [songs, dj, audio, chars, scenes, frames, specs, h3, cut, review, srt]
ALL = {f.__name__: f for f in ORDER + [songtext, yue]}

if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    want = [a for a in ARGS if a in ALL]
    bad = [a for a in ARGS if not a.startswith("--") and a not in ALL and not (ARGS.index(a) > 0 and ARGS[ARGS.index(a) - 1] in ("--battle", "--ver"))]
    if bad:
        sys.exit(f"不認得的 stage：{bad}；可用：{' '.join(ALL)}")
    for f in ([ALL[w] for w in want] or ORDER):
        f()
