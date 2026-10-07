"""安裝完成後的自我驗證：每個本地模型各跑一個小工作，不需要任何外部素材（聲音、圖片都自己生）。
用 H3 venv 執行（ComfyUI 要先啟動：call configs\\profile.cmd → tools\\start_comfy.cmd）：
  C:\\AI\\H3\\venv\\Scripts\\python.exe setup\\smoke_test.py [--quick]
--quick 跳過 FlashVSR 與 LoRA 項目。結果寫 setup\\smoke_out\\report.json，並印出跟 docs\\hardware.md 對照用的時間。
流程：Breeze 設計聲音 → BreezyVoice 用它念台詞＋自動挑選 → VoxCPM2（備用引擎）→ faster-whisper 聽寫 → 聲調比對 → Qwen-Image 2.1 生首幀 → Qwen 附參考圖 →
MiniMax Music 3 → BS-RoFormer 分離 → H3（DMAD 4 步，首幀＋配音當固定音軌）→ RTX VSR → FlashVSR"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "smoke_out"; OUT.mkdir(exist_ok=True)
T = Path(os.environ.get("AI_TOOLS", r"C:\AI\tools"))
PYH3 = os.environ.get("PY_H3", r"C:\AI\H3\venv\Scripts\python.exe")
PYV = os.environ.get("PY_VOICE", r"C:\AI\Voice\venv\Scripts\python.exe")
PYB = os.environ.get("PY_BREEZE", r"C:\AI\BreezeTTS\venv\Scripts\python.exe")
PYBV = os.environ.get("PY_BREEZYVOICE", r"C:\AI\BreezyVoice\venv\Scripts\python.exe")
SEP = str(Path(PYV).parent / "audio-separator.exe")
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
QUICK = "--quick" in sys.argv
LINE = "老師，考卷是熱的。"
PROMPT = ("A cinematic film still from a Taiwanese coming-of-age movie, shot on Kodak Vision3 500T film with an anamorphic 50mm lens at f/2, medium close-up "
          "at eye level. Late-afternoon golden-hour sun pours in low through the classroom windows behind the subject, warm backlight with a glowing rim light, "
          "hazy air with visible dusty light beams, warm amber color grade. In a Taiwanese public elementary school classroom. In the foreground, a cheerful "
          "12-year-old Taiwanese boy with short spiky black hair, wearing a plain white short-sleeve school shirt, sits at his wooden desk facing the camera "
          "with both palms resting on a single exam paper, mouth closed, puzzled. In the softly out-of-focus background, a few seated classmates. "
          "Natural skin texture, sharp focus on the face, shallow depth of field, subtle film grain. No text, no watermark.")


def comfy_ok():
    try:
        urllib.request.urlopen(HOST + "/system_stats", timeout=5); return True
    except Exception:
        return False


def free_comfy():
    try:
        r = urllib.request.Request(HOST + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r, timeout=30)
    except Exception:
        pass
    time.sleep(5)


def newest(d, exts):
    fs = sorted([f for f in Path(d).rglob("*") if f.suffix.lower() in exts], key=lambda f: f.stat().st_mtime) if Path(d).exists() else []
    return fs[-1] if fs else None


rows = []


def step(name, cmd, expect=None, timeout=1800):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(OUT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        rc, tail = r.returncode, (r.stdout + r.stderr)[-500:]
    except subprocess.TimeoutExpired:
        rc, tail = -9, "timeout"
    out = expect() if callable(expect) else (OUT / expect if expect else None)
    ok = rc == 0 and (out is None or (out is not None and Path(out).exists()))
    rows.append(dict(step=name, ok=ok, seconds=round(time.time() - t0, 1), output=str(out) if out else None, tail="" if ok else tail))
    print(f"{'OK  ' if ok else 'FAIL'} {name:14s} {rows[-1]['seconds']:7.1f}s  {'' if ok else tail[-200:]}", flush=True)
    return out if ok else None


def main():
    if not comfy_ok():
        sys.exit(f"ComfyUI not running at {HOST}: call configs\\profile.cmd, then tools\\start_comfy.cmd")
    # --- 聲音（ComfyUI 先釋放顯存）
    free_comfy()
    (OUT / "breeze.json").write_text(json.dumps(dict(out_dir="breeze", jobs=[dict(
        name="design", text="大家好，我是阿福。今天天氣很好，我們一起去上課吧。",
        instruction="A cheerful 12-year-old Taiwanese boy, bright and friendly, natural Taiwanese Mandarin accent.", seed=7)]), ensure_ascii=False), encoding="utf-8")
    ref = step("breeze_design", [PYB, str(T / "breeze_batch.py"), "breeze.json"], "breeze/design.wav")
    (OUT / "breeze_line.json").write_text(json.dumps(dict(out_dir="breeze", jobs=[dict(
        name="line", text=LINE, instruction="A cheerful 12-year-old Taiwanese boy, natural Taiwanese Mandarin accent, standard pronunciation.", seed=11)]),
        ensure_ascii=False), encoding="utf-8")
    tw = step("breeze_line", [PYB, str(T / "breeze_batch.py"), "breeze_line.json"], "breeze/line.wav")
    # 台詞配音＝BreezyVoice：用設計好的聲音念台詞（3 個 seed），再自動挑（聽寫＋對照台灣國語參考音；這裡用 Breeze 那句當參考，不需連網）
    (OUT / "bv.json").write_text(json.dumps(dict(out_dir="bv", seeds=3, jobs=[dict(
        name="line", text=LINE, ref_audio="breeze/design.wav", ref_text="大家好，我是阿福。今天天氣很好，我們一起去上課吧。", tw_ref="breeze/line.wav")]),
        ensure_ascii=False), encoding="utf-8")
    bv = step("breezyvoice", [PYBV, str(T / "breezyvoice_batch.py"), "bv.json"], "bv/cand/line_s1.wav") if ref else None
    if bv and tw:
        bv = step("breezyvoice_pick", [PYV, str(T / "breezyvoice_pick.py"), "bv.json"], "bv/line.wav")
    vox = step("voxcpm2", [PYV, str(T / "gen_voice.py"), "--text", LINE, "--ref", str(ref or ""), "--seed", "7", "--out", "voxcpm.wav"], "voxcpm.wav")
    line_wav = bv or vox
    if line_wav:
        step("whisper", [PYV, str(T / "stt.py"), "--audio", str(line_wav), "--outdir", "stt"], "stt/transcript.txt")
    if line_wav and tw:
        step("pron_compare", [PYV, str(T / "pron_compare.py"), str(line_wav), "breeze/line.wav", LINE])
    # --- 圖、音樂、影片（ComfyUI）
    (OUT / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    img = step("qwen_image", [PYH3, str(T / "gen_image.py"), "--prompt-file", "prompt.txt", "--seed", "5101", "--prefix", "smoke/first", "--out", "qwen"],
               lambda: newest(OUT / "qwen", {".png"}))
    if img:
        from PIL import Image
        im = Image.open(img).convert("RGB"); w, h = im.size
        im.crop((int(w * 0.3), 0, int(w * 0.7), int(h * 0.75))).save(OUT / "ref_bust.png")      # 單張半身當參考圖（不要用多格定妝照）
        im.resize((1344, 768), Image.LANCZOS).save(OUT / "first.png")
        (OUT / "prompt_ref.txt").write_text("The boy in <image1> is the same boy: keep exactly his face and hair. " + PROMPT.replace("sits at his wooden desk facing the camera",
                                            "stands by the classroom window looking out"), encoding="utf-8")
        step("qwen_ref", [PYH3, str(T / "gen_image.py"), "--prompt-file", "prompt_ref.txt", "--ref", "ref_bust.png", "--seed", "5102", "--prefix", "smoke/ref",
                          "--out", "qwen_ref"], lambda: newest(OUT / "qwen_ref", {".png"}))
    (OUT / "cap.txt").write_text("Genre: light playful school comedy underscore, purely instrumental. BPM 108.\nVocal: NONE.\nArrangement: pizzicato strings, marimba.",
                                 encoding="utf-8")
    (OUT / "lyr.txt").write_text("[Intro]\n" + "[Instrumental]\n" * 14 + "[Outro]\n[Instrumental]\n", encoding="utf-8")
    mus = step("music3", [PYH3, str(T / "gen_music3.py"), "--caption-file", "cap.txt", "--lyrics-file", "lyr.txt", "--seconds", "30", "--seed", "7",
                          "--prefix", "audio/MM3/smoke", "--out", "music"], lambda: newest(OUT / "music", {".flac"}))
    if img and line_wav:
        sr = 48000
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(line_wav), "-ar", str(sr), "-ac", "1", "-f", "s16le", "-"], capture_output=True)
        pcm = bytes(int(0.4 * sr) * 2) + r.stdout; dur = 4.4
        pcm = (pcm + bytes(int(dur * sr) * 2))[: int(dur * sr) * 2]
        with wave.open(str(OUT / "guide.wav"), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm)
        spec = dict(duration=4.4, size=[1344, 768], seed=1, steps=14, draft=True, style="a realistic cinematic live-action Taiwanese film, 35mm grain",
                    setting="a Taiwanese elementary school classroom", first_frame="first.png",
                    subjects=[dict(key="boy", desc="a cheerful 12-year-old Taiwanese boy with short spiky black hair in a white school shirt",
                                   voice="a bright 12-year-old boy's voice")],
                    audio={"fixed": {"file": "guide.wav"}},
                    shots=[dict(camera="The camera holds a static shot on a tripod.", action="The boy looks up from the exam paper and says his line, puzzled.",
                                dialogue=[dict(subject="boy", line=LINE, lang="Chinese", after="Right after the line his lips close.")])],
                    constraints=["No new people appear; no captions and no readable text."], soundscape="Quiet classroom room tone.", music="N/A")
        (OUT / "h3.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        clip = step("h3", [PYH3, str(T / "h3_shot.py"), "h3.json", "--out", "h3"], "h3/clip.mp4")
    else:
        clip = None
    free_comfy()
    if mus:
        step("separator", [SEP, str(mus), "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "--model_file_dir", r"C:\AI\Voice\models\separator",
                           "--output_dir", "sep", "--output_format", "WAV"], lambda: newest(OUT / "sep", {".wav"}))
    if clip:
        (OUT / "vsr_1080p.mp4").unlink(missing_ok=True)
        step("rtx_vsr", [PYH3, str(T / "upscale_vsr.py"), "--source", str(clip), "--output", "vsr_1080p.mp4"], "vsr_1080p.mp4")
        if not QUICK:
            step("flashvsr", [PYH3, str(T / "flashvsr_cli.py"), str(clip), "flashvsr"], "flashvsr/clip.mp4")
    (OUT / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r["step"] for r in rows if not r["ok"]]
    print("\nALL OK" if not bad else f"\nFAILED: {bad}  (see setup/smoke_out/report.json)")
    print("Watch setup/smoke_out/h3/clip.mp4 and vsr_1080p.mp4 to check picture and lip-sync.")


if __name__ == "__main__":
    main()
