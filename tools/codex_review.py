r"""叫 Codex CLI 當審核副手（預設 gpt-6.2-astra、思考強度 medium、唯讀；要審得更深才加 --effort high）。2026-11-24 建立。

為什麼有這支：Codex 的唯讀沙盒讀不到本機檔，所有材料都要從 stdin 餵。手寫指令時踩過的坑——
用 `cut -c` 截行把中文字切壞，Codex 直接拒收（input is not valid UTF-8）；忘了寫思考強度（config 預設是 xhigh）；
上一輪的意見沒附，Codex 只好重頭審；提示詞與結果散在暫存資料夾，事後查不到。這支把這些固定下來。

用法（任何 Python；codex 要在 PATH，版本 ≥ 0.170.0 才有 gpt-6.2-astra）：
  python codex_review.py --ask ask.md [--attach 檔案 ...] [--image 圖 ...] [--with-prev] [--name 主題] [--outdir 資料夾]
                         [--model gpt-6.2-astra] [--effort medium] [--timeout 900]

  --ask       你要問 Codex 的話（UTF-8 文字檔）：背景、你做了什麼、要它回答的編號問題、字數上限。
  --attach    要給它看的文字檔，原文整份附在後面（不截斷、不改寫）。可以給很多個。
              要附指令的輸出（git diff、測試結果）就先存成檔再附。
  --image     畫面（每秒一格總表、封面、截圖），用 Codex 的 -i 傳。
  --with-prev 把同一個主題上一輪的審核意見附在最前面（第二輪起都該加，Codex 才知道自己上次說了什麼）。
              它拿的是這個 --name 在這個 --outdir 裡「輪次最大、有內容」的那一份。
  --prev 檔案 自己指定要附哪一份上一輪意見（同一個主題分兩條路各自送審時用）。
  --name      主題（檔名用，預設 review）。同一件事每一輪用同一個名字，輪次自動加一。
              兩件不同的事、或同一件事分兩條路改，要用不同的名字（例 preflight、preflight_alt），不然 --with-prev 會拿到另一邊的意見。
  --outdir    提示詞與結果存哪裡（預設 ./codex_review）。片子放 <片>/review/codex，專案整理放暫存區。
輸出：<outdir>/<name>_r<輪次>_prompt.md、_review.md、_log.txt；審核意見同時印在畫面上。
回傳碼：0＝拿到審核意見；1＝Codex 執行失敗或沒有回內容；2＝用法錯、檔案讀不了、不是 UTF-8。

注意：送出去的內容會到 OpenAI。不要附金鑰、個資；只附這次判斷需要的東西。"""
import argparse
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

SEP = "=====【{}】====="


def read_utf8(p, what):
    try:
        return Path(p).read_bytes().decode("utf-8")       # 嚴格解碼：壞一個位元組就擋下來，不要送出去才被拒
    except FileNotFoundError:
        raise SystemExit(f"找不到{what}：{p}")
    except OSError as e:                                   # 給的是資料夾、沒有權限、被別的程式鎖住
        raise SystemExit(f"{what}讀不了（{p}）：{type(e).__name__}。要給的是一個讀得到的文字檔。")
    except UnicodeDecodeError as e:
        raise SystemExit(f"{what}不是合法的 UTF-8（{p}，第 {e.start} 個位元組）。多半是用 cut／head -c 把中文字切壞了，改用整行或整檔。")


