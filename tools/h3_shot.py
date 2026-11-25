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
  # "first_clip": "prev_tail22.mp4",  # optional: last 5/22/39 frames of the previous clip pinned at frames 0.. instead of the single first frame (continuation); keep first_frame = its last frame for <Picture 1>
  "camera_video": {"file": "blender_S01.mp4"},   # optional <Video 1>: Blender previs camera/layout guide (blender-previs skill)
  # or {"file": "wm.mp4", "kind": "motion", "people": 1, "follow": "..."}: gray-mannequin motion reference from make_whitemodel.py
  #    (dance / fight shots, 2026-10-14; describe props such as swords in "action" - the mannequins carry none)
  "last_frame": "end.png",          # optional; pinned at the last frame (only for long continuous actions / fixed end states)
  # "push_end": 1.15,               # optional "end-frame push" (singing push-ins; our camera A/B 2026-11-24): shoots this spec with a
  #    locked-off camera line (its own camera text is not used) into <out>/push_fixed/, crops its LAST frame around the largest face by 1.15x as last_frame, then
  #    re-shoots with the same seed and a slow push-in camera line -> exact push, stable face/clothes, still sings to the end.
  #    Or {"zoom": 1.15, "fixed_clip": "take.mp4" (reuse an existing fixed take), "camera": "..." (push wording),
  #    "fixed_camera": "..." (pass-1 locked-off wording)}. Normal specs (no push_end) give the same output as before; they
  #    only take a small lock in the system temp dir and are refused (ERROR, exit 1) while a push_end run uses the same folder
  #    or when that lock cannot be used.
  #    Single-shot specs with first_frame only (no last_frame / first_clip / camera_video / control). Costs one extra generation.
  "subjects": [                     # everyone visible or speaking; order = <Subject N>
                                    # {"key": "sky", "desc": "a deep, echoing off-screen male voice", "voice_only": true}
                                    #   = voice with no body (Heaven): no <Subject> label, speaks as "<desc> (S2)"
                                    # "in_first_frame": false = subject not visible in <Picture 1>
    {"key": "ahe", "desc": "Ahe, a mischievous 12-year-old Taiwanese boy (messy spiky black hair, white school shirt, brown shorts)",
     "voice": "a bright, unbroken 12-year-old boy's voice with a playful tone and a soft Taiwanese accent",
     "identity_image": null}         # optional extra identity picture (NOT recommended in multi-person shots: extra people appear)
  ],
  "audio": {"voice_ref": {"subject": "ahe", "file": "ahe_ref.wav"}},   # timbre only, H3 speaks the line itself
       # or {"voice_refs": [{"subject": "ahe", "file": ...}, {"subject": "teacher", "file": ...}]}  two or three speakers in one
       #    shot (2026-10-23; <Audio 1..3> in this order, each line names the <Audio k> timbre it uses)
       # or {"fixed": {"file": "guide.wav"}}  exact soundtrack reused 1:1 (48 kHz mono; [] silence -> write a silent wav)
  "shots": [
    {"camera": "The camera holds a static shot on a tripod.",           # official camera wording (type + amplitude + speed)
     # action: since 2026-10-23 write 50-150 words in the official order "Starting from <Picture 1>, ..." first-frame anchor ->
     # action onset -> continuous development -> result; name the body parts, amplitude and repetitions, no abstract adjectives
     # (our A/B 2026-10-23: one-line actions gave 1/2.7 of the motion). In-shot times ("at about 1.2 seconds") optional.
     # Since 2026-11-23 (our A/B 2026-11-23): split it into 2-3 causal "Beat 1: ... Beat 2: ..." actions tied to the lines, only things
     # visible in the first frame, and end with the held pose ("After the last word he holds still, ...") -> talking close-ups
     # moved ~1.4-2x more. With a locked last_frame the end image decides the motion; change the end frame instead.
     "action": "Starting from <Picture 1>, Ahe lifts his chin from the notebook and turns his head toward the teacher on his left. "
               "His eyebrows rise, the corners of his mouth curl up slowly into a small grateful smile, and he gives one short nod.",
     "dialogue": [{"subject": "ahe", "line": "謝謝你讓我自己做。", "lang": "Chinese", "offscreen": false,
                   "after": "He closes his lips and keeps smiling."}],
     "at": null},                    # later shots: cut time in seconds, strictly increasing and < duration
  ],
  "soundscape": "Quiet empty-classroom room tone with the faint rustle of a cloth.",   # NO dialogue here
  "music": "N/A"
}
"""
import argparse
import hashlib
import stat
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


def voice_refs(spec):
    """audio.voice_ref (one speaker) or audio.voice_refs (list, max 3 - the Ref2VA node takes ref_audio_0..2), in <Audio k> order."""
    a = spec.get("audio") or {}
    v = a.get("voice_refs") or ([a["voice_ref"]] if a.get("voice_ref") else [])
    if len(v) > 3:
        raise ValueError("H3 takes at most 3 reference audios (voice_refs)")
    return v


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
    fixed = audio.get("fixed")
    vrefs = voice_refs(spec)
    aud = {v["subject"]: k for k, v in enumerate(vrefs, start=1)}  # speaker key -> <Audio k>
    voice_ref = vrefs[0] if len(vrefs) == 1 else None  # single-speaker wording kept exactly as before 2026-10-23
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
    motion = bool(cam) and cam.get("kind") == "motion"  # 2026-10-14: gray-mannequin video from make_whitemodel.py as the motion reference
    if motion:
        cols = cam.get("colors")  # 2026-10-15: per-person colored mannequins (make_whitemodel.py --colors), in <Subject> order
        L.append("<Video 1> is ONLY a motion reference: " + (f"{len(cols)} smooth 3D mannequins colored " + ", ".join(cols) if cols else
                 "smooth gray 3D mannequin" + ("s" if cam.get("people", 1) > 1 else ""))
                 + " on a plain background performing the movement. Only body movement, timing, foot placement and arm positions are followed;"
                 + (" the mannequin colors only tell the characters apart and are not reproduced;" if cols else "")
                 + " the " + ("colored" if cols else "gray") + " skin, bald heads, adult body proportions and plain background are not reproduced, and the mannequins carry no props.")
        if cols:
            L.append(" ".join(f"<Subject {idx[s['key']]}> moves like the {c} mannequin." for s, c in zip(subs, cols)))
    elif cam:
        L.append("<Video 1> is ONLY a " + cam.get("role", "Blender camera and spatial-layout guide")
                 + ": its low-poly proxy figures and flat colors are not characters or visual style; only its camera path and spatial relationships are followed.")
    for k, v in enumerate(vrefs, start=1):  # 2026-10-23: up to 3 speakers, one <Audio k> each (node input ref_audio_{k-1})
        L.append(f"<Audio {k}> is the voice-timbre reference for {lab(v['subject'])}.")
    if fixed:
        L.append("<Audio 1> is the complete, exactly timed soundtrack of the target video"
                 + (", containing the spoken lines" if sid else ", containing only quiet room tone") + ".")

    tasks = []
    if first or last:
        tasks.append("keyframe completion")
    if cam or (not first and any(s.get("identity_image") for s in subs)):
        tasks.append("reference generation")
    if vrefs:
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
                 + (f" with the voice timbre referenced from <Audio {aud[key]}>" if key in aud else "")
                 + (" exactly as in <Audio 1>" if fixed else "") + ".")
    L += ["", "summary:", summ, "", "retention_analysis:"]
    for s in subs:
        L.append(f"<Subject {idx[s['key']]}> (appears in [Shot 1]): fully_preserved - identity, face, age, hairstyle, body build and clothing"
                 + (" and props" if s.get("props") else "") + " are retained.")
    if first:
        L.append("<Picture 1> ([Shot 1] first frame): fully_preserved - camera position, framing, set layout, furniture and lighting are retained.")
    if motion:
        L.append("<Video 1> (motion reference): partially_preserved - body movement, timing, leg and arm positions are followed;"
                 " the mannequins' appearance, proportions and background are discarded.")
    elif cam:
        L.append("<Video 1> (camera path and spatial layout): partially_preserved - the camera trajectory and room geometry are followed; the proxy figures' appearance and stiffness are discarded.")
    for k in range(1, len(vrefs) + 1):
        L.append(f"<Audio {k}>: reference - only the voice timbre and accent are followed; the words of <Audio {k}> are not reused.")
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
        if i == 1 and motion:
            cols = cam.get("colors")
            parts.append(cam.get("follow") or (" ".join(f"{_cap(s['desc'].split(',')[0].split(' (')[0])} moves exactly like the {c} mannequin in <Video 1>."
                                                         for s, c in zip(subs, cols)) + " Same timing; everyone keeps their own body proportions."
                                                if cols else
                                                "The characters move exactly like the mannequins in <Video 1>, with the same timing, "
                         "each keeping their own body proportions." if cam.get("people", 1) > 1 else
                         f"{_cap(subs[0]['desc'].split(',')[0].split(' (')[0])} moves exactly like the mannequin in <Video 1>, with the same timing, "
                         "keeping their own body proportions."))
        elif i == 1 and cam:
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
                tim = f", using the voice timbre referenced from <Audio {aud[d['subject']]}>," if len(vrefs) > 1 and d["subject"] in aud else ""
                parts.append(f"{_cap(lab(d['subject']))} says{voice}{tim}" + ("" if tim else ",") + f" <d>[{d.get('lang', 'Chinese')}] {line}</d>")
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
    ctrl = sorted({hex(ord(c)) for c in prompt if ord(c) < 32 and c not in "\n\r\t"})
    if ctrl:  # 2026-11-06 Ep9: a bad regex replacement left \x01\x02 in 23 lines; H3 babbled instead of reading them
        E.append(f"control characters in prompt: {ctrl}")
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


# Veda sparse attention (2026-10-16; needs ComfyUI >= 0.38 + custom_nodes/Veda-on-ComfyUI + setup/downloads_veda.json).
# Measured on a Colab G4: shots <= 5 s about 3% faster, 12 s shots 29% (DMAD 4 steps) / 39% (14 steps) faster, no visible quality loss.
# ON automatically for shots >= 7 s (H3_VEDA_MIN_SEC) when the server has the node (local 5090: 4.5 s shot +10% slower, 12 s shot -29%);
# spec "veda": true/false or env H3_VEDA=1/0 forces it.
VEDA_PREDICTOR = os.environ.get("H3_VEDA_PREDICTOR", "minimax_h3_r2va_veda_preview_fp8.safetensors")
_VEDA_AVAILABLE = None


def use_veda(spec):
    global _VEDA_AVAILABLE
    # 2026-11-02 OFF by default: Veda makes the WHOLE frame flash at frames 51 / 119 / 187 (+18-25 luma levels, decays over ~4 frames).
    # ep1-3 of the Confucius series: 10 of 17 Veda shots flash, 0 of 121 non-Veda shots; same shot + same seed with Veda off has no flash (84 -> 103 s, +23%).
    # Only spec "veda": true or H3_VEDA=1 turns it on; run flashcheck.py on the clip if you do.
    if not (spec.get("veda") is True or os.environ.get("H3_VEDA", "") == "1"):
        return False
    if _VEDA_AVAILABLE is None:
        try:
            _VEDA_AVAILABLE = bool(req("/object_info/VedaSparseAttention", timeout=10))
        except Exception:
            _VEDA_AVAILABLE = False
    return _VEDA_AVAILABLE


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
    # 2026-10-09: may be a list -> chained applies (e.g. pose 0.6 + depth 0.3; community: keep total strength <= ~1)
    # 2026-10-10: default patch = Union 2.0 (1.0 at total 0.95 still turned the subject; 2.0 did not). Old default: "patch": "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"
    for ci, one in enumerate(ctl if isinstance(ctl, list) else ([ctl] if ctl else [])):
        o = 100 * ci  # ids 70-73, 170-173 (80-83 are taken by attention/LoRA/shift)
        g[str(70 + o)] = {"class_type": "LoadVideo", "inputs": {"file": stage(base / one["file"], f"{tag}_control{ci}.mp4")}}
        g[str(71 + o)] = {"class_type": "GetVideoComponents", "inputs": {"video": [str(70 + o), 0]}}
        g[str(72 + o)] = {"class_type": "ModelPatchLoader", "inputs": {"name": one.get("patch", "minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors")}}
        g[str(73 + o)] = {"class_type": "MiniMaxH3FunControlNetApply", "inputs": {
            "model": model, "model_patch": [str(72 + o), 0], "vae": ["3", 0], "strength": one.get("strength", 1.0),
            "start_percent": one.get("start", 0.0), "end_percent": one.get("end", 1.0), "control_video": [str(71 + o), 0]}}
        model = [str(73 + o), 0]
        g["9"]["inputs"]["model"] = model
    if spec.get("easycache"):
        g["50"] = {"class_type": "EasyCache", "inputs": {"model": model, "reuse_threshold": 0.2, "start_percent": 0.15, "end_percent": 0.95, "verbose": True}}
        model = ["50", 0]
        g["9"]["inputs"]["model"] = model
    if use_veda(spec):  # 2026-10-16: Veda learned sparse attention, last on the MODEL wire (only the guider sees it, the scheduler keeps the plain model)
        g["96"] = {"class_type": "VedaSparseAttention", "inputs": {"model": model, "predictor": VEDA_PREDICTOR, "generated_sparsity": "trained",
                   "reference_sparsity": "trained", "full_attention_layers": "", "full_attention_steps": "", "verbose": False}}
        model = ["96", 0]
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
    else:  # timbre only, H3 speaks; 2026-10-23: up to 3 speakers -> ref_audio_0..2 = <Audio 1..3>
        for k, v in enumerate(voice_refs(spec)):
            n = str(32 + k)
            g[n] = {"class_type": "LoadAudio", "inputs": {"audio": stage(base / v["file"], f"{tag}_voice{k}.wav" if k else f"{tag}_voice.wav")}}
            g["6"]["inputs"][f"ref_audios.ref_audio_{k}"] = [n, 0]
    if spec.get("first_clip"):  # 2026-10-10: multi-frame continuation - previous clip's last 5/22/39 frames anchored at frame 0 (AddGuide accepts 17k+5 frame clips)
        g["44"] = {"class_type": "LoadVideo", "inputs": {"file": stage(base / spec["first_clip"], f"{tag}_firstclip.mp4")}}
        g["45"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["44", 0]}}
        g["40"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": cond, "latent": latent, "vae": ["3", 0], "image": ["45", 0], "frame_idx": 0}}
        cond = ["40", 0]
    elif spec.get("first_frame"):
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


def _place(dst, data=None, src=None):
    """Put `data` (bytes) or a copy of file `src` at dst as a brand-new file: written to an exclusively created temp file next to
    it, then os.replace()d over dst - whatever sat at dst (even a hard / symbolic link to another file) is replaced, never
    written through. Only the temp file this call created is ever removed."""
    import uuid
    dst = Path(dst)
    tmp = dst.with_name(f".{dst.name}.new_{uuid.uuid4().hex[:8]}")
    made = False
    try:
        with open(tmp, "xb") as fh:
            made = True
            if src is not None:
                with open(src, "rb") as fs:
                    shutil.copyfileobj(fs, fh, 1 << 20)
            else:
                fh.write(data)
        os.replace(tmp, dst)
    except BaseException:
        if made:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


_LAST_GEN = {}  # what the latest generate() call wrote (push mode re-writes / checks its files from this; unused otherwise)


def generate(spec, prompt, base, out, tag=None, private_io=False):
    tag = tag or f"{out.name}_{int(time.time())}"
    g, length = build_graph(spec, prompt, base, tag)
    _LAST_GEN.clear()
    _LAST_GEN["workflow"] = json.dumps(g, ensure_ascii=False, indent=1)
    if private_io:  # push mode: every file written into staging is placed as a new file (see _place)
        _place(out / "workflow_api.json", _LAST_GEN["workflow"].encode("utf-8"))
    else:
        (out / "workflow_api.json").write_text(_LAST_GEN["workflow"], encoding="utf-8")
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
        _LAST_GEN["raw_src"] = str(COMFY / "output" / v.get("subfolder", "") / v["filename"])
        if private_io:
            _place(raw, src=_LAST_GEN["raw_src"])
        else:
            shutil.copy2(COMFY / "output" / v.get("subfolder", "") / v["filename"], raw)
        frames = [COMFY / "output" / "h3_shot_png" / tag / im["filename"] for im in e["outputs"]["16"]["images"]]
        lst = out / "frames.txt"
        # concat-list quoting: a ' inside a path is written '\'' (only names containing a quote differ; they failed before)
        _LAST_GEN["frames"] = "".join("file '" + f.as_posix().replace("'", "'\\''") + f"'\nduration {1 / FPS:.6f}\n" for f in frames)
        if private_io:
            # push mode (staging may sit in a synced folder): the frame list is a file in the private folder below, the audio is read from
            # ComfyUI's own output, and the clip is encoded into a private folder in the system temp dir (the caller checks and
            # hashes it there: _LAST_GEN["clip_private"]); `out` only gets a copy. frames.txt is only a record (KEEP_PNG)
            import tempfile
            priv = Path(tempfile.mkdtemp(prefix="h3push_"))
            _LAST_GEN["clip_private"] = str(priv / "clip.mp4")
            # the list is a file in the private folder, not stdin: ffmpeg reads a POSIX absolute path inside a list given as
            # pipe:0 as "pipe:/usr/..." and cannot open it (Linux / Colab / RunPod); Windows C:/ paths worked either way
            plist = priv / "frames_list.txt"
            plist.write_bytes(_LAST_GEN["frames"].encode("utf-8"))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                            "-i", str(plist), "-i", _LAST_GEN["raw_src"], "-r", str(FPS),
                            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
                            "-c:a", "copy", _LAST_GEN["clip_private"]], check=True)
            _place(out / "clip.mp4", src=_LAST_GEN["clip_private"])
            if os.environ.get("H3_KEEP_PNG") == "1":
                _place(lst, _LAST_GEN["frames"].encode("utf-8"))
        else:
            lst.write_text(_LAST_GEN["frames"], encoding="utf-8")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(raw), "-r", str(FPS),
                            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
                            "-c:a", "copy", str(out / "clip.mp4")], check=True)
        # The PNG frames are only needed to encode clip.mp4 (crf 12) and fill a disk fast (~36 MB per second of 768p video, every seed kept).
        # Delete them once clip.mp4 exists. H3_KEEP_PNG=1 keeps them (e.g. lossless frame experiments).
        if os.environ.get("H3_KEEP_PNG") != "1" and (out / "clip.mp4").stat().st_size > 0:
            shutil.rmtree(COMFY / "output" / "h3_shot_png" / tag, ignore_errors=True)
            if not private_io:  # normal mode wrote frames.txt above; push mode never did, so it never deletes one
                (out / "frames.txt").unlink(missing_ok=True)
    else:
        print(json.dumps(e.get("status", {}), ensure_ascii=False)[:3000])
    meta = {"ok": ok, "length": length, "seed": spec.get("seed", 42), "wall_s": round(time.time() - t0, 1), "tag": tag, "veda": "96" in g}
    _LAST_GEN["meta"] = json.dumps(meta, ensure_ascii=False, indent=1)
    if private_io:
        _place(out / "meta.json", _LAST_GEN["meta"].encode("utf-8"))
    else:
        (out / "meta.json").write_text(_LAST_GEN["meta"], encoding="utf-8")
    print(f"[{'ok' if ok else 'FAIL'}] {out / 'clip.mp4'} {meta['wall_s']}s", flush=True)
    return ok


# ----------------------------------------------------------------------------------------------- end-frame push
PUSH_CAMERA = ("Very slow, smooth dolly push-in that ends exactly on the framing of the supplied last-frame image:"
               " the frame becomes only slightly tighter; no zoom, no cut.")
PUSH_FIXED_CAMERA = ("Static locked-off shot on a tripod: the framing stays exactly as in the first frame and the depth of field"
                     " does not change.")  # pass 1 always uses this (or push_end.fixed_camera): its last frame must keep the first-frame framing
PUSH_KEYS = {"zoom", "fixed_clip", "camera", "fixed_camera"}
FACE_MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_URL = "https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet"


def push_conf(spec):
    """None when the key is absent; otherwise a dict (invalid values are reported by push_errors, never silently dropped)."""
    if "push_end" not in spec:
        return None
    p = spec["push_end"]
    if isinstance(p, bool) or not isinstance(p, (int, float, dict)):
        return {"zoom": None, "_bad": f"push_end must be a number or an object, got {p!r}"}
    p = {"zoom": p} if isinstance(p, (int, float)) else dict(p)
    p.setdefault("zoom", 1.15)
    return p


def _inputs(spec, conf, raw=False):
    """Every file the graph loads (mirror of build_graph) + the external fixed take. Only string paths are returned
    (raw=True: every non-empty value, so push_errors can report a number / object given as a path)."""
    d = lambda x: x if isinstance(x, dict) else {}  # noqa: E731
    L = lambda x: x if isinstance(x, list) else []  # noqa: E731
    a = d(spec.get("audio"))
    ctl = spec.get("control")
    files = [spec.get("first_frame"), spec.get("last_frame"), spec.get("first_clip"), d(a.get("fixed")).get("file"),
             d(spec.get("camera_video")).get("file"), conf.get("fixed_clip") if conf else None]
    files += [d(s).get("identity_image") for s in L(spec.get("subjects"))]
    files += [d(c).get("file") for c in (ctl if isinstance(ctl, list) else ([ctl] if ctl else []))]
    files += [d(v).get("file") for v in L(a.get("voice_refs")) + ([a["voice_ref"]] if a.get("voice_ref") else [])]
    return [f for f in files if f not in (None, "") and (raw or isinstance(f, str))]


def fixed_spec(spec, conf):
    """Pass-1 spec: push_end removed and the camera line replaced by a locked-off one, whatever the spec's own camera says
    (a moving pass 1 would end on a different framing and the end frame would not be a push of the first frame)."""
    sp = json.loads(json.dumps(spec))
    sp.pop("push_end", None)
    cam = conf.get("fixed_camera") if isinstance(conf.get("fixed_camera"), str) and conf.get("fixed_camera").strip() else PUSH_FIXED_CAMERA
    if sp.get("shots"):
        sp["shots"][0]["camera"] = cam
    return sp


def face_model_error():
    try:
        import cv2
    except ImportError:
        return "push_end needs OpenCV (pip install opencv-python) for the face-centred end-frame crop"
    hint = f"download face_detection_yunet_2023mar.onnx from OpenCV Zoo ({YUNET_URL}) into {FACE_MODEL.parent}"
    if not FACE_MODEL.exists():
        return f"push_end needs the YuNet face model {FACE_MODEL}: {hint}"
    try:
        cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.6)
    except Exception as e:  # truncated / corrupt download
        return f"YuNet face model {FACE_MODEL} cannot be loaded ({type(e).__name__}); {hint}"
    return None


def graph_errors(sp, base, label, skip=None):
    """Build the real ComfyUI graph for `sp` with staging replaced by a recorder (nothing copied, nothing sent): a field the
    graph needs but the spec lacks (e.g. a control entry without "file") or any input file that does not exist is an error now,
    not halfway through a generation. `skip` = a path that will only exist later (the pass-2 end frame)."""
    global stage
    seen, real = [], stage
    def record(src, name):
        seen.append(Path(src))
        return f"h3_shot/{name}"
    stage = record
    try:
        build_graph(sp, "check", base, "check")
    except Exception as e:
        return [f"push_end {label}: the spec cannot be turned into a ComfyUI graph ({type(e).__name__}: {e})"]
    finally:
        stage = real
    sk = Path(skip).resolve() if skip else None
    return [f"push_end {label}: input file {q} not found" for q in seen if q.resolve() != sk and not q.is_file()]


def push_errors(spec, conf, base, out, spec_path=None):
    """Everything push mode needs, checked before any prompt is built or any file is written, generated or replaced."""
    nul = [str(x) for x in [out, spec_path] + _inputs(spec, None if conf.get("_bad") else conf) if x is not None and "\0" in str(x)]
    if nul:  # before any path is resolved (Linux: ValueError; Windows: silently read as another name)
        return [f"push_end: path(s) contain a NUL character: {', '.join(repr(x) for x in nul)}"]
    E = [conf["_bad"]] if conf.get("_bad") else []
    if conf.get("_bad"):
        return E + push_input_errors(spec, conf, base, out, spec_path)
    unknown = sorted(set(conf) - PUSH_KEYS)
    if unknown:
        E.append(f"push_end has unknown key(s) {unknown}; allowed: {sorted(PUSH_KEYS)}")
    z = conf.get("zoom")
    if not isinstance(z, (int, float)) or isinstance(z, bool) or not 1.0 < z <= 1.5:
        E.append(f"push_end zoom {z!r} outside (1.0, 1.5]; round-2 test used 1.15")
    for k in ("fixed_clip", "camera", "fixed_camera"):
        if k in conf and not (isinstance(conf[k], str) and conf[k].strip()):
            E.append(f"push_end {k} must be a non-empty string, got {conf[k]!r}")
    if not isinstance(spec.get("shots"), list) or len(spec["shots"]) != 1 or not isinstance(spec["shots"][0], dict):
        E.append("push_end needs a single-shot spec (\"shots\": [ {...} ], no in-clip cuts)")
    d = spec.get("duration")
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not 0 < d <= 20:
        E.append(f"push_end: duration must be a number of seconds, got {d!r}")
    if not spec.get("first_frame") or spec.get("last_frame") or spec.get("first_clip"):
        E.append("push_end needs first_frame only (no last_frame / first_clip): the end frame is made from the fixed take")
    if spec.get("raw_prompt"):
        E.append("push_end cannot be combined with raw_prompt (the camera line is rewritten for both passes)")
    if spec.get("camera_video"):
        E.append("push_end cannot be combined with camera_video: a camera guide would move pass 1 (the end frame must come from a"
                 " locked-off take), and a mannequin motion reference + push is untested")
    if spec.get("control"):
        E.append("push_end cannot be combined with control (ControlNet video): it would hold pass 1 and pass 2 to the control"
                 " video's own framing, against the locked-off take and the zoomed end frame")
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            E.append(f"push_end needs {t} on PATH (checks the takes and reads the last frame)")
    fm = face_model_error()
    if fm:
        E.append(fm)
    for k in ("audio", "camera_video"):
        if spec.get(k) and not isinstance(spec[k], dict):
            E.append(f"push_end: {k} must be an object, got {spec[k]!r}")
    for f in _inputs(spec, conf, raw=True):
        if not isinstance(f, str):
            E.append(f"push_end: input path {f!r} is not a string")
        elif not (base / f).is_file():
            E.append(f"push_end: input file {f} not found (checked before anything is generated or replaced)")
    E += push_input_errors(spec, conf, base, out, spec_path)
    if not E:  # both passes, exactly as they will be built (fixed take reused via fixed_clip -> pass 1 is not built)
        if not conf.get("fixed_clip"):
            E += graph_errors(fixed_spec(spec, conf), base, "pass 1")
        end = (out / "push_end.png").resolve()  # absolute: build_graph would otherwise prefix it with the spec folder
        E += [x for x in graph_errors(push_spec(spec, conf, end), base, "pass 2", skip=end) if x not in E]
    return E


INTERNAL_DIRS = re.compile(r"push_fixed|push_fixed_new_.*|push_pass2_.*|push_dryrun", re.IGNORECASE)  # Windows names: any case


def _is_link(path):
    """Symbolic link or Windows directory junction (a folder that is really somewhere else)."""
    path = Path(path)
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def link_errors(out):
    """push_end only ever writes into folders it owns: <out>/push_fixed, push_dryrun (and its notes) and the staging folders
    must be real folders / files here, never links / junctions to another shot folder (its files would be replaced there)."""
    out = Path(out)
    dr = out / "push_dryrun"  # a dry run writes these three notes
    cands = ([out / "push_fixed", dr] + [dr / x for x in ("prompt_fixed.txt", "prompt.txt", "shot.json")]
             + list(out.glob("push_pass2_*")) + list(out.glob("push_fixed_new_*"))) if out.is_dir() else []
    E = [f"{q} is a link / junction to another folder; push_end does not write through it - replace it with a real folder"
         for q in cands if _is_link(q)]
    # wrong kinds at the names push_end writes to (checked before the first write, so nothing is half-written)
    for q in (out / "push_fixed", dr):
        if os.path.lexists(q) and not q.is_dir():
            E.append(f"{q} exists and is not a folder; push_end needs that name for its own folder")
    for q in [dr / x for x in ("prompt_fixed.txt", "prompt.txt", "shot.json")]:
        if os.path.lexists(q) and not q.is_file() and not _is_link(q):
            E.append(f"{q} exists and is not a file; a dry run writes its notes there")
    return E


def push_input_errors(spec, conf, base, out, spec_path=None):
    """Push mode writes many files into --out (prompts, spec copies, temp/end PNGs, both takes): no input may live there,
    including the spec file itself (e.g. re-running from <out>/push_spec.json would overwrite it)."""
    o = out.resolve()
    E = []
    if out.exists() and not out.is_dir():
        return [f"push_end --out {out} exists and is not a folder"]
    E += link_errors(out)
    if INTERNAL_DIRS.fullmatch(o.name):
        E.append(f"push_end --out {out}: '{o.name}' is a folder push_end manages inside a shot folder; use the shot folder itself")
    if spec_path is not None:
        q = Path(spec_path).resolve()
        if o in q.parents:
            E.append(f"push_end spec {spec_path} is inside the --out folder {out}: copy it elsewhere first")
    for r in _inputs(spec, conf if not conf.get("_bad") else None):
        q = (base / r).resolve()
        if q == o or o in q.parents:
            E.append(f"push_end input {r} is inside the --out folder {out}: it could be overwritten; keep inputs elsewhere")
    return E


FINGERPRINT_VERSION = 2


def push_fingerprint(spec, prompt_fixed, base, snap=None):
    """Spec (minus push_end) + fixed prompt + content hash of every input file + model setup (MODELS, ComfyUI dir, H3_* env)
    -> reuse a cached fixed take only if all of it is unchanged. With `snap` ({spec path string: (path as resolved when it was
    copied, snapshot file)}) every input is hashed from the run's snapshot only - the very files both passes load - and the
    fingerprint records the path as resolved at copy time; an input missing from the map is an error, never re-read live."""
    import hashlib
    sp = {k: v for k, v in spec.items() if k != "push_end"}
    st = []
    for f in _inputs(spec, None):
        if snap is not None:
            where, src = snap[f]  # KeyError -> the run stops (no fallback to the live file)
            st.append([where, hashlib.sha256(Path(src).read_bytes()).hexdigest()])
            continue
        q = (base / f).resolve()
        st.append([str(q), hashlib.sha256(q.read_bytes()).hexdigest() if q.exists() else None])
    env = {k: v for k, v in os.environ.items() if k.startswith("H3_") and k != "H3_KEEP_PNG"}
    veda = use_veda(spec) if (spec.get("veda") is True or os.environ.get("H3_VEDA", "") == "1") else False
    # FINGERPRINT_VERSION: bump whenever what the fingerprint covers changes, so caches written by an older rule are never
    # reused (v2 = input content hashed from the run's snapshot, paths as resolved when copied)
    blob = json.dumps(["h3_shot push_end fingerprint", FINGERPRINT_VERSION, sp, prompt_fixed, st, MODELS, str(COMFY), env, veda],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sha_ino(path):
    """(sha256, file id) of a file, both read through one open handle (the id is the very file that was hashed)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        ino = os.fstat(fh.fileno()).st_ino
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), ino


