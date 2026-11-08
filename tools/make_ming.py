"""角色台詞固定音軌一條龍：Ming-3.0-TTS 0.5B（⭐ 2026-10-29 起配音備案預設，取代 Breeze TTS 2 固定音軌與 Qwen3-TTS 營利備案）。
原專案使用者 2026-10-28 試聽：「聲音非常的好，也沒有大陸腔。」程式與權重 MIT＝可營利。
原專案實測（RTX 5090，三個角色各 3 句、每句 4 seed）：9 句全對、候選 31/36 合格（Breeze 12/35）、像本人 0.86（Breeze 0.81）、句尾截斷 3/36（Breeze 15/35）。
畫面內台詞仍預設由 H3 自己念＋角色參考音；本工具用在：念錯抽不出來又沒人能錄、數字日期難字、精準聲畫同步、系統聲／內心旁白。

用法（Voice venv）：C:\\AI\\tools\\make_ming.cmd jobs.json
jobs.json 與 make_breeze 相同格式：{"out_dir": "ming", "seeds": 4, "extra_seeds"?: 4, "jobs": [{"name","text","ref_audio","ref_text","seeds"?}]}
  text 照寫繁體（字幕用的字）；可在句中加 Ming 行內標籤，例 "[Sigh]又是回爐計劃……"、"[Laughter]"、"[Surprise-ah]"（共 14 種，見 README §4a0）。
  ⚠ 克隆模式不能加語氣指令（instruction 會被忽略），表演靠台詞寫法和標籤。
流程：
  1. 確認裝了 ComfyUI-Ming-3-tts 節點的 ComfyUI（預設 0.41、127.0.0.1:8189）在跑，沒有就背景啟動（H3 的 0.40／8188 不受影響）；
  2. 台詞與參考逐字稿去注音標記 → **OpenCC t2s 轉簡體**（餵繁體會每支念錯：線上報名→憲章奉明，2026-10-28 實測）；
  3. 每句 seed 1..N（預設 4）生成到 <out_dir>/cand/<name>_s<k>.wav（已存在的跳過）；沒合格的句子自動把句尾改「……」再多抽 extra_seeds 支（預設 4；
     Ming 會太早收尾：最後一個字被切、逗號後的短句整段不見，句尾留延長號就好很多）；
  4. breeze_tailfilter.py 排除句尾截斷 → asr_pick.py（聽寫拼音含聲調逐字對）挑；
  5. 修正聽寫誤判：句首語氣詞（標籤念出來的唉／哼／呵呵／啊）、「山獅霸」聽成「三師爸／三十八」、「喔」寫成「哦」不算錯；
  6. 最後叫 ComfyUI 釋放顯存（模型約 2.7 GB），讓 H3 可以接著跑。
輸出 <out_dir>/<name>.wav（44.1 kHz，已去頭尾靜音）＋ asr_picks.json。標 NEEDS_REVIEW 的要換說法或多抽 seed 再跑；腔調最後仍要人聽。"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from hashlib import md5
from pathlib import Path

import opencc

AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
TOOLS = Path(__file__).resolve().parent
_EXE = "Scripts/python.exe" if os.name == "nt" else "bin/python"
VOICE_PY = os.environ.get("PY_VOICE", str(AI / "Voice" / "venv" / _EXE))
H3_PY = os.environ.get("PY_H3", str(AI / "H3" / "venv" / _EXE))
# 原專案：Ming 節點裝在另一份 ComfyUI 0.41（8189 埠；input／output／models 都連到 0.36），H3 用的 0.40（8188）不動。路徑不同用環境變數改
# （Colab：colab_h3.py 指到 VM 上已經在跑的 8188，節點由 install_full.sh 裝好）。
COMFY_DIR = Path(os.environ.get("MING_COMFY_DIR", str(AI / "H3" / "ComfyUI-0.41.0")))
PORT = os.environ.get("MING_COMFY_PORT", "8189")
COMFY = f"http://127.0.0.1:{PORT}"
COMFY_INPUT = Path(os.environ.get("MING_COMFY_INPUT", str(AI / "H3" / "ComfyUI-0.36.0" / "input")))
COMFY_OUTPUT = Path(os.environ.get("MING_COMFY_OUTPUT", str(AI / "H3" / "ComfyUI-0.36.0" / "output")))
LOG = AI / "H3" / "comfy041_ming.log"
T2S = opencc.OpenCC("t2s")   # 只做字形轉換；不要用 tw2sp（會把台灣用詞換成大陸用詞）


def api(path, data=None, timeout=10):
    req = urllib.request.Request(COMFY + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")


def ensure_comfy():
    try:
        api("/system_stats", timeout=4); return
    except Exception:
        pass
    print(f"[ming] 啟動 ComfyUI（{COMFY_DIR.name}，{PORT} 埠）…", flush=True)
    log = open(LOG, "ab")
    detach = (dict(creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt"
              else dict(start_new_session=True))
    subprocess.Popen([H3_PY, "-X", "utf8", str(COMFY_DIR / "main.py"), "--listen", "127.0.0.1", "--port", PORT,
                      "--disable-auto-launch", "--preview-method", "none", "--cache-none", "--fast", "fp16_accumulation"],
                     cwd=str(COMFY_DIR), stdout=log, stderr=log, stdin=subprocess.DEVNULL, **detach)
    for i in range(90):
        time.sleep(2)
        try:
            api("/system_stats", timeout=4); print(f"[ming] ComfyUI 啟動完成（{(i + 1) * 2} 秒）", flush=True); return
        except Exception:
            pass
    raise SystemExit(f"[ming] ComfyUI 三分鐘內沒起來，看 {LOG}")


# OpenCC t2s 會把「活著、看著、睡著、著急、穿著」的「著」原樣留下，可是簡體的「著」只念 zhù（著作）→ Ming 把「活著」念成「活住」
# （〈Bravo 之戰〉DJ 兩處，使用者 2026-11-08 聽出來）。簡體裡 zhe／zháo／zhuó 都寫「着」，只有下面這些 zhù 的詞寫「著」。
ZHU_WORDS = ("著作", "著名", "著称", "著述", "著录", "著者", "著书", "著有", "名著", "原著", "巨著", "专著", "论著", "编著", "合著",
             "译著", "遗著", "新著", "拙著", "大著", "土著", "显著", "卓著", "昭著", "彰著", "撰著")


def fix_zhe(s):
    keep = {i for w in ZHU_WORDS for m in re.finditer(w, s) for i in range(m.start(), m.end())}
    return "".join("着" if c == "著" and i not in keep else c for i, c in enumerate(s))


def ming_text(t):
    return fix_zhe(T2S.convert(re.sub(r"\[:[^\]]*\]", "", t)))      # 去注音標記；[Sigh] 等英文標籤保留


def pick_text(t):
    return re.sub(r"\[[^\]]*\]", "", t)                      # 聽寫比對用：標籤全拿掉


def gen_one(text, ref_name, ref_text, seed, dst):
    g = {
        "1": {"class_type": "MingLoadModel", "inputs": {"model": "Ming-3.0-tts-0.5b", "precision": "auto", "device": "auto", "download_if_missing": False}},
        "2": {"class_type": "LoadAudio", "inputs": {"audio": ref_name}},
        "3": {"class_type": "MingGenerate", "inputs": {
            "model": ["1", 0], "text": text, "task": "clone",
            "task.reference_audio": ["2", 0], "task.reference_text": ref_text, "task.language": "Chinese",
            "seed": seed, "cfg": 2.0, "flow_steps": 10, "sigma": 0.25, "temperature": 0.0, "max_steps": 250, "trim": True}},
        "4": {"class_type": "SaveAudio", "inputs": {"audio": ["3", 0], "filename_prefix": f"make_ming/{dst.stem}"}},
    }
    pid = api("/prompt", {"prompt": g})["prompt_id"]
    while True:
        h = api(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(f"[ming] {dst.stem} 失敗：{json.dumps(st, ensure_ascii=False)[:1500]}")
            if st.get("completed"): break
        time.sleep(0.5)
    a = h[pid]["outputs"]["4"]["audio"][0]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(COMFY_OUTPUT / a["subfolder"] / a["filename"]), str(dst)], check=True)


def recheck(out, jobs):
    """聽寫誤判修正：原本不合格的句子，若有候選修正後全對，就改挑那支（長度最接近合格者中位數）。"""
    sys.path.insert(0, str(TOOLS))
    import breezyvoice_pick as bp
    from pypinyin import Style, lazy_pinyin
    py = lambda s: lazy_pinyin(re.sub(r"[^一-鿿A-Za-z0-9]", "", bp.norm(s)), style=Style.TONE3)
    fix = lambda s: re.sub(r"三師爸|三十八|三獅霸", "山獅霸", re.sub(r"^[唉哎哼呵哈啊噢哦喔嗯欸誒呃,，。、\s]+", "", s)).replace("哦", "喔")
    f = out / "asr_picks.json"; picks = json.loads(f.read_text(encoding="utf-8"))
    for j in jobs:
        p = picks.get(j["name"])
        if not p or not p["needs_review"]: continue
        good = [c for c in p["cands"] if py(fix(c["asr"])) == py(fix(j["text"]))]
        if not good: continue
        med = sorted(c["dur"] for c in good)[len(good) // 2]
        best = min(good, key=lambda c: abs(c["dur"] - med))
        bp.write_trimmed(out / "cand" / best["file"], out / f"{j['name']}.wav")
        p.update(pick=best["file"], n_ok=len(good), needs_review=False, fixed="語氣詞／山獅霸同音")
        print(f"[ming] {j['name']}：聽寫誤判修正後合格（{best['file']}）", flush=True)
    f.write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    return picks


def trail(t):
    """補抽用：句尾標點換成「……」。2026-10-29 實測「…交到教務處。」4 支有 4 支最後一個字被切掉、「…交到教務處，逾期不候。」7 支只有 1 支念完，
    句尾改「……」後 3/3 合格（模型的停止判斷太早觸發，留個延長號就不會在最後一個字收掉）。"""
    return t.rstrip("。！？!?…，,．. ") + "……"


def generate(spec, J, out, jobs, k_from, k_to, ending=None):
    """jobs 的每句生 seed k_from..k_to；已存在（含被判截斷的）跳過。ending＝改寫句尾的函式（補抽用）。回傳新生成支數。"""
    t0 = time.time(); n_new = 0
    for j in jobs:
        ref = (spec.parent / j["ref_audio"]).resolve()
        ref_name = f"ming_{md5(str(ref).encode()).hexdigest()[:10]}{ref.suffix}"
        shutil.copy(ref, COMFY_INPUT / ref_name)
        text, ref_text = ming_text(j["text"]), ming_text(j["ref_text"])
        if ending: text = ending(text)
        for k in range(k_from, k_to + 1):
            dst = out / "cand" / f"{j['name']}_s{k}.wav"
            if dst.exists() or (out / "cand_trunc" / dst.name).exists(): continue   # 被判截斷的同 seed 重生也一樣，跳過
            gen_one(text, ref_name, ref_text, k, dst); n_new += 1
        print(f"[ming] {j['name']} seed {k_from}–{k_to} 完成（{time.time() - t0:.0f} 秒）：{text}", flush=True)
    return n_new


def pick_all(spec, J, out, jobs):
    pspec = spec.parent / (spec.stem + "_ming_pick.json")
    pspec.write_text(json.dumps({"out_dir": J.get("out_dir", "ming"), "jobs": [dict(name=j["name"], text=pick_text(j["text"])) for j in jobs]},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    subprocess.run([VOICE_PY, str(TOOLS / "breeze_tailfilter.py"), str(out)], check=True)
    subprocess.run([VOICE_PY, str(TOOLS / "asr_pick.py"), str(pspec)], check=True)
    return recheck(out, [dict(name=j["name"], text=pick_text(j["text"])) for j in jobs])


def main():
    spec = Path(sys.argv[1]).resolve(); J = json.loads(spec.read_text(encoding="utf-8-sig"))
    out = spec.parent / J.get("out_dir", "ming"); (out / "cand").mkdir(parents=True, exist_ok=True)
    jobs = J["jobs"]; seeds = lambda j: j.get("seeds", J.get("seeds", 4)); extra = J.get("extra_seeds", 4)
    ensure_comfy()
    t0 = time.time(); n_new = sum(generate(spec, J, out, [j], 1, seeds(j)) for j in jobs)
    picks = pick_all(spec, J, out, jobs)
    # Ming 的毛病是太早收尾（最後一個字被切、或逗號後的短句整段不見）→ 沒合格的句子自動用「……」結尾多抽 extra_seeds 支再挑一次
    bad = [j for j in jobs if picks.get(j["name"], {}).get("needs_review")]
    if bad and extra:
        print(f"[ming] {len(bad)} 句沒有合格候選 → 句尾改「……」各多抽 {extra} 支", flush=True)
        n_new += sum(generate(spec, J, out, [j], 101, 100 + extra, ending=trail) for j in bad)   # 檔名 _s101 起＝「……」版
        picks = pick_all(spec, J, out, jobs)
    try:
        api("/free", {"unload_models": True, "free_memory": True})   # 釋放顯存給 H3
    except Exception:
        pass
    bad = [k for k, v in picks.items() if v.get("needs_review")]
    print(f"[ming] 新生成 {n_new} 支，共 {time.time() - t0:.0f} 秒；合格 {len(picks) - len(bad)}/{len(picks)} 句"
          + (f"；NEEDS_REVIEW：{', '.join(bad)}（逗號前後拆成兩句、換說法，或加大 seeds 再跑）" if bad else ""), flush=True)


if __name__ == "__main__":
    main()
