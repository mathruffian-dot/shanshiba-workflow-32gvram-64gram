"""H3 video editing (character swap) in the OFFICIAL Ref2VA prompt format  (added 2026-10-01).

Takes an existing clip + a reference picture of the NEW character and asks H3 to produce an edited version of the clip:
same scene / camera / timing / action, the person replaced by the new character.  Official task type: `[video editing + audio reuse]`
(github.com/MiniMax-AI/MiniMax-H3/skills/h3-prompt-writing/references/ref-en.txt, sec. 2.3 / 3 / 4).
Only use characters/faces you own or have permission for (project characters, San-shi-ba himself); no public figures or other people's likeness.

Usage:  C:\\AI\\H3\\venv\\Scripts\\python.exe C:\\AI\\tools\\h3_edit.py edit.json --out <dir> [--dry-run]
edit.json:
{
  "source_video": "C:/.../clip.mp4",        # clip to edit (<Video 1>); duration/frames/audio are taken from it
  "identity_image": "C:/.../01_dingzhuangzhao.png",  # new character (<Picture 1> -> <Subject 1>)
  "new_desc": "Ahe, a mischievous 12-year-old Taiwanese boy (...)",   # English, locks the new look
  "old_desc": "the chubby boy in the white school uniform",           # what is being replaced
  "describe": "<Subject 1> walks up to the ball ... ",                # English: what happens in the video, with <Subject 1> as the actor
  "style": "a realistic cinematic live-action ...", "setting": "...", # optional
  "soundscape": "Quiet outdoor ambience ...", "reuse_audio": true,
  "seed": 1, "steps": 14, "size": [1344, 768]                         # optional
}

"recipe" (added 2026-11-01, 試行/H3社群候選對照_20261101): Alissonerdx LoRAs, run the way their author trained them -
the whole source clip goes in as aligned guide frames (MiniMaxH3AddGuide at frame 0, not the native video reference) with the
author's one-line prompt template; the LoRA is added automatically (strength 1.0, override with "lora"). Source audio is reused.
  "recipe": "body_swap"  -> minimax_h3_character_swap_v1.1_ref2va_fro (whole person: face, hair, body, clothes)
  "recipe": "head_swap"  -> minimax_h3_head_swap_v1.0_r32 (head only; body, clothes and performance stay)
  "details": "Male, around 32, slim build, ..."   # body_swap: head-to-toe, starts with the gender, no article, no final period
                                                  # head_swap: the face/head only (shape, skin, eyes, hair, glasses ...)
Measured: works when the new character looks clearly different (Confucius -> Shanshiba close-up with dialogue: scene, other
people and audio kept); lookalikes (two chubby 12-year-old boys in the same uniform) still do not change. head_swap shifted the
colour grade warmer. "describe"/"old_desc"/"style"/"setting"/"soundscape" are ignored by recipes.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import h3_shot as H


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True).stdout
    j = json.loads(r)
    return j["streams"][0], float(j["format"]["duration"])


def build_prompt(spec, reuse_audio):
    """Community lesson (seedance.tv / RunComfy character-replacement guides, 2026-10): define BOTH the replacement (<Subject 1>) and the original
    performer (<Subject 2>) so H3 knows who to swap, and say that the original must not reappear; otherwise it may keep the source person."""
    old, new = spec["old_desc"], spec["new_desc"]
    L = ["subject_definitions:",
         f"<Subject 1> is {new}, whose appearance comes from <Picture 1> and whose motion, timing and performance follow the performer in <Video 1>.",
         f"<Subject 2> is {old} in <Video 1>, the original performer who is replaced by <Subject 1> and must not appear in the target video.",
         "<Video 1> is the source video for the target video edit."]
    if reuse_audio:
        L.append("<Audio 1> is the synchronized audio track of <Video 1> and is reused in the target video.")
    tasks = "video editing + audio reuse" if reuse_audio else "video editing"
    setting = f" set in {spec['setting']}" if spec.get("setting") else ""
    L += ["", "summary:",
          f"[{tasks}] The target video is an edited version of <Video 1>. <Subject 1> replaces <Subject 2> while the scene{setting}, "
          "the camera, the timing and the action stay as in <Video 1>.",
          "", "retention_analysis:",
          "<Subject 1> (appears in [Shot 1]): fully_preserved - the face, age, hairstyle, body build and clothing of the person in <Picture 1> are used for the actor.",
          "<Subject 2> (appears only in <Video 1>): weak_reference - only the body position, timing and movement are followed; the face, hairstyle and clothing of <Subject 2> do not appear in the target video.",
          "<Video 1> (source video structure): partially_preserved - the scene, camera, timing, body movement and background are retained; "
          "only the performer is replaced."]
    if reuse_audio:
        L.append("<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.")
    style = spec.get("style", "the same visual style, lighting and color grade as <Video 1>")
    L += ["", "detailed_description:", f"The target video keeps {style}.",
          "[Shot 1] The shot follows <Video 1> exactly, but the actor is <Subject 1>, not <Subject 2>: " + new + ". " + spec["describe"].strip(),
          "", "overall_soundscape:", spec.get("soundscape", "The original sound of <Video 1> continues unchanged."),
          "", "non_diegetic_music:", "N/A"]
    return "\n".join(L)


BODY_SWAP = (
    "body_swap: subject_definitions: <Subject 1> is the {details} shown in <Picture 1>, whose identity, face, head, hair or fur, skin, "
    "body shape, proportions and clothing define the character in the target video. The guide video provides the scene and the performance: "
    "its background, environment, lighting, camera, framing, body pose, hand and arm movement, head rotation, gaze direction, lip movement and "
    "facial expression, frame by frame; only the main subject of the guide video is replaced: its face, hair, body and clothing become "
    "<Subject 1>.  summary: [video generation + reference] Replace the guide subject with <Subject 1>, keeping the scene, camera and the "
    "complete motion and performance of the guide video.  detailed_description: [Shot 1] <Subject 1> takes the exact place of the guide "
    "subject and moves with the same timing, body pose, gestures, head motion, gaze, speech and facial expressions, while keeping the complete "
    "identity from <Picture 1>: facial structure, hair or fur, skin, body shape and clothing stay stable in every frame. The background, "
    "lighting, colors and camera of the guide video are preserved. Prevent identity drift, clothing changes, texture crawling and flicker.")

HEAD_SWAP = """head_swap:

subject_definitions:

<Subject 1> is the reference head identity from <Picture 1>, including the complete head, facial identity, facial structure, head shape, hairstyle, hairline, skin appearance, proportions, and all distinctive visual features.

Facial details of <Subject 1>:
{details}

<Subject 2> is the original person in <Video 1>, whose body, neck, clothing, pose, physical proportions below the head, actions, motion, timing, and interaction with the environment must remain unchanged.

<Video 1> is the source video for the target video edit, providing the original body performance, motion, camera movement, framing, timing, lighting, environment, scene composition, and temporal structure.

summary:

[video editing + reference generation]

The target video is an edited version of <Video 1>. Replace only the entire head of <Subject 2> with the reference head identity defined by <Subject 1> from <Picture 1>. Preserve the source video's body, clothing, performance, motion, camera behavior, environment, lighting, timing, and composition.

retention_analysis:

<Subject 1> (appears throughout the target video): attribute_transfer - the complete head identity from <Picture 1>, including facial identity, facial structure, hairstyle, head shape, proportions, skin appearance, and distinctive features, is transferred consistently onto the body of <Subject 2>.

<Subject 2> (appears throughout the target video): partially_preserved - the original body, neck position, clothing, pose, motion, gestures, actions, and physical performance are preserved, while only the original head is replaced.

<Video 1> (entire target timeline): partially_preserved - the original video timing, body motion, camera movement, framing, lighting, background, environment, scene composition, and temporal structure are preserved; only the subject's head appearance is modified.

detailed_description:

Preserve <Video 1> as the complete temporal and compositional foundation of the target video. <Subject 2> retains the exact original body, clothing, pose, body proportions, movement, gestures, actions, speed, timing, and interaction with the environment.

Replace only the entire original head of <Subject 2> with <Subject 1>, the reference head identity from <Picture 1>. Preserve the complete recognizable identity of <Subject 1>, including facial structure, skull and head shape, hairstyle, hairline, skin appearance, facial proportions, eyes, eyebrows, nose, mouth, jawline, ears, and distinctive identifying features.

The transferred head follows the original head motion and performance of <Subject 2> throughout <Video 1>, including head rotation, tilt, pitch, yaw, natural translation, facial orientation, gaze direction, and perspective changes. Maintain anatomically correct head scale and a seamless connection between the transferred head and the original neck.

Preserve the lighting conditions of <Video 1> on the transferred head. The head naturally responds to changes in illumination, shadows, highlights, color temperature, exposure, depth of field, motion blur, occlusion, camera angle, and perspective while continuously maintaining the identity established by <Picture 1>.