def _ident(path):
    """A file's identity for the publish journal: "sha256:file-id" (content and which file), read through one handle. A symbolic
    link is never followed: it gets a "link:..." identity that can never equal a recorded file identity."""
    import hashlib
    import stat as stat_
    if Path(path).is_symlink():
        return "link:" + os.readlink(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        fst = os.fstat(fh.fileno())
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    lst = os.lstat(path)  # the name itself (never followed): must be the very file that was opened and hashed
    if stat_.S_ISLNK(lst.st_mode) or lst.st_ino != fst.st_ino or lst.st_dev != fst.st_dev:
        return f"changed:{lst.st_ino}:{fst.st_ino}"
    return f"{h.hexdigest()}:{fst.st_ino}"


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


OPTIONAL_FILES = ("frames.txt",)  # the only per-take file that may legitimately be absent (exists only with H3_KEEP_PNG=1)
FIXED_FILES = ("clip.mp4", "clip_savevideo.mp4", "meta.json", "workflow_api.json", "frames.txt", "prompt.txt", "shot.json")
# the files a fixed take in push_fixed/ can consist of (generate() output + the records written with it)


def _tool_file(name, known):
    """`name` is one of `known` or the tool's own backup of one: <name>.old_<job>, job = 8 lowercase hex digits (uuid4 hex[:8]),
    left if a backup could not be deleted. Any other name (e.g. a user's clip.mp4.old_trial) is not the tool's."""
    return name in known or any(re.fullmatch(re.escape(k) + r"\.old_[0-9a-f]{8}", name) for k in known)


FIXED_VIDEOS = ("clip.mp4", "clip_savevideo.mp4")  # the irreplaceable files a push_fixed/ folder can hold


def owned_fixed_videos(fdir):
    """{video name: identity "sha:id" or None if absent} when every video present in fdir is push_end's own cached file
    (fingerprint.txt lists it as "<sha256> <name>" with exactly its content); False as soon as one is not (a normal run's output,
    a file put there by hand, an old one-line fingerprint that cannot show it). push_end never replaces or deletes a video it
    cannot show is its own."""
    present = [n for n in FIXED_VIDEOS if os.path.lexists(fdir / n)]
    if not present:
        return {n: None for n in FIXED_VIDEOS}
    try:
        lines = (fdir / "fingerprint.txt").read_bytes().decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    out = {n: None for n in FIXED_VIDEOS}
    for n in present:
        want = [ln.partition(" ")[0] for ln in lines[1:] if ln.partition(" ")[2] == n]
        try:
            if len(want) != 1 or not (fdir / n).is_file():
                return False
            ident = _ident(fdir / n)  # content + file id from one handle
        except OSError:
            return False
        if ident.split(":")[0] != want[0]:
            return False
        out[n] = ident
    return out


def cache_hit(fdir, fp, shot1, prompt1, used):
    """True if push_fixed/ holds exactly the set fingerprint.txt describes for this fingerprint (see _run_push). On a hit the
    clip is left copied at `used` (the private copy whose hash was checked)."""
    try:
        lines = (fdir / "fingerprint.txt").read_bytes().decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if len(lines) < 2 or lines[0] != fp:
        return False
    want = {}
    for ln in lines[1:]:
        sha, _, name = ln.partition(" ")
        if len(sha) != 64 or not name or "/" in name or "\\" in name:
            return False
        want[name] = sha
    required = {n for n in FIXED_FILES if n not in OPTIONAL_FILES}  # same list the publish requires
    if not required <= set(want) or not set(want) <= set(FIXED_FILES):
        return False
    try:
        # the tool's own files must be exactly the listed ones (an unlisted frames.txt, or a listed file missing -> miss);
        # anything else in the folder (a note, a .old_ backup left by an interrupted publish) is ignored
        present = {q.name for q in fdir.iterdir() if q.is_file() and q.name in FIXED_FILES}  # .old_ leftovers: ignored
        if present != set(want):
            return False
        if (fdir / "shot.json").read_bytes() != shot1 or (fdir / "prompt.txt").read_bytes() != prompt1:
            return False
        for name, sha in want.items():
            if name != "clip.mp4" and _sha256(fdir / name) != sha:
                return False
        shutil.copyfile(fdir / "clip.mp4", used)  # content only: a read-only source must not make the working copy read-only
    except OSError:
        return False
    return _sha256(used) == want["clip.mp4"]


def probe(clip):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", str(clip)], capture_output=True, text=True, errors="replace")
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):  # "0/0" or junk -> 0 fps, reported as a mismatch by check_fixed
        fps = 0.0
    return int(s.get("width") or 0), int(s.get("height") or 0), fps, int(s.get("nb_read_frames") or 0)


