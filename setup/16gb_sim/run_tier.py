"""三種硬體配置下，逐一跑所有本地模型。H3 venv：python run_tier.py base|t1|t2|t3 [--bg 12]
base＝本機不設限（96GB、32GB 顯卡），當比對基準
t1＝32GB VRAM＋64GB RAM　t2＝16GB VRAM＋64GB RAM　t3＝16GB VRAM＋32GB RAM
記憶體：電腦平常的程式照開，再鎖住記憶體，讓可用量＝總記憶體－常駐（--bg，預設 12GB）；ComfyUI 也被告知總記憶體只有 32／64GB。
每個測試記錄：成功與否、時間、顯存峰值（扣掉佔位）、系統可用記憶體最低值、該程式記憶體峰值、輸出檔雜湊。"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

import run_32g as Q
import run_test as R

HERE = R.HERE
ROOT = R.ROOT
CH = ROOT / "角色資產" / "老師這次換你"
PYH3, PYV = R.PY, r"C:\AI\Voice\venv\Scripts\python.exe"
PYB = r"C:\AI\BreezeTTS\venv\Scripts\python.exe"
SEP = r"C:\AI\Voice\venv\Scripts\audio-separator.exe"
T = r"C:\AI\tools"
TIERS = {"base": dict(vram_hog=False, ramcap=None, flags=[]),
         "t1": dict(vram_hog=False, ramcap=64, flags=[]),
         "t2": dict(vram_hog=True, ramcap=64, flags=["--reserve-vram", "1.5"]),
         "t3": dict(vram_hog=True, ramcap=32, flags=["--reserve-vram", "1.5"])}
CINE = ("A cinematic film still from a Taiwanese coming-of-age movie, shot on Kodak Vision3 500T film with an anamorphic 50mm lens at f/2, medium shot at eye level. "
        "Late-afternoon golden-hour sun pours in low through the classroom windows behind the subject, strong warm backlight with a glowing rim light on the hair "
        "and shoulders, hazy air with visible dusty light beams, warm amber and honey color grade, soft deep warm shadows, gentle halation on the highlights. "
        "In a Taiwanese public elementary school classroom. In the foreground, {who} sits at his wooden desk, leaning forward with a puzzled, doubtful look, "
        "both palms resting flat on a single exam paper. In the softly out-of-focus background, a few seated classmates in white school shirts. "
        "Cinematic lighting, filmic color grading, natural skin texture, sharp focus on the faces, shallow depth of field with creamy bokeh, subtle film grain, "
        "balanced uncluttered composition. No text, no watermark, no extra people in the foreground.")
AFU = "a chubby 12-year-old Taiwanese boy with round cheeks and short spiky black hair, wearing a plain white short-sleeve school shirt"
LINE = "老師，考卷是熱的。"
AFU_REF_TEXT = "老師,我剛剛真的都有聽,我只是眼睛閉起來而已啦。"


def tests(o):
    """(名稱, 指令, 主要輸出檔（相對 o）, 需要 ComfyUI)"""
    (o / "p_t2i.txt").write_text(CINE.format(who="the boy Afu, " + AFU), encoding="utf-8")
    (o / "p_ref.txt").write_text("The boy in <image1> is Afu: keep exactly his face, round cheeks and spiky black hair. " + CINE.format(who="the boy Afu from <image1>, " + AFU), encoding="utf-8")
    (o / "p_lora.txt").write_text(CINE.format(who="afu_img25, the boy Afu, " + AFU), encoding="utf-8")
    (o / "breeze.json").write_text(json.dumps(dict(out_dir="breeze", jobs=[dict(name="line", text=LINE, ref_audio=str(CH / "阿福/voice_ref.wav"), ref_text=AFU_REF_TEXT, seed=37)]),
                                              ensure_ascii=False), encoding="utf-8")
    (o / "music_cap.txt").write_text("Genre: light playful school comedy underscore, purely instrumental film score. BPM 108, key F major.\nVocal: NONE.\n"
                                     "Arrangement: pizzicato strings, marimba, glockenspiel, light brushed snare, upright bass.", encoding="utf-8")
    (o / "music_lyr.txt").write_text("[Intro]\n" + "[Instrumental]\n" * 14 + "[Outro]\n[Instrumental]\n", encoding="utf-8")
    h3spec = json.loads((R.FILM / "C04_a0" / "shot.json").read_text(encoding="utf-8")); h3spec["draft"] = True
    (o / "h3_C04.json").write_text(json.dumps(h3spec, ensure_ascii=False), encoding="utf-8")
    return [
        ("qwen_t2i", [PYH3, f"{T}\\gen_image.py", "--prompt-file", "p_t2i.txt", "--seed", "5101", "--prefix", "tier/t2i", "--out", "qwen_t2i"], "qwen_t2i", True),
        ("qwen_ref", [PYH3, f"{T}\\gen_image.py", "--prompt-file", "p_ref.txt", "--ref", str(CH / "阿福/01_定妝照.png"), "--seed", "5101", "--prefix", "tier/ref",
                      "--out", "qwen_ref"], "qwen_ref", True),
        ("qwen_lora", [PYH3, f"{T}\\gen_image.py", "--prompt-file", "p_lora.txt", "--lora", "afu_img25_qwen21_768_1600.safetensors:1.0", "--seed", "5101",
                       "--prefix", "tier/lora", "--out", "qwen_lora"], "qwen_lora", True),
        ("face_refine", [PYH3, f"{T}\\qwen21_face_refine.py", "@qwen_t2i", "face_refine.png", "--box", "900", "150", "1800", "1050",
                         "--lora", "afu_img25_qwen21_768_1600.safetensors", "--prompt", "afu_img25, the boy Afu, " + AFU + ", puzzled doubtful look"], "face_refine.png", True),
        ("music3_60s", [PYH3, f"{T}\\gen_music3.py", "--caption-file", "music_cap.txt", "--lyrics-file", "music_lyr.txt", "--seconds", "60", "--seed", "7",
                        "--prefix", "audio/MM3/tier", "--out", "music3"], "music3", True),
        ("h3_C04", [PYH3, f"{T}\\h3_shot.py", "h3_C04.json", "--out", "h3_C04"], "h3_C04/clip.mp4", True),
        ("__free__", None, None, True),
        ("voxcpm2", [PYV, f"{T}\\gen_voice.py", "--text", LINE, "--ref", str(CH / "阿福/voice_ref.wav"), "--seed", "7", "--out", "voxcpm.wav"], "voxcpm.wav", False),
        ("breeze", [PYB, f"{T}\\breeze_batch.py", "breeze.json"], "breeze/line.wav", False),
        ("whisper", [PYV, f"{T}\\stt.py", "--audio", "voxcpm.wav", "--outdir", "stt"], "stt/transcript.txt", False),
        ("pron_compare", [PYV, f"{T}\\pron_compare.py", "voxcpm.wav", "breeze/line.wav", LINE], None, False),
        ("separator", [SEP, "@music3_60s", "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "--model_file_dir", r"C:\AI\Voice\models\separator",
                       "--output_dir", "sep", "--output_format", "WAV"], "sep", False),
        ("rtx_vsr", [PYH3, f"{T}\\upscale_vsr.py", "--source", str(HERE / "out" / "A" / "C04" / "clip.mp4"), "--output", "vsr/C04_1080p.mp4"], "vsr/C04_1080p.mp4", False),
        ("flashvsr", [PYH3, str(HERE / "flashvsr_cli.py"), str(HERE / "out" / "A" / "C04" / "clip.mp4"), "flashvsr"], "flashvsr/clip.mp4", False),
    ]


def first_file(p, exts=(".png", ".flac", ".wav", ".mp4", ".txt")):
    if p.is_file():
        return p
    if p.is_dir():
        fs = sorted([f for f in p.rglob("*") if f.suffix.lower() in exts], key=lambda f: f.stat().st_mtime)
        return fs[-1] if fs else None
    return None


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p and p.is_file() else None


class Mon(threading.Thread):
    def __init__(self, comfy_pid):
        super().__init__(daemon=True); self.cp = comfy_pid; self.stop = False; self.target = None; self.reset()

    def reset(self, target=None):
        self.target = target; self.vram = 0; self.priv = 0; self.avail = 1e9; self.comfy_priv = 0

    @staticmethod
    def tree_priv(pid):
        try:
            p = psutil.Process(pid)
            return sum(getattr(q.memory_info(), "private", 0) for q in [p] + p.children(recursive=True))
        except Exception:
            return 0

    def run(self):
        while not self.stop:
            try:
                u, _ = R.smi_used(); self.vram = max(self.vram, u)
                self.avail = min(self.avail, Q.memstat()["avail_phys"])
                if self.target: self.priv = max(self.priv, self.tree_priv(self.target))
                if self.cp: self.comfy_priv = max(self.comfy_priv, self.tree_priv(self.cp))
            except Exception:
                pass
            time.sleep(0.5)


def main(tier, bg):
    C = TIERS[tier]; o = HERE / "tier" / f"{tier}_bg{bg}"; o.mkdir(parents=True, exist_ok=True)
    resf = HERE / f"results_tier_{tier}_bg{bg}.json"
    _, total = R.smi_used()
    procs = []
    if C["vram_hog"]:
        vh = subprocess.Popen([PYH3, str(HERE / "hog.py"), str(total - R.CARD_MIB)], stdout=subprocess.PIPE, text=True); procs.append(vh)
        print(vh.stdout.readline().strip(), flush=True)
    base_vram, _ = R.smi_used()
    ms0 = Q.memstat(); target = (C["ramcap"] - bg) if C["ramcap"] else None
    if target:
        hog = max(0, int(ms0["avail_phys"] - target))
        rh = subprocess.Popen([PYH3, str(HERE / "ram_hog.py"), str(hog)], stdout=subprocess.PIPE, text=True); procs.append(rh)
        print(rh.stdout.readline().strip(), flush=True)
    time.sleep(5); ms1 = Q.memstat(); print("mem", ms1, flush=True)
    log = open(HERE / f"comfy_tier_{tier}_bg{bg}.log", "w", encoding="utf-8")
    cmd = [PYH3, "-X", "utf8", str(HERE / "comfy_ramcap.py"), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch",
           "--preview-method", "none", "--cache-none", "--fast", "fp16_accumulation"] + C["flags"]
    env_c = {**os.environ, "RAMCAP_GB": str(C["ramcap"] or 1024)}
    comfy = subprocess.Popen(cmd, cwd=str(R.COMFY), stdout=log, stderr=subprocess.STDOUT, env=env_c); procs.append(comfy)
    for _ in range(180):
        time.sleep(2)
        try:
            R.req("/system_stats"); break
        except Exception:
            pass
    mon = Mon(comfy.pid); mon.start()
    rows = []
    outs = {}
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    only = [x for x in os.environ.get("ONLY", "").split(",") if x]
    prev = {}
    if only and resf.exists():                       # 補跑：保留前一次結果，只重跑指定項目
        for r in json.loads(resf.read_text(encoding="utf-8"))["runs"]:
            prev[r["test"]] = r
            if r.get("output"): outs[r["test"]] = o / r["output"]
    for name, cmd, out, needs_comfy in tests(o):
        if only and name not in only and name != "__free__":
            if name in prev: rows.append(prev[name])
            continue
        if name == "__free__":
            try:
                R.req("/free", {"unload_models": True, "free_memory": True})
            except Exception:
                pass
            time.sleep(10); continue
        cmd = [str(outs.get(c[1:])) if isinstance(c, str) and c.startswith("@") else c for c in cmd]
        mon.reset(); t0 = time.time()
        try:
            p = subprocess.Popen(cmd, cwd=str(o), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            mon.target = p.pid
            so, _ = p.communicate(timeout=1500); rc = p.returncode
            tail = so.decode("utf-8", "replace")[-600:]
        except subprocess.TimeoutExpired:
            Q.kill_tree(p.pid); rc = -9; tail = "timeout"
        wall = round(time.time() - t0, 1)
        f = first_file(o / out) if out else None
        ok = rc == 0 and (f is not None or out is None)
        if out: outs[name] = f
        row = dict(tier=tier, bg=bg, test=name, ok=ok, rc=rc, wall_s=wall, vram_peak_mib=max(0, mon.vram - base_vram),
                   proc_private_peak_gib=round(mon.priv / 2**30, 2), comfy_private_peak_gib=round(mon.comfy_priv / 2**30, 2),
                   sys_avail_min_gib=round(mon.avail, 2), output=str(f.relative_to(o)) if f else None, sha=sha(f),
                   tail="" if ok else tail)
        if name == "pron_compare" or name == "whisper":
            row["result"] = tail.strip().splitlines()[-1][:200] if tail.strip() else ""
            if name == "whisper" and f: row["result"] = f.read_text(encoding="utf-8").strip()[:100]
        rows.append(row); print(json.dumps({k: v for k, v in row.items() if k != "tail"}, ensure_ascii=False), flush=True)
        resf.write_text(json.dumps(dict(tier=tier, bg=bg, mem_before=ms0, mem_after_hogs=ms1, runs=rows), ensure_ascii=False, indent=1), encoding="utf-8")
    mon.stop = True
    print("DONE", tier, flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    bg = int(a[a.index("--bg") + 1]) if "--bg" in a else 12
    started = []
    _P = subprocess.Popen

    def track(*x, **k):
        p = _P(*x, **k); started.append(p.pid); return p
    subprocess.Popen = track
    try:
        main(a[0], bg)
    finally:
        for pid in started:
            Q.kill_tree(pid)
