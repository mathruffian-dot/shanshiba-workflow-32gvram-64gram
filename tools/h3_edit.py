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