def check_fixed(clip, spec):
    """A take must match this spec's size, 24 fps and frame count and carry an audio track (fixed take: else its last frame is the
    wrong moment/framing; pushed take: else a short/broken encode would be delivered as success)."""
    if not clip.exists() or clip.stat().st_size == 0:
        return [f"{clip} missing or empty"]
    w, h, fps, n = probe(clip)
    want = spec.get("size") or [1344, 768]
    need = frames_for(spec["duration"])
    bad = []
    if [w, h] != list(want):
        bad.append(f"size {w}x{h} != spec {want[0]}x{want[1]}")
    if abs(fps - FPS) > 0.01:
        bad.append(f"fps {fps:.3f} != {FPS}")
    if n != need:  # H3 always writes exactly frames_for(duration) frames; one missing frame = a cut-short take
        bad.append(f"{n} frames != expected {need} for {spec['duration']} s")
    def span(sel):
        """(first pts, last pts + its duration) from the packets themselves: the stream 'duration' header can be derived from
        the frame count and hides a held / stretched frame. None = no such stream; 'unreadable' = timestamps missing."""
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries", "packet=pts_time,duration_time",
                            "-of", "json", str(clip)], capture_output=True, text=True, errors="replace")
        pk = json.loads(r.stdout or "{}").get("packets") or []
        if not pk:
            has = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries", "stream=index", "-of", "csv=p=0",
                                  str(clip)], capture_output=True, text=True, errors="replace").stdout.strip()
            return "unreadable" if has else None
        try:
            ts = [(float(x["pts_time"]), float(x["duration_time"])) for x in pk]  # missing / "N/A" -> unreadable (never assume 0)
        except (KeyError, TypeError, ValueError):
            return "unreadable"
        ts.sort()
        gaps[sel] = max([b[0] - (a[0] + a[1]) for a, b in zip(ts, ts[1:])] or [0.0])  # hole between two consecutive packets
        if sel == "v:0":  # every frame on the 24 fps grid: a held frame and a short one that cancel out keep the total length
            grid[sel] = max(abs(t - ts[0][0] - i / FPS) for i, (t, _d) in enumerate(ts))
        return ts[0][0], max(t + d for t, d in ts)
    gaps, grid = {}, {}
    va, aa = span("v:0"), span("a:0")
    if grid.get("v:0", 0.0) > 0.001:  # timestamp rounding only (real H3 takes: 3e-7 s); 1 ms also bounds every frame interval
        bad.append(f"video frames are off the {FPS} fps grid by up to {grid['v:0']:.3f} s (held / dropped frame)")
    if gaps.get("a:0", 0.0) > 0.05:
        # a hole in the middle of the audio (start and end still line up): lip-sync would drift / the line would drop out.
        # Real H3 clips have no gap at all between AAC packets (32 sampled clips: 0.000 s)
        bad.append(f"audio has a {gaps['a:0']:.2f} s gap between packets")
    if aa is None:
        bad.append("no audio track")
    elif aa == "unreadable" or not isinstance(va, tuple):  # va None (no video) or "unreadable"
        bad.append("audio/video start or duration unreadable")
    elif abs(aa[0] - va[0]) > 0.1 or abs(aa[1] - va[1]) > 0.1:
        # truncated, overlong or offset audio (MV lip-sync would be shifted) must not pass
        bad.append(f"audio {aa[0]:.2f}-{aa[1]:.2f} s does not line up with video {va[0]:.2f}-{va[1]:.2f} s")
    # the packets can have perfect timestamps and still hold damaged data: decode both tracks once (about 0.2 s per clip; 25
    # sampled real H3 clips decode with no error at all)
    dec = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(clip), "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace")
    if dec.returncode or dec.stderr.strip():
        bad.append("video/audio do not decode cleanly: " + ((dec.stderr.strip().splitlines() or [f"ffmpeg exit {dec.returncode}"])[0])[:160])
    if isinstance(va, tuple) and abs((va[1] - va[0]) - need / FPS) > 0.001:  # timestamp rounding only (real H3: 7e-7 s)
        # right frame count but a held/stretched frame (edited take) -> wrong timing
        bad.append(f"video lasts {va[1] - va[0]:.2f} s, expected {need / FPS:.2f} s ({need} frames at {FPS} fps)")
    return bad


def settle_generated(d):
    """Push mode, right after a successful generate() into staging folder d: re-write workflow_api.json, meta.json (and
    frames.txt, if kept) byte-for-byte from what generate() produced, so nothing done to them while the job waited on the GPU
    survives, and check clip_savevideo.mp4 against ComfyUI's own output file. Returns (expected sha256 per file, problem)."""
    exp = {}
    for name, key in (("workflow_api.json", "workflow"), ("meta.json", "meta"), ("frames.txt", "frames")):
        # frames.txt is a record only with H3_KEEP_PNG=1 (then always re-written, even if it went missing)
        if key in _LAST_GEN and (name != "frames.txt" or os.environ.get("H3_KEEP_PNG") == "1"):
            data = _LAST_GEN[key].encode("utf-8")
            try:
                _place(d / name, data)  # a new file of our own; whatever sits at `name` (even a hard link) is replaced
            except OSError as e:
                return exp, f"could not write {d / name} ({type(e).__name__}: {e})"
            exp[name] = hashlib.sha256(data).hexdigest()
    src = _LAST_GEN.get("raw_src")
    if src and not (d / "clip_savevideo.mp4").is_file():  # generate() copied it: a missing copy is a failure, never skipped
        return exp, f"{d / 'clip_savevideo.mp4'} is missing (ComfyUI's output was copied there)"
    if src:
        want = _sha256(src)
        if _sha256(d / "clip_savevideo.mp4") != want:
            return exp, f"{d / 'clip_savevideo.mp4'} is not ComfyUI's output {src}"
        exp["clip_savevideo.mp4"] = want
    return exp, None


