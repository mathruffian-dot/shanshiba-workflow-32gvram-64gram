"""選用：用 Kie.ai 的 Suno V6 API 生兩位饒舌手的歌（沒有 Kie 的話，把 out/songtext/ 的文字貼到 Suno 網頁的 Custom 模式也一樣）。
金鑰：環境變數 KIE_API_KEY（或 KIE_KEY_FILE＝存金鑰的文字檔）。每次送件生 2 版，約 12 點（2026-10 價格）。
用法（先跑 make_battle.py songtext）：
  python kie_suno.py submit A [標籤]   → out/suno/tasks_<標籤>.json（標籤預設 a1）
  python kie_suno.py poll <標籤>       → out/suno/<歌名>_<標籤>_v1.mp3、_v2.mp3
兩人各生一首（同一首歌分兩人＝同一個聲音），挑好的複製到 song/A.mp3、song/B.mp3。
⚠ 歌詞要跟 battle.json 一字不差（songs 階段靠它對齊）；改了歌詞就重跑 songtext 再送。"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
OUT = HERE / "out" / "suno"; OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("KIE_API_KEY") or (Path(os.environ["KIE_KEY_FILE"]).read_text(encoding="utf-8").strip() if os.environ.get("KIE_KEY_FILE") else "")
API = "https://api.kie.ai/api/v1"


def req(path, data=None, params=""):
    if not KEY:
        sys.exit("設定環境變數 KIE_API_KEY（或 KIE_KEY_FILE）")
    r = urllib.request.Request(API + path + params, data=json.dumps(data).encode() if data is not None else None,
                               headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.loads(f.read().decode())


def submit(who, tag="a1"):
    r = CFG["rappers"][who]
    lyr = (HERE / "out" / "songtext" / f"suno_{who}_lyrics.txt").read_text(encoding="utf-8")
    style = os.environ.get("SUNO_STYLE") or r["suno_style"]     # 換人聲時用環境變數覆蓋風格
    if len(style) > 1000:
        sys.exit(f"風格 {len(style)} 字元，超過 Suno 上限 1000")
    inp = {"custom_mode": True, "instrumental": False, "model": "V6", "title": r.get("suno_title", f"{CFG['title']}_{r['name']}"),
           "lyrics": lyr, "style": style, "negative_tags": os.environ.get("SUNO_NEG") or r.get("suno_negative", ""), "vocal_gender": r.get("vocal_gender", "m"),
           "duration": int(r.get("suno_duration", 120))}
    res = req("/jobs/createTask", {"model": "ai-music-api/generate", "input": inp})
    print(res)
    if res.get("code") != 200:
        sys.exit(res)
    (OUT / f"tasks_{tag}.json").write_text(json.dumps({"taskId": res["data"]["taskId"], "who": who, "input": inp, "submitted": time.time()},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")


def poll(tag):
    t = json.loads((OUT / f"tasks_{tag}.json").read_text(encoding="utf-8"))
    while True:
        d = req("/jobs/recordInfo", params=f"?taskId={t['taskId']}").get("data") or {}
        print(tag, d.get("state"), d.get("failMsg") or "", flush=True)
        if d.get("state") in ("success", "fail"):
            break
        time.sleep(20)
    t.update(state=d.get("state"), raw=d, files=[])
    if d.get("state") == "success":
        for i, x in enumerate(json.loads(d["resultJson"])["data"], 1):
            out = OUT / f"{t['input']['title']}_{tag}_v{i}{Path(x['audio_url']).suffix or '.mp3'}"
            r = urllib.request.Request(x["audio_url"], headers={"User-Agent": "Mozilla/5.0"})
            out.write_bytes(urllib.request.urlopen(r, timeout=300).read()); t["files"].append(out.name); print("saved", out, flush=True)
    (OUT / f"tasks_{tag}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"submit": submit, "poll": poll}[sys.argv[1]](*sys.argv[2:])