Maintain strong temporal consistency across every frame. The identity, facial geometry, hairstyle, head size, skin appearance, and distinguishing features of <Subject 1> remain stable during motion and viewpoint changes. Prevent identity drift, facial morphing, hairstyle changes, head-size fluctuations, geometry instability, texture crawling, temporal flickering, frame-to-frame inconsistency, or sudden changes in facial appearance.

Do not alter the body, clothing, hands, pose, gestures, action, background, objects, environment, camera trajectory, framing, lens behavior, scene timing, or composition inherited from <Video 1>. The final result should appear as though <Subject 1>'s head naturally belonged to <Subject 2>'s body during the original recorded performance.

overall_soundscape:

Preserve the original audiovisual timing and visible action structure of <Video 1>. No visual modifications are made outside the head replacement.

non_diegetic_music:
N/A"""

RECIPES = {"body_swap": (BODY_SWAP, "minimax_h3_character_swap_v1.1_ref2va_fro.safetensors"),
           "head_swap": (HEAD_SWAP, "minimax_h3_head_swap_v1.0_r32.safetensors")}


def guide_clip(src, frames, out):
    """AddGuide needs 17n+5 frames: cut the source down to the largest such length (H3 clips already fit)."""
    n = (frames - 5) // 17 * 17 + 5
    if n < 22:
        sys.exit(f"source has only {frames} frames; recipes need at least 22")
    if n == frames:
        return src, n
    dst = out / "source_guide.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-frames:v", str(n), "-r", "24", "-c:v", "libx264", "-crf", "12",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)], check=True)
    print(f"[recipe] source cut {frames} -> {n} frames (17n+5) for the guide")
    return dst, n


def main_recipe(spec, src, frames, size, out, dry):
    tmpl, lora = RECIPES[spec["recipe"]]
    details = (spec.get("details") or spec["new_desc"]).strip().rstrip(".")
    prompt = tmpl.format(details=details)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"[recipe] {spec['recipe']} + {lora}; prompt {out / 'prompt.txt'}")
    if dry:
        return
    guide, n = guide_clip(src, frames, out)
    wav = out / "source_audio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(guide), "-vn", "-ac", "1", "-ar", "48000", str(wav)], check=True)
    g = {"duration": n / 24, "size": size, "seed": spec.get("seed", 42), "steps": spec.get("steps", 14), "easycache": False,
         "subjects": [{"key": "new", "desc": details, "identity_image": str(spec["identity_image"])}],
         "first_clip": str(guide), "audio": {"fixed": {"file": str(wav)}}, "shots": [],
         "lora": spec.get("lora") or {"name": lora, "strength": 1.0}}
    for k in ("attention", "sampler"):
        if k in spec:
            g[k] = spec[k]
    sys.exit(0 if H.generate(g, prompt, src.parent, out) else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = Path(spec["source_video"])
    st, dur = probe(src)
    num, den = st["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    frames = int(st.get("nb_frames") or round(dur * fps))
    size = spec.get("size") or [int(st["width"]), int(st["height"])]
    if spec.get("recipe"):
        if spec["recipe"] not in RECIPES:
            sys.exit(f"unknown recipe {spec['recipe']!r}; use one of {sorted(RECIPES)}")
        if Path(a.spec).resolve() != (out / "edit.json").resolve():
            shutil.copy2(a.spec, out / "edit.json")
        return main_recipe(spec, src, frames, size, out, a.dry_run)
    reuse = spec.get("reuse_audio", True)
    guide = None
    if reuse:
        guide = out / "source_audio.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", str(guide)], check=True)
    prompt = build_prompt(spec, reuse)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    shutil.copy2(a.spec, out / "edit.json")
    E, W = H.lint(prompt, dur)
    for x in E:
        print("ERROR", x)
    for x in W:
        print("WARN ", x)
    print(f"[prompt] {out / 'prompt.txt'} ({len(E)} errors, {len(W)} warnings); source {frames}f {dur:.2f}s {size}")
    if a.dry_run:
        return
    g = {"duration": frames / 24 - 0.001, "size": size, "seed": spec.get("seed", 42), "steps": spec.get("steps", 14), "easycache": False,
         "subjects": [{"key": "new", "desc": spec["new_desc"], "identity_image": str(spec["identity_image"])}],
         "camera_video": {"file": str(src)}, "shots": []}
    if reuse:
        g["audio"] = {"fixed": {"file": str(guide)}}
    for k in ("lora", "attention", "sparse", "draft", "sampler"):
        if k in spec:
            g[k] = spec[k]
    sys.exit(0 if H.generate(g, prompt, src.parent, out) else 1)


if __name__ == "__main__":
    main()
