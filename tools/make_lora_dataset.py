"""用一張「單張半身定妝照」在本機產生角色 LoRA 的訓練資料（Qwen-Image-Edit 2511 換景別、角度、表情、場景，長相不變）。
H3 venv（ComfyUI 要開著）：
  python make_lora_dataset.py --ref bust.png --trigger xyun_local --desc "the girl Xiaoyun, a bright 11-year-old Taiwanese schoolgirl with ..." --out dataset_dir [--n 24]
輸出 dataset_dir/<序號>.png ＋ 同名 .txt（caption＝觸發詞＋外觀＋這張的景別動作），可直接給 AI Toolkit。
原專案做法（2026-09-28〜10-01）：定妝照裁切幾張＋以定妝照為參考生成多角度多場景（當時用 Image 2.5），逐張目視審過再訓練；
**產生後一定要逐張看，刪掉臉不像、多手多腳、有字的圖**，再開始訓練。"""
import argparse
import shutil
import subprocess
from pathlib import Path

T = Path(__file__).resolve().parent
VARIANTS = [
    ("tight close-up portrait facing the camera, warm gentle smile", "soft window light, blurred classroom behind"),
    ("close-up, three-quarter view facing right, thoughtful expression", "late afternoon golden light"),
    ("close-up, three-quarter view facing left, laughing", "bright daylight, school corridor behind"),
    ("close-up exact side profile looking into the distance", "soft backlight, plain wall behind"),
    ("medium shot sitting at a wooden school desk writing in a notebook", "classroom, warm light"),
    ("medium shot standing and raising one hand", "classroom with a green chalkboard"),
    ("medium shot leaning on a windowsill looking outside", "sunset light through the window"),
    ("full-body shot standing on a school sports field", "clear afternoon sky"),
    ("full-body shot walking along a school corridor", "soft daylight"),
    ("medium close-up looking surprised, eyes wide", "classroom, neutral light"),
    ("medium close-up looking worried, eyebrows raised", "classroom, cool evening light"),
    ("medium close-up with a big proud grin", "school playground, sunny"),
    ("medium shot sitting on stairs reading a book", "school staircase, soft light"),
    ("medium shot holding a lunch box and smiling", "school cafeteria, warm light"),
    ("close-up looking down at a paper, focused", "desk lamp light at night"),
    ("medium shot standing with arms crossed, confident", "plain light grey studio background"),
    ("full-body shot, front view, standing straight", "plain light grey studio background"),
    ("full-body shot, back three-quarter view looking over the shoulder", "plain light grey studio background"),
    ("medium shot waving hello", "school gate, morning light"),
    ("close-up with eyes closed, calm, peaceful", "soft warm light"),
    ("medium shot running, mid-stride", "school sports track"),
    ("medium close-up yawning, sleepy", "classroom in the morning"),
    ("medium shot sitting on a bench eating a snack", "school courtyard with trees"),
    ("close-up, low angle, determined look", "dramatic sky behind"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True); ap.add_argument("--trigger", required=True); ap.add_argument("--desc", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--n", type=int, default=len(VARIANTS)); ap.add_argument("--seed", type=int, default=100)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); tmp = out / "_raw"; tmp.mkdir(exist_ok=True)
    shutil.copy2(a.ref, out / "000.png")
    (out / "000.txt").write_text(f"{a.trigger}, {a.desc}, bust portrait facing the camera, plain light grey studio background", encoding="utf-8")
    for i, (shot, light) in enumerate(VARIANTS[: a.n], start=1):
        dst = out / f"{i:03d}.png"
        if dst.exists():
            continue
        prompt = (f"Keep exactly the same person as <image1>: same face, age, hairstyle and clothes. New realistic photo, {shot}, {light}. "
                  "Only this one person. Natural skin texture, sharp focus on the face. No text, no watermark.")
        r = subprocess.run([str(Path(__import__('sys').executable)), str(T / "gen_image.py"), "--model", "qwen-edit", "--ref", a.ref, "--width", "1024",
                            "--height", "1024", "--prompt", prompt, "--seed", str(a.seed + i), "--prefix", f"lora_ds/{a.trigger}_{i:03d}", "--out", str(tmp)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        made = sorted(tmp.glob(f"{a.trigger}_{i:03d}*.png"))
        if r.returncode != 0 or not made:
            print("FAIL", i, (r.stdout + r.stderr)[-300:]); continue
        made[-1].rename(dst)
        (out / f"{i:03d}.txt").write_text(f"{a.trigger}, {a.desc}, {shot}, {light}", encoding="utf-8")
        print("ok", dst.name, flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("done:", len(list(out.glob('*.png'))), "images. Review every image, delete bad ones, then train (setup/lora/README.md).")


if __name__ == "__main__":
    main()
