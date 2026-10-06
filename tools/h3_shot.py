"""H3 shot generator with OFFICIAL MiniMax prompt format (project rule since 2026-09-28).

Writes every H3 prompt in the official `h3-prompt-writing` Ref2VA six-section format
(github.com/MiniMax-AI/MiniMax-H3/skills/h3-prompt-writing/references/ref-en.txt):
  subject_definitions: / summary: / retention_analysis: / detailed_description: / overall_soundscape: / non_diegetic_music:
with <Subject N>, <Picture N>, <Audio N> labels, speaker IDs (S1), dialogue as <d>[Chinese] ...</d>, cuts as
"[Shot 2] At 00:03.500, the camera cuts to ...", off-screen voice-over with closed lips, soundscape without dialogue.
Then generates the clip on local ComfyUI with the settings validated in 〈老師，這次換你〉 (Ref2VA INT8, first frame pinned at
frame 0, 14 steps res_multistep, no EasyCache, lossless PNG frames re-encoded at CRF 12).

Usage (H3 venv: C:\\AI\\H3\\venv\\Scripts\\python.exe, or C:\\AI\\tools\\make_shot.cmd):
  h3_shot.py shot.json --out <dir>            build prompt + lint + generate  -> <dir>/{prompt.txt, workflow_api.json, clip.mp4, meta.json}
  h3_shot.py shot.json --out <dir> --dry-run  build prompt + lint only (no GPU)
  h3_shot.py --lint prompt.txt [--duration 4]  check a hand-written prompt against the official format

Shot spec (JSON; relative paths resolve against the JSON file's folder):
{
  "duration": 3.75,                 # seconds of the clip (H3: 4-15 s recommended; frames = smallest 17n+5 >= duration*24)
  "size": [1344, 768], "seed": 42, "steps": 14, "easycache": false,
  "style": "a realistic live-action Taiwanese film shot on 35mm, natural window light, subtle believable acting",
  "setting": "a Taiwanese elementary school classroom",
  "first_frame": "kf.png",          # <Picture 1>; pinned at frame 0 (strongly recommended - project default)
  "camera_video": {"file": "blender_S01.mp4"},   # optional <Video 1>: Blender previs camera/layout guide (blender-previs skill)
  "last_frame": "end.png",          # optional; pinned at the last frame (only for long continuous actions / fixed end states)
  "subjects": [                     # everyone visible or speaking; order = <Subject N>
                                    # {"key": "sky", "desc": "a deep, echoing off-screen male voice", "voice_only": true}
                                    #   = voice with no body (Heaven): no <Subject> label, speaks as "<desc> (S2)"
                                    # "in_first_frame": false = subject not visible in <Picture 1>
    {"key": "ahe", "desc": "Ahe, a mischievous 12-year-old Taiwanese boy (messy spiky black hair, white school shirt, brown shorts)",
     "voice": "a bright, unbroken 12-year-old boy's voice with a playful tone and a soft Taiwanese accent",
     "identity_image": null}         # optional extra identity picture (NOT recommended in multi-person shots: extra people appear)
  ],
  "audio": {"voice_ref": {"subject": "ahe", "file": "ahe_ref.wav"}},   # timbre only, H3 speaks the line itself
       # or {"fixed": {"file": "guide.wav"}}  exact soundtrack reused 1:1 (48 kHz mono; [] silence -> write a silent wav)
  "shots": [
    {"camera": "The camera holds a static shot on a tripod.",           # official camera wording (type + amplitude + speed)
     "action": "Ahe looks up at the teacher with a small grateful smile.",
     "dialogue": [{"subject": "ahe", "line": "謝謝你讓我自己做。", "lang": "Chinese", "offscreen": false,
                   "after": "He closes his lips and keeps smiling."}],
     "at": null},                    # later shots: cut time in seconds, strictly increasing and < duration
  ],
  "soundscape": "Quiet empty-classroom room tone with the faint rustle of a cloth.",   # NO dialogue here
  "music": "N/A"
}
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0"))
FPS = 24
SECTIONS = ["subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music"]
MODELS = dict(unet=os.environ.get("H3_UNET", "minimax_h3_ref2va_pruned_int8_convrot.safetensors"),  # H3_UNET: A/B other weights (e.g. unpruned minimax_h3_ref2va_int8_convrot.safetensors)
              clip=os.environ.get("H3_CLIP", "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors"),  # 16GB profile: qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
              video_vae=os.environ.get("H3_VIDEO_VAE", "minimax_h3_video_vae_fp16.safetensors"), audio_vae="minimax_h3_audio_vae_fp32.safetensors")


# ----------------------------------------------------------------------------------------------- prompt
def frames_for(duration):
    n = 0
    while 17 * n + 5 < duration * FPS:
        n += 1
    return 17 * n + 5


def _cap(x):
    return x[:1].upper() + x[1:]


def ts(sec):
    return f"{int(sec // 60):02d}:{sec % 60:06.3f}"


def build_prompt(spec):
    allsubs = spec["subjects"]
    subs = [s for s in allsubs if not s.get("voice_only")]  # voice_only: off-screen voice with no visible body (e.g. Heaven)
    vo = {s["key"]: s for s in allsubs if s.get("voice_only")}
    idx = {s["key"]: i + 1 for i, s in enumerate(subs)}
    first, last = spec.get("first_frame"), spec.get("last_frame")
    # picture numbering = order of ref_images in the graph: first frame, then identity images
    pic = 1 if first else 0
    id_pic = {}
    for s in subs:
        if s.get("identity_image"):
            pic += 1
            id_pic[s["key"]] = pic
    audio = spec.get("audio") or {}
    voice_ref, fixed = audio.get("voice_ref"), audio.get("fixed")
    shots = spec["shots"]
    # speaker IDs in order of first vocal event
    sid = {}
    for sh in shots:
        for d in sh.get("dialogue", []):
            sid.setdefault(d["subject"], len(sid) + 1)

    def lab(key):
        if key in vo:  # official: a speaker with no defined subject = stable voice description + (Sx)
            return f"{vo[key]['desc']} (S{sid[key]})"
        return f"<Subject {idx[key]}>" + (f" (S{sid[key]})" if key in sid else "")

    L = ["subject_definitions:"]
    for s in subs:
        src = []
        if first and s.get("in_first_frame", True):
            src.append("visible in <Picture 1>")
        if s["key"] in id_pic:
            src.append(f"whose appearance comes from <Picture {id_pic[s['key']]}>")
        L.append(f"<Subject {idx[s['key']]}> is {s['desc']}" + (", " + " and ".join(src) if src else "") + ".")
    if first:
        L.append("<Picture 1> is the first frame of [Shot 1], fixing the camera position, framing, set layout and lighting.")
    cam = spec.get("camera_video")
    if cam:
        L.append("<Video 1> is ONLY a " + cam.get("role", "Blender camera and spatial-layout guide")
                 + ": its low-poly proxy figures and flat colors are not characters or visual style; only its camera path and spatial relationships are followed.")
    if voice_ref:
        L.append(f"<Audio 1> is the voice-timbre reference for {lab(voice_ref['subject'])}.")
    if fixed:
        L.append("<Audio 1> is the complete, exactly timed soundtrack of the target video"
                 + (", containing the spoken lines" if sid else ", containing only quiet room tone") + ".")

    tasks = []
    if first or last:
        tasks.append("keyframe completion")
    if cam or (not first and any(s.get("identity_image") for s in subs)):
        tasks.append("reference generation")
    if voice_ref:
        tasks.append("audio reference")
    if fixed:
        tasks.append("audio reuse")
    tasks = tasks or ["reference generation"]
    n_shots = len(shots)
    summ = (f"[{' + '.join(tasks)}] The target video is " + ("one continuous shot" if n_shots == 1 else f"{n_shots} shots")
            + (f" set in {spec['setting']}" if spec.get("setting") else "")
            + (", beginning from <Picture 1>" if first else "") + (" and ending on the supplied last-frame image" if last else "") + ".")
    for key in sid:
        n_lines = sum(1 for sh in shots for d in sh.get("dialogue", []) if d["subject"] == key)
        summ += (f" {_cap(lab(key))} speaks {n_lines} short line{'s' if n_lines > 1 else ''}"
                 + (" with the voice timbre referenced from <Audio 1>" if voice_ref and voice_ref["subject"] == key else "")
                 + (" exactly as in <Audio 1>" if fixed else "") + ".")
    L += ["", "summary:", summ, "", "retention_analysis:"]
    for s in subs:
        L.append(f"<Subject {idx[s['key']]}> (appears in [Shot 1]): fully_preserved - identity, face, age, hairstyle, body build and clothing"
                 + (" and props" if s.get("props") else "") + " are retained.")
    if first:
        L.append("<Picture 1> ([Shot 1] first frame): fully_preserved - camera position, framing, set layout, furniture and lighting are retained.")
    if cam:
        L.append("<Video 1> (camera path and spatial layout): partially_preserved - the camera trajectory and room geometry are followed; the proxy figures' appearance and stiffness are discarded.")
    if voice_ref:
        L.append("<Audio 1>: reference - only the voice timbre and accent are followed; the words of <Audio 1> are not reused.")
    if fixed:
        L.append("<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete audio track, and lips follow it exactly.")

    D = [f"The target video is in the style of {spec.get('style', 'a realistic live-action film')}."]
    for i, sh in enumerate(shots, start=1):
        head = f"[Shot {i}]" + (f" At {ts(sh['at'])}, the camera cuts to {sh.get('cut_to', 'a new view')}." if i > 1 else "")
        if i == 1 and first:
            head += " The shot begins from <Picture 1>."
        parts = [head]
        if i == 1:  # first appearance: label every subject once
            parts.append(" ".join(f"{_cap(s['desc'].split(',')[0].split(' (')[0])} is {lab(s['key'])}." for s in subs))
        if sh.get("camera"):
            parts.append(sh["camera"])
        if i == 1 and cam:
            parts.append("The camera follows the path and spatial layout of <Video 1>.")
        if sh.get("action"):
            parts.append(sh["action"])
        for d in sh.get("dialogue", []):
            s = next(x for x in allsubs if x["key"] == d["subject"])
            line = d["line"].replace("……", "…")
            voice = f" in {s['voice']}" if s.get("voice") else ""
            if d.get("offscreen"):
                parts.append(f"{_cap(lab(d['subject']))} says in an off-screen voiceover{voice}: <d>[{d.get('lang', 'Chinese')}] {line}</d> "
                             + (d.get("closed_lips") or "while every visible character's lips remain completely closed."))
            else:
                parts.append(f"{_cap(lab(d['subject']))} says{voice}, <d>[{d.get('lang', 'Chinese')}] {line}</d>")
                if d.get("after"):
                    parts.append(d["after"])
        if i == n_shots and last:
            parts.append("The shot ends on the supplied last-frame image.")
        D.append(" ".join(parts))
    if sid:
        silent = [s for s in subs if s["key"] not in sid]
        if silent:
            D.append("Everyone else in the frame keeps their lips closed and does not speak.")
    for extra in spec.get("constraints", []):
        D.append(extra)
    L += ["", "detailed_description:", "\n".join(D), "",
          "overall_soundscape:", spec.get("soundscape") or "Quiet room tone.", "",
          "non_diegetic_music:", spec.get("music") or "N/A"]
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------- lint
def lint(prompt, duration=None):
    """Return (errors, warnings) against the official Ref2VA format."""
    E, W = [], []
    heads = [(m.group(1), m.group(2), m.start()) for m in re.finditer(r"^([a-z_]+)(:?)[ \t]*$", prompt, re.M) if m.group(1) in SECTIONS]
    names = [h[0] for h in heads]
    if names != SECTIONS:
        E.append(f"sections must be exactly {SECTIONS} in order; found {names}")
    for n, colon, _ in heads:
        if not colon:
            E.append(f"section '{n}' must end with a colon ('{n}:')")
    body = {}
    for i, (n, _, p) in enumerate(heads):
        end = heads[i + 1][2] if i + 1 < len(heads) else len(prompt)
        body[n] = prompt[p:end].split("\n", 1)[1] if "\n" in prompt[p:end] else ""
    defs = body.get("subject_definitions", "")
    defined = set(re.findall(r"^(<(?:Subject|Picture|Video|Audio) \d+>) is", defs, re.M))
    defined |= {m for m in re.findall(r"<(?:Picture|Video) \d+>", defs)}  # sources cited inside a subject definition
    for lbl in sorted(set(re.findall(r"<(?:Subject|Picture|Video|Audio) \d+>", prompt))):
        if lbl not in defined:
            E.append(f"label {lbl} is used but never defined in subject_definitions")
    if "retention_analysis" in body:
        for lbl in sorted(defined):
            if lbl.startswith(("<Subject", "<Audio")) and lbl not in body["retention_analysis"]:
                W.append(f"{lbl} has no retention_analysis line")
        if re.search(r"\(S\d+\)", body["retention_analysis"]):
            E.append("speaker IDs (Sx) must not appear in retention_analysis")
    opens, closes = prompt.count("<d>"), prompt.count("</d>")
    if opens != closes:
        E.append(f"unbalanced <d> tags ({opens} open, {closes} close)")
    for m in re.finditer(r"<d>(.*?)</d>", prompt, re.S):
        if not re.match(r"\[[A-Za-z]+\] ", m.group(1)):
            E.append(f"dialogue must start with a language tag like [Chinese]: <d>{m.group(1)[:30]}")
        before = prompt[max(0, m.start() - 200):m.start()]
        if not re.search(r"\(S\d+(,S\d+)*\)", before):
            W.append(f"no speaker ID (S1) shortly before <d>{m.group(1)[:20]}")
    for n in ("overall_soundscape", "non_diegetic_music"):
        t = body.get(n, "")
        if "<d>" in t or re.search(r"[\u4e00-\u9fff]", t) or re.search(r"\b(says?|speaks?|speaking|dialogue|the line)\b", t, re.I):
            E.append(f"{n} must not contain dialogue (it belongs in detailed_description)")
    if body.get("non_diegetic_music", "").strip() in ("None.", "None", ""):
        W.append("non_diegetic_music: write 'N/A' when there is no score")
    dd = body.get("detailed_description", "")
    shots = re.findall(r"\[Shot (\d+)\]( At (\d+):(\d+\.\d+))?", dd)
    if not shots:
        E.append("detailed_description needs [Shot 1]")
    prev = 0.0
    for k, (num, has_t, mm, ss) in enumerate(shots, start=1):
        if int(num) != k:
            E.append(f"shot numbers must be sequential: got [Shot {num}] at position {k}")
        if k == 1 and has_t:
            E.append("[Shot 1] must not have a timestamp")
        if k > 1:
            if not has_t:
                E.append(f"[Shot {num}] needs 'At MM:SS.mmm,'")
                continue
            t = int(mm) * 60 + float(ss)
            if t <= prev or (duration and t >= duration):
                E.append(f"[Shot {num}] cut time {t}s must be increasing and inside the clip")
            prev = t
    outside = re.sub(r"<d>.*?</d>|\"[^\"]*\"|“[^”]*”", "", prompt, flags=re.S)
    if re.search(r"[\u4e00-\u9fff]", outside):
        W.append("Chinese text outside <d> or on-screen quotes: write the rewrite in English, keep only dialogue / visible text in Chinese")
    words = len(dd.split())
    if words < 60:
        W.append(f"detailed_description is short ({words} words; official guide suggests rich, concrete detail)")
    neg = len(re.findall(r"\b(never|no|not|don't|without)\b", dd, re.I))
    if neg > 6:
        W.append(f"{neg} negative words in detailed_description; official guide prefers concrete positive description")
    return E, W


# ----------------------------------------------------------------------------------------------- generate
def req(path, data=None, timeout=60):
    r = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read().decode())


def stage(src, name):
    d = COMFY / "input" / "h3_shot"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, d / name)
    return f"h3_shot/{name}"


DRAFT = {"lora": {"name": "dmad_h3_4step_lora_critic_comfy.safetensors", "strength": 1.0}, "steps": 4, "sampler": "euler",
         "shift": {"video": 12, "audio": 2}}  # DMAD 4-step LoRA (~-49..58%); since 2026-10-06 accepted as the everyday final (keep the drawn seed, don't re-render at 14 steps)


def build_graph(spec, prompt, base, tag):
    if spec.get("draft"):  # draft forces the DMAD settings (shot specs usually carry "steps": 14 for the final)
        spec = {**spec, **DRAFT}
    w, h = spec.get("size", [1344, 768])
    length = frames_for(spec["duration"])
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["clip"], "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": spec.get("video_vae", MODELS["video_vae"])}},  # e.g. minimax_h3_video_vae_int8_convrot.safetensors
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["audio_vae"]}},
        "6": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0], "prompt": prompt,
              "width": w, "height": h, "length": length, "ref_image_size": "match"}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": spec.get("seed", 42)}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": spec.get("steps", 14), "denoise": 1.0}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": f"h3_shot/{tag}", "format": "mp4", "codec": "h264"}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": f"h3_shot_png/{tag}/f"}},
    }
    model = ["1", 0]
    lr = spec.get("lora")  # {"name": "xxx.safetensors", "strength": 1.0} or a list of them (stacked in order); 2026-10-01
    if lr:
        for li, one in enumerate(lr if isinstance(lr, list) else [lr]):
            nid = str(82 + 100 * li)
            g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": one["name"], "strength_model": one.get("strength", 1.0)}}
            model = [nid, 0]
        g["9"]["inputs"]["model"] = model
    if spec.get("sampler"):
        g["8"]["inputs"]["sampler_name"] = spec["sampler"]
    sh = spec.get("shift")  # {"video": 12, "audio": 2} -> core MiniMaxH3SigmaShift (e.g. DMAD 4-step LoRA: video 12 / audio 2); 2026-10-05
    if sh:
        g["83"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": model, "shift_video": sh.get("video", 12.0), "shift_audio": sh.get("audio", 3.0)}}
        model = ["83", 0]
        g["9"]["inputs"]["model"] = model
    # Speed (2026-10-01 bench, 5090): comfy kitchen INT8 attention is the default (-35..43%, PSNR 31-42 dB vs dense).
    # "draft": true = preview-roll fast mode: DMAD 4-step LoRA (see DRAFT above). Sparse attention is now only via explicit "sparse".
    # Opt out: spec "attention": "pytorch attention" (or env H3_ATTENTION=pytorch); explicit "sparse": {...} overrides draft.
    att = spec.get("attention") or os.environ.get("H3_ATTENTION", "comfy kitchen attention")
    if att.lower().startswith("pytorch"):
        att = None
    if att:
        g["80"] = {"class_type": "ModelAttentionBackend", "inputs": {"model": model, "attention": "comfy kitchen attention"}}
        model = ["80", 0]
        g["9"]["inputs"]["model"] = model
    sp = spec.get("sparse")  # (before 2026-10-05 "draft" turned this on; now draft = DMAD 4-step LoRA){"tau": 1.3, "start": 0.2, "end": 1.0, "sink": "exact_kv_and_rows", "dense_blocks": ""}
    if sp:
        g["81"] = {"class_type": "BlockSparseAttention", "inputs": {"model": model, "selection": "sol-attn", "selection.tau": sp.get("tau", 1.0),
                   "start_percent": sp.get("start", 0.2), "end_percent": sp.get("end", 1.0), "dense_blocks": sp.get("dense_blocks", ""),
                   "min_tokens": 12288, "extra_tokens": 256, "verbose": True, "sink_conditioning": sp.get("sink", "exact_kv_and_rows")}}
        model = ["81", 0]
        g["9"]["inputs"]["model"] = model
    ctl = spec.get("control")  # optional H3 Fun ControlNet (pose/depth/canny control video); 2026-09-30
    if ctl:
        g["70"] = {"class_type": "LoadVideo", "inputs": {"file": stage(base / ctl["file"], f"{tag}_control.mp4")}}
        g["71"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["70", 0]}}
        g["72"] = {"class_type": "ModelPatchLoader", "inputs": {"name": ctl.get("patch", "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors")}}
        g["73"] = {"class_type": "MiniMaxH3FunControlNetApply", "inputs": {
            "model": model, "model_patch": ["72", 0], "vae": ["3", 0], "strength": ctl.get("strength", 1.0),
            "start_percent": ctl.get("start", 0.0), "end_percent": ctl.get("end", 1.0), "control_video": ["71", 0]}}
        model = ["73", 0]
        g["9"]["inputs"]["model"] = model
    if spec.get("easycache"):
        g["50"] = {"class_type": "EasyCache", "inputs": {"model": model, "reuse_threshold": 0.2, "start_percent": 0.15, "end_percent": 0.95, "verbose": True}}
        model = ["50", 0]
        g["9"]["inputs"]["model"] = model
    i = 0
    if spec.get("first_frame"):
        g["5"] = {"class_type": "LoadImage", "inputs": {"image": stage(base / spec["first_frame"], f"{tag}_first.png")}}
        g["6"]["inputs"]["ref_images.ref_image_0"] = ["5", 0]
        i = 1
    for s in spec["subjects"]:
        if s.get("identity_image") and not s.get("voice_only"):
            n = str(20 + i)
            g[n] = {"class_type": "LoadImage", "inputs": {"image": stage(base / s["identity_image"], f"{tag}_id{i}.png")}}
            g["6"]["inputs"][f"ref_images.ref_image_{i}"] = [n, 0]
            i += 1
    if spec.get("camera_video"):  # Blender previs camera guide (blender-previs skill), as in 〈那句話，我收回〉v5
        g["30"] = {"class_type": "LoadVideo", "inputs": {"file": stage(base / spec["camera_video"]["file"], f"{tag}_camera.mp4")}}
        g["31"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}}
        g["6"]["inputs"]["ref_videos.ref_video_0"] = ["31", 0]
    cond, latent = ["6", 0], ["6", 1]
    audio = spec.get("audio") or {}
    if audio.get("fixed"):  # exact soundtrack: audio latent frozen + guide at frame 0
        g["32"] = {"class_type": "LoadAudio", "inputs": {"audio": stage(base / audio["fixed"]["file"], f"{tag}_guide.wav")}}
        g["6"]["inputs"]["ref_audios.ref_audio_0"] = ["32", 0]
        g["60"] = {"class_type": "VAEEncodeAudio", "inputs": {"audio": ["32", 0], "vae": ["4", 0]}}
        g["61"] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": 32, "height": 32}}
        g["62"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["60", 0], "mask": ["61", 0]}}
        g["63"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["6", 1], "audio_latent": ["62", 0]}}
        latent = ["63", 0]
    elif audio.get("voice_ref"):  # timbre only, H3 speaks
        g["32"] = {"class_type": "LoadAudio", "inputs": {"audio": stage(base / audio["voice_ref"]["file"], f"{tag}_voice.wav")}}
        g["6"]["inputs"]["ref_audios.ref_audio_0"] = ["32", 0]
    if spec.get("first_frame"):
        g["40"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": cond, "latent": latent, "vae": ["3", 0], "image": ["5", 0], "frame_idx": 0}}
        cond = ["40", 0]
    if audio.get("fixed"):
        g["41"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": cond, "latent": latent, "audio_vae": ["4", 0], "audio": ["32", 0], "frame_idx": 0}}
        cond = ["41", 0]
    if spec.get("last_frame"):
        g["43"] = {"class_type": "LoadImage", "inputs": {"image": stage(base / spec["last_frame"], f"{tag}_last.png")}}
        g["42"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": cond, "latent": latent, "vae": ["3", 0], "image": ["43", 0], "frame_idx": -1}}
        cond = ["42", 0]
    if audio.get("fixed"):
        g["14"] = {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["32", 0], "fps": FPS}}
    else:
        g["13"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}}
        g["14"] = {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["13", 0], "fps": FPS}}
    g["10"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": cond}}
    g["11"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["10", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": latent}}
    return g, length


def generate(spec, prompt, base, out):
    tag = f"{out.name}_{int(time.time())}"
    g, length = build_graph(spec, prompt, base, tag)
    (out / "workflow_api.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    t0 = time.time()
    pid = req("/prompt", {"prompt": g})["prompt_id"]
    print(f"[queued] {tag} {length}f seed={spec.get('seed', 42)}", flush=True)
    while True:
        time.sleep(4)
        h = req(f"/history/{pid}")
        if pid in h:
            break
    e = h[pid]
    ok = e.get("status", {}).get("status_str") == "success"
    if ok:
        v = (e["outputs"]["15"].get("images") or e["outputs"]["15"].get("videos"))[0]
        raw = out / "clip_savevideo.mp4"
        shutil.copy2(COMFY / "output" / v.get("subfolder", "") / v["filename"], raw)
        frames = [COMFY / "output" / "h3_shot_png" / tag / im["filename"] for im in e["outputs"]["16"]["images"]]
        lst = out / "frames.txt"
        lst.write_text("".join(f"file '{f.as_posix()}'\nduration {1 / FPS:.6f}\n" for f in frames), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(raw), "-r", str(FPS),
                        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", str(out / "clip.mp4")], check=True)
    else:
        print(json.dumps(e.get("status", {}), ensure_ascii=False)[:3000])
    meta = {"ok": ok, "length": length, "seed": spec.get("seed", 42), "wall_s": round(time.time() - t0, 1), "tag": tag}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{'ok' if ok else 'FAIL'}] {out / 'clip.mp4'} {meta['wall_s']}s", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser(description="H3 shot generator (official MiniMax prompt format)")
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lint", help="lint a hand-written prompt file instead")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--force", action="store_true", help="generate even if lint reports errors")
    a = ap.parse_args()
    if a.lint:
        E, W = lint(Path(a.lint).read_text(encoding="utf-8"), a.duration)
        for x in E:
            print("ERROR", x)
        for x in W:
            print("WARN ", x)
        print("OK" if not E else f"{len(E)} error(s)")
        sys.exit(1 if E else 0)
    spec_path = Path(a.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = Path(a.out or spec_path.with_suffix(""))
    out.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(spec)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    shutil.copy2(spec_path, out / "shot.json")
    E, W = lint(prompt, spec["duration"])
    if spec["duration"] > 12:
        W.append(f"duration {spec['duration']}s > 12 s: in this project 15 s clips drifted / self-cut; keep shots <= 12 s")
    for x in E:
        print("ERROR", x)
    for x in W:
        print("WARN ", x)
    print(f"[prompt] {out / 'prompt.txt'} ({len(E)} errors, {len(W)} warnings)")
    if E and not a.force:
        sys.exit(1)
    if a.dry_run:
        return
    try:
        req("/system_stats")
    except Exception as e:
        sys.exit(f"ComfyUI not reachable at {HOST} ({e}); run C:\\AI\\tools\\start_comfy.cmd first")
    sys.exit(0 if generate(spec, prompt, spec_path.parent, out) else 1)


if __name__ == "__main__":
    main()