def check_private(staged, spec):
    """Push mode after generate(private_io=True): check_stable on the private copy (system temp, not synced), then the clip in
    staging must have exactly that hash. The private folder is removed afterwards. (problems, sha)."""
    priv = _LAST_GEN.get("clip_private")
    if not priv:  # generate() did not encode privately (e.g. a test double): check the staged file itself
        return check_stable(staged, spec)
    try:
        bad, sha = check_stable(Path(priv), spec)
        if not bad and (not Path(staged).is_file() or _sha256(staged) != sha):
            bad = [f"{staged} is not the clip that was encoded and checked"]
        return bad, sha
    finally:
        shutil.rmtree(Path(priv).parent, ignore_errors=True)
        _LAST_GEN.pop("clip_private", None)


def check_stable(clip, spec):
    """check_fixed + the clip's sha256 taken BEFORE the checks and confirmed after them: (problems, sha). A take that changed
    while it was being checked fails; the returned sha is the one every later step (copy, publish) must still see."""
    h0 = _sha256(clip) if Path(clip).is_file() else None
    bad = check_fixed(clip, spec)
    if not bad and (_sha256(clip) if Path(clip).is_file() else None) != h0:
        bad = [f"{clip} changed while it was being checked"]
    return bad, h0


def last_frame_png(clip, dst):
    """Decode the whole first video track (v:0, the one check_fixed verified) into one PNG that keeps being overwritten ->
    the true last frame of THAT track, whatever other tracks / container end time say. Clips are <= 12 s, so this is quick."""
    dst.unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-map", "0:v:0", "-update", "1", str(dst)], check=True)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"could not read the last frame of {clip}")


def crop_zoom(src, dst, zoom):
    """Zoom `zoom`x around the largest face (face kept ~38% down the crop), same output size; plain centre crop if no face."""
    import cv2
    import numpy as np
    img = cv2.imdecode(np.fromfile(str(src), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {src}")
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (w, h), 0.6)
    _, f = det.detect(img)
    cw, ch = w / zoom, h / zoom
    if f is not None and len(f):
        f = max(f, key=lambda r: r[2] * r[3])
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        x0 = min(max(cx - cw / 2, 0), w - cw)
        y0 = min(max(cy - ch * 0.38, 0), h - ch)
        face = [round(float(cx)), round(float(cy))]
    else:
        x0, y0, face = (w - cw) / 2, (h - ch) / 2, None
    M = np.float32([[zoom, 0, -x0 * zoom], [0, zoom, -y0 * zoom]])
    tmp = dst.with_name(dst.stem + "_tmp.png")
    cv2.imencode(".png", cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4))[1].tofile(str(tmp))
    os.replace(tmp, dst)
    return {"face": face, "crop": [round(float(x0)), round(float(y0)), round(cw), round(ch)]}


def abs_spec(spec, base, to=None):
    """Copy of `spec` with every input path made absolute (relative paths are relative to the spec's folder `base`), so a
    spec saved in another folder (push_fixed/shot.json, push_spec.json) still points at the same files. With `to`
    ({path string as written in the spec: (resolved path, snapshot file)}) every path is replaced by its snapshot file, taken
    from that map only (never re-resolved)."""
    sp = json.loads(json.dumps(spec))
    ab = lambda f: (to[f][1] if to else str((base / f).resolve())) if f else f  # noqa: E731  (KeyError = input not snapshotted)
    for k in ("first_frame", "first_clip"):
        if sp.get(k):
            sp[k] = ab(sp[k])
    for k in ("fixed", "voice_ref"):
        if isinstance((sp.get("audio") or {}).get(k), dict) and sp["audio"][k].get("file"):
            sp["audio"][k]["file"] = ab(sp["audio"][k]["file"])
    for v in (sp.get("audio") or {}).get("voice_refs") or []:
        if v.get("file"):
            v["file"] = ab(v["file"])
    if (sp.get("camera_video") or {}).get("file"):
        sp["camera_video"]["file"] = ab(sp["camera_video"]["file"])
    for su in sp.get("subjects", []):
        if su.get("identity_image"):
            su["identity_image"] = ab(su["identity_image"])
    ctl = sp.get("control")
    for c in (ctl if isinstance(ctl, list) else ([ctl] if ctl else [])):
        if c.get("file"):
            c["file"] = ab(c["file"])
    return sp


def push_spec(spec, conf, end_png, base=None, to=None):
    """Second-pass spec. With `base`, every input path is made absolute so the saved push_spec.json is a faithful record
    (`to`: map the paths through abs_spec's map, e.g. to the paths as resolved when the input snapshot was taken)."""
    sp = abs_spec(spec, base, to) if base is not None else json.loads(json.dumps(spec))
    sp.pop("push_end", None)
    sp["last_frame"] = str(end_png)
    sp["shots"][0]["camera"] = conf.get("camera") or PUSH_CAMERA
    return sp


def _locks(out):
    import hashlib
    import tempfile
    d = Path(tempfile.gettempdir()) / "h3_shot_locks"
    d.mkdir(parents=True, exist_ok=True)
    return d, hashlib.sha1(str(Path(out).resolve()).lower().encode("utf-8")).hexdigest()[:16]


def _try_lock(path):
    """Open + exclusively lock byte 0 of `path` without waiting. The open file (keep it referenced) or None if busy."""
    f = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


GATE_TIMEOUT = 10.0  # s; the gate is only ever held for milliseconds


def _wait_lock(path, timeout=None):
    """Like _try_lock, but waits (polling) up to `timeout` s (default GATE_TIMEOUT): used for the gate."""
    timeout = GATE_TIMEOUT if timeout is None else timeout
    t0 = time.monotonic()
    while True:
        f = _try_lock(path)
        if f is not None or time.monotonic() - t0 > timeout:
            return f
        time.sleep(0.02)


# Three lock files per output folder, all in the temp dir (<out> gets no extra files; the OS drops a lock when its process
# exits, so a crash never leaves a stale one):
#   <key>.gate    held for milliseconds while a run checks / registers; serialises the steps below
#   <key>.lock    held by a push_end run for its whole run (dry or real)
#   <key>.n<pid>  held by each normal run for its whole run (normal runs never block each other)
def _lock_failed(out, e):
    import tempfile
    return None, f"could not use the lock files for {out} in {Path(tempfile.gettempdir()) / 'h3_shot_locks'} ({type(e).__name__}: {e})"


def push_acquire(out):
    """For a push_end run: (lock, None) - keep the lock referenced for the whole run - or (None, reason). Refused while another
    push run or any normal run is working on this folder, and when the lock files cannot be used (never an exception)."""
    try:
        return _push_acquire(out)
    except (OSError, ValueError) as e:  # e.g. the lock folder not writable, a NUL in the path
        return _lock_failed(out, e)


def _push_acquire(out):
    d, key = _locks(out)
    g = _wait_lock(d / f"{key}.gate")
    if g is None:
        return None, f"could not get the lock gate for {out} within {GATE_TIMEOUT:g} s"
    try:
        lk = _try_lock(d / f"{key}.lock")
        if lk is None:
            return None, f"another push_end run is using {out}"
        if normal_runs_active(out):
            lk.close()
            return None, f"a normal h3_shot run is writing into {out}; wait for it (or use another --out)"
        return lk, None
    finally:
        g.close()


def normal_guard(out):
    """For a normal (non-push) run: refused only while a push_end run holds this folder; otherwise registers its own
    per-process lock that push runs look for. Two normal runs never block each other (they only take turns on the gate for
    milliseconds). Returns (open registration - keep it referenced -, None) or (None, reason); never an exception."""
    try:
        return _normal_guard(out)
    except (OSError, ValueError) as e:
        return _lock_failed(out, e)


def _normal_guard(out):
    d, key = _locks(out)
    g = _wait_lock(d / f"{key}.gate")
    if g is None:
        return None, f"could not get the lock gate for {out} within {GATE_TIMEOUT:g} s"
    try:
        lk = _try_lock(d / f"{key}.lock")
        if lk is None:
            return None, f"a push_end run is using {out}; wait for it (or use another --out)"
        lk.close()  # the gate is still held, so no push run can take the folder lock before we are registered
        mine = _try_lock(d / f"{key}.n{os.getpid()}.lock")
    finally:
        g.close()
    return (mine if mine is not None else open(os.devnull, "rb")), None


def normal_runs_active(out):
    """Called by push_acquire while it holds the gate: True if a normal run registered on this folder is still running.
    Registrations of finished runs (lock released by the OS) are deleted."""
    d, key = _locks(out)
    busy = False
    for q in d.glob(f"{key}.n*.lock"):
        f = _try_lock(q)
        if f is None:
            busy = True
            continue
        f.close()
        try:
            q.unlink()
        except OSError:
            pass
    return busy


def run_push(spec, conf, base, out, prompt_fixed, spec_bytes=None, locked=False):
    """Pass 1 = spec with a locked-off camera line -> last frame x zoom -> pass 2 with last_frame + push camera, same seed.
    Holds the folder lock for the whole run via push_acquire (main() already holds it and passes locked=True)."""
    def go():
        E = push_errors(spec, conf, base, out)  # also for direct calls: inputs inside --out, missing files, tools, structure
        # every argument must describe this spec, or the published records (shot.json / push_spec.json) would not match the clip
        if conf != push_conf(spec):
            E.append(f"conf {conf!r} differs from the spec's push_end {push_conf(spec)!r}")
        elif not E:
            try:
                if prompt_fixed != build_prompt(fixed_spec(spec, conf)):
                    E.append("prompt_fixed is not the pass-1 prompt of this spec (build it with build_prompt(fixed_spec(spec, conf)))")
            except Exception as e:
                E.append(f"cannot build the prompt from this spec ({type(e).__name__}: {e})")
        if spec_bytes is not None:
            canon = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True)  # noqa: E731  (true != 1, 1 != 1.0, unlike ==)
            try:
                same = canon(json.loads(spec_bytes.decode("utf-8"))) == canon(spec)
            except (UnicodeDecodeError, ValueError, TypeError):
                same = False
            if not same:
                E.append("spec_bytes do not decode to this spec")
        if E:
            print("[FAIL] push_end checks failed; nothing was changed: " + "; ".join(E), flush=True)
            return False
        try:
            return _run_push(spec, conf, base, out, prompt_fixed, spec_bytes)
        except Exception as e:  # ComfyUI / ffmpeg / OpenCV errors: report cleanly. Published files are only ever replaced
            # inside publish_set, which restores them itself before an error leaves it.
            print(f"[FAIL] push_end stopped ({type(e).__name__}: {e}); {out / 'clip.mp4'} was not replaced (a new fixed take is"
                  f" saved in {out / 'push_fixed'} only if a '[push] new fixed take saved' line is printed above)", flush=True)
            return False
        finally:
            if _LAST_GEN.get("clip_private"):  # a private encode folder left by a failed step (normally removed by check_private)
                shutil.rmtree(Path(_LAST_GEN.pop("clip_private")).parent, ignore_errors=True)
    if locked:
        return go()
    lk, why = push_acquire(out)  # same exclusion as main(): no other push run and no normal run on this folder
    if lk is None:
        print(f"[FAIL] {why}; nothing was changed", flush=True)
        return False
    try:
        return go()
    finally:
        lk.close()


