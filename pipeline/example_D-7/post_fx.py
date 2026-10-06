"""〈D-7〉後製素材：撕日曆字卡、咒印名片（欄內／全畫面）、手機聊天畫面、三分割調色。assemble.py 匯入。
  python post_fx.py test   → post/test_*.png 樣張"""
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080
KAI = "C:/Windows/Fonts/kaiu.ttf"; JH = "C:/Windows/Fonts/msjhbd.ttc"; JHR = "C:/Windows/Fonts/msjh.ttc"
SEAL_DIR = HERE.parents[1] / "templates" / "seals"   # 原專案放在別支片的資料夾，這裡集中到 templates/seals
SEALS = {"eye": SEAL_DIR / "SEAL_1_eye.png", "time": SEAL_DIR / "SEAL_2_time.png", "soul": SEAL_DIR / "SEAL_3_soul.png", "gold": SEAL_DIR / "seal_gold.png"}


def ease(x): x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ 三分割調色
def grade_grey(fr, g):
    """g=1 灰（還沒開始準備）、0 正常。fr float32 0–1。"""
    if g <= 0: return fr
    lum = (fr * np.array([0.3, 0.59, 0.11], np.float32)).sum(-1, keepdims=True)
    grey = lum * np.array([0.92, 0.96, 1.04], np.float32) * 0.55
    return fr * (1 - g) + grey * g


def grade_lit(fr, k):
    """k 0–1：亮起來（暖、微亮）。"""
    if k <= 0: return fr
    warm = np.clip(fr * np.array([1.08, 1.02, 0.92], np.float32) * 1.06, 0, 1)
    return fr * (1 - k) + warm * k


# ------------------------------------------------------------------ 撕日曆字卡
def _page(label, sub, w=760, h=860, red=(196, 32, 38)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 14, fill=(248, 244, 232, 255))
    d.rectangle((0, 0, w, 170), fill=red + (255,))
    for x in range(60, w - 40, 64): d.ellipse((x, 18, x + 22, 40), fill=(60, 20, 20, 255))
    f1 = ImageFont.truetype(JH, 78); t = "段考倒數"; b = d.textbbox((0, 0), t, font=f1); d.text(((w - b[2]) / 2, 62), t, font=f1, fill=(255, 245, 230))
    f2 = ImageFont.truetype(JH, 300); b = d.textbbox((0, 0), label, font=f2); d.text(((w - (b[2] - b[0])) / 2 - b[0], 250), label, font=f2, fill=(40, 34, 30))
    if sub:
        f3 = ImageFont.truetype(JH, 70); b = d.textbbox((0, 0), sub, font=f3); d.text(((w - b[2]) / 2, 680), sub, font=f3, fill=red)
    rng = np.random.default_rng(len(label)); a = np.asarray(im, np.float32)
    a[..., :3] *= (1 - rng.uniform(0, 0.05, a.shape[:2]))[..., None]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


@lru_cache(None)
def _bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = 1 - 0.75 * (np.hypot(xx - W / 2, yy - H / 2) / np.hypot(W / 2, H / 2)) ** 1.6
    base = np.array([0.20, 0.15, 0.11], np.float32)
    rng = np.random.default_rng(3); n = rng.normal(0, 0.012, (H, W, 1)).astype(np.float32)
    return np.clip(base * v[..., None] + n, 0, 1)


