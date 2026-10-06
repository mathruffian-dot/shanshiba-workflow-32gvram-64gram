"""OpenAI Image 2.5 helper. API key from env OPENAI_API_KEY, or a text file named by env OPENAI_KEY_FILE (never printed).
generate(prompt, out_stem, n) -> /images/generations ; edit(prompt, images, out_stem, n) -> /images/edits (refs)."""
import base64
import os
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

KEY = os.environ.get("OPENAI_API_KEY") or (Path(os.environ["OPENAI_KEY_FILE"]).read_text(encoding="utf-8").strip() if os.environ.get("OPENAI_KEY_FILE") else "")
if not KEY:
    raise SystemExit("img25: set OPENAI_API_KEY (or OPENAI_KEY_FILE)")
MODEL = "gpt-image-2.5-sunburst"
SIZE = "1344x768"
# 2026-09-30 全域預設改 medium（輸出 token 約 high 的 1/4；臉部特寫肉眼與 high 差異很小）。
# 定稿或臉不夠像時：環境變數 IMG25_QUALITY=high；純探索可用 low（約 1/9）。預設每次只生 1 張（n=1）。
import os
QUALITY = os.environ.get("IMG25_QUALITY", "medium")
# 2026-10-06 參考圖降本：送出前在記憶體裡把每張參考圖縮成約一半面積（邊長 ×0.707，原檔不動）。
# 實測定妝表 1296→680 輸入 token、臉部目視無差。
# 已經小於 REF_MIN_PIXELS 的圖不縮。關閉：IMG25_REF_SCALE=1。日後若發現角色不像參考圖，先用 =1 重生比對。
REF_SCALE = float(os.environ.get("IMG25_REF_SCALE", "0.707"))
REF_MIN_PIXELS = 1024 * 576


def _ref_bytes(path, scale=None):
    """PNG bytes of a reference image, downscaled by REF_SCALE (linear) unless already small. Returns (bytes, (w, h))."""
    scale = REF_SCALE if scale is None else scale
    path = Path(path)
    if scale >= 1:
        return path.read_bytes(), None
    from io import BytesIO
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    if w * h <= REF_MIN_PIXELS:
        return path.read_bytes(), (w, h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA")
    buf = BytesIO()
    im.resize((nw, nh), Image.LANCZOS).save(buf, format="PNG")
    return buf.getvalue(), (nw, nh)


def _post(url, body, ctype):
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {KEY}", "Content-Type": ctype})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:1500]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(20 * (attempt + 1)); continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(20); continue
            raise


def _save(res, out_stem, meta):
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for i, d in enumerate(res.get("data", []), start=1):
        p = out_stem.with_name(f"{out_stem.name}_c{i}.png")
        p.write_bytes(base64.b64decode(d["b64_json"]))
        files.append(p)
    meta.update(usage=res.get("usage"), files=[f.name for f in files])
    out_stem.with_name(out_stem.name + "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return files


def generate(prompt, out_stem, n=1, size=SIZE):
    t0 = time.time()
    body = json.dumps({"model": MODEL, "prompt": prompt, "n": n, "size": size, "quality": QUALITY}).encode()
    res = _post("https://api.openai.com/v1/images/generations", body, "application/json")
    return _save(res, out_stem, {"mode": "generate", "prompt": prompt, "seconds": round(time.time() - t0, 1)})


def edit(prompt, images, out_stem, n=1, size=SIZE, mask=None):
    """mask: PNG (same size as images[0]); transparent pixels = area Image 2.5 may repaint.
    Refs are downscaled per REF_SCALE; with a mask, images[0] and the mask stay full size (they must match)."""
    t0 = time.time()
    b = uuid.uuid4().hex
    body = bytearray()
    for k, v in {"model": MODEL, "prompt": prompt, "n": str(n), "size": size, "quality": QUALITY}.items():
        body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    if mask:
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"mask\"; filename=\"mask.png\"\r\n"
                 f"Content-Type: image/png\r\n\r\n").encode() + Path(mask).read_bytes() + b"\r\n"
    sent = []
    for i, f in enumerate(images):
        f = Path(f)
        data, wh = _ref_bytes(f, scale=1 if (mask and i == 0) else None)
        sent.append(list(wh) if wh else "original")
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"image[]\"; filename=\"{f.stem}.png\"\r\n"
                 f"Content-Type: image/png\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    res = _post("https://api.openai.com/v1/images/edits", bytes(body), f"multipart/form-data; boundary={b}")
    return _save(res, out_stem, {"mode": "edit", "prompt": prompt, "refs": [str(x) for x in images],
                                 "ref_scale": REF_SCALE, "ref_sent_size": sent,
                                 "seconds": round(time.time() - t0, 1)})