def _run_push(spec, conf, base, out, prompt_fixed, spec_bytes=None):
    """A private work folder in the system temp dir (not synced, not shared) holds the fixed take's working copy, its last frame
    and the end frame for the whole run; it is removed at the end whatever happens."""
    import tempfile
    wd = Path(tempfile.mkdtemp(prefix="h3pushwork_"))
    try:
        return _run_push_in(spec, conf, base, out, prompt_fixed, spec_bytes, wd)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def _run_push_in(spec, conf, base, out, prompt_fixed, spec_bytes, wd):
    import uuid
    job = uuid.uuid4().hex[:8]  # unique ComfyUI tags: two jobs started in the same second must not share staged files / PNG folders
    probs = recover_publishes(out)  # a publish killed half-way (power cut, task kill) is rolled back before anything else
    if probs:
        print("[FAIL] " + "; ".join(probs) + ("" if probs[0].endswith(BUSY_HINT) else
              f" - fix {out} by hand first (any rollback already done is listed above; nothing was deleted)"), flush=True)
        return False
    for pat in ("push_pass2_*", "push_fixed_new_*"):  # synced drives (Google Drive) keep emptied folders locked for a while;
        for old in out.glob(pat):                     # tidy EMPTY leftovers only
            try:
                old.rmdir()
            except OSError:
                pass
    sp1 = fixed_spec(spec, conf)
    # input snapshot: every file the two passes load (first frame, guide audio, voice / identity refs, ...) is copied ONCE into
    # the private work folder; both passes and the fingerprint use these copies, so an input changed during the run cannot give
    # pass 2 a different first frame than the one the end frame was derived from
    snap = {}  # {path string as in the spec: (path as resolved now, snapshot file)} - fixed here, never re-resolved later
    (wd / "inputs").mkdir()
    for i, f_ in enumerate(_inputs(spec, None)):
        if f_ in snap:
            continue
        q = (base / f_).resolve()
        dst_ = wd / "inputs" / f"{i:02d}_{q.name}"
        shutil.copyfile(q, dst_)
        snap[f_] = (str(q), str(dst_))
    spec_in = abs_spec(spec, base, to=snap)  # the spec as generated: inputs = the snapshot
    as_copied = {k: (w, w) for k, (w, _) in snap.items()}  # for the records: each path as it resolved when it was copied
    sp1_in = fixed_spec(spec_in, conf)
    # per-run staging folder (uuid): <out>/clip.mp4 (a previous good take) and its end frame / spec are only replaced after the
    # new take passed. The fixed take actually used is first COPIED into the private work folder (push_fixed_used.mp4); the
    # cache hash, the checks, its last frame and the end frame are all made from that private copy, so nothing done to
    # push_fixed/, the fixed_clip file or the (possibly synced) staging folder can change which take the end frame comes from.
    pdir = out / f"push_pass2_{job}"
    pdir.mkdir(parents=True)
    used = wd / "push_fixed_used.mp4"
    cached = False
    if conf.get("fixed_clip"):
        src = (base / conf["fixed_clip"]).resolve()
        shutil.copyfile(src, used)  # content only (a read-only fixed_clip must not make the working copy read-only)
        print(f"[push] reusing fixed take {src}", flush=True)
    else:
        fdir = out / "push_fixed"
        fixed = fdir / "clip.mp4"
        fp = push_fingerprint(spec, prompt_fixed, base, snap)
        fpf = fdir / "fingerprint.txt"
        # fingerprint.txt = line 1 the spec/inputs/model fingerprint, then "<sha256> <name>" for EVERY file of the published set
        # (clip, shot.json, prompt.txt, meta.json, ...). A cache hit needs every listed file unchanged - the clip is hashed on
        # the private copy - and shot.json / prompt.txt to be exactly this run's pass-1 record and prompt. Anything rewritten
        # since (by hand, or by a normal run with --out .../push_fixed, even a failed one) -> re-shoot. Old formats never hit.
        shot1 = json.dumps(abs_spec(sp1, base, as_copied), ensure_ascii=False, indent=1).encode("utf-8")  # absolute: re-runnable
        prompt1 = prompt_fixed.encode("utf-8")
        cached = cache_hit(fdir, fp, shot1, prompt1, used)
        if cached:
            print(f"[push] fixed take unchanged, reusing {fixed}", flush=True)
        elif owned_fixed_videos(fdir) is False:
            print(f"[FAIL] a video in {fdir} is not a push_end fixed take (no matching fingerprint, e.g. a normal run wrote it); it"
                  " is never replaced - move it elsewhere (or point fixed_clip at it). Nothing was changed", flush=True)
            try:
                pdir.rmdir()  # still empty: nothing was staged
            except OSError:
                pass
            return False
        else:
            used.unlink(missing_ok=True)
            # shoot the new fixed take in its own staging folder; push_fixed/ (whatever is there) is only replaced after
            # the new take passed check_fixed, all files at once
            ndir = out / f"push_fixed_new_{job}"
            ndir.mkdir(parents=True)
            _place(ndir / "prompt.txt", prompt1)
            # the pass-1 spec goes out with the take (else an older push_fixed/shot.json would sit beside the new clip)
            _place(ndir / "shot.json", shot1)
            if not generate(sp1_in, prompt_fixed, base, ndir, tag=f"{out.name}_pushfixed_{job}", private_io=True):
                print(f"[FAIL] fixed take failed (kept in {ndir}); {fdir} left as it was", flush=True)
                return False
            gexp, gbad = settle_generated(ndir)
            if gbad:
                print(f"[FAIL] {gbad} (kept in {ndir}; {fdir} left as it was)", flush=True)
                return False
            bad, fsha = check_private(ndir / "clip.mp4", sp1)
            if bad:
                print(f"[FAIL] new fixed take does not match the spec (kept in {ndir}; {fdir} left as it was): " + "; ".join(bad), flush=True)
                return False
            shutil.copyfile(ndir / "clip.mp4", used)  # the copy this run uses, taken before the set is published
            if _sha256(used) != fsha:
                print(f"[FAIL] the new fixed take changed after its checks (kept in {ndir}; {fdir} left as it was)", flush=True)
                return False
            # the set = what THIS run produced, never a folder listing: the checked clip, the two records written above and the
            # files generate() made (settle_generated). The fingerprint and the publish both use exactly this list.
            fexpect = {"clip.mp4": fsha, "shot.json": hashlib.sha256(shot1).hexdigest(), "prompt.txt": hashlib.sha256(prompt1).hexdigest()}
            fexpect.update(gexp)
            missing_ = sorted({n for n in FIXED_FILES if n not in OPTIONAL_FILES} - set(fexpect))
            if missing_:
                print(f"[FAIL] the new fixed take is missing {', '.join(missing_)} (kept in {ndir}; {fdir} left as it was)", flush=True)
                return False
            listed = [n for n in FIXED_FILES if n in fexpect]
            fbytes = ("\n".join([fp] + [f"{fexpect[n]} {n}" for n in listed]) + "\n").encode("utf-8")
            _place(ndir / "fingerprint.txt", fbytes)
            fexpect["fingerprint.txt"] = hashlib.sha256(fbytes).hexdigest()  # published only if it is exactly what was written
            # push_fixed/ is a folder of its own: hold its push lock (refused while a normal run writes there, and normal runs
            # there are refused meanwhile) until the set is published or rolled back
            le = link_errors(out)  # checked again right before writing into push_fixed/
            flk, why = (None, "; ".join(le)) if le else push_acquire(fdir)
            if flk is None:
                print(f"[FAIL] cannot save the new fixed take into {fdir}: {why}; it is in {ndir}", flush=True)
                return False
            try:
                owned = owned_fixed_videos(fdir)  # checked again under the lock
                if owned is False:
                    print(f"[FAIL] a video in {fdir} is not a push_end fixed take (written meanwhile?); it is never replaced. The new"
                          f" fixed take is in {ndir}", flush=True)
                    return False
                fdir.mkdir(parents=True, exist_ok=True)
                names = listed + ["fingerprint.txt"]  # exactly the fingerprinted set
                # every file a fixed take always has is required; the only optional one (frames.txt, H3_KEEP_PNG=1) is the only
                # one an older take may leave behind -> dropped. Nothing else is ever dropped, .old_ leftovers never touched
                stale = [n for n in OPTIONAL_FILES if n not in names and (fdir / n).is_file()]
                err = publish_set(ndir, fdir, names, job, drop=stale, old_expect=owned,  # each video: this very file, or still absent
                                  absent=[n for n in OPTIONAL_FILES if n not in names],
                                  required=tuple(n for n in FIXED_FILES if n not in OPTIONAL_FILES) + ("fingerprint.txt",),
                                  expect=fexpect)  # every listed file = what was checked / written / generated
            finally:
                flk.close()
            if isinstance(err, Unconfirmed):
                print(f"[FAIL] new fixed take moved into {fdir}, but {err}; run again to re-check it", flush=True)
                return False
            if err:
                print(f"[FAIL] could not save the new fixed take into {fdir} ({err}); it is in {ndir}", flush=True)
                return False
            try:
                ndir.rmdir()
            except OSError:
                pass
            print(f"[push] new fixed take saved as {fixed}", flush=True)
    bad, used_sha = check_stable(used, sp1)
    if bad:
        if cached:  # never keep re-reading a broken cached take: invalidate the fingerprint's first line so the next run re-shoots,
            # but keep the per-file lines - they are what shows this clip is push_end's own (owned_fixed_videos)
            tmp_ = fdir / f".fingerprint.txt.tmp_{job}"
            made = False
            try:
                lines_ = fpf.read_bytes().decode("utf-8").splitlines()
                with open(tmp_, "xb") as fh:  # exclusive create: an existing file at that name is never truncated / written through
                    made = True
                    fh.write(("\n".join(["invalid"] + lines_[1:]) + "\n").encode("utf-8"))
                os.replace(tmp_, fpf)
            except (OSError, UnicodeDecodeError) as e:
                if made:
                    try:
                        tmp_.unlink()
                    except OSError:
                        pass
                print(f"WARN could not invalidate {fpf} ({type(e).__name__}: {e}); the next run may try this cached take again", flush=True)
        print(f"[FAIL] fixed take does not match the spec: " + "; ".join(bad), flush=True)
        return False
    end_png = (wd / "push_end.png").resolve()  # private; pass 2 loads it from here
    last_png = wd / "push_fixed_last.png"
    last_frame_png(used, last_png)
    if _sha256(used) != used_sha:
        print("[FAIL] the fixed take changed while its last frame was read; nothing was changed", flush=True)
        return False
    used.unlink(missing_ok=True)  # intermediate only; the end frame and push_fixed_last.png are kept with the take
    info = crop_zoom(last_png, end_png, conf["zoom"])
    print(f"[push] end frame {end_png.name}: zoom {conf['zoom']} {info}" + ("" if info["face"] else "  (no face found: centre crop)"), flush=True)
    # every file of the set is published only if it is byte-identical to what this run made (a sync client may touch staging):
    # records = the bytes written here, end frames = the private ones made above, generated files = right after generate(),
    # clip = the hash it had when it passed its checks
    expect = {"push_end.png": _sha256(end_png), "push_fixed_last.png": _sha256(last_png)}
    for name, src in (("push_end.png", end_png), ("push_fixed_last.png", last_png)):  # the copies published with the take
        _place(pdir / name, src=src)
        if _sha256(pdir / name) != expect[name]:
            print(f"[FAIL] {pdir / name} is not the end frame that was made; nothing was changed", flush=True)
            return False
    sp2 = push_spec(spec_in, conf, end_png, base)  # pass 2 loads the same input snapshot as pass 1
    prompt2 = build_prompt(sp2)
    rec = push_spec(spec, conf, (out / "push_end.png").resolve(), base, as_copied)  # points at the published end frame
    if spec_bytes is None:  # direct run_push() call: record the spec actually used, never leave an older shot.json beside the new clip
        spec_bytes = json.dumps(spec, ensure_ascii=False, indent=1).encode("utf-8")
    # shot.json = the exact spec read at start (not re-read from disk)
    for name, data in (("prompt.txt", prompt2.encode("utf-8")), ("prompt_fixed.txt", prompt_fixed.encode("utf-8")), ("shot.json", spec_bytes),
                       ("push_spec.json", json.dumps(rec, ensure_ascii=False, indent=1).encode("utf-8"))):
        _place(pdir / name, data)
        expect[name] = hashlib.sha256(data).hexdigest()
    if not generate(sp2, prompt2, base, pdir, tag=f"{out.name}_push_{job}", private_io=True):
        print(f"[FAIL] push pass 2 failed; {out / 'clip.mp4'} left as it was", flush=True)
        return False
    gexp, gbad = settle_generated(pdir)
    if gbad:
        print(f"[FAIL] {gbad} (kept in {pdir}, {out / 'clip.mp4'} left as it was)", flush=True)
        return False
    expect.update(gexp)
    bad, clip2 = check_private(pdir / "clip.mp4", sp1)  # clip2 = the take that passed (checked in the private folder)
    if bad:
        print(f"[FAIL] pushed take does not match the spec (kept in {pdir}, {out / 'clip.mp4'} left as it was): " + "; ".join(bad), flush=True)
        return False
    expect["clip.mp4"] = clip2
    names = [n for n in TAKE_FILES if n in expect]  # what this run produced (never a folder listing); each one is expected
    # per-take files of a previous take in <out> that this set does not replace (e.g. frames.txt of a normal H3_KEEP_PNG=1 run)
    # are removed with the publish (restored on rollback); any other file in <out> is never touched
    stale = [n for n in OPTIONAL_FILES if n not in names and (out / n).is_file()]  # only optional files are ever dropped
    err = publish_set(pdir, out, names, job, drop=stale, expect=expect, absent=[n for n in OPTIONAL_FILES if n not in names],
                      required=tuple(n for n in TAKE_FILES if n not in OPTIONAL_FILES))  # everything a push take always has
    if isinstance(err, Unconfirmed):
        print(f"[FAIL] the new take was moved into {out}, but {err}", flush=True)
        return False
    if err:
        ok_rb = "ROLLBACK INCOMPLETE" not in err
        print(f"[FAIL] could not publish the new take ({err}); "
              + (f"every old file in {out} was restored, the new take is in {pdir}" if ok_rb else f"{out} is in a mixed state, see above"), flush=True)
        return False
    try:
        pdir.rmdir()
    except OSError:
        pass
    print(f"[push] {out / 'clip.mp4'} replaced after passing size/fps/frames/audio-sync checks", flush=True)
    return True


TAKE_FILES = ("clip.mp4", "shot.json", "prompt_fixed.txt", "push_end.png", "push_fixed_last.png", "push_spec.json", "prompt.txt",
              "workflow_api.json", "clip_savevideo.mp4", "meta.json", "frames.txt")  # the files of one published push take
#                                                                     (frames.txt only exists with H3_KEEP_PNG=1)


JOURNAL = ".publish_journal.json"  # in the staging folder while a publish_set is in progress (see publish_set / recover_publishes)


def _move_new(a, b):
    """Move a -> b, never replacing an existing b (raises FileExistsError then): os.rename on Windows does not overwrite;
    elsewhere a hard link + unlink (link fails if b exists). Where hard links are not supported the move fails (OSError), so a
    publish there is rolled back rather than risking an overwrite."""
    if os.name == "nt":
        os.rename(a, b)
        return
    os.link(a, b)
    os.unlink(a)


def _is_reg(path):
    """True if a regular file (never a link / folder) is at `path`, False only if nothing is there or it is something else.
    Any other error (access denied, locked by a sync client) is raised - Path.is_file would read it as "no file"."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


def _publish_marker(dst, job):
    """The local record of a publish (outside the synced folder, so a sync client cannot remove or bring it back):
    H3_PUBLISH_MARKERS, else %LOCALAPPDATA%/h3_shot/publishing (else ~/.h3_shot/publishing); one file per target + job."""
    base = os.environ.get("H3_PUBLISH_MARKERS") or (
        os.path.join(os.environ["LOCALAPPDATA"], "h3_shot", "publishing") if os.environ.get("LOCALAPPDATA")
        else os.path.join(os.path.expanduser("~"), ".h3_shot", "publishing"))
    key = hashlib.sha256(str(Path(dst).resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return Path(base) / f"{key}_{job}.json"


def _drop_marker(dst, job):
    try:
        _publish_marker(dst, job).unlink(missing_ok=True)
    except OSError:
        pass  # a leftover record is checked (and removed) by the next recovery of that folder


def _present(path):
    """True if something (file, folder, link - never followed) is at `path`, False only if nothing is there. Any other
    error (access denied, locked by a sync client) is raised: os.path.lexists / Path.exists would read it as "absent"."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _ident_or_old(path, old):
    """_ident(path); but when the file cannot be read (PermissionError: locked exclusively by a player or the sync client) and
    it is still the very old file recorded before the publish (`old` = "sha:id"; same file id by os.lstat, which needs no read
    access), that recorded identity. Such a file was never moved by the publish, so a rollback has nothing to do with it and
    must not stop at it (it used to: every other old file then stayed as <name>.old_<job>). Any other error is raised."""
    try:
        return _ident(path)
    except PermissionError:
        if not old:
            raise
        st = os.lstat(path)
        rec = old.rsplit(":", 1)[-1]
        if st.st_ino and rec not in ("", "0") and stat.S_ISREG(st.st_mode) and str(st.st_ino) == rec:
            return old  # (a file system without file ids - st_ino 0, e.g. exFAT, some network drives - never gets here)
        raise


