"""〈D-7〉剪接：H3 片段＋三分割＋字卡＋名片＋手機畫面 → 配音、旁白、音效、配樂、字幕 → cut/D-7_v<N>_1080p.mp4（＋手機版）
  C:\\AI\\H3\\venv\\Scripts\\python.exe assemble.py [--ver 1] [--all] [--vsr] [S05 N2 ...（強制重做的段）]
分段快取 post/seg/*.mp4；音訊、字幕、合成每次重做。--vsr：16:9 的 H3 片段先用 RTX VSR 放大（否則 lanczos）。"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import post_fx as FX

HERE = Path(__file__).resolve().parent
W, H, FPS, SR = 1920, 1080, 24, 48000
POST = HERE / "post"; SEG = POST / "seg"; CUT = HERE / "cut"; VSRD = POST / "vsr"; LIB = HERE.parents[1] / "音效庫"
for d in (POST, SEG, CUT, VSRD): d.mkdir(exist_ok=True)
TL = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
VS = json.loads((HERE / "voice_state.json").read_text(encoding="utf-8"))
ver = int(sys.argv[sys.argv.index("--ver") + 1]) if "--ver" in sys.argv else 1
ALL = "--all" in sys.argv; USE_VSR = "--vsr" in sys.argv
force = {a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()}
SAY_LEAD = 0.2
CW, GAP = 634, 9                     # 三分割：每欄 634、間隔 9

# ------------------------------------------------------------------ 段落表
# kind: cal 字卡｜h3 片段｜split 三分割｜phone 手機｜four 三欄→四欄｜card 全畫面名片｜end 片尾
SEGS = [
    ("C1", "cal", dict(prev="D-8", label="D-7", dur=1.6)),
    ("S01", "h3", {}), ("S02", "h3", {}), ("S03", "h3", dict(trim=(0.3, 3.3))), ("S04", "h3", dict(trim=(0.2, 3.0))),
    ("N1", "split", dict(src=[("crop", "S04", 3.2, 0), ("crop", "S04", 3.2, 1), ("crop", "S04", 3.2, 2)], dur=3.0, entry="cut3",
                         state=["lit", "grey", "grey"], card=(0, "先知先覺", "eye", 0.55))),
    ("P1", "split", dict(src=[("port", "P1a", 0.3), ("port", "P1b", 0.3), ("port", "P1c", 0.3)], dur=5.6, entry="none",
                         state=["lit", "grey", "grey"])),
    ("C2", "cal", dict(prev="D-2", label="D-1", dur=1.6)),
    ("S05", "h3", {}), ("S06", "h3", dict(trim=(0.3, 2.8))),
    ("N2", "split", dict(src=[("port", "N2a", 0.3), ("port", "N2b", 0.3), ("port", "N2c", 0.3)], dur=3.0, entry="slide",
                         state=["lit", ("light", 0.35), "grey"], card=(1, "後知後覺", "time", 0.5))),
    ("S07", "h3", dict(trim=(0.3, 3.6), corner="22:00")), ("S08", "h3", dict(trim=(0.3, 3.0))),
    ("S09", "h3", dict(trim=(0.3, 3.4), corner="01:30")),
    ("S10", "phone", dict(dur=4.4)),
    ("S11", "h3", dict(trim=(0.3, 2.8))),
    ("P3", "split", dict(src=[("port", "P3a", 0.3), ("port", "P3b", 0.3), ("port", "P3c", 0.3)], dur=4.6, entry="slide",
                         state=["lit", "lit", "grey"])),
    ("C3", "cal", dict(prev="D-1", label="D-0", sub="段考當天", dur=1.8)),
    ("S12", "h3", dict(trim=(0.3, 4.2))), ("S13", "h3", dict(trim=(0.3, 4.0))), ("S14", "h3", {}),
    ("S15", "h3", dict(trim=(0.2, 2.6), title=True)), ("S16", "h3", {}),
    ("N3", "split", dict(src=[("port", "N3a", 0.3), ("port", "N3b", 0.3), ("port", "N3c", 0.3)], dur=3.0, entry="slide",
                         state=["lit", "lit", ("light", 0.35)], card=(2, "不知不覺", "soul", 0.5))),
    ("S17", "h3", {}), ("S19", "h3", dict(zoom=(1.65, 0.5, 0.33))),
    ("N4", "four", dict(dur=2.4)),
    ("S20", "h3", dict(trim=(0.0, 4.6), corner="D-1　02:47")),
    ("N5", "card", dict(dur=2.8, text="昨天才出好題")),
    ("S21", "h3", dict(tail=1.8)),
    ("END", "end", {}),
]
ORDER = [k for k, _, _ in SEGS]; KIND = {k: (t, o) for k, t, o in SEGS}
# 旁白（阿禾 VO）：段落 id、段內秒數；實際時間會自動往後推，避免與前一句重疊
VO = [("V01", "S04", 0.5), ("V02", "N1", 0.6), ("V03", "P1", 1.4), ("V04", "N2", 0.55), ("V05", "S07", 0.6), ("V06", "S09", 0.7),
      ("V07", "S11", 0.9), ("V08", "P3", 1.0), ("V09", "N3", 0.55), ("V10", "N4", 0.25)]


def sh(cmd): return subprocess.run(cmd, check=True, capture_output=True)
def probe(p): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)
def clip(k): return HERE / "h3" / k / "clip.mp4"


def frames(path, w, h, ss=0.0, n=None, crop=None):
    """讀片段成 uint8 陣列（n 格；不夠就重複最後一格）。crop：先縮放到 (sw, sh) 再裁 (x, y, w, h)。"""
    vf = f"scale={w}:{h}:flags=lanczos,fps={FPS}" if crop is None else f"scale={crop[0]}:{crop[1]}:flags=lanczos,fps={FPS},crop={w}:{h}:{crop[2]}:{crop[3]}"
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{ss:.3f}", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8); a = a[: len(a) // (w * h * 3) * w * h * 3].reshape(-1, h, w, 3)
    if n is not None:
        if len(a) == 0: a = np.zeros((1, h, w, 3), np.uint8)
        if len(a) < n: a = np.concatenate([a, np.repeat(a[-1:], n - len(a), 0)])
        a = a[:n]
    return a


class Enc:
    def __init__(self, out):
        self.p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                   "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    def put(self, fr): self.p.stdin.write((np.clip(fr, 0, 1) * 255).astype(np.uint8).tobytes() if fr.dtype != np.uint8 else fr.tobytes())
    def close(self): self.p.stdin.close(); self.p.wait()


# ------------------------------------------------------------------ h3 片段
def trim_of(k, o, L):
    if "trim" in o: ss, d = o["trim"]; return ss, min(d, L - ss)
    lines = TL[k]["lines"]
    ss = max(0.0, lines[0]["start"] - 0.55); end = min(L, lines[-1]["end"] + o.get("tail", 0.6))
    return ss, end - ss


def vsr_src(k):
    src = clip(k)
    if not USE_VSR: return src
    dst = VSRD / f"{k}.mp4"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        dst.unlink(missing_ok=True)
        sh([r"C:\AI\H3\venv\Scripts\python.exe", r"C:\AI\tools\upscale_vsr.py", "--source", str(src), "--output", str(dst)])
    return dst


TITLE_BOX = None


def title_layer(img_w, img_h):
    """S15：考卷抬頭方框裡寫「第一次段考　數學」（位置由首幀偵測，見 find_title_box）。"""
    x0, y0, x1, y1 = TITLE_BOX
    lay = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    f = ImageFont.truetype(FX.KAI, int((y1 - y0) * 0.52))
    t = "第一次段考　數學"; b = d.textbbox((0, 0), t, font=f)
    d.text(((x0 + x1) / 2 - (b[2] - b[0]) / 2 - b[0], (y0 + y1) / 2 - (b[3] - b[1]) / 2 - b[1]), t, font=f, fill=(30, 30, 38, 225), stroke_width=1, stroke_fill=(30, 30, 38, 120))
    return lay


def find_title_box():
    """在 S15 首幀找抬頭空白方框（紙上方最亮的一塊矩形）→ 1920x1080 座標。"""
    im = np.asarray(Image.open(HERE / "first/S15.png").convert("L").resize((W, H)), np.float32)
    bright = im > 200; rows = np.where(bright[:, 600:1400].mean(1) > 0.5)[0]
    top = rows.min() if len(rows) else 150
    band = bright[top: top + 200]; cols = np.where(band.mean(0) > 0.6)[0]
    x0, x1 = (cols.min(), cols.max()) if len(cols) else (680, 1240)
    return (x0 + 25, top + 25, x1 - 25, top + 115)


def render_h3(k, o, out):
    src = vsr_src(k); L = probe(src); ss, dur = trim_of(k, o, L); n = int(round(dur * FPS))
    if not any(x in o for x in ("corner", "title", "zoom")):
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}",
            "-an", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(out)]); return ss, dur
    fr = frames(src, W, H, ss, n); e = Enc(out)
    lay = title_layer(W, H) if o.get("title") else None
    for i, f in enumerate(fr):
        t = i / FPS; img = f.astype(np.float32) / 255
        if lay is not None:
            im = Image.fromarray(f).convert("RGBA"); im.alpha_composite(lay); img = np.asarray(im.convert("RGB"), np.float32) / 255
            s = 1 + 0.06 * t / dur; cw, ch = W / s, H / s
            img = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).crop(((W - cw) / 2, (H - ch) * 0.3, (W + cw) / 2, (H - ch) * 0.3 + ch)).resize((W, H), Image.BILINEAR), np.float32) / 255
        if "zoom" in o:
            z, cx, cy = o["zoom"]; cw, ch = W / z, H / z; x = min(W - cw, max(0, cx * W - cw / 2)); y = min(H - ch, max(0, cy * H - ch / 2))
            img = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS), np.float32) / 255
        if "corner" in o: img = FX.corner_text(img, o["corner"], t, min(dur, 2.4))
        e.put(img)
    e.close(); return ss, dur


# ------------------------------------------------------------------ 三分割
def col_frames(srcspec, n):
    if srcspec[0] == "crop":
        _, k, ss, i = srcspec; x = i * (CW + GAP)
        return frames(clip(k), CW, H, ss, n, crop=(W, H, x, 0))
    _, k, ss = srcspec                              # 直式 768x1344 → 634x1110 → 裁中間 1080（偏上，保留頭部）
    return frames(clip(k), CW, H, ss, n, crop=(CW, 1110, 0, 10))


def col_state(st, t):
    """回傳 (灰度 g, 亮度 k, 閃光 f)"""
    if st == "lit": return 0.0, 0.55, 0.0
    if st == "grey": return 1.0, 0.0, 0.0
    tl = st[1]; u = FX.ease((t - tl) / 0.35)
    return 1 - u, 0.55 * u, 0.45 * np.exp(-((t - tl - 0.12) / 0.12) ** 2)


def render_split(k, o, out):
    n = int(round(o["dur"] * FPS)); cols = [col_frames(s, n) for s in o["src"]]; e = Enc(out)
    full = frames(clip(o["src"][0][1]), W, H, o["src"][0][2], 1)[0].astype(np.float32) / 255 if o["entry"] == "cut3" else None
    prev = None
    if o["entry"] == "slide":                       # 欄位蓋在上一鏡最後一格（壓暗）上滑入，避免黑閃
        pk = SEG / f"{ORDER[ORDER.index(k) - 1]}.mp4"; prev = frames(pk, W, H, max(0, probe(pk) - 0.06), 1)[0].astype(np.float32) / 255
    LAST[k] = []
    for i in range(n):
        t = i / FPS
        can = prev * (1 - 0.6 * FX.ease(t / 0.3)) if prev is not None else np.zeros((H, W, 3), np.float32)
        if prev is not None and t > 0.5: can = np.zeros((H, W, 3), np.float32)
        for c in range(3):
            fr = cols[c][i].astype(np.float32) / 255
            g, kk, fl = col_state(o["state"][c], t)
            if o["entry"] == "cut3": g *= FX.ease((t - 0.15) / 0.45)        # 先是一整張畫面，再裂成三欄、兩欄褪灰
            fr = FX.grade_lit(FX.grade_grey(fr, g), kk) + fl
            if i == n - 1: LAST[k].append(np.clip(fr, 0, 1))
            card = o.get("card")
            if card and card[0] == c and t >= card[3]: fr = FX.namecard(fr, t - card[3], o["dur"] - card[3] + 0.05, card[1], seal=card[2])
            x = c * (CW + GAP); dy = 0
            if o["entry"] == "slide": dy = int((1 - FX.ease((t - c * 0.07) / 0.32)) * H * (1 if c % 2 else -1))
            ys, ye = max(0, dy), min(H, H + dy)
            if ye > ys: can[ys:ye, x:x + CW] = fr[ys - dy:ye - dy]
        if o["entry"] == "cut3" and t < 0.5:          # 裂開：從完整畫面開始，間隔由 0 長到 9
            u = FX.ease(t / 0.45); can2 = full.copy()
            for c in range(1, 3):
                x = c * (CW + GAP) - GAP; gw = int(round(GAP * u))
                can2[:, x + (GAP - gw) // 2: x + (GAP - gw) // 2 + gw] = 0
            mask = u; can = can * mask + can2 * (1 - mask)
        e.put(can)
    e.close()


LAST = {}


def render_four(k, o, out):
    """N3 的三欄縮成四欄、第四欄（S20 首幀，暖亮）從右邊擠進來；接著第四欄展開成全畫面。"""
    n = int(round(o["dur"] * FPS)); e = Enc(out)
    if "N3" not in LAST: LAST["N3"] = [f.astype(np.float32) / 255 for f in [frames(SEG / "N3.mp4", W, H, max(0, probe(SEG / "N3.mp4") - 0.05), 1)[0][:, c * (CW + GAP):c * (CW + GAP) + CW] for c in range(3)]]
    s20 = frames(clip("S20"), W, H, 0.0, 1)[0].astype(np.float32) / 255; s20 = FX.grade_lit(s20, 0.3)
    old = LAST["N3"]; w4, g4 = 474, 8
    for i in range(n):
        t = i / FPS; can = np.zeros((H, W, 3), np.float32)
        a = FX.ease((t - 0.1) / 0.55); b = FX.ease((t - 1.15) / 0.75)
        cw = int(CW + (w4 - CW) * a); gap = GAP + (g4 - GAP) * a
        x4b = int((W - w4) * (1 - b)); shift = (x4b - 3 * (w4 + g4)) - 0 if b > 0 else 0
        for c in range(3):
            x = int(c * (cw + gap) + shift); src = old[c]; off = (CW - cw) // 2
            seg = src[:, off:off + cw] * (1 - 0.35 * a)
            xs, xe = max(0, x), min(W, x + cw)
            if xe > xs: can[:, xs:xe] = seg[:, xs - x:xe - x]
        w = int(w4 + (W - w4) * b); x4 = int(W - a * w4) if b == 0 else x4b
        cx = (W - w) // 2; strip = s20[:, cx:cx + w]
        xs, xe = max(0, x4), min(W, x4 + w)
        if xe > xs: can[:, xs:xe] = strip[:, xs - x4:xe - x4]
        e.put(can)
    e.close()


def render_card(k, o, out):
    base = frames(clip("S20"), W, H, max(0, probe(clip("S20")) - 0.1), 1)[0].astype(np.float32) / 255
    n = int(round(o["dur"] * FPS)); e = Enc(out)
    for i in range(n): e.put(FX.namecard(base * 0.85, i / FPS, o["dur"], o["text"], seal="gold", cols=3, size=210))
    e.close()


def render_cal(k, o, out):
    n = int(round(o["dur"] * FPS)); e = Enc(out)
    for i in range(n): e.put(FX.calendar_frame(i / FPS, o["dur"], o["prev"], o["label"], o.get("sub", "")))
    e.close()


def render_phone(k, o, out):
    n = int(round(o["dur"] * FPS)); e = Enc(out)
    for i in range(n): e.put(FX.phone_frame(i / FPS, o["dur"]))
    e.close()


TRIMS = {}
TRIMS_F = POST / "trims.json"
if TRIMS_F.exists(): TRIMS.update({k: tuple(v) for k, v in json.loads(TRIMS_F.read_text(encoding="utf-8")).items()})


def render(k):
    kind, o = KIND[k]; out = SEG / f"{k}.mp4"
    if kind == "end": return HERE / "ending" / "ending.mp4"
    if out.exists() and not ALL and k not in force: return out
    if kind == "h3": TRIMS[k] = render_h3(k, o, out)
    elif kind == "split": render_split(k, o, out)
    elif kind == "four": render_four(k, o, out)
    elif kind == "card": render_card(k, o, out)
    elif kind == "cal": render_cal(k, o, out)
    elif kind == "phone": render_phone(k, o, out)
    return out


# ------------------------------------------------------------------ 音訊
def rd(p, sr=SR):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-ar", str(sr), "-ac", "1", "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()
def noise(d, seed=1): return np.random.default_rng(seed).standard_normal(int(d * SR)).astype(np.float32)
def lp(x, k): return np.convolve(x, np.ones(k, np.float32) / k, "same")
def hp(x, k=200): return x - lp(x, k)
def tone(f, d, amp=1.0, decay=3.0):
    t = np.arange(int(d * SR)) / SR; return (np.sin(2 * np.pi * f * t) * np.exp(-decay * t) * amp).astype(np.float32)
def put(buf, x, t):
    s = int(t * SR)
    if s < 0: x = x[-s:]; s = 0
    if s >= len(buf): return
    e = min(len(buf), s + len(x)); buf[s:e] += x[:e - s]
def boom(a=0.5):
    x = tone(65, 1.4, a, 3.0); nz = lp(noise(0.4, 3), 6) * np.exp(-7 * np.arange(int(0.4 * SR)) / SR).astype(np.float32) * a
    x[:len(nz)] += nz; return x
def whoosh(d, amp=0.3, seed=5):
    n = lp(noise(d, seed), 40) * 6; t = np.linspace(0, 1, len(n)); return (n * np.sin(np.pi * t) ** 2 * amp).astype(np.float32)
def shimmer(d, amp=0.06, seed=9):
    t = np.arange(int(d * SR)) / SR; r = np.random.default_rng(seed); x = np.zeros_like(t, dtype=np.float32)
    for f in r.uniform(2200, 5200, 12): x += np.sin(2 * np.pi * f * t + r.uniform(0, 6)) * (0.5 + 0.5 * np.sin(2 * np.pi * r.uniform(0.5, 3) * t))
    return (x / 12 * amp * np.sin(np.pi * t / d) ** 2).astype(np.float32)
def chime(amp=0.2): return tone(1568, 1.4, amp, 3) + tone(2349, 1.4, amp * 0.6, 4) + tone(3136, 1.4, amp * 0.3, 6)
def click(): return tone(1800, 0.04, 0.35, 90) + lp(noise(0.04, 77), 3) * 0.08
def roomtone(d, seed=41, amp=0.010):
    n = noise(d, seed); return (lp(hp(n, 40), 8) * amp + hp(lp(noise(d, seed + 1), 30), 120) * amp * 0.4).astype(np.float32)
def lib(rel, ss=0.0, dur=None, gain=1.0):
    p = LIB / rel; x = rd(p); x = x[int(ss * SR):]; x = x[:int(dur * SR)] if dur else x
    if len(x): x = x / (np.abs(x).max() + 1e-9) * gain
    return x
def native(k, ss=None, dur=None):
    x = rd(clip(k)); s0 = TRIMS[k][0] if ss is None else ss; d = TRIMS[k][1] if dur is None else dur
    return x[int(s0 * SR): int((s0 + d) * SR)]
def bed_from(x, d, fade=0.25):
    """把一段環境音延長成 d 秒（交叉淡化循環）。"""
    if len(x) == 0: return np.zeros(int(d * SR), np.float32)
    out = x.copy(); cf = int(min(0.6, len(x) / SR / 3) * SR)
    while len(out) < d * SR:
        f = np.linspace(0, 1, cf, dtype=np.float32); out = np.concatenate([out[:-cf], out[-cf:] * (1 - f) + x[:cf] * f, x[cf:]])
    out = out[:int(d * SR)].copy(); k = int(fade * SR)
    if k: out[:k] *= np.linspace(0, 1, k); out[-k:] *= np.linspace(1, 0, k)
    return out


def vo_times(S):
    out, last = {}, -9
    for lid, seg, off in VO:
        t = max(S[seg] + off, last + 0.3); out[lid] = t; last = t + VS[lid]["dur"]
    return out


def build_audio(S, total, VT):
    buf = np.zeros(int((total + 1) * SR), np.float32)
    seg = lambda k: (S[k], S[k + "_end"])
    rec = native("S04", 0.0, probe(clip("S04")))           # 下課吵雜：S04 的 H3 原生環境音
    rec = rec / (np.sqrt((rec ** 2).mean()) + 1e-9) * 0.035
    exam = native("S15", 0.0, probe(clip("S15"))); exam = exam / (np.sqrt((exam ** 2).mean()) + 1e-9) * 0.035
    a, _ = seg("S01"); b = S["N1_end"]; put(buf, bed_from(rec, b - a + 0.3), a)
    a, b = S["S05"], S["N2_end"]; put(buf, bed_from(rec, b - a, 0.4) * 0.5, a)
    for k in ("P1", "S07", "S09", "S10", "S11", "P3"): a, b = seg(k); put(buf, roomtone(b - a, 50 + ORDER.index(k)), a)
    a, b = S["S12"], S["S14_end"]; put(buf, roomtone(b - a, 61, 0.008), a)
    a, b = S["S15"], S["S21_end"]; put(buf, bed_from(exam, b - a, 0.5), a)
    for k in ("S08", "S20"):                                   # 原生音效（螢光筆、印表機＋哈欠）
        x = native(k); x = x / (np.abs(x).max() + 1e-9) * (0.35 if k == "S08" else 0.5); put(buf, x, S[k])
    for k in ("C1", "C2", "C3"):
        put(buf, lib("翻頁/page_turn_144110.mp3", gain=0.5), S[k] + 0.2); put(buf, whoosh(0.5, 0.06, 3), S[k] + 0.25)
    for k, t0 in (("N1", 0.55), ("N2", 0.5), ("N3", 0.5)):
        put(buf, boom(0.42), S[k] + t0 + 0.05); put(buf, shimmer(2.2, 0.05, ORDER.index(k)), S[k] + t0); put(buf, chime(0.12), S[k] + t0 + 1.3)
    for k, tl in (("N2", 0.35), ("N3", 0.35)): put(buf, whoosh(0.4, 0.12, 7), S[k] + tl - 0.1)
    put(buf, whoosh(0.5, 0.1, 8), S["N1"] + 0.05)
    for k in ("N2", "N3", "P3"): put(buf, whoosh(0.45, 0.08, 9), S[k])
    put(buf, click(), S["S10"] + 1.3); put(buf, click() * 0.7, S["S10"] + 2.3)
    put(buf, lib("翻頁/page_turn_860360.mp3", gain=0.3), S["S13"] + 2.4)
    put(buf, lib("翻頁/page_flip_683706.mp3", 0.0, 1.0, 0.25), S["S14"] + 0.4)
    put(buf, whoosh(1.0, 0.14, 11), S["N4"] + 0.1); put(buf, whoosh(0.9, 0.16, 12), S["N4"] + 1.15)
    put(buf, boom(0.5), S["N5"] + 0.4); put(buf, shimmer(2.4, 0.06, 13), S["N5"] + 0.3); put(buf, chime(0.15), S["N5"] + 1.4)
    mb = POST / "music_bed.wav"
    if mb.exists():
        mm = rd(mb); n_ = min(len(mm), len(buf)); buf[:n_] += mm[:n_] * 0.85
    buf *= 0.6
    for k in ORDER:                                           # 畫面內台詞
        if KIND[k][0] != "h3": continue
        for l in TL.get(k, {}).get("lines", []):
            x = rd(HERE / "voice" / f"{l['id']}.wav"); x = np.clip(x * (0.16 / np.sqrt((x ** 2).mean() + 1e-9)), -0.9, 0.9)
            st = S[k] + l["start"] - TRIMS[k][0] - SAY_LEAD; s0 = int((st - 0.1) * SR)
            if s0 >= 0:                                       # 台詞時背景壓低（含淡入淡出，避免突兀）
                L_ = len(x) + int(0.4 * SR); env = np.full(L_, 0.3, np.float32); r_ = int(0.08 * SR)
                env[:r_] = np.linspace(1, 0.3, r_); env[-r_:] = np.linspace(0.3, 1, r_); buf[s0:s0 + L_] *= env[:len(buf[s0:s0 + L_])]
            put(buf, x, st)
    for lid, t in VT.items():                                 # 旁白
        x = rd(HERE / "voice" / f"{lid}.wav"); x = np.clip(x * (0.15 / np.sqrt((x ** 2).mean() + 1e-9)), -0.9, 0.9)
        s0 = int((t - 0.1) * SR); buf[s0:s0 + len(x) + int(0.3 * SR)] *= 0.62; put(buf, x, t)
    buf[int((total - 2.0) * SR):int(total * SR)] *= np.linspace(1, 0, int(2.0 * SR))
    rms = np.sqrt((buf[buf != 0] ** 2).mean()); buf = buf * min(4.0, 0.085 / max(rms, 1e-6)); buf = buf / max(1.0, np.abs(buf).max() / 0.84)
    raw = POST / "audio_raw.wav"; out = POST / "audio.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(np.stack([buf, buf], 1), -1, 1) * 32767).astype(np.int16).tobytes())
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", "loudnorm=I=-15.5:TP=-1.5:LRA=11", "-ar", str(SR), str(POST / "audio_ln.wav")])
    r = subprocess.run(["ffmpeg", "-i", str(POST / "audio_ln.wav"), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    import re as _re
    m = _re.findall(r"I:\s*(-?[\d.]+) LUFS", r.stderr); gain = -15.5 - float(m[-1]) if m else 0.0      # 第二段：補到 -15.5
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(POST / "audio_ln.wav"), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.72:level=false", "-ar", str(SR), str(out)])
    print("loudness gain", round(gain, 2), flush=True)
    return out


# ------------------------------------------------------------------ 字幕＋合成
SUBCOL = {"shb": (170, 215, 255), "xw": (255, 196, 215), "afu": (255, 232, 130), "ahe": (205, 245, 205)}
FONT_SUB = "C:/Windows/Fonts/msjhbd.ttc"


def cap_sprite(text, color):
    f = ImageFont.truetype(FONT_SUB, 46); b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=f, stroke_width=5)
    im = Image.new("RGBA", (b[2] - b[0] + 20, b[3] - b[1] + 20), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10 - b[0], 10 - b[1]), text, font=f, fill=color + (255,), stroke_width=5, stroke_fill=(0, 0, 0, 220))
    return im


def split_caps(text):
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in "。？！": out.append(cur); cur = ""
    if cur: out.append(cur)
    return [p for p in out if p.strip("。？！…")] or [text]


def captions(S, VT):
    items = []
    for k in ORDER:
        if KIND[k][0] != "h3": continue
        for l in TL.get(k, {}).get("lines", []):
            items.append((S[k] + l["start"] - TRIMS[k][0] - SAY_LEAD, l["end"] - l["start"], l["text"], l["speaker"]))
    for lid, t in VT.items(): items.append((t, VS[lid]["dur"], VS[lid]["text"], "ahe"))
    caps = []
    for st, d, text, spk in sorted(items):
        parts = split_caps(text); tot = sum(len(p) for p in parts); c = st
        for p in parts:
            dd = d * len(p) / tot; caps.append((c, c + dd + 0.12, cap_sprite(p.rstrip("。"), SUBCOL[spk]), p)); c += dd
    for i in range(len(caps) - 1):                       # 不重疊：前一句提早收
        if caps[i][1] > caps[i + 1][0] - 0.04: caps[i] = (caps[i][0], caps[i + 1][0] - 0.04, caps[i][2], caps[i][3])
    return caps


def final(S, total, audio, caps):
    lst = POST / "concat.txt"; lst.write_text("".join(f"file '{render(k).as_posix()}'\n" for k in ORDER), encoding="utf-8")
    joined = POST / "joined.mp4"; sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    out = CUT / f"D-7_v{ver}_1080p.mp4"
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(joined), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    e = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
                          "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
                         stdin=subprocess.PIPE)
    i = 0
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3: break
        t = i / FPS; fr = None
        for (t0, t1, spr, _) in caps:
            if t0 <= t <= t1:
                if fr is None: fr = Image.fromarray(np.frombuffer(b, np.uint8).reshape(H, W, 3)).convert("RGBA")
                a = min(1, (t - t0) / 0.1, (t1 - t) / 0.1); s = spr.copy(); s.putalpha(s.getchannel("A").point(lambda v: int(v * a)))
                fr.alpha_composite(s, (int(W / 2 - s.width / 2), int(H * 0.9 - s.height / 2)))
        e.stdin.write(b if fr is None else np.asarray(fr.convert("RGB")).tobytes()); i += 1
    p.wait(); e.stdin.close(); e.wait()
    return out


if __name__ == "__main__":
    TITLE_BOX = (716, 170, 1212, 266)          # S15 考卷抬頭方框（1920x1080，從 H3 片段 0.5 秒量出）
    for k in ORDER:
        render(k); print("seg", k, TRIMS.get(k), flush=True)
    TRIMS_F.write_text(json.dumps(TRIMS, indent=1), encoding="utf-8")
    S, t = {}, 0.0
    for k in ORDER:
        S[k] = t; t += probe(render(k)); S[k + "_end"] = t
    print("total", round(t, 1), flush=True)
    VT = vo_times(S)
    (POST / "starts.json").write_text(json.dumps(dict(S, _total=t, _vo=VT), indent=1), encoding="utf-8")
    caps = captions(S, VT)
    (POST / "captions.json").write_text(json.dumps([(a, b, txt) for a, b, _, txt in caps], ensure_ascii=False, indent=1), encoding="utf-8")
    out = final(S, t, build_audio(S, t, VT), caps); print("wrote", out, flush=True)
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "27", "-c:a", "aac", "-b:a", "96k",
        str(CUT / f"D-7_v{ver}_手機版720p.mp4")])
    print("DONE", flush=True)