def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="叫 Codex CLI 審核（唯讀、資料從 stdin 餵）")
    ap.add_argument("--ask", required=True)
    ap.add_argument("--attach", nargs="*", default=[])
    ap.add_argument("--image", nargs="*", default=[])
    ap.add_argument("--with-prev", action="store_true")
    ap.add_argument("--prev", help="指定要附哪一份上一輪意見（檔案路徑），不照輪次自動找")
    ap.add_argument("--name", default="review")
    ap.add_argument("--outdir", default="codex_review")
    ap.add_argument("--model", default="gpt-6.2-astra")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "ultra"])
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--dry-run", action="store_true", help="只組提示詞、存檔、印大小，不呼叫 Codex")
    try:
        a = ap.parse_args()
    except SystemExit as e:
        sys.exit(2 if e.code else 0)
    if not re.fullmatch(r"[\w\-]+", a.name):
        print("--name 只能用字母、數字、中文、底線、連字號（要當檔名）")
        return 2
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    def rounds(kind):
        return sorted(int(m.group(1)) for f in out.glob(f"{a.name}_r*_{kind}.md") if (m := re.fullmatch(rf"{re.escape(a.name)}_r(\d+)_{kind}", f.stem)))
    # 「審完的輪次」只算有內容的意見檔；失敗留下的空檔不算，下一輪 --with-prev 不會拿到殘缺的意見
    done = [n for n in rounds("review") if (out / f"{a.name}_r{n}_review.md").read_text(encoding="utf-8", errors="replace").strip()]
    rnd = max(rounds("prompt") + rounds("review") + [0]) + 1
    try:
        parts = [read_utf8(a.ask, "提問檔").rstrip() + "\n"]
        if a.prev:
            body = read_utf8(a.prev, "上一輪意見").strip()
            if not body:
                print(f"--prev 指的檔是空的：{a.prev}")
                return 2
            parts.insert(0, SEP.format(f"你上一輪的審核意見（{Path(a.prev).name}）") + "\n" + body + "\n\n" + SEP.format("這一輪") + "\n")
        elif a.with_prev:
            if not done:
                print("--with-prev：這個主題還沒有上一輪的審核意見（檢查 --name 和 --outdir 是不是跟上一輪一樣）")
                return 2
            prev = out / f"{a.name}_r{done[-1]}_review.md"
            parts.insert(0, SEP.format(f"你上一輪（第 {done[-1]} 輪）的審核意見") + "\n" + read_utf8(prev, "上一輪意見").rstrip() + "\n\n" + SEP.format("這一輪") + "\n")
        for f in a.attach:
            parts.append("\n" + SEP.format(Path(f).name) + "\n" + read_utf8(f, "附件").rstrip() + "\n")
    except SystemExit as e:
        print(e)
        return 2
    for im in a.image:
        if not Path(im).is_file():
            print(f"找不到圖：{im}")
            return 2
    prompt = "".join(parts)
    if a.dry_run:
        pf = out / f"{a.name}_dryrun_prompt.md"       # 試組不佔輪次
        pf.write_text(prompt, encoding="utf-8", newline="\n")
    else:
        while True:                                   # 用「獨占建立提示詞檔」搶輪次：兩個工作階段同時送同一個主題也不會互蓋
            pf = out / f"{a.name}_r{rnd}_prompt.md"
            try:
                with open(pf, "x", encoding="utf-8", newline="\n") as f:
                    f.write(prompt)
                break
            except FileExistsError:
                rnd += 1
    rf, lf = (out / f"{a.name}_r{rnd}_{k}" for k in ("review.md", "log.txt"))
    kb = len(prompt.encode("utf-8")) / 1024
    print(f"第 {rnd} 輪｜{a.model}／{a.effort}｜提示詞 {kb:.0f} KB、附件 {len(a.attach)} 個、圖 {len(a.image)} 張 → {pf}")
    if kb > 400:
        print("⚠ 提示詞超過 400 KB：Codex 可能讀不完或抓不到重點。只附這次判斷需要的檔，長檔先摘出相關段落（整段、不要切字）。")
    if a.dry_run:
        return 0
    codex = shutil.which("codex")
    if not codex:
        print("找不到 codex 指令（npm i -g @openai/codex，版本要 ≥ 0.170.0）")
        return 1
    cmd = [codex, "exec", "--skip-git-repo-check", "-m", a.model, "-c", f"model_reasoning_effort={a.effort}", "--sandbox", "read-only"]
    for im in a.image:
        cmd += ["-i", str(Path(im).resolve())]
    tmp = out / f"{a.name}_r{rnd}_review.partial"      # Codex 先寫到暫存檔，成功且有內容才改名成 _review.md
    cmd += ["-o", str(tmp.resolve()), "-"]
    tmp.unlink(missing_ok=True)
    try:
        r = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, timeout=a.timeout, cwd=str(out))
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        print(f"Codex 超過 {a.timeout} 秒沒回來（這一輪的思考強度是 {a.effort}；--timeout 可加長，high 一輪通常 3–6 分鐘）。這一輪（第 {rnd} 輪）沒有意見。")
        return 1
    log = r.stdout.decode("utf-8", "replace") + "\n--- stderr ---\n" + r.stderr.decode("utf-8", "replace")
    lf.write_text(log, encoding="utf-8", newline="\n")
    text = tmp.read_text(encoding="utf-8", errors="replace").strip() if tmp.exists() else ""
    if r.returncode != 0 or not text:      # 短短一句「可以推送」也是有效意見，只擋空的
        tmp.unlink(missing_ok=True)                   # 失敗或殘缺的不留成意見檔
        tail = log.strip().splitlines()[-6:]
        print(f"Codex 沒有回審核意見（回傳碼 {r.returncode}）。紀錄最後幾行：\n" + "\n".join(tail))
        if "not supported" in log or "model" in log.lower() and "not found" in log.lower():
            print("模型名稱不被接受時：看 ~/.codex/models_cache.json 有沒有這個模型，沒有就更新 Codex CLI。")
        return 1
    tmp.replace(rf)
    print(f"\n===== Codex 第 {rnd} 輪審核意見（{rf}）=====\n{text}\n")
    print("（回傳 0 只代表拿到意見，不代表通過。讀它的結論：有擋點就改完再送下一輪。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