def _where(src, dst, names, drop, job):
    """For a ROLLBACK INCOMPLETE message: where each file of the publish is now (its name in the target folder, its backup
    <name>.old_<job>, its staging copy), so the set can be put together by hand. Never raises."""
    rows = []
    for n in dict.fromkeys(list(names) + list(drop)):
        at = []
        for q in (dst / n, dst / f"{n}.old_{job}", src / n):
            try:
                if _present(q):
                    at.append(str(q))
            except OSError as e:
                at.append(f"{q} (cannot be checked: {e.strerror or e})")
        rows.append(f"{n}: " + (", ".join(at) if at else "in none of its places"))
    return " | files now: " + "; ".join(rows)


def _rollback(src, dst, names, drop, job, sha, old_sha):
    """Undo a (possibly half-done) publish of `names` from src into dst, judged from the files on disk alone (sha / old_sha
    hold identities "sha256:file-id", see _ident - a file with the same bytes but another id is NOT ours): a new file that is
    in dst but no longer in src goes back to src, every <name>.old_<job> gets its name back. Never overwrites anything: if a
    different file now sits at a name (written meanwhile, e.g. by a normal run after a crash), both are kept and reported.
    Returns what could not be undone."""
    stuck = []
    try:
        _rollback_steps(src, dst, names, drop, job, sha, old_sha, stuck)
    except OSError as e:  # a name that cannot be checked (access error): stop here, nothing more is moved
        stuck.append(f"could not check {getattr(e, 'filename', None) or dst} ({e.strerror or e}) - rollback stopped there")
    return stuck


def _rollback_steps(src, dst, names, drop, job, sha, old_sha, stuck):
    for n in drop:  # dropped files were only moved aside: put them back
        old = dst / f"{n}.old_{job}"
        if _present(old):
            if _present(dst / n) or _ident(old) != old_sha.get(n):
                stuck.append(f"{dst / n} / {n}.old_{job}: not the state this publish left - both kept; choose by hand")
                continue
            try:
                _move_new(old, dst / n)
            except OSError:
                stuck.append(f"old {n} left as {n}.old_{job}")
    for n in reversed(names):
        here = dst / n
        if _is_reg(here) and _ident_or_old(here, old_sha.get(n)) == sha.get(n):  # this very new file is in place (identity,
            #                                                    not staging's state); a locked untouched old file is skipped
            try:
                _move_new(here, src / n)  # fails if staging has another file at that name: never overwritten
            except OSError:
                stuck.append(f"new {n} still in {dst}")
                if _present(dst / f"{n}.old_{job}"):
                    stuck.append(f"old {n} left as {n}.old_{job}")
                continue  # never overwrite a new file we could not move back
            try:
                back_ok = _ident(src / n) == sha.get(n)
            except OSError:
                back_ok = False
            if not back_ok:  # swapped between the identity check and the move: what went to staging is not ours
                stuck.append(f"{src / n} is not the new {n} this publish moved in (swapped in {dst} meanwhile?) - kept in {src};"
                             " choose by hand")
                continue
        old = dst / f"{n}.old_{job}"
        if _present(old):
            if _present(dst / n) or _ident(old) != old_sha.get(n):  # someone wrote one of them after the publish was cut short
                stuck.append(f"{dst / n} / {n}.old_{job}: not the state this publish left - both kept; choose by hand")
                continue
            try:
                _move_new(old, dst / n)
            except OSError:
                stuck.append(f"old {n} left as {n}.old_{job}")


def _restored(dst, old_sha, names=()):
    """After a rollback: every old file this publish recorded must be back at its name as that very file ("sha:id"), and
    every other name in `names` (new names that had no old file, and the journal's absent names) must be free again. Returns what is not (a backup that vanished between the conflict
    check and the rollback, a foreign file put at a free name meanwhile, a file locked meanwhile)."""
    bad = []
    for n in names:
        if n in old_sha:
            continue
        try:
            if _present(dst / n):
                bad.append(f"{dst / n} is there although this publish had no old {n} (written meanwhile?) - kept as it is")
        except OSError as e:
            bad.append(f"{dst / n} could not be checked ({e.strerror or e})")
    for n, want in old_sha.items():
        try:
            if not (_is_reg(dst / n) and _ident_or_old(dst / n, want) == want):
                bad.append(f"old {n} is not back in {dst}")
        except OSError as e:
            bad.append(f"old {n} in {dst} could not be checked ({e.strerror or e})")
    return bad


def _new_back(src, names, sha):
    """After a rollback: every new file of this publish must be back in staging as that very file ("sha:id"). Returns what is
    not (a foreign file at the staging name, a new file that is in neither place, a file that cannot be checked)."""
    bad = []
    for n in names:
        try:
            if not _present(src / n):
                bad.append(f"the new {n} of this publish is neither in its target folder nor in {src} (gone?)")
            elif not (_is_reg(src / n) and _ident(src / n) == sha.get(n)):
                bad.append(f"{src / n} is not the new {n} this publish moved in - kept as it is; choose by hand")
        except OSError as e:
            bad.append(f"{src / n} could not be checked ({e.strerror or e})")
    return bad


def _complete(dst, names, drop, job, sha, old_sha, absent=()):
    """True if a journaled publish is wholly in place: every new file in dst as the very file moved in, every old file as its
    backup <name>.old_<job>, every dropped / absent name free. Such a publish only lacked (or already passed) its commit
    point - it is taken as done, never undone. Any access error -> None (cannot tell: the caller stops, nothing is moved)."""
    order = sorted(names, key=lambda x: (x.lower().endswith(".mp4"), x == "clip.mp4"))  # videos last, the main clip the very last
    free = [n for n in list(drop) + list(absent) if n not in names]
    try:
        return (not any(_present(dst / n) for n in free)
                and all(_is_reg(dst / f"{n}.old_{job}") and _ident(dst / f"{n}.old_{job}") == v for n, v in old_sha.items())
                and all(_is_reg(dst / n) and _ident(dst / n) == sha.get(n) for n in order)
                and not any(_present(dst / n) for n in free))  # again after the main clip (a name restored meanwhile)
    except OSError:
        return None


def _conflicts(src, dst, names, drop, job, sha, old_sha, absent=()):
    """What a rollback of this journal could not do without overwriting or moving a file that is not this publish's own.
    A name that cannot be checked (access error) is itself a conflict: then nothing is moved."""
    try:
        return _conflicts_found(src, dst, names, drop, job, sha, old_sha, absent)
    except OSError as e:
        return [f"could not check {getattr(e, 'filename', None) or dst} ({e.strerror or e})"]


def _conflicts_found(src, dst, names, drop, job, sha, old_sha, absent=()):
    bad = [f"{q} is not a regular file" for q in [dst / x for x in list(names) + drop] + [dst / f"{x}.old_{job}" for x in list(names) + drop]
           + [src / x for x in names] if _present(q) and not (_is_reg(q) and not q.is_symlink())]
    if bad:
        return bad
    for n in names:
        here, theirs, stg = dst / n, dst / f"{n}.old_{job}", src / n
        here_id = _ident_or_old(here, old_sha.get(n)) if _is_reg(here) else None  # a locked untouched old file: its recorded id
        if here_id is None or here_id != sha.get(n):  # the new file is not in its target: it must still be in staging, as itself
            if not _present(stg):
                bad.append(f"the new {n} of this publish is neither in {dst} nor in {src} (gone?)")
            elif not (_is_reg(stg) and _ident(stg) == sha.get(n)):
                bad.append(f"{stg} is not the new {n} this publish moved in (changed in staging meanwhile?)")
        if here_id is not None and here_id == sha.get(n):  # the new file is in place ...
            if _present(stg):                        # ... and staging holds another file at its name: cannot move back
                bad.append(f"{stg} exists while the new {n} is already in {dst} (recreated?)")
        elif _present(here):  # something else at the name: only the untouched old file is fine
            if not (n in old_sha and here_id == old_sha[n] and not _present(theirs)):
                bad.append(f"{here} is neither the file this publish moved in nor its old version (written afterwards?)")
    for n in drop:
        if _present(dst / f"{n}.old_{job}") and _present(dst / n):
            bad.append(f"{dst / n} was written after the interrupted publish while its old version is {n}.old_{job}")
    for n in absent:  # names that were free when the publish started and are not part of it
        if n not in names and n not in drop and _present(dst / n):
            bad.append(f"{dst / n} appeared during the interrupted publish (not part of it)")
    for n in list(names) + list(drop):  # a backup can only exist for an old file this publish recorded
        if n not in old_sha and _present(dst / f"{n}.old_{job}"):
            bad.append(f"{dst / f'{n}.old_{job}'} exists but this publish had no old {n} to move aside (put there afterwards?)")
    for n, want in old_sha.items():  # every old file must still be intact: as its backup, or not yet moved aside
        bak, here = dst / f"{n}.old_{job}", dst / n
        if _present(bak):
            if _ident(bak) != want:
                bad.append(f"backup {bak} is not the old file this publish moved aside (changed afterwards?)")
        elif not (_present(here) and _ident_or_old(here, want) == want):
            if not (n in names and _is_reg(here) and _ident(here) == sha.get(n)):
                bad.append(f"the old {n} of {dst} is neither in place nor kept as {bak.name}")
            else:
                bad.append(f"the old {n} of {dst} was moved aside but its backup {bak.name} is gone")
    return bad


class Unconfirmed(str):
    """publish_set result: committed (the new set was moved in), but afterwards a delivered file was missing / changed /
    could not be checked. Truthy like an error string, so callers fail; they tell it apart from "not committed"."""


