"""饒舌對決的字卡與逐格特效（make_battle.py 的 cut／srt 階段用）。
字卡：片名、VS、講白字卡（battle.json 的 cards）、人物直排名牌（intro_card）、投票片尾卡；臉部偵測避開臉。
特效（逐格 ffmpeg 讀入 → numpy／PIL → ffmpeg 寫出）：
- 字幕：整句出現，韻腳字用己方顏色；唱到韻腳字時從 1.8 倍砸下來＋閃白發光。說話者色塊、左上 ROUND 角標。
- 攻擊：押回去的那句最後一個韻腳字，從唱的人那側射出月牙斬，飛到對手那側爆開（震動＋放大＋色差）；近景／插入鏡不畫飛行、只在下緣角落爆開（不掃臉）。
- COMBO：押韻！／雙押！／三押！；兩人的最後一句＝殺招！
- 長演唱鏡在鏡內每句開頭交替推近 1.18 倍（以臉為中心）；只在切進 flash_scenes 的閃回時閃白；片尾 DJ 三拍大字。
字型：tools/fonts.py 的粗黑體（Windows 微軟正黑體／Linux Noto Sans CJK）；想用源石黑體等字型，設環境變數 FONT_JHBD。"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 24
SUB_Y = 935
INK, GOLD = (246, 244, 236), (255, 206, 96)
CLOSE = ("ECU", "CU", "MCU")
PUNCH = 1.18
import os as _os
_CFG0 = json.loads((HERE / "battle.json").read_text(encoding="utf-8")) if (HERE / "battle.json").exists() else {}
LANG = _CFG0.get("lang", "zh")
SUBS = _os.environ.get("SUBS", "bi")                      # 英文對決：bi＝英文大字＋中文小字｜en＝只有英文


def _fonts(cfg):
    sys.path.insert(0, str((HERE / cfg.get("repo_dir", "../..")).resolve() / "tools"))
    from fonts import font
    return font("jhbd"), font("kai")


def font(size, cfg=None, kind=0):
    global _FP
    try:
        _FP
    except NameError:
        _FP = _fonts(cfg or {})
    return ImageFont.truetype(_FP[kind], size)


def colors(cfg):
    src = {"A": cfg["rappers"]["A"], "B": cfg["rappers"]["B"], "J": cfg["dj"]}
    col = {k: tuple(v.get("color", GOLD)) for k, v in src.items()}
    glow = {k: tuple(v.get("glow") or [min(255, c + 60) for c in col[k]]) for k, v in src.items()}
    return col, glow


# ------------------------------------------------------------------------------------------------ 字卡
def _panel(w, h, accent):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(g).rounded_rectangle([6, 6, w - 7, h - 7], radius=16, outline=accent + (255,), width=8)
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, w - 9, h - 9], radius=14, fill=(10, 10, 18, 218))
    d.rounded_rectangle([8, 8, w - 9, h - 9], radius=14, outline=accent + (255,), width=3)
    d.rounded_rectangle([18, 18, w - 19, h - 19], radius=9, outline=GOLD + (150,), width=1)
    return im, d


def _t(d, xy, s, f, fill=INK, anchor="la"):
    d.text(xy, s, font=f, fill=fill + (255,), anchor=anchor, stroke_width=3, stroke_fill=(8, 8, 16, 255))


def _save(im, out):
    sh = Image.new("RGBA", (im.width + 16, im.height + 16), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (10, 12), im.split()[3].point(lambda v: v * 0.5))
    sh = sh.filter(ImageFilter.GaussianBlur(6)); sh.alpha_composite(im, (0, 0))
    sh.save(out); return out, sh.size


def text_card(lines, out, accent, size=46):
    fs = [font(size)] + [font(int(size * 0.78))] * (len(lines) - 1)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = int(max(tmp.textlength(t, font=f) for (t, _), f in zip(lines, fs)) + 100)
    h = int(size * 1.5 + (len(lines) - 1) * size * 1.15 + 64)
    im, d = _panel(w, h, accent)
    y = 36
    for i, ((t, c), f) in enumerate(zip(lines, fs)):
        _t(d, (w / 2, y), t, f, c, "ma"); y += size * 1.5 if i == 0 else size * 1.15
    return _save(im, out)


def name_card(columns, out, accent, pad=40, gap=26):
    """直排人物名牌（第一欄在最右）：楷書金字＋深色底＋己方顏色框。columns＝[[文字, 字級], …]。"""
    cols = []
    for text, size in columns:
        f = font(size, kind=1); step = int(size * 1.08)
        m = Image.new("L", (int(size * 1.3), step * len(text) + int(size * 0.3)), 0); dm = ImageDraw.Draw(m)
        for i, ch in enumerate(text):
            dm.text((m.width / 2, step * i + step / 2), ch, font=f, fill=255, anchor="mm")
        c = Image.new("RGBA", m.size, (0, 0, 0, 0))
        c.paste(Image.new("RGBA", m.size, (0, 0, 0, 200)), (4, 5), m.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(5)))
        c.paste(Image.new("RGBA", m.size, (40, 20, 6, 255)), (0, 0), m.filter(ImageFilter.MaxFilter(5)))
        grad = Image.linear_gradient("L").resize(m.size)
        gold = Image.merge("RGBA", [grad.point(lambda v: 255 - v // 6), grad.point(lambda v: 214 - v // 4), grad.point(lambda v: 110 - v // 3),
                                    Image.new("L", m.size, 255)])
        c.paste(gold, (0, 0), m); cols.append(c)
    w = sum(c.width for c in cols) + gap * (len(cols) - 1) + pad * 2; h = max(c.height for c in cols) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=16, fill=(10, 12, 24, 205))
    d.rounded_rectangle([6, 6, w - 7, h - 7], radius=12, outline=accent + (240,), width=3)
    d.rounded_rectangle([13, 13, w - 14, h - 14], radius=8, outline=GOLD + (200,), width=1)
    x = w - pad
    for c in cols:
        x -= c.width; im.alpha_composite(c, (x, pad)); x -= gap
    return _save(im, out)


def card(cfg, key, out):
    font(10, cfg)
    R, DJ = cfg["rappers"], cfg["dj"]
    col, _ = colors(cfg)
    acc = lambda a: {"A": col["A"], "B": col["B"], "J": col["J"], "ink": INK, "gold": GOLD}.get(a, GOLD)
    if key == "title":
        en = cfg.get("title_en")
        w, h = 1180, (380 if en else 300); im, d = _panel(w, h, GOLD)
        _t(d, (w / 2, 34), cfg["title"], font(112), GOLD, "ma")
        y = 196
        if en:
            _t(d, (w / 2, 172), en, font(62), INK, "ma"); y = 276
        _t(d, (w / 2 - 44, y), R["A"]["name"], font(56), col["A"], "ra")
        _t(d, (w / 2, y), "vs", font(56), INK, "ma")
        _t(d, (w / 2 + 44, y), R["B"]["name"], font(56), col["B"], "la")
        return _save(im, out)
    if key == "vs":
        w, h = 1560, 150; im, d = _panel(w, h, GOLD)
        _t(d, (40, 36), f"{R['A'].get('team', '紅方')}｜{R['A']['name']}", font(46), col["A"])
        _t(d, (40, 98), R["A"].get("tagline", ""), font(28), INK)
        _t(d, (w - 40, 36), f"{R['B'].get('team', '藍方')}｜{R['B']['name']}", font(46), col["B"], "ra")
        _t(d, (w - 40, 98), R["B"].get("tagline", ""), font(28), INK, "ra")
        _t(d, (w / 2, h / 2), "VS", font(70), GOLD, "mm")
        return _save(im, out)
    if key == "end_vote":
        v = cfg.get("vote", {})
        w, h = 1300, 310; im, d = _panel(w, h, GOLD)
        _t(d, (w / 2, 30), v.get("title", "留言投票！"), font(64), GOLD, "ma")
        _t(d, (w / 2 - 30, 130), v.get("A", f"挺{R['A']['name']}打 1"), font(44), col["A"], "ra")
        _t(d, (w / 2 + 30, 130), v.get("B", f"挺{R['B']['name']}打 2"), font(44), col["B"], "la")
        _t(d, (w / 2, 204), v.get("sub", "下一場想看誰對決？也寫在留言！"), font(34), INK, "ma")
        _t(d, (w / 2, 262), v.get("note", "歌詞為饒舌對決的誇飾，史實見字卡與說明欄｜本片影像與聲音由 AI 生成"), font(24), (200, 196, 186), "ma")
        return _save(im, out)
    if key in ("A", "B", "K"):
        c = R[key] if key in R else DJ
        return name_card(c["intro_card"], out, col["J" if key == "K" else key])
    c = cfg["cards"][key]
    if c.get("image"):                                       # 自己畫好的圖解卡（精準的數學圖、表格）：直接用 PNG
        im = Image.open((HERE / c["image"]).resolve()).convert("RGBA"); im.save(out); return out, im.size
    return text_card([(t, acc(a)) for t, a in c["lines"]], out, acc(c.get("accent", "J")), c.get("size", 46))


# ------------------------------------------------------------------------------------------------ 臉
_DET = {}


def faces(frame_bgr):
    """臉框 [(x, y, w, h)]：YuNet 模型（AI_ROOT/tools/models/face_detection_yunet_2023mar.onnx，沒有就從 OpenCV 官方 opencv_zoo 下載，約 230 KB）；
    下載不到才用 OpenCV 內建 Haar（OpenCV 5 已拿掉 Haar → 回傳空的，字卡只是不避臉。2026-10-29 Colab 實測）。"""
    import os
    import urllib.request
    import cv2
    h, w = frame_bgr.shape[:2]
    yn = Path(os.environ.get("AI_ROOT", r"C:\AI")) / "tools" / "models" / "face_detection_yunet_2023mar.onnx"
    if not yn.exists() and "yunet_tried" not in _DET:
        _DET["yunet_tried"] = True
        try:
            yn.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
                                       "face_detection_yunet_2023mar.onnx", str(yn))
        except Exception as e:
            print("（YuNet 下載失敗：", e, "）", flush=True)
    if yn.exists():
        det = _DET.get((w, h)) or cv2.FaceDetectorYN.create(str(yn), "", (w, h), 0.6); _DET[(w, h)] = det
        _, res = det.detect(frame_bgr)
        return [tuple(int(v) for v in r[:4]) for r in (res if res is not None else [])]
    if not hasattr(cv2, "CascadeClassifier"):
        return []
    hc = _DET.get("haar") or cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"); _DET["haar"] = hc
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return [tuple(int(v) for v in r) for r in hc.detectMultiScale(g, 1.1, 5, minSize=(60, 60))]


def seg_faces(p):
    import cv2
    boxes = []; cap = cv2.VideoCapture(str(p)); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for j in (int(n * 0.15), n // 2, int(n * 0.85)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, j); ok, fr = cap.read()
        if ok:
            boxes += faces(fr)
    cap.release()
    return boxes


def place(size, face_boxes, sub_top=900, margin=40):
    """字卡位置：先試右上、左上、左中、右中、左下、右下，避開臉（臉框放大 25%）、字幕區與左上 ROUND 角標。"""
    w, h = size; top_l = 150
    cands = [(W - w - margin, 60), (margin, top_l), (margin, max(top_l, (sub_top - h) // 2)), (W - w - margin, (sub_top - h) // 2),
             (margin, sub_top - h - 20), (W - w - margin, sub_top - h - 20), ((W - w) // 2, 60)]
    boxes = [(x - 0.25 * fw, y - 0.25 * fh, x + 1.25 * fw, y + 1.25 * fh) for x, y, fw, fh in face_boxes if fw > 40]

    def overlap(px, py):
        return sum(max(0, min(px + w, b[2]) - max(px, b[0])) * max(0, min(py + h, b[3]) - max(py, b[1])) for b in boxes)
    ok = [c for c in cands if c[1] >= 0 and c[1] + h <= sub_top and overlap(*c) == 0]
    return ok[0] if ok else min(cands, key=lambda c: overlap(*c))


# ------------------------------------------------------------------------------------------------ 事件
def char_times(line):
    """每個字的開口時間：強制對齊的詞時間平均分給詞裡的字。"""
    out = []
    for w in line["words"]:
        cs = [c for c in w["w"] if c.strip() and c not in "，。！？、 "]
        if cs:
            d = (w["e"] - w["s"]) / len(cs); out += [(c, w["s"] + i * d) for i, c in enumerate(cs)]
    return out


def build_events(cfg, tl):
    """字幕句、攻擊、片尾三拍大字。攻擊＝每位饒舌手第 2、4、6…句（押回去的那句；或歌詞那句寫 "atk": true/false）＋最後一句＝殺招。"""
    lines, attacks = [], []
    en = LANG == "en"
    nz = lambda w: re.sub(r"[^a-z]", "", w.lower().replace("\u00e9", "e"))
    for who in ("A", "B"):
        L = tl[who]
        for i, l in enumerate(L):
            rh = l.get("rhyme", "")
            if en:                                           # 英文：韻腳＝一個字，用對齊的最後一個相同的字的開口時間
                ws = [w for w in l["words"] if rh and nz(w["w"]) == nz(rh.split()[-1])]
                hits = [ws[-1]["s"]] if ws else []
            else:
                ct = char_times(l); seq = "".join(c for c, _ in ct)
                k = seq.rfind(rh) if rh else -1
                hits = [ct[k + j][1] for j in range(len(rh))] if k >= 0 else []
            lines.append(dict(who=who, text=l["show"], zh=l.get("zh", ""), start=l.get("show_start", l["start"]) - 0.05, end=l["end"] + 0.25,
                              rh=l.get("rhyme_show", rh), hits=hits, words=l["words"]))
            atk = l.get("atk")
            atk = (i % 2 == 1) if atk is None else atk
            if (atk or i == len(L) - 1) and hits:
                attacks.append(dict(who=who, t=hits[-1], n="kill" if i == len(L) - 1 else (l.get("combo", 1) if en else len(rh)),
                                    until=L[i + 1]["start"] if i + 1 < len(L) and L[i + 1].get("atk") is False else 1e9))   # 下一句是「收」的段落：押韻字不留到那句
    pos, text = tl["dj"]["pos"], tl["dj"]["text"]
    for key, (a, b) in pos.items():
        if key == "end":
            continue
        mf = HERE / "out" / "voice" / "ming" / f"dj_{key}.json"
        if en and mf.exists():                               # 英文 DJ：每句的實際起訖（ming_en.py 接句子時記下的）
            ms = json.loads(mf.read_text(encoding="utf-8"))
            k_n = min([(b0, k2) for k2, (b0, _) in pos.items() if b0 > a], default=(1e9, None))
            nxt = k_n[0]                                     # 下一段 DJ 口白（含片尾 end：它沒有字幕行，不會自動截短）
            cut = min([nxt + s["at"][2] for s in cfg["shots"] if isinstance(s["at"], list) and s["at"][:2] == ["dj", k_n[1]]] + [nxt])
            # 審核回饋 #3：收尾遠景 E01 排在片尾口白前 0.4 秒切進來 → 字幕要在「畫面切鏡」前消失，不是在口白前（以前只看口白，疊了 4 格）
            for j, m in enumerate(ms):                       # 每段最後一句多留 1.2 秒（結論句「Can you prove it?」只有 0.6 秒），但不跨進下一段口白
                lines.append(dict(who="J", text=m["en"], zh=m["zh"], start=a + m["start"] - 0.05,
                                  end=min(a + m["end"] + (1.2 if j == len(ms) - 1 else 0.15), nxt - 0.25, cut - 0.08), rh="", hits=[]))
            continue
        parts = []                                           # DJ 長句照標點拆段，太長再照逗號拆（字才不會縮小，〈向日葵之戰〉使用者看不清）
        for x in re.findall(r"[^！？。；：]+[！？。；：]?", text[key]):
            cur = ""
            for y in re.findall(r"[^，]+，?", x):
                if cur and len(cur) + len(y) > 17:
                    parts.append(cur); cur = ""
                cur += y
            if cur.strip():
                parts.append(cur)
        n_all = sum(len(x) for x in parts); t0 = a
        af = HERE / "out" / "voice" / "ming" / "dj_align.json"; times = None
        if af.exists():                                      # 有逐字對齊（換了口白檔要重跑）就照實際念到的字出字幕
            drop = "，。！？；：、《》「」 "; times = []
            for w, st, en_ in json.loads(af.read_text(encoding="utf-8")).get(key, []):
                cs = [c for c in w if c not in drop]
                times += [(max(st, 0) + (en_ - st) * j / max(1, len(cs)), en_) for j in range(len(cs))]
            if len(times) != sum(1 for x in parts for c in x if c not in drop):
                times = None
        k = 0
        for x in parts:
            if times:
                m = sum(1 for c in x if c not in drop); t0, t1 = a + times[k][0], a + times[k + m - 1][1]; k += m
            else:
                t1 = t0 + (b - a) * len(x) / n_all
            lines.append(dict(who="J", text=x, start=t0 - 0.05, end=t1 + 0.1, rh="", hits=[])); t0 = t1
    beats3 = []
    if "end" in pos:
        a, b = pos["end"]; words = cfg["dj"].get("end_beats") or [text["end"]]
        n_all = sum(len(w) for w in words); acc = 0
        for i, w in enumerate(words):
            beats3.append(dict(text=w, t=a + (b - a) * acc / n_all, row=i)); acc += len(w)
    lines.sort(key=lambda l: l["start"])                    # 前後句重疊 → 每句最晚在下一句開始前消失
    for x, y in zip(lines, lines[1:]):
        x["end"] = min(x["end"], y["start"] - 0.04)
    return {"lines": lines, "attacks": attacks, "beats3": beats3}


# ------------------------------------------------------------------------------------------------ 逐格特效
def render_sub(text, rh, who, lit, pops, now, col, glow):
    size = 66
    while font(size).getlength(text) > 1560 and size > 40:
        size -= 2
    f = font(size); pos = text.rfind(rh) if rh else -1
    cw = [f.getlength(c) for c in text]
    im = Image.new("RGBA", (int(sum(cw)) + 160, 220), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x, base = 60, 80
    for i, c in enumerate(text):
        j = i - pos if pos >= 0 else -1
        if 0 <= j < len(rh):
            cc = col[who] if j < lit else (255, 255, 255)
            k = (now - (pops[j] if j < len(pops) else 1e9)) * FPS
            sc = 1.0 + 0.8 * max(0.0, 1 - k / 6) if 0 <= k < 6 else 1.0
            fs = font(int(size * sc)); dy = -int((sc - 1) * 40)
            if 0 <= k < 4:
                cc = (255, 255, 255)
            if j < lit:
                g = Image.new("RGBA", im.size, (0, 0, 0, 0))
                ImageDraw.Draw(g).text((x - (fs.getlength(c) - cw[i]) / 2, base + dy), c, font=fs, fill=glow[who] + (255,), stroke_width=10,
                                       stroke_fill=glow[who] + (255,))
                im.alpha_composite(g.filter(ImageFilter.GaussianBlur(9)))
            d.text((x - (fs.getlength(c) - cw[i]) / 2, base + dy), c, font=fs, fill=cc + (255,), stroke_width=6, stroke_fill=(0, 0, 0, 255))
        else:
            d.text((x, base), c, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
        x += cw[i]
    return im


def render_sub_en(text, zh, rh, who, lit, pops, now, col, glow, targets):
    """英文字幕（大）＋中文（小，SUBS=en 時不顯示）：韻腳字用己方顏色、唱到時砸下來；目標字加紙白淡紫底線（DJ 顏色）。"""
    size = 60
    while font(size).getlength(text) > 1700 and size > 36:
        size -= 2
    f = font(size); zf = font(40)
    tw = f.getlength(text); zw = zf.getlength(zh) if zh else 0
    im = Image.new("RGBA", (int(max(tw, zw)) + 120, 200), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x0 = (im.width - tw) / 2; y0 = 22
    low = text.lower()
    pos = low.rfind(rh.lower()) if rh else -1
    if pos >= 0 and lit:                                     # 韻腳字另外畫：先畫前後文字，避免放大時疊在原本的字上
        d.text((x0, y0), text[:pos], font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
        d.text((x0 + f.getlength(text[:pos + len(rh)]), y0), text[pos + len(rh):], font=f, fill=(255, 255, 255, 255), stroke_width=6,
               stroke_fill=(0, 0, 0, 255))
    else:
        d.text((x0, y0), text, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    for m in re.finditer(r"[A-Za-z\u00e9\u00c9'-]+", text):
        w = re.sub(r"[^a-z]", "", m.group().lower().replace("\u00e9", "e"))
        if w in targets:
            a_ = x0 + f.getlength(text[:m.start()]); b_ = a_ + f.getlength(m.group())
            yy = y0 + size + 6
            d.rounded_rectangle([a_, yy, b_, yy + 7], radius=3, fill=col["J"] + (255,), outline=(0, 0, 0, 255), width=1)
    if pos >= 0 and lit:
        word = text[pos:pos + len(rh)]
        k = (now - pops[0]) * FPS if pops else 99
        sc = 1.0 + 0.45 * max(0.0, 1 - k / 6) if 0 <= k < 6 else 1.0
        fs = font(int(size * sc)); xw = x0 + f.getlength(text[:pos])
        xx = xw; yy = y0 - int((sc - 1) * size * 0.9)
        cc = (255, 255, 255) if 0 <= k < 4 else col[who]
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).text((xx, yy), word, font=fs, fill=glow[who] + (255,), stroke_width=10, stroke_fill=glow[who] + (255,))
        im.alpha_composite(g.filter(ImageFilter.GaussianBlur(9)))
        d.text((xx, yy), word, font=fs, fill=cc + (255,), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    if zh:
        d.text(((im.width - zw) / 2, y0 + size + 22), zh, font=zf, fill=(236, 232, 222, 255), stroke_width=5, stroke_fill=(0, 0, 0, 255))
    return im


def gfx_textw(text):
    size = 60
    while font(size).getlength(text) > 1700 and size > 36:
        size -= 2
    return font(size).getlength(text)


def speaker_tab(name, c):
    big = LANG != "en"
    f = font(30 if big else 24); hh = 54 if big else 40; w = int(f.getlength(name)) + (36 if big else 26)
    im = Image.new("RGBA", (w, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, hh - 1], radius=10, fill=c + (235,))
    dark = sum(c) > 560
    d.text((18 if big else 13, 9 if big else 6), name, font=f, fill=(40, 20, 0, 255) if dark else (255, 255, 255, 255))
    return im


def round_bug(label, name, c):
    im = Image.new("RGBA", (330, 96), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, 329, 95], radius=12, fill=(8, 10, 22, 170), outline=c + (230,), width=3)
    d.text((18, 10), label, font=font(30), fill=c + (255,)); d.text((18, 52), name, font=font(26), fill=(255, 255, 255, 235))
    return im


def big_word(text, k, g):
    base = 84 if LANG == "en" else 118
    sc = 1.0 + 0.9 * max(0.0, 1 - k / 6); f = font(int(base * sc)); w = int(f.getlength(text)) + 60
    im = Image.new("RGBA", (w, int(base * 1.6 * sc)), (0, 0, 0, 0)); gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).text((30, 12), text, font=f, fill=g + (255,), stroke_width=16, stroke_fill=g + (255,))
    im.alpha_composite(gl.filter(ImageFilter.GaussianBlur(12)))
    ImageDraw.Draw(im).text((30, 12), text, font=f, fill=(255, 244, 200, 255), stroke_width=8, stroke_fill=(40, 18, 0, 255))
    return im


COMBO = {"kill": "殺招！", 1: "押韻！", 2: "雙押！", 3: "三押！", 4: "四押！", 5: "五押！", 6: "六押！"}
COMBO_EN = {"kill": "KILL SHOT!", 1: "RHYME!", 2: "DOUBLE!", 3: "TRIPLE!"}


def combo_badge(n, g, k):
    txt = (COMBO_EN.get(n, "RHYME!") if LANG == "en" else COMBO.get(n, f"{n}押！")); sc = 1.0 + 1.2 * max(0.0, 1 - k / 5); f = font(int(64 * sc))
    im = Image.new("RGBA", (int(f.getlength(txt)) + 60, int(130 * sc)), (0, 0, 0, 0)); gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).text((30, 10), txt, font=f, fill=g + (255,), stroke_width=14, stroke_fill=g + (255,))
    im.alpha_composite(gl.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(im).text((30, 10), txt, font=f, fill=(255, 236, 140, 255), stroke_width=7, stroke_fill=(30, 10, 0, 255))
    a = 1.0 if k < 18 else max(0.0, 1 - (k - 18) / 6)
    if a < 1:
        im.putalpha(im.split()[3].point(lambda v: int(v * a)))
    return im


def attack_layer(who, k, col, glow, close=False):
    """k＝攻擊開始後第幾格：0–5 月牙斬飛行（拖尾＋速度線），6 起爆開（閃色＋放射線＋衝擊環＋火花）。A 從左往右、B 從右往左；高度在胸口以下。"""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    c, g = col[who], glow[who]; dirn = 1 if who == "A" else -1
    sx, ex = (300, W - 420) if who == "A" else (W - 300, 420); cy = 740
    if close:
        if k < 6:
            return lay
        ex, cy = (W - 230, 820) if who == "A" else (230, 820)
    rng = np.random.default_rng(7 if who == "A" else 11)
    if k < 6:
        p = (k + 1) / 6
        for y in rng.integers(120, H - 300, 18):
            L = int(rng.integers(200, 600)); x0 = int(sx + (ex - sx) * p * rng.uniform(0.3, 1.0))
            d.line([(x0, int(y)), (x0 - dirn * L, int(y))], fill=(255, 255, 255, int(rng.integers(60, 160))), width=3)
        for t in range(10, -1, -1):
            q = max(0.0, p - t * 0.035); x = sx + (ex - sx) * q; Rr = 190 - t * 6
            box = [x - Rr, cy - Rr * 1.25, x + Rr, cy + Rr * 1.25]; st, en = (-62, 62) if who == "A" else (118, 242)
            al = int(255 * (1 - t / 11) ** 1.5); wid = max(4, 42 - t * 3)
            d.arc(box, st, en, fill=g + (al,), width=wid + 18); d.arc(box, st, en, fill=c + (al,), width=wid)
            if t == 0:
                d.arc(box, st + 10, en - 10, fill=(255, 255, 255, 255), width=max(6, wid // 3))
    else:
        m = k - 6; a = max(0.0, 1 - m / 10)
        if m < 3:
            d.rectangle([0, 0, W, H], fill=c + (int(70 * (1 - m / 3)),))
        for i in range(36):
            ang = i / 36 * 2 * math.pi; r0, r1 = 70 + m * 30, 200 + m * 55
            d.line([(ex + r0 * math.cos(ang), cy + r0 * math.sin(ang)), (ex + r1 * math.cos(ang), cy + r1 * math.sin(ang))],
                   fill=(255, 255, 255, int(230 * a)), width=7)
        for j in range(2):
            rr = 90 + m * (42 - j * 15)
            d.ellipse([ex - rr, cy - rr, ex + rr, cy + rr], outline=(g if j == 0 else c) + (int(255 * a),), width=int(18 * a) + 2)
        for _ in range(40):
            ang = rng.uniform(0, 2 * math.pi); sp = rng.uniform(25, 60); r = 60 + sp * m
            x, y = ex + r * math.cos(ang), cy + r * math.sin(ang)
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(255, 240, 200, int(255 * a)))
        if m < 4:
            r2 = 140 - m * 30; d.ellipse([ex - r2, cy - r2, ex + r2, cy + r2], fill=(255, 255, 255, int(170 * (1 - m / 4))))
    return lay.filter(ImageFilter.GaussianBlur(1.2))


def punch_plan(shots, lines):
    """長演唱鏡（> 3.3 秒、單人、沒字卡）在鏡內每句開頭交替推近（ERB 約 2 秒一刀，不用多生 H3）。"""
    plan = []
    for sh in shots:
        if sh["kind"] != "sing" or sh["end"] - sh["start"] <= 3.3 or len(sh["subj"]) > 1 or sh.get("gfx") or sh.get("card") or sh.get("dist") == "CU":   # 特寫再推會切到頭頂（〈向日葵之戰〉P11、Z19）
            continue
        starts = sorted(l["start"] + 0.05 for l in lines if sh["start"] + 0.6 < l["start"] + 0.05 < sh["end"] - 0.8)
        if not starts:
            mid = (sh["start"] + sh["end"]) / 2
            ws = [w["s"] for l in lines if "words" in l for w in l["words"] if sh["start"] + 1.2 < w["s"] < sh["end"] - 1.0]
            if ws:
                plan.append(dict(id=sh["id"], t0=min(ws, key=lambda x: abs(x - mid)), t1=sh["end"]))
            continue
        z = True
        for i, t0 in enumerate(starts):
            if z:
                plan.append(dict(id=sh["id"], t0=t0, t1=starts[i + 1] if i + 1 < len(starts) else sh["end"]))
            z = not z
    return plan


def render_fx(cfg, shots, ev, src, dst, wav, post):
    import cv2
    font(10, cfg)
    col, glow = colors(cfg)
    R, DJ = cfg["rappers"], cfg["dj"]
    names = {"A": R["A"].get("short", R["A"]["name"]) if LANG == "en" else R["A"]["name"], "B": R["B"].get("short", R["B"]["name"]) if LANG == "en" else R["B"]["name"], "J": DJ.get("short", DJ["name"])}
    tl = json.loads((Path(post).parent / "audio" / "timeline.json").read_text(encoding="utf-8"))
    rounds = [(tl["A"][0]["start"] - 0.6, tl["marks"]["a_end"], "ROUND 1", "A"),
              (tl["B"][0]["start"] - 0.6, tl["B"][-1]["end"] + 1.0, "ROUND 2", "B")]
    lines, attacks, beats3 = ev["lines"], ev["attacks"], ev["beats3"]
    targets = {re.sub(r"[^a-z]", "", w.lower().replace("\u00e9", "e")) for w in cfg.get("targets", [])}
    punches = punch_plan(shots, lines)
    cap = cv2.VideoCapture(str(src))
    for p_ in punches:                                       # 推近中心＝那段中間格最大的臉
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((p_["t0"] + p_["t1"]) / 2 * FPS)); ok, fr0 = cap.read()
        cx, cy = W / 2, H * 0.42
        if ok:
            fs_ = faces(fr0)
            if fs_:
                x, y, w_, h_ = max(fs_, key=lambda f: f[2] * f[3]); cx, cy = x + w_ / 2, y + h_ * 0.7
        p_["cx"], p_["cy"] = float(cx), float(cy)
        # 審核回饋 #4：推近不能切到頭頂（舊 A11 在 102 秒推近，頭頂被裁掉）。整段取 5 格量「髮頂」＝臉框上緣再往上 0.45 個臉高，
        # 裁切框上緣不得低於髮頂上方 3%；整段找不到臉就不推近。
        tops = []
        for k in range(5):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int((p_["t0"] + (p_["t1"] - p_["t0"]) * (k + 0.5) / 5) * FPS)); ok, frk = cap.read()
            fk = faces(frk) if ok else []
            if fk:
                x, y, w_, h_ = max(fk, key=lambda f: f[2] * f[3]); tops.append(y - 0.45 * h_)
        p_["ymax"] = float(max(0.0, min(tops) - 0.03 * H)) if tops else None
    cap.release()
    punches = [p_ for p_ in punches if p_["ymax"] is not None]
    flash = set(cfg.get("flash_scenes", []))
    cuts = [b["start"] for a, b in zip(shots, shots[1:]) if a["scene"] != b["scene"] and b["scene"] in flash]
    (Path(post) / "fx_events.json").write_text(json.dumps({**ev, "cuts": cuts, "punches": punches}, ensure_ascii=False, indent=1), encoding="utf-8")
    for a in attacks:                                        # 押韻字不疊到別人的鏡頭（〈瑜亮之戰〉v6「三押！」殘留到孔明反應鏡）
        nx = next((s for s in shots if a["t"] < s["start"] < a["t"] + 1 and a["who"] not in s.get("subj", [])), None)
        if nx:
            a["until"] = min(a["until"], nx["start"])
    tabs = {k: speaker_tab(names[k], col[k]) for k in names}
    bugs = {lab: round_bug(lab, names[who], col[who]) for _, _, lab, who in rounds}
    shot_at = lambda t: next((s for s in shots if s["start"] <= t < s["end"]), None)
    n = int(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                                 capture_output=True, text=True).stdout) * FPS)
    rd = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    wr = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "192k", "-shortest", str(dst)], stdin=subprocess.PIPE)
    cache = {}
    for fi in range(n):
        raw = rd.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        t = fi / FPS
        fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32)
        for c in cuts:                                       # 切進閃回：閃白＋速度放大
            k = (t - c) * FPS
            if -2 <= k < 6:
                z = 1.0 + 0.12 * max(0.0, 1 - max(k, 0) / 6)
                if z > 1.001:
                    hh, ww = int(H / z), int(W / z); y0, x0 = (H - hh) // 2, (W - ww) // 2
                    fr = np.asarray(Image.fromarray(fr[y0:y0 + hh, x0:x0 + ww].astype(np.uint8)).resize((W, H), Image.BILINEAR), np.float32)
                fl = max(0.0, 1 - abs(k) / 4) * 0.85; fr = fr * (1 - fl) + 255 * fl
        for p_ in punches:
            if p_["t0"] <= t < p_["t1"]:
                hh, ww = int(H / PUNCH), int(W / PUNCH)
                x0 = int(min(max(p_["cx"] - ww / 2, 0), W - ww)); y0 = int(min(max(p_["cy"] - hh / 2, 0), H - hh, p_["ymax"]))
                fr = np.asarray(Image.fromarray(fr[y0:y0 + hh, x0:x0 + ww].astype(np.uint8)).resize((W, H), Image.LANCZOS), np.float32)
                break
        shake = (0, 0); zoom = 1.0; ab = 0
        for a in attacks:
            k = (t - (a["t"] - 6 / FPS)) * FPS
            if 6 <= k < 16:
                m = k - 6; amp = 16 * (1 - m / 10)
                shake = (int(amp * math.sin(m * 2.7)), int(amp * math.cos(m * 3.1)))
                zoom = max(zoom, 1.0 + 0.05 * (1 - m / 10)); ab = max(ab, int(10 * (1 - m / 4))) if m < 4 else ab
        if zoom > 1.0 or shake != (0, 0):
            hh, ww = int(H / zoom), int(W / zoom)
            y0 = min(max((H - hh) // 2 + shake[1], 0), H - hh); x0 = min(max((W - ww) // 2 + shake[0], 0), W - ww)
            fr = np.asarray(Image.fromarray(fr[y0:y0 + hh, x0:x0 + ww].astype(np.uint8)).resize((W, H), Image.BILINEAR), np.float32)
        if ab > 0:
            fr[:, ab:, 0] = fr[:, :-ab, 0]; fr[:, :-ab, 2] = fr[:, ab:, 2]
        img = Image.fromarray(np.clip(fr, 0, 255).astype(np.uint8)).convert("RGBA")
        for a in attacks:
            k = (t - (a["t"] - 6 / FPS)) * FPS
            if 0 <= k < 16:
                s_ = shot_at(a["t"]); close = bool(s_) and (s_["dist"] in CLOSE or s_["scene"] != "arena")
                img.alpha_composite(attack_layer(a["who"], int(k), col, glow, close))
        for l in lines:
            if l["start"] <= t <= l["end"]:
                lit = sum(1 for h in l["hits"] if t >= h)
                key = (l["text"], lit, tuple(int((t - h) * FPS) if 0 <= (t - h) * FPS < 6 else -1 for h in l["hits"]))
                sp = cache.get(key)
                if sp is None:
                    if LANG == "en":
                        sp = render_sub_en(l["text"], l.get("zh", "") if SUBS != "en" else "", l["rh"], l["who"], lit, l["hits"], t, col, glow,
                                           targets)
                    else:
                        sp = render_sub(l["text"], l["rh"], l["who"], lit, l["hits"], t, col, glow)
                    cache[key] = sp
                sx = (W - sp.width) // 2
                if LANG == "en":
                    sy = H - sp.height - 6 + shake[1] // 2
                    img.alpha_composite(sp, (sx, sy))
                    tb = tabs[l["who"]]; img.alpha_composite(tb, (max(10, sx + (sp.width - int(gfx_textw(l["text"]))) // 2), max(0, sy - 40)))
                else:
                    img.alpha_composite(sp, (sx, SUB_Y - 80 + shake[1] // 2))
                    tb = tabs[l["who"]]; img.alpha_composite(tb, (max(10, sx + 60 - tb.width - 14), SUB_Y + 14 + shake[1] // 2))
        for t0, t1, lab, who in rounds:
            if t0 <= t <= t1:
                img.alpha_composite(bugs[lab], (36, 30))
        for b in beats3:
            k = (t - b["t"]) * FPS
            if k >= 0:
                bw = big_word(b["text"], k, glow["J"]) if k < 6 else cache.setdefault(("bw", b["text"]), big_word(b["text"], 99, glow["J"]))
                img.alpha_composite(bw, (70, (40 + b["row"] * 115) if LANG == "en" else ((90 + b["row"] * 165) if len(beats3) <= 3 else (50 + b["row"] * 145))))   # 4 行時收緊，第 4 行不碰投票卡（〈Bravo 之戰〉v2）
        for a in attacks:
            k = (t - a["t"]) * FPS
            if 0 <= k < 24 and t < a["until"]:
                b = combo_badge(a["n"], glow[a["who"]], k); img.alpha_composite(b, ((W - b.width) // 2, SUB_Y - 190))
        if len(cache) > 4000:
            cache.clear()
        wr.stdin.write(np.asarray(img.convert("RGB")).tobytes())
        if fi % 480 == 0:
            print(f"fx {fi}/{n}", flush=True)
    wr.stdin.close(); wr.wait(); rd.kill(); rd.wait()
