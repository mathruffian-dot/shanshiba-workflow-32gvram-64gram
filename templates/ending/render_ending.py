"""《山獅霸的多重宇宙》頻道片尾範本（2026-09-30，阿福〈三個絕招〉定稿使用的版本）
結構：N 張特寫靜幀（緩推＋下緣壓暗）＋每張 2 行「AI 工具・用途」名單 → 金色咒印法陣＋大標題逐字由光浮現、爆光、淡出。
用法（H3 venv 有 numpy／Pillow／ffmpeg 即可）：
    C:\\AI\\H3\\venv\\Scripts\\python.exe render_ending.py config.json
config.json 範例見同資料夾 config_example.json。輸出 24fps、1920x1080、無音訊（配樂與音效在主片後製疊）。
規則：名單依實際使用的工具填寫；非商用授權工具（使用者指示）不列名；MiniMax Music 3 等要求標示的授權需列名並揭露 AI 生成。"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 24
FONT_TITLE = "C:/Windows/Fonts/kaiu.ttf"        # 標楷體：大標題
FONT_BOLD = "C:/Windows/Fonts/msjhbd.ttc"       # 微軟正黑粗體：名單
GLOW, CORE = (255, 190, 60), (255, 246, 215)


def glow_layer(mask, color, radii=(6, 16, 36, 70), gains=(0.55, 0.42, 0.34, 0.26)):
    base = np.zeros((H, W, 3), np.float32); col = np.array(color, np.float32) / 255
    for r, g in zip(radii, gains):
        base += (np.asarray(mask.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255)[..., None] * col * g
    return base


def rays(cx, cy, n=36, length=1500, strength=0.35, rot=0.0):
    yy, xx = np.mgrid[0:H, 0:W]; ang = np.arctan2(yy - cy, xx - cx) + rot; dist = np.hypot(xx - cx, yy - cy)
    a = (np.cos(ang * n) * 0.5 + 0.5) ** 6
    fall = np.clip(1 - dist / length, 0, 1) ** 1.5 * np.clip((dist - 260) / 220, 0, 1)
    return (a * fall * strength).astype(np.float32)


def encoder(out):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)


def render(cfg):
    base = Path(cfg.get("_base", HERE)); title = cfg.get("title", "山獅霸的多重宇宙")
    card_dur, title_dur = cfg.get("card_dur", 3.3), cfg.get("title_dur", 7.5)
    f_head = ImageFont.truetype(FONT_BOLD, 30); f_a = ImageFont.truetype(FONT_BOLD, 46); f_b = ImageFont.truetype(FONT_BOLD, 30)
    enc = encoder(base / cfg.get("out", "ending.mp4")); n_card = int(card_dur * FPS)
    for ci, card in enumerate(cfg["cards"]):
        im = Image.open(base / card["image"]).convert("RGB").resize((W, H), Image.LANCZOS)
        for i in range(n_card):
            u = i / (n_card - 1); z = 1.03 + (0.07 * u if ci % 2 == 0 else 0.07 * (1 - u))
            cw, ch = int(W / z), int(H / z); x0, y0 = (W - cw) // 2, (H - ch) // 2
            a = np.asarray(im.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)).astype(np.float32)
            yy = np.linspace(0, 1, H)[:, None, None]; a = a * (0.55 + 0.45 * (1 - yy * 0.9))
            fr = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(fr); fade = min(1.0, u / 0.15, (1 - u) / 0.15)
            for k, (name, what) in enumerate(card["tools"]):
                y = 780 + k * 92
                d.text((150, y), name, font=f_a, fill=(255, 244, 222), stroke_width=4, stroke_fill=(0, 0, 0))
                if what: d.text((150 + d.textlength(name, font=f_a) + 28, y + 12), "・ " + what, font=f_b, fill=(255, 226, 170), stroke_width=3, stroke_fill=(0, 0, 0))
            if ci == 0: d.text((150, 725), cfg.get("header", "本片使用的 AI 工具"), font=f_head, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
            enc.stdin.write(np.clip(np.asarray(fr).astype(np.float32) * fade, 0, 255).astype(np.uint8).tobytes())
    seal = Image.open(HERE / "assets" / "seal_gold.png").convert("RGB").resize((W, H), Image.LANCZOS)
    f = ImageFont.truetype(FONT_TITLE, 176); meas = ImageDraw.Draw(Image.new("L", (W, H)))
    chars = []; tw = sum(meas.textlength(c, font=f) for c in title) + 10 * (len(title) - 1); x = (W - tw) / 2
    for c in title:
        cm = Image.new("L", (W, H), 0); ImageDraw.Draw(cm).text((x, H / 2 - 110), c, font=f, fill=255, stroke_width=3, stroke_fill=255); chars.append(cm); x += meas.textlength(c, font=f) + 10
    n = int(title_dur * FPS)
    for i in range(n):
        u = i / (n - 1); fade = min(1.0, u / 0.08) * min(1.0, (1 - u) / 0.22)
        reveal = min(1.0, max(0.0, (u - 0.10) / 0.45)); flash = np.sin(min(1, max(0, (u - 0.56) / 0.2)) * np.pi)
        S_ = np.asarray(seal.rotate(u * 18, resample=Image.BICUBIC), np.float32) / 255 * 0.55
        col = np.array(GLOW, np.float32) / 255; out = S_ + rays(W / 2, H / 2, rot=u * 0.5, strength=0.22)[..., None] * col
        mm = Image.new("L", (W, H), 0)
        for k, cm in enumerate(chars):
            al = min(1.0, max(0.0, reveal * len(chars) - k))
            if al > 0: mm = ImageChops.lighter(mm, cm.point(lambda v, al=al: int(v * al)))
        dark = np.asarray(mm.filter(ImageFilter.GaussianBlur(50)), np.float32)[..., None] / 255
        out = out * (1 - 0.55 * np.clip(dark * 2.0, 0, 1))
        out = out + glow_layer(mm, GLOW) * 1.1 + np.asarray(mm.filter(ImageFilter.GaussianBlur(1.2)), np.float32)[..., None] / 255 * (np.array(CORE, np.float32) / 255) * 1.1
        if flash > 0.01: out = out + glow_layer(mm, GLOW, radii=(30, 90, 180), gains=(0.6, 0.5, 0.4)) * flash
        enc.stdin.write((np.clip(out * fade, 0, 1) * 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait(); print("wrote", base / cfg.get("out", "ending.mp4"))


if __name__ == "__main__":
    p = Path(sys.argv[1]).resolve(); cfg = json.loads(p.read_text(encoding="utf-8")); cfg["_base"] = p.parent; render(cfg)