def publish_set(src, dst, names, job, drop=(), required=(), expect=None, old_expect=None, absent=()):
    """All-or-nothing: move old dst files aside (<name>.old_<job>), move the new ones in, then drop the old ones; files named
    in `drop` (in dst, not part of the new set) are moved aside too and removed with them, or restored on rollback. Any failure
    (a file locked by a player or the sync client) or interruption (Ctrl+C) rolls back and returns / re-raises.
    The rollback looks at the files on disk, not at in-memory progress, so an interruption between a rename and its
    bookkeeping cannot be missed. A journal (src/.publish_journal.json) is written before anything moves and deleted as the
    commit point, so a publish cut short by a hard kill is rolled back by the next push run (recover_publishes).
    None on success, else the error text."""
    drop = [n for n in drop if n not in names]
    try:
        odd = [str(q) for q in [dst / n for n in list(names) + drop] + [src / n for n in names]
               if _present(q) and not (_is_reg(q) and not q.is_symlink())]
    except OSError as e:
        return f"could not check {getattr(e, 'filename', None) or dst} ({e.strerror or e}); nothing was moved"
    if odd:  # a folder / link named like a take file: never rename or replace it
        return f"{', '.join(odd)} is not a regular file; nothing was moved"
    try:
        missing = [n for n in required if n not in names or not _is_reg(src / n)]
    except OSError as e:
        return f"could not check {getattr(e, 'filename', None) or src} ({e.strerror or e}); nothing was moved"
    if missing:  # e.g. the verified clip vanished from staging: never publish (or drop the old one) without it
        return f"required file(s) {', '.join(missing)} missing in {src}; nothing was moved"
    try:
        new_id = {n: _sha_ino(src / n) for n in names}
        sha = {n: v[0] for n, v in new_id.items()}  # content of the new files (expect / pre-commit checks)
        new_ident = {n: f"{v[0]}:{v[1]}" for n, v in new_id.items()}  # rollback moves back only these very files
        wrong = [n for n, v in (expect or {}).items() if sha.get(n) != v]  # (missing from names counts as wrong)
        if wrong:
            return f"{', '.join(wrong)} in {src} is not the file that passed the checks; nothing was moved"
        old_id = {n: _sha_ino(dst / n) for n in list(names) + drop if _is_reg(dst / n)}  # sha + file id, one handle each
        old_sha = {n: v[0] for n, v in old_id.items()}
        old_ident = {n: f"{v[0]}:{v[1]}" for n, v in old_id.items()}  # rollback restores / the cleanup deletes only these files
        # a drop file already gone when the old files were hashed is not dropped by this publish: its name must simply stay free
        absent = list(dict.fromkeys(list(absent) + [n for n in drop if n not in old_sha]))
        drop = [n for n in drop if n in old_sha]
        wrong_old = [n for n, v in (old_expect or {}).items() if old_ident.get(n) != v]  # identities ("sha:id"), None = absent
        if wrong_old:  # an old file to be replaced is no longer the one that was verified (changed / swapped meanwhile)
            return f"{', '.join(wrong_old)} in {dst} is not the file that was checked before the publish; nothing was moved"
        jbytes = (json.dumps({"dst": str(Path(dst).resolve()), "names": list(names), "drop": drop, "job": job,
                                               "sha": new_ident, "old_sha": old_ident, "absent": list(absent)},
                                              ensure_ascii=False)).encode("utf-8")
        marker = _publish_marker(dst, job)
        marker.parent.mkdir(parents=True, exist_ok=True)
        with open(marker, "xb") as mfh:  # the local record (a journal that vanishes from the synced folder is still known)
            mfh.write(json.dumps({**json.loads(jbytes.decode("utf-8")), "staging": str(Path(src).resolve())},
                                 ensure_ascii=False).encode("utf-8"))
        try:
            with open(src / JOURNAL, "xb") as jfh:  # created exclusively: a file already at that name stops the publish
                jfh.write(jbytes)
                jident = ("sha", hashlib.sha256(jbytes).hexdigest(), os.fstat(jfh.fileno()).st_ino)  # removed only while still this file
        except OSError:
            _drop_marker(dst, job)
            raise
    except OSError as e:
        return f"could not write the publish journal ({e}); nothing was moved"
    try:
        for n in list(names) + drop:
            if n in old_sha:  # only the old files hashed above; one that appeared since is never moved (the move-in then stops)
                _move_new(dst / n, dst / f"{n}.old_{job}")
        for n in names:
            _move_new(src / n, dst / n)
        # before the commit point, check the WHOLE set: every new file in place is the one moved in, every backup still is the
        # old file it was (a sync client may have rewritten / removed one). If not, keep all backups and the journal (the next
        # run reports the conflict) and say exactly what is wrong
        def state(path, want):
            return "missing" if not _is_reg(path) else ("changed" if _sha256(path) != want else None)
        bad = {}
        for n in names:  # each new file must still be the very file moved in (content and file id)
            st_ = "missing" if not _is_reg(dst / n) else (None if _ident(dst / n) == new_ident[n] else "changed")
            if st_:
                bad.setdefault(st_, []).append(f"new {n}")
        for n in old_sha:  # each backup must still be the very file that was moved aside (same file id and content)
            bak = dst / f"{n}.old_{job}"
            st_ = "missing" if not _is_reg(bak) else (None if _note_id(bak) == ("sha", *old_id[n]) else "changed")
            if st_:
                bad.setdefault(st_, []).append(f"backup {n}.old_{job}")
        for n in list(drop) + [x for x in absent if x not in names and x not in drop]:
            # a dropped file must stay gone, and a name that is not part of the new set must still be free: a file written at
            # such a name meanwhile (e.g. an old frames.txt restored) does not belong to this set
            try:
                if _present(dst / n):
                    bad.setdefault("present but not part of this set", []).append(n)
            except OSError as e:
                bad.setdefault("could not be checked", []).append(f"{n} ({e.strerror or e})")
        bak_ids = {n: ("sha", *old_id[n]) for n in old_sha}  # the identities recorded before anything moved (not re-read)
        if bad:
            return (f"publish into {dst} not committed: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(bad.items()))
                    + " - every remaining backup and the publish journal are kept - ROLLBACK INCOMPLETE, check by hand"
                    + _where(src, dst, names, drop, job))
        _drop_marker(dst, job)  # before the journal: a crash in between leaves the journal (handled as a complete publish)
        if not _remove_if_same(src / JOURNAL, jident):  # commit point: from here on the new set stands
            return (f"publish into {dst} not committed: the publish journal {src / JOURNAL} was replaced or removed meanwhile - every"
                    " backup is kept - ROLLBACK INCOMPLETE, check by hand" + _where(src, dst, names, drop, job))
    except BaseException as e:  # also Ctrl+C / SystemExit mid-publish: roll back first, then re-raise non-OS errors
        # same rule as the recovery: check the whole batch first; on any conflict move nothing (journal kept for the next run)
        stuck = [f"{c} - kept as it is; choose by hand" for c in _conflicts(src, dst, names, drop, job, new_ident, old_ident, absent)]
        if _note_id(src / JOURNAL) != jident:
            stuck.append(f"{src / JOURNAL} is not the journal this publish wrote - kept as it is; choose by hand")
        if not stuck:
            stuck = _rollback(src, dst, names, drop, job, new_ident, old_ident)
        if not stuck:
            stuck = _restored(dst, old_ident, list(names) + list(absent))  # journal goes only once the old state is back
        if not stuck:
            stuck = _new_back(src, names, new_ident)  # ... and every new file is back in staging as the very file moved in
        jnote = ""
        if not stuck:
            _drop_marker(dst, job)
        if not stuck and not _remove_if_same(src / JOURNAL, jident):  # only our own journal
            jnote = f" | the publish journal {src / JOURNAL} could not be removed; the next push run checks it again"
        msg = str(e) + (" | ROLLBACK INCOMPLETE: " + "; ".join(stuck) + " - fix by hand before using this folder"
                        + _where(src, dst, names, drop, job) if stuck else jnote)
        if not isinstance(e, OSError):
            print(f"[FAIL] publish interrupted ({type(e).__name__}); " + ("old files restored" + jnote if not stuck else msg), flush=True)
            raise
        return msg
    free_ = [x for x in list(drop) + list(absent) if x not in names]
    order_ = sorted(names, key=lambda x: (x.lower().endswith(".mp4"), x == "clip.mp4"))  # videos last, the main clip the very last
    def unconfirmed():  # the delivered names that are not (or cannot be confirmed to be) the files this publish moved in
        bad_ = []
        def check_free():  # a name that is not part of the new set must still be free (e.g. no old frames.txt put back)
            for x in free_:
                try:
                    os.lstat(dst / x)  # not lexists(): that turns an access error into "free"
                except FileNotFoundError:
                    continue
                except OSError as e:
                    msg_ = f"{x} could not be checked ({e.strerror or e})"
                else:
                    msg_ = f"{x} is present but not part of this set (kept as it is)"
                if msg_ not in bad_:
                    bad_.append(msg_)
        check_free()
        for n in order_:
            try:
                if not (_is_reg(dst / n) and _ident(dst / n) == new_ident[n]):
                    bad_.append(f"{n} changed or disappeared")
            except OSError as e:  # e.g. locked by a sync client: not necessarily gone, but not confirmed either
                bad_.append(f"{n} could not be confirmed ({e.strerror or e})")
        check_free()  # again after the delivered files (a name restored while the main clip was being hashed)
        return bad_
    def report(bad_):
        return Unconfirmed(f"published into {dst} (committed), but the delivered files are not confirmed: {'; '.join(bad_)} - every"
                           f" backup (<name>.old_{job}) that is still there is kept; check {dst} by hand")
    bad_ = unconfirmed()
    if bad_:  # the old files are the only known-good copies - keep every backup
        return report(bad_)
    # every old file stays as its backup <name>.old_<job>: a new file could still vanish after any check, and then the old
    # set is the only known-good copy - the user deletes the backups once the new take is checked
    kept = [f"{n}.old_{job}" for n in old_sha]
    if kept:
        print(f"NOTE the previous file(s) in {dst} are kept as {', '.join(kept)}; delete them by hand once the new take is"
              " checked", flush=True)
    return None


BUSY_HINT = " - try again when that run has finished"


def recover_publishes(out):
    """Holds <out>/push_fixed's folder lock (if that folder exists) for the whole recovery, so no push or normal run can work
    there meanwhile (a push run may even use push_fixed/ as its own --out), then runs _recover. Problems, as _recover."""
    fd = out / "push_fixed"
    le = link_errors(out)
    if le:
        return le
    lk = None
    if fd.is_dir():
        lk, why = push_acquire(fd)
        if lk is None:
            return [f"{fd} is busy ({why}); nothing was checked or changed{BUSY_HINT}"]
    try:
        return _recover(out)
    finally:
        if lk is not None:
            lk.close()


def _orphan_markers(dsts, jobs):
    """Local publish records (see _publish_marker) for these target folders whose journal is no longer in the staging folder
    (removed or lost by the sync client). A record is removed when its target is verifiably in the published state (the
    commit point was passed) or in the old state with the new files back in staging (rolled back); otherwise it is a problem
    and nothing is moved."""
    probs = []
    d0 = _publish_marker(Path("."), "00000000").parent
    try:
        with os.scandir(d0) as it:
            recs = sorted(d0 / e.name for e in it if e.name.endswith(".json"))
    except FileNotFoundError:
        return []
    except OSError as e:
        return [f"could not list the local publish records in {d0} ({e.strerror or e})"]
    for m in recs:
        try:
            M = json.loads(m.read_bytes().decode("utf-8"))
            dst, job, st = Path(M["dst"]).resolve(), str(M["job"]), Path(M["staging"])
            names, drop, sha, old_sha = list(M["names"]), list(M["drop"]), dict(M["sha"]), dict(M["old_sha"])
            absent = list(M.get("absent", []))
        except (OSError, ValueError, KeyError, TypeError):
            continue  # not readable: it cannot be tied to a folder (left alone)
        if dst not in dsts or (job, dst) in jobs:  # another folder, or its journal is still there (handled with the journal)
            continue
        try:
            jthere = _present(st / JOURNAL)
        except OSError as e:
            probs.append(f"could not check {st / JOURNAL} ({e.strerror or e}) for the local publish record {m}")
            continue
        if jthere:  # a journal is there but was not taken up (another check reports it)
            continue
        done = _complete(dst, names, drop, job, sha, old_sha, absent)
        back = None
        if done is False:
            try:
                back = not _restored(dst, old_sha, list(names) + list(absent)) and not _new_back(st, names, sha)
            except OSError:
                back = None
        if done or back:
            try:
                m.unlink()
            except OSError:
                pass
            continue
        probs.append(f"a publish into {dst} (job {job}) was started on this computer but its journal {st / JOURNAL} is gone and"
                     f" {dst} is neither in the published nor in the old state - nothing moved; check by hand"
                     f" (the publish record is {m}: delete it once the folder is sorted out)")
    return probs


def _recover(out):
    """Run at the start of every push run (folder lock held). Two steps, and nothing is touched until step 1 found no problem:
    1. check: every journal (in push_pass2_<job>/ or push_fixed_new_<job>/) must parse, look like this tool's (job = 8 lowercase
       hex = the staging folder's suffix, target <out> or <out>/push_fixed, tool file names only), and every tool backup
       <name>.old_<job> in a target folder must be listed in its own journal's names/drop.
    2. roll back every journaled publish (killed before its commit point): old set restored, new files back to staging.
    Backups without a journal of their own (an earlier publish killed after its commit point) are never deleted automatically,
    only reported (WARN). Returns problems (empty = folder consistent); with problems nothing at all is moved."""
    problems, jobs, leftovers = [], {}, []
    # each staging kind publishes into exactly one folder: push_pass2_<job> -> <out>, push_fixed_new_<job> -> <out>/push_fixed
    kinds = {"push_pass2_": (out.resolve(), TAKE_FILES), "push_fixed_new_": ((out / "push_fixed").resolve(), FIXED_FILES + ("fingerprint.txt",))}
    staging = {}  # (job, target folder) -> staging folder
    try:  # one listing, errors raised (Path.glob skips a folder it cannot read: an interrupted publish could be missed)
        with os.scandir(out) as it:
            entries = sorted(e.name for e in it)
    except FileNotFoundError:
        return []  # no output folder yet: nothing was ever published there
    except OSError as e:
        return [f"could not list {out} ({e.strerror or e}); nothing was checked or changed"]
    for prefix, (dst, known) in kinds.items():
        for st in [out / x for x in entries if x.casefold().startswith(prefix)]:  # Windows names: case does not matter
            try:
                if stat.S_ISDIR(os.lstat(st).st_mode):
                    staging[(st.name[len(prefix):], dst)] = st
                elif re.fullmatch(r"[0-9a-f]{8}", st.name[len(prefix):]):  # a staging name that is a file / link: never skipped
                    problems.append(f"{st} is not a folder (a staging folder of an interrupted publish?) - kept as it is; choose by hand")
            except FileNotFoundError:
                continue
            except OSError as e:
                problems.append(f"could not check {st} ({e.strerror or e})")
    for (job8, dst0), st in staging.items():
        j = st / JOURNAL
        try:
            jmode = os.lstat(j).st_mode
        except FileNotFoundError:
            continue  # no journal: nothing was in progress there
        except OSError as e:
            problems.append(f"could not check {j} ({e.strerror or e})")
            continue
        if not stat.S_ISREG(jmode):  # a folder / link at the journal's name: never taken as "no publish in progress"
            problems.append(f"{j} is not a regular file - kept as it is; choose by hand")
            continue
        try:
            with open(j, "rb") as jfh:  # one handle: the id, the bytes that are parsed and their hash all describe one file
                jino = os.fstat(jfh.fileno()).st_ino
                jdata = jfh.read()
            jsha = hashlib.sha256(jdata).hexdigest()
            J = json.loads(jdata.decode("utf-8"))
            dst, names, drop, job = Path(J["dst"]).resolve(), list(J["names"]), list(J["drop"]), str(J["job"])
            sha, old_sha = dict(J["sha"]), dict(J["old_sha"])
            # journals written before "absent" existed: every optional take file that is neither new nor an old one moved aside
            absent = list(J["absent"]) if "absent" in J else [n for n in OPTIONAL_FILES if n not in names and n not in old_sha]
            absent += [n for n in drop if n not in old_sha and n not in absent]  # a drop name with no old file = must stay free
            drop = [n for n in drop if n in old_sha]
        except (OSError, ValueError, KeyError, TypeError) as e:
            problems.append(f"unreadable publish journal {j} ({type(e).__name__})")
            continue
        known = dict(kinds.values()).get(dst)
        if (dst != dst0 or job != job8 or not re.fullmatch(r"[0-9a-f]{8}", job)
                or not all(isinstance(n, str) and _tool_file(n, known) for n in names + drop + absent)
                or set(sha) != set(names) or not set(old_sha) <= set(names + drop)
                or not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}:[0-9]+", v) for v in list(sha.values()) + list(old_sha.values()))):
            problems.append(f"publish journal {j} does not look like one this tool wrote (folder / job / file names)")
            continue
        jobs[(job, dst)] = (st, names, drop, sha, old_sha, absent, ("sha", jsha, jino))
    problems += _orphan_markers({d for d, _k in kinds.values()}, jobs)
    for dst, known in kinds.values():
        try:
            if not _present(dst):
                continue
            with os.scandir(dst) as it:
                here_ = sorted(dst / e.name for e in it)
        except OSError as e:
            problems.append(f"could not list {dst} ({e.strerror or e})")
            continue
        for q in here_:
            if not (q.name not in known and _tool_file(q.name, known)):
                continue
            try:
                if not _is_reg(q):
                    continue
            except OSError as e:
                problems.append(f"could not check {q} ({e.strerror or e})")
                continue
            base_name, job = q.name[:-len(".old_00000000")], q.name[-8:]
            if (job, dst) in jobs:
                st, names, drop, _sha, _old, _abs, _jid = jobs[(job, dst)]
                if base_name not in names + drop:
                    problems.append(f"backup {q} is not covered by its publish journal {st / JOURNAL}")
            else:
                try:  # the take's clip: a backup of it with no clip at its name may be the only copy of the old take
                    base_there = base_name != "clip.mp4" or _is_reg(dst / base_name)  # (others, e.g. a dropped frames.txt,
                except OSError as e:                                                 #  have no file at their name by design)
                    problems.append(f"could not check {dst / base_name} ({e.strerror or e}) next to the backup {q}")
                    continue
                if not base_there:  # no journal and no clip at its name: it may be the only copy of the old clip
                    problems.append(f"{q} has no publish journal and there is no {base_name} in {dst}: it may be the only copy of"
                                    f" the old {base_name} - kept as it is; check by hand (rename it back, or delete it if not needed)")
                    continue
                leftovers.append(q)  # no journal of its own: from an earlier publish; never deleted automatically
    for (job, dst), (st, names, drop, sha, old_sha, absent, jid) in jobs.items():  # a rollback must not overwrite / move anyone else's file
        problems += [f"{c} - kept as it is; choose by hand" for c in _conflicts(st, dst, names, drop, job, sha, old_sha, absent)]
        if _note_id(st / JOURNAL) != jid:
            problems.append(f"{st / JOURNAL} changed after it was read - kept as it is; choose by hand")
    if problems:
        return problems
    for (job, dst), (st, names, drop, sha, old_sha, _absent, jid) in jobs.items():  # push_fixed/ is locked by recover_publishes
        done = _complete(dst, names, drop, job, sha, old_sha, _absent)
        if done is None:  # e.g. a file locked by the sync client: neither "complete" nor "roll back" can be decided
            problems.append(f"could not check whether the publish into {dst} is complete ({st / JOURNAL} kept, nothing moved)"
                            " - run again once the folder is not busy")
            continue
        if done:  # e.g. a journal brought back after the commit point
            _drop_marker(dst, job)
            if not _remove_if_same(st / JOURNAL, jid):
                problems.append(f"{st / JOURNAL} changed after it was read; kept - the publish into {dst} is complete, check by hand")
                continue
            print(f"[push] a publish into {dst} was found complete (every new file in place); taken as done"
                  + (f" - the old files are kept as <name>.old_{job}, delete them by hand once checked" if old_sha else ""), flush=True)
            continue
        stuck = _rollback(st, dst, names, drop, job, sha, old_sha)
        if not stuck:
            stuck = _restored(dst, old_sha, list(names) + list(_absent))  # journal goes only once the old state is back
        if not stuck:
            stuck = _new_back(st, names, sha)  # ... and every new file is back in staging as the very file moved in
        if stuck:
            problems.append(f"interrupted publish into {dst}: ROLLBACK INCOMPLETE: " + "; ".join(stuck)
                            + _where(st, dst, names, drop, job))
            continue
        _drop_marker(dst, job)
        if not _remove_if_same(st / JOURNAL, jid):
            problems.append(f"{st / JOURNAL} changed after it was read; kept - the rollback above is done, check by hand")
            continue
        print(f"[push] an interrupted publish into {dst} was rolled back: old files restored; its new files are back in {st}",
              flush=True)
    if leftovers and not problems:
        print("WARN leftover backup(s) (kept by an earlier publish, or left by an interrupted one), not used by anything - delete them by hand once"
              " you have checked them: " + ", ".join(str(q) for q in sorted(leftovers)), flush=True)
    return problems