def calendar_frame(t, dur, prev, label, sub=""):
    """prev 那一頁從上方撕走、露出 label。t 秒。"""
    bg = Image.fromarray((_bg() * 255).astype(np.uint8)).convert("RGBA")
    px, py = (W - 760) // 2, (H - 860) // 2 + 20
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((px + 18, py + 26, px + 778, py + 886), 14, fill=(0, 0, 0, 150))
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    cur = _page(label, sub); bg.alpha_composite(cur, (px, py))
    u = ease((t - 0.25) / 0.55)
    if prev is not None and u < 1:
        pg = _page(prev, "")
        if u > 0:
            ang = -28 * u; pg = pg.rotate(ang, expand=True, resample=Image.BICUBIC)
            a = pg.getchannel("A").point(lambda v: int(v * (1 - u ** 1.5))); pg.putalpha(a)
            ox, oy = int(px - 260 * u - (pg.width - 760) / 2), int(py - 700 * u ** 1.4 - (pg.height - 860) / 2)
        else:
            ox, oy = px, py
        bg.alpha_composite(pg, (ox, oy))
    fade = min(1, t / 0.15, (dur - t) / 0.15)
    a = np.asarray(bg.convert("RGB"), np.float32) / 255 * max(0.0, fade)
    s = 1 + 0.03 * t / dur                                     # 緩推
    im = Image.fromarray((a * 255).astype(np.uint8)); cw, ch = W / s, H / s
    return np.asarray(im.crop(((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)).resize((W, H), Image.BILINEAR), np.float32) / 255


# ------------------------------------------------------------------ 咒印名片
@lru_cache(None)
def _seal(key, size):
    im = Image.open(SEALS[key]).convert("RGB"); w, h = im.size; s = min(w, h)
    sq = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((size, size), Image.LANCZOS)
    yy, xx = np.mgrid[0:size, 0:size]; r = np.hypot(xx - size / 2, yy - size / 2) / (size / 2)
    a = np.asarray(sq, np.float32) / 255 * np.clip((1.02 - r) / 0.12, 0, 1)[..., None]
    return a


@lru_cache(None)
def _text_masks(text, cols, size, w, h, cy):
    font = ImageFont.truetype(KAI, size); cell = size + 14; rows = math.ceil(len(text) / cols)
    x0, y0 = w / 2 - cols * cell / 2, cy - rows * cell / 2; out = []
    for i, ch in enumerate(text):
        m = Image.new("L", (w, h), 0); d = ImageDraw.Draw(m); bb = d.textbbox((0, 0), ch, font=font)
        cx, cyy = x0 + (i % cols) * cell + cell / 2, y0 + (i // cols) * cell + cell / 2
        d.text((cx - (bb[0] + bb[2]) / 2, cyy - (bb[1] + bb[3]) / 2), ch, font=font, fill=255, stroke_width=3, stroke_fill=255)
        out.append(np.asarray(m, np.float32) / 255)
    return out


def _blur(a, r): return np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def namecard(fr, t, dur, text, seal="eye", glow=(1.0, 0.62, 0.25), cols=2, size=None):
    """fr：要蓋的畫面（欄或全畫面，float32 HxWx3）。t 從名片開始算。法陣淡入轉動、字逐字由光浮現、爆光、淡出。"""
    h, w = fr.shape[:2]; size = size or int(min(w * 0.36, 230)); g = np.array(glow, np.float32)
    fade = ease(t / 0.3) * ease((dur - t) / 0.35)
    dim = 1 - 0.55 * fade; out = fr * dim
    sd = int(min(w * 1.05, h * 0.9)); sl = _seal(seal, sd)
    ang = t * 18; sl_img = Image.fromarray((sl * 255).astype(np.uint8)).rotate(ang, resample=Image.BILINEAR)
    sc = 0.9 + 0.12 * ease(t / dur); s2 = int(sd * sc); sl = np.asarray(sl_img.resize((s2, s2), Image.BILINEAR), np.float32) / 255
    x0, y0 = (w - s2) // 2, (h - s2) // 2
    xs, ys, xe, ye = max(0, x0), max(0, y0), min(w, x0 + s2), min(h, y0 + s2)
    out[ys:ye, xs:xe] += sl[ys - y0:ye - y0, xs - x0:xe - x0] * 0.85 * fade
    masks = _text_masks(text, cols, size, w, h, h / 2)
    rev = (t - 0.35) / 0.9; n = len(masks); m = np.zeros((h, w), np.float32)
    for i, mk in enumerate(masks):
        a = ease(rev * n - i)
        if a > 0: m = np.maximum(m, mk * a)
    m *= fade
    if m.max() > 0:
        out *= (1 - 0.6 * np.clip(_blur(m, 30) * 2.2, 0, 1))[..., None]
        fl = math.sin(min(1, max(0, (t - 1.25) / 0.3)) * math.pi) if 1.25 < t < 1.55 else 0
        for r, gg in ((5, 0.55), (14, 0.45), (32, 0.35), (60, 0.25 + 0.5 * fl)):
            out += _blur(m, r)[..., None] * g * gg
        out += _blur(m, 1.0)[..., None] * np.array([1.0, 0.95, 0.85], np.float32) * 1.05
    return np.clip(out, 0, 1)


# ------------------------------------------------------------------ 手機聊天畫面（S10）
def _rr(d, box, r, fill): d.rounded_rectangle(box, r, fill=fill)


def phone_frame(t, dur):
    """0–1.4s 聊天列表（遊戲群組 999+ 在最上面、小雯（1）在下面）→ 點小雯 → 聊天室：上週四 21:03、4 張筆記照片、「我就知道你會問。」"""
    bg = Image.fromarray((_bg() * 255 * 0.55).astype(np.uint8)).convert("RGBA")
    pw, ph = 600, 1040; px, py = (W - pw) // 2, (H - ph) // 2 + 30
    ph_im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0)); d = ImageDraw.Draw(ph_im)
    _rr(d, (0, 0, pw - 1, ph - 1), 60, (18, 18, 20, 255)); _rr(d, (16, 16, pw - 17, ph - 17), 48, (245, 245, 247, 255))
    sx, sy = 16, 16; f = lambda s, b=True: ImageFont.truetype(JH if b else JHR, s)
    _rr(d, (pw / 2 - 70, 30, pw / 2 + 70, 58), 14, (18, 18, 20, 255))
    d.text((60, 34), "01:30", font=f(24), fill=(20, 20, 20))
    tap = 1.4
    if t < tap + 0.15:
        d.rectangle((sx, 80, pw - sx, 160), fill=(255, 255, 255)); d.text((48, 100), "聊天", font=f(40), fill=(20, 20, 20))
        rows = [("遊戲群組", "【小胖】快上線！！！", "999+", (90, 160, 255)), ("小雯", "[照片]", "1", (255, 150, 180)),
                ("阿福", "你晚餐吃什麼", "", (255, 200, 80)), ("班級群組", "老師：明天段考，早點睡", "", (120, 200, 140)),
                ("媽媽", "記得帶便當盒回來", "", (200, 160, 220))]
        for i, (name, msg, badge, col) in enumerate(rows):
            y = 175 + i * 118
            if name == "小雯" and t > tap - 0.25: d.rectangle((sx, y - 8, pw - sx, y + 104), fill=(225, 230, 240))
            d.ellipse((40, y + 6, 124, y + 90), fill=col); d.text((148, y + 8), name, font=f(34), fill=(20, 20, 20))
            d.text((148, y + 54), msg, font=f(26, False), fill=(120, 120, 125))
            if badge:
                bw = 30 + 18 * len(badge); _rr(d, (pw - 50 - bw, y + 34, pw - 50, y + 76), 21, (240, 60, 60)); d.text((pw - 50 - bw + 15, y + 38), badge, font=f(28), fill=(255, 255, 255))
        if tap - 0.25 < t < tap + 0.1:
            yy = 175 + 118 + 48; d.ellipse((300 - 34, yy - 34, 300 + 34, yy + 34), fill=(120, 120, 140, 90))
    else:
        d.rectangle((sx, 80, pw - sx, 160), fill=(255, 255, 255)); d.text((48, 100), "‹  小雯", font=f(40), fill=(20, 20, 20))
        d.rectangle((sx, 160, pw - sx, ph - sx), fill=(214, 226, 238))
        u = t - tap - 0.15
        _rr(d, (pw / 2 - 110, 190, pw / 2 + 110, 236), 22, (170, 185, 200)); d.text((pw / 2 - 86, 196), "上週四 21:03", font=f(28), fill=(255, 255, 255))
        rng = np.random.default_rng(4)
        for i in range(4):
            if u > 0.15 * i:
                x, y = 122 + (i % 2) * 196, 270 + (i // 2) * 250; _rr(d, (x, y, x + 184, y + 236), 14, (255, 253, 245))
                for k in range(9):
                    ly = y + 26 + k * 22; d.line((x + 18, ly, x + 18 + rng.integers(90, 150), ly), fill=(120, 120, 150), width=4)
                    if k % 3 == 1: d.line((x + 18, ly, x + 18 + rng.integers(60, 120), ly), fill=(255, 220, 60), width=10)
        if u > 0.8:
            d.ellipse((40, 790, 104, 854), fill=(255, 150, 180)); _rr(d, (122, 790, 520, 862), 30, (255, 255, 255))
            d.text((148, 806), "我就知道你會問。", font=f(36), fill=(20, 20, 20))
            d.text((122, 870), "21:03", font=f(22, False), fill=(110, 120, 130))
    bg.alpha_composite(ph_im, (px, py))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).rounded_rectangle((px - 30, py - 30, px + pw + 30, py + ph + 30), 80, fill=(150, 180, 255, 40))
    out = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)), bg)
    s = 1 + 0.06 * t / dur; cw, ch = W / s, H / s
    im = out.convert("RGB").crop(((W - cw) / 2, (H - ch) / 2 + 40 * t / dur, (W + cw) / 2, (H + ch) / 2 + 40 * t / dur)).resize((W, H), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255 * min(1, t / 0.12, (dur - t) / 0.12)


# ------------------------------------------------------------------ 角落小字（時間）
def corner_text(fr, text, t, dur, big=False):
    im = Image.fromarray((fr * 255).astype(np.uint8)).convert("RGBA"); lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    a = int(255 * ease(t / 0.3) * ease((dur - t) / 0.3)); f = ImageFont.truetype(JH, 64 if big else 52)
    d.text((70, 56), text, font=f, fill=(255, 255, 255, a), stroke_width=4, stroke_fill=(0, 0, 0, int(a * 0.7)))
    im.alpha_composite(lay); return np.asarray(im.convert("RGB"), np.float32) / 255


if __name__ == "__main__":
    import sys
    (HERE / "post").mkdir(exist_ok=True)
    Image.fromarray((calendar_frame(0.5, 1.5, "D-8", "D-7") * 255).astype(np.uint8)).save(HERE / "post/test_cal_mid.png")
    Image.fromarray((calendar_frame(1.2, 1.5, "D-1", "D-0", "段考當天") * 255).astype(np.uint8)).save(HERE / "post/test_cal_end.png")
    col = np.asarray(Image.open(HERE / "first/P1a.png").convert("RGB").resize((640, 1120)).crop((0, 20, 640, 1100)), np.float32) / 255
    Image.fromarray((namecard(col, 1.5, 2.6, "先知先覺") * 255).astype(np.uint8)).save(HERE / "post/test_nc_col.png")
    full = np.asarray(Image.open(HERE / "first/S20.png").convert("RGB").resize((W, H)), np.float32) / 255
    Image.fromarray((namecard(full, 1.6, 2.6, "昨天才出好題", seal="gold", cols=3, size=210) * 255).astype(np.uint8)).save(HERE / "post/test_nc_full.png")
    Image.fromarray((phone_frame(0.9, 4.2) * 255).astype(np.uint8)).save(HERE / "post/test_phone1.png")
    Image.fromarray((phone_frame(3.5, 4.2) * 255).astype(np.uint8)).save(HERE / "post/test_phone2.png")
    print("ok")