DRYRUN_NOTES = ("prompt_fixed.txt", "prompt.txt", "shot.json")


def _note_id(q):
    """Which file a note is right now: ("link", target, file id) for a link, ("sha", sha256, file id) for a file (file id =
    st_ino, the NTFS file index: a different file with the same bytes still differs), None if absent / something else."""
    try:
        if q.is_symlink():
            return ("link", os.readlink(q), os.lstat(q).st_ino)
        if q.is_file():
            return ("sha", *_sha_ino(q))  # content and file id from ONE handle (the id is the very file that was hashed)
    except OSError:
        pass
    return None


def _remove_if_same(q, ident):
    """Delete the file at q only if it is still exactly `ident` (a _note_id taken earlier): q is first renamed to a unique name,
    then checked, so a file swapped in at q meanwhile can never be the one deleted; not the same -> put back (Windows rename
    never overwrites) and WARN. A read-only flag is cleared only on a file with a single name (with hard links the flag
    belongs to the shared file). True if deleted."""
    import uuid
    if ident is None or not os.path.lexists(q):
        return False
    grab = q.with_name(f".{q.name}.del_{uuid.uuid4().hex[:8]}")
    try:
        os.rename(q, grab)
    except OSError:
        return False
    if _note_id(grab) == ident:
        try:
            if ident[0] == "sha" and os.lstat(grab).st_nlink == 1:
                os.chmod(grab, 0o666)
            grab.unlink()
            return True
        except OSError:
            try:
                os.rename(grab, q)
                print(f"WARN {q} could not be removed (read-only / shared file); kept", flush=True)
            except OSError:
                print(f"WARN {grab} could not be removed (read-only / shared file); kept under this name", flush=True)
            return False
    try:
        os.rename(grab, q)  # not the file we checked: put it back
        print(f"WARN {q} is not the file that was checked (changed or replaced); kept", flush=True)
    except OSError:
        print(f"WARN {grab} changed (or replaced the file we checked); kept under this name", flush=True)
    return False


def _remove_notes(d, known):
    """Delete in folder d only the notes listed in `known` ({name: _note_id when we wrote / checked it}) that are still exactly
    that (see _remove_if_same), then d itself if it is empty. Anything else - another file, or a note that changed since - is
    left alone and reported (WARN). Never a recursive delete."""
    for name, ident in known.items():
        _remove_if_same(d / name, ident)
    try:
        d.rmdir()
    except FileNotFoundError:
        pass
    except OSError:
        print(f"WARN {d} still holds files that are not push_end's notes; kept - check it by hand", flush=True)


def write_dryrun_notes(out, files):
    """Write the push dry-run notes as a whole: a new folder is filled with brand-new files (never writing through an existing
    file or link), then swapped in for <out>/push_dryrun by two folder renames; on any failure the old folder is put back.
    push_dryrun may only hold these notes (anything else -> refused, nothing changed). None, or the error text."""
    import uuid
    notes = out / "push_dryrun"
    if notes.is_dir():
        other = sorted(q.name for q in notes.iterdir() if q.name not in DRYRUN_NOTES)
        if other:
            return f"{notes} also holds {', '.join(other)}; it is push_end's own notes folder - move those elsewhere first. Nothing was written"
    job = uuid.uuid4().hex[:8]
    new, old = out / f".push_dryrun_new_{job}", out / f".push_dryrun_old_{job}"
    if os.path.lexists(new) or os.path.lexists(old):
        return f"{new} / {old} already exists; nothing was written"
    created, mine = False, {}
    old_ids = {n: _note_id(notes / n) for n in DRYRUN_NOTES} if notes.is_dir() else {}  # the old notes as checked
    try:
        out.mkdir(parents=True, exist_ok=True)
        new.mkdir()
        created = True  # from here on `new` is ours to clean up (only the files we wrote)
        for name, data in files.items():
            with open(new / name, "xb") as fh:  # exclusive create in a folder made just now
                fh.write(data)
                ino = os.fstat(fh.fileno()).st_ino
            mine[name] = ("sha", hashlib.sha256(data).hexdigest(), ino)
    except OSError as e:
        if created:
            _remove_notes(new, mine)
        return f"could not write the dry-run notes ({e}); {notes} unchanged"
    had = notes.exists()
    try:
        if had:
            os.rename(notes, old)
        try:
            os.rename(new, notes)
        except OSError:
            if had:
                os.rename(old, notes)  # put the old notes back
            raise
    except OSError as e:
        _remove_notes(new, mine)
        return f"could not replace {notes} ({e}); the old notes were kept"
    moved = [n for n, ident in mine.items() if _note_id(notes / n) != ident]  # the new notes must be in place (every swap)
    if moved:
        return (f"the new dry-run notes in {notes} are not the ones just written ({', '.join(moved)})"
                + (f"; the old notes are kept in {old}" if had else "") + " - check by hand")
    if had:  # the old notes folder: only push_end's three notes are deleted, then the folder if empty
        _remove_notes(old, old_ids)
        moved = [n for n, ident in mine.items() if _note_id(notes / n) != ident]  # again: changed while the old ones went?
        if moved:
            return f"the new dry-run notes in {notes} changed while the old ones were removed ({', '.join(moved)}) - check by hand"
    return None


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
    spec_bytes = spec_path.read_bytes()  # read once: the push mode publishes exactly these bytes as shot.json
    spec = json.loads(spec_bytes.decode("utf-8"))
    out = Path(a.out or spec_path.with_suffix(""))
    push = push_conf(spec)
    hold = None
    if push is not None:
        # 2026-11-24 push_end: hold a per-folder OS lock for the whole run (lock files in the temp dir, nothing added to <out>)
        # so a push run never interleaves with another push run or a normal run on the same folder, and refuse before the
        # first write if anything is wrong with the spec or its inputs.
        hold, why = push_acquire(out)
        if hold is None:
            print(f"ERROR {why}; nothing was written")
            sys.exit(1)
        PE = push_errors(spec, push, spec_path.parent, out, spec_path)
        if not PE:
            try:  # both prompts are built before the first write; a malformed spec field is an ERROR, not a traceback
                prompt = build_prompt(fixed_spec(spec, push))
                prompt2 = build_prompt(push_spec(spec, push, out / "push_end.png"))
            except Exception as e:
                PE = [f"push_end: cannot build the prompt from this spec ({type(e).__name__}: {e})"]
        if PE:
            for x in PE:
                print("ERROR", x)
            print("[prompt] nothing written (push_end checks failed)")
            sys.exit(1)
    if push is None:  # normal spec: unchanged behaviour (except: refused while a push_end run uses the same folder)
        hold, why = normal_guard(out)
        if hold is None:
            print(f"ERROR {why}. Nothing was written")
            sys.exit(1)
        out.mkdir(parents=True, exist_ok=True)
        # 2026-10-10: "raw_prompt" bypasses the official 6-section builder + lint (e.g. CrossView-Warp LoRA was trained on the single caption "crossview")
        prompt = spec.get("raw_prompt") or build_prompt(spec)
        (out / "prompt.txt").write_text(prompt, encoding="utf-8")
        shutil.copy2(spec_path, out / "shot.json")
    E, W = ([], ["raw_prompt: official-format lint skipped"]) if spec.get("raw_prompt") else lint(prompt, spec["duration"])
    if spec["duration"] > 12:
        W.append(f"duration {spec['duration']}s > 12 s: in this project 15 s clips drifted / self-cut; keep shots <= 12 s")
    # 2026-10-23 A/B (6 shots x 2 seeds, optical flow): one-line actions -> ~1/2.7 of the motion; end frame = first frame freezes people
    if not spec.get("raw_prompt"):
        for i, sh in enumerate(spec["shots"], start=1):
            n = len((sh.get("action") or "").split())
            if 0 < n < 50:
                W.append(f"[Shot {i}] action is short ({n} words): write 50-150 words 'Starting from <Picture 1>, ...' split into 'Beat 1: ... Beat 2: ...' (2-3 causal actions) and a held end pose,"
                         " with body parts, amplitude and repetitions (official h3-prompt-writing; one-liners moved ~1/2.7 as much)")
            if n >= 50 and sh.get("dialogue") and "beat 1" not in (sh.get("action") or "").lower():
                W.append(f"[Shot {i}] talking shot without beats: split the action into 'Beat 1: ... Beat 2: ...' tied to the sentences,"
                         " plus a held end pose (2026-11-23 A/B: ~1.4-2x more motion than one continuous sentence)")
        first, last = spec.get("first_frame"), spec.get("last_frame")
        if first and last and (spec_path.parent / first).resolve() == (spec_path.parent / last).resolve():
            W.append("last_frame = first_frame pins everyone back to the first pose (2026-10-23 S22: 100% still); fine for static/prop-lock shots,"
                     " but if someone must move, use an end image of the finished pose or no end frame")
    if push is not None:  # 2026-11-24 end-frame push (structure already checked above): also lint the second-pass prompt
        cam0 = spec["shots"][0].get("camera")
        if isinstance(cam0, str) and cam0.strip() and cam0.strip() != fixed_spec(spec, push)["shots"][0]["camera"].strip():
            W.append("push_end: the spec's camera line is not used (pass 1 = locked-off camera"
                     + (" from push_end.fixed_camera" if push.get("fixed_camera") else "") + ", pass 2 = push line)")
        if push.get("fixed_clip"):
            W.append("push_end.fixed_clip: that take must itself be shot with a locked-off camera (this tool cannot check it);"
                     " its last frame becomes the zoomed end frame")
        E2, W2 = lint(prompt2, spec["duration"])  # pass 2 is linted even when pass 1 has errors: the report lists both
        E += [f"(push pass) {x}" for x in E2]
        W += [f"(push pass) {x}" for x in W2 if x not in W]
    for x in E:
        print("ERROR", x)
    for x in W:
        print("WARN ", x)
    where = (out / "prompt.txt" if push is None else "(nothing written: errors)" if (E and not a.force)
             else (out / "push_dryrun" / "prompt_fixed.txt" if a.dry_run else out / "(published with the clip)"))
    print(f"[prompt] {where} ({len(E)} errors, {len(W)} warnings)" + (" + push_end second pass" if push is not None else ""))
    if E and not a.force:
        sys.exit(1)
    if a.dry_run:
        if push is not None:  # push mode: notes go to push_dryrun/ (never the published set), only once every check passed
            err = write_dryrun_notes(out, {"prompt_fixed.txt": prompt.encode("utf-8"), "prompt.txt": prompt2.encode("utf-8"),
                                           "shot.json": spec_bytes})
            if err:
                print(f"ERROR {err}")
                sys.exit(1)
        return
    try:
        req("/system_stats")
    except Exception as e:
        sys.exit(f"ComfyUI not reachable at {HOST} ({e}); run C:\\AI\\tools\\start_comfy.cmd first")
    if push is not None:
        sys.exit(0 if run_push(spec, push, spec_path.parent, out, prompt, spec_bytes, locked=True) else 1)
    sys.exit(0 if generate(spec, prompt, spec_path.parent, out) else 1)


if __name__ == "__main__":
    main()
