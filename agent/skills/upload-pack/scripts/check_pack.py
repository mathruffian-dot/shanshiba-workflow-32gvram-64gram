"""上架包自查：檢查 <片>/youtube/ 裡的 metadata.md 與檔案有沒有漏項。2026-11-24 建立（Codex gpt-6.2-astra 審過）。

用法（專案根目錄，要有 Pillow 的 Python，例 C:\\AI\\Voice\\venv\\Scripts\\python.exe）：
  python agent/skills/upload-pack/scripts/check_pack.py <片>/youtube
  python agent/skills/upload-pack/scripts/check_pack.py --selftest      改這支腳本之後跑：合成一份好的包，再逐項改壞，確認每一種都抓得到
回傳碼：0＝自動查得到的都沒問題；1＝有不通過；2＝沒檢查到（找不到資料夾或 metadata.md、沒有 Pillow）。
★ 回傳 0 不代表可以上架：「要人看」的項目這支查不了，一定要逐項看過。

自動查的（都是作者實際漏過的）：
  標題剛好 10 個、第 1 個標 ★；SEO 頓號版與逗號版都有、是同一批詞、15–20 個不重複、逗號版 ≤500 字元；
  社群貼文有內容、沒有表情符號；實際要貼的說明欄裡有 AI 生成標示（指名的說明欄 txt 要找得到）；
  上傳設定的瀏覽權限寫的是「私人」、「已變更或合成的內容／AI 使用」寫的是勾「是」，而且沒有互相矛盾的寫法；
  cover.png 是 1280x720；可上傳的封面（剛好 16:9）有 3 張不一樣的；
  要上傳的 srt 找得到（有寫路徑的照路徑找），每一段都有完整的起訖時間與台詞。
只能提醒人看的：說明欄主體字數與前 100 字有沒有主關鍵字、章節時間碼、社群貼文裡的網址是不是只在「第一則留言」、
  封面上的字與手、★1 標題跟選定的封面主標有沒有呼應、配樂署名、畫面裡的真人若是 H3 生成有沒有寫。
已知限制（Codex 第二十輪列的，都不擋使用；報告裡有對應的「要人看」）：
  - srt 某一段同時漏了空行與時間碼時，那一段跟上一段的多行台詞長得一樣，分不出來；台詞本身含「-->」會被誤判成有問題；
    時間碼的分、秒寫到 60 以上不會被抓。srt 都是各片的 make_srt 腳本產生、不是手打，上傳後在字幕編輯器核對段數。
  - 封面只改一小塊字或局部換色，縮圖比對可能當成同一張；所以三張封面要人看過確實是三個不同的概念。
  - 有寫路徑的檔名只在這支片的資料夾範圍內找，但資料夾配置不照「短片/<片>/…」時範圍可能偏大。
  - 標題那一行只有序號沒有字時，可能把下一行當成它的內容。
  - 回歸測試檢查的是「該抓的有抓到」，同一個壞包多報幾項不算錯。"""
import io
import re
import sys
from pathlib import Path

# 表情符號：U+1F000 以上整段都是；U+2xxx、U+3xxx 那幾段是符號與表情符號混在一起，只逐一列出真的是表情符號的字，不整段收。
# 同段裡的一般符號（⌘ ⌥ ⏎、步驟編號 ❶❷➀➁、✓ ✗、★ ☆、♪、箭頭）不算，寫教學貼文會用到。
EMOJI_BMP = ("⌚⌛⌨⏏⏩⏪⏫⏬⏭⏮⏯⏰⏱⏲⏳⏸⏹⏺"
             "☀☁☂☃☄☎☑☔☕☘☝☠☢☣☦☪☮☯☸☹☺♀♂♈♉♊♋♌♍♎♏♐♑♒♓♟♠♣♥♦♨♻♾♿⚒⚓⚔⚕⚖⚗⚙⚛⚜⚠⚡⚧⚪⚫⚰⚱⚽⚾⛄⛅⛈⛎⛏⛑⛓⛔⛩⛪⛰⛱⛲⛳⛴⛵⛷⛸⛹⛺⛽"
             "✂✅✈✉✊✋✌✍✏✒✔✖✝✡✨✳✴❄❇❌❎❓❔❕❗❣❤➕➖➗➰➿"
             "⬛⬜⭐⭕‼⁉〰〽㊗㊙")      # 箭頭 ➡ ⬅ ⬆ ⬇ 不列：「檔案 ➡ 儲存」這種步驟說明是一般用法
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0000FE0F" + EMOJI_BMP + "]")
ALLOW = set("★☆♪✓✗→←↑↓▶■□●○◆◇※")       # 明確允許的一般符號（都不在上面的清單裡，留著當說明）
IMG = (".png", ".jpg", ".jpeg")
NOT_COVER = re.compile(r"overview|總覽|compare|sheet|preview|三選一|並排|contact", re.I)
TS = r"\d{1,2}:\d\d:\d\d[,.]\d{1,3}"
SRT_LINE = re.compile(TS + r"\s*-->\s*" + TS + r"(\s.*)?")
SRT_REF = re.compile(r"([^\s`「」|（）()：:，,]+\.srt)", re.I)      # 副檔名不分大小寫
TXT_ANY = re.compile(r"([^\s`「」|（）()：:，,]+\.txt)", re.I)
# 瀏覽權限：只接受「瀏覽權限：私人」「瀏覽權限：預設私人」「預設私人」後面直接是句讀或行尾；後面接括號補充（例「私人（改為公開）」）不算
PV_OK = re.compile(r"(瀏覽權限\s*[：:]\s*(預設\s*)?|預設\s*|設成\s*|設為\s*)私人\s*([。；;，,、]|$)")
PV_BAD = re.compile(r"瀏覽權限\s*[：:]\s*(?!(預設\s*)?私人)\S|私人\s*[（(]|非私人|不是私人|尚未|還沒|改[成為]?\s*公開|設[成為]?\s*公開|[：:]\s*公開")
SY_ANY = re.compile(r"已變更或合成|合成內容|合成的內容|AI 使用")
SY_OK = re.compile(r"(已變更或合成的內容|合成的內容|合成內容|AI 使用)[^。；;]{0,12}?(勾|選|[：:])\s*是\s*([。；;，,、）)]|$)")
SY_BAD = re.compile(r"尚未|還沒|未勾|不勾|(勾|選|[：:])\s*否|是\s*[（(]")


def sections(text):
    out, cur = [], ["", []]
    for line in text.splitlines():
        if line.startswith("## "):
            out.append(cur)
            cur = [line[3:].strip(), []]
        else:
            cur[1].append(line)
    out.append(cur)
    return [(h, "\n".join(b)) for h, b in out]


def plain(s):
    return re.sub(r"[*`「」『』\[\]]", "", s)


def cover_candidates(d):
    """可上傳的封面候選：cover.png、cover_A／cover_B…、alternates/ 裡的圖。總覽圖、並排比較圖不算；不是剛好 16:9 的不算。"""
    from PIL import Image
    out, unreadable = [], []
    for p in list(d.glob("cover*.*")) + list((d / "alternates").glob("*.*")):
        if p.suffix.lower() not in IMG or NOT_COVER.search(p.stem):
            continue
        if p.parent == d and not re.fullmatch(r"cover([_\-][A-Za-z0-9]{1,3})?", p.stem):
            continue
        try:
            w, h = Image.open(p).size
        except Exception:  # noqa: BLE001  連檔頭都讀不了的圖：回報出去，不能默默跳過
            unreadable.append(p.name)
            continue
        if 9 * w == 16 * h:
            out.append(p)
    return out, unreadable


def distinct_images(paths):
    """「看起來不一樣」的圖有幾張：縮成 32x18 彩色，每個色版的平均差 < 6 當成同一張（同一張存成 png 和 jpg 只算一張；
    版面一樣、只換配色的三張會算成三張）。"""
    from PIL import Image
    sigs = []
    for p in paths:
        px = list(Image.open(p).convert("RGB").resize((32, 18)).tobytes())
        if not any(sum(abs(a - b) for a, b in zip(px, s)) / len(px) < 6 for s in sigs):
            sigs.append(px)
    return len(sigs)


def _sec(ts):
    h, m, s = re.split(":", ts.replace(",", "."))
    return int(h) * 3600 + int(m) * 60 + float(s)


def check_srt(p):
    """回傳 (正常的段數, 有問題的段數)。逐行解析、不靠空行分段。每一段要有：序號（從 1 連號）、完整的「起 --> 訖」且起 < 訖、
    至少一行台詞。序號跳號（例 1 之後直接 3）代表中間有一段漏了時間碼、被併進前一段，算有問題。"""
    lines = [x.strip() for x in p.read_text(encoding="utf-8-sig").splitlines()]
    idx = [i for i, x in enumerate(lines) if "-->" in x]
    good = bad = 0
    for k, i in enumerate(idx):
        nxt = idx[k + 1] if k + 1 < len(idx) else len(lines)
        body = [x for x in lines[i + 1:nxt] if x]
        if nxt < len(lines) and body and body[-1].isdigit():
            body = body[:-1]                      # 下一段的序號
        num = next((x for x in reversed(lines[:i]) if x), "")      # 時間碼前一個非空行應該是這一段的序號
        m = SRT_LINE.fullmatch(lines[i])
        ok = bool(m) and bool(body) and num == str(k + 1)
        if ok:
            a, b = re.findall(TS, lines[i])[:2]
            ok = _sec(a) < _sec(b)
        # 這一段的台詞裡如果出現「空行＋下一段的序號＋文字（不是時間碼）」，就是下一段漏了整行時間碼、被併進來了
        seg = lines[i + 1:nxt]
        for j in range(1, len(seg)):
            if seg[j] == str(k + 2) and seg[j - 1] == "":
                rest = [x for x in seg[j + 1:] if x]
                # 後面接的是文字（漏了時間碼）、或什麼都沒有而且已經是檔尾（只剩一個孤伶伶的序號）
                if (rest and "-->" not in rest[0]) or (not rest and nxt == len(lines)):
                    ok = False
        good, bad = good + ok, bad + (not ok)
    return good, bad


def has_path(ref):
    return "/" in ref or "\\" in ref


def file_refs(text, bare):
    """metadata 裡提到的檔名。反引號包起來的整段都算（路徑裡可以有空白）；沒有用反引號包的才用 bare 這個樣式抓。"""
    quoted = [m.strip() for m in re.findall(r"`([^`\n]+)`", text)]
    out = {q for q in quoted if bare.fullmatch(q) or (bare.search(q) and bare.search(q).end() == len(q))}
    out |= set(bare.findall(re.sub(r"`[^`\n]+`", " ", text)))
    return sorted(out)


def bases_for(d):
    """有寫路徑的檔名，相對於哪些資料夾找：youtube/ 往上到這支片（或這個系列）的資料夾為止，不跨到別支片、不出專案。"""
    out = [d]
    for q in d.parents:
        if q.name in ("短片", "試行", "教學動畫") or (q / ".git").exists() or len(out) >= 5:
            break
        out.append(q)
    return out


def resolve(d, ref):
    """metadata 裡寫的檔名 → 實際的檔。有寫路徑的照路徑找；只有檔名的只在 youtube/ 找。找不到回 None。
    找到的檔一定要在「這支片自己的資料夾」（youtube/ 的上一層）裡面。往上幾層只是為了看懂路徑怎麼寫
    （系列片常從系列資料夾寫起，例 `s2/ep8/youtube/x.srt`）；解析出來的檔如果落在別一集、別支片或專案外，一律當成找不到。"""
    bases = bases_for(d) if has_path(ref) else [d]
    top = d.parent.resolve()
    for b in bases:
        p = b / ref
        try:
            if p.is_file() and p.resolve().is_relative_to(top):
                return p
        except OSError:
            continue
    return None


def check(target):
    """回傳 (回傳碼, 結果清單)。結果清單每筆是 (通過／不通過／要人看, 項目, 說明)。"""
    d = Path(target)
    md = d / "metadata.md" if d.is_dir() else d
    d = md.parent
    if not md.is_file():
        return 2, [("沒檢查到", f"找不到 {md}", "")]
    try:
        from PIL import Image
    except ImportError:
        return 2, [("沒檢查到", "這個 Python 沒有 Pillow，封面沒辦法檢查", "改用 C:\\AI\\Voice\\venv\\Scripts\\python.exe 跑")]
    text = md.read_text(encoding="utf-8")
    secs = sections(text)
    res = []

    def find(*keys):
        return [(h, b) for h, b in secs if any(k.lower() in h.lower() for k in keys)]

    def add(ok, item, msg=""):
        res.append(("通過" if ok is True else "不通過" if ok is False else "要人看", item, msg))

    # 1 必要的節（要有內容，空的不算）
    need = {"標題": ("標題",), "說明欄": ("說明欄",), "SEO 關鍵字": ("SEO", "關鍵字"), "社群貼文": ("社群", "臉書", "Facebook", "FB", "Threads"),
            "上傳設定／上架檢查": ("上傳設定", "checklist", "上傳前檢查", "上架檢查")}
    def real_len(body):
        """這一節真正的內容有多少字：只有粗體小標的行、「待補／TODO」這種佔位字不算。"""
        keep = [x for x in body.splitlines() if not re.fullmatch(r"\s*\*\*[^*]+\*\*\s*", x)]
        return len(re.sub(r"\s|待補|TODO|todo|（待[^）]*）", "", "".join(keep)))

    for name, keys in need.items():
        got = find(*keys)
        add(bool(got) and sum(real_len(b) for _, b in got) >= 20, f"有「{name}」這一節而且有內容")

    # 2 標題：剛好 10 個，第 1 個標 ★
    t = find("標題")
    if t:
        items = re.findall(r"^\s*(\d+)[\.、]\s*(\S.*)$", t[0][1], re.M)
        short = [n for n, x in items if len(re.sub(r"[★\s*`]", "", x)) < 2]      # 只擋空的（只有 ★ 或一個字）；短標題如「明天會下雨」是可以的
        add(len(items) == 10 and not short, "標題剛好 10 個、每個都有寫", f"找到 {len(items)} 個" + (f"；空的：第 {'、'.join(short)} 個" if short else ""))
        add(bool(items) and items[0][0] == "1" and "★" in items[0][1], "第 1 個標題標 ★（建議用的那一個）")
        add(None, "★1 標題跟「選定的」封面主標呼應", "使用者改選封面後要重看這一條")

    # 3 SEO：頓號版＋逗號版，同一批詞、不重複
    s = find("SEO", "關鍵字")
    if s:
        body = s[0][1]
        dun_lines = [x.strip() for x in body.splitlines() if x.count("、") >= 5]
        com_lines = [x.strip() for x in body.splitlines() if x.count(",") + x.count("，") >= 5 and x.count("、") < 3]
        com = [k.strip() for k in re.split(r"[,，]", re.sub(r"^[^,，]{0,12}[：:]\s*", "", max(com_lines, key=len))) if k.strip()] if com_lines else []
        dun = [k.strip() for k in re.sub(r"^[^、]{0,12}[：:]\s*", "", max(dun_lines, key=len)).split("、") if k.strip()] if dun_lines else []
        add(bool(dun), "SEO 有頓號版")
        add(bool(com), "SEO 有「全部一次貼」的逗號版")
        if com:
            add(15 <= len(set(com)) <= 20 and len(set(com)) == len(com), "SEO 關鍵字 15–20 個、沒有重複", f"逗號版 {len(com)} 個、不重複的 {len(set(com))} 個")
            add(len(",".join(com)) <= 500, "逗號版 ≤500 字元（YouTube 標籤欄上限）", f"{len(','.join(com))} 字元")
        if com and dun:
            diff = sorted(set(dun) ^ set(com))
            add(not diff and len(dun) == len(set(dun)) == len(com), "頓號版與逗號版是同一批詞、都沒有重複",
                f"頓號版 {len(dun)} 個、逗號版 {len(com)} 個" + (f"；對不上的：{'、'.join(diff[:8])}" if diff else ""))

    # 4 社群貼文
    soc = find("社群", "臉書", "Facebook", "FB", "Threads")
    if soc:
        body = "\n".join(b for _, b in soc)
        # 貼文正文要真的有寫：照粗體小標分段，「留言」那幾段不算正文；剩下的去掉網址、hashtag 行之後還要有 30 個字（正常的貼文 150 字以上）
        segs, cur_label, cur = [], "", []
        for x in body.splitlines():
            m = re.fullmatch(r"\s*\*\*([^*]+)\*\*.*", x)
            if m:
                segs.append((cur_label, cur))
                cur_label, cur = m.group(1), []
            else:
                cur.append(x)
        segs.append((cur_label, cur))
        post = "\n".join(x for lab, ls in segs if "留言" not in lab and "回覆" not in lab for x in ls if not x.strip().startswith("#"))
        add(real_len(re.sub(r"https?://\S+", "", post)) >= 30, "社群貼文有正文（留言、回覆那幾段不算）")
        em = sorted({c for c in EMOJI.findall(body) if c not in ALLOW})
        add(not em, "社群貼文沒有表情符號", "找到：" + " ".join(em) if em else "")
        if re.findall(r"https?://\S+", body):
            add(None, "社群貼文裡的網址只在「第一則留言」那一段", "確認貼文本文沒有（臉書本文放連結會降觸及）")
        add(None, "FB／IG 貼文 150–200 字、每段 ≤3 行、結尾一個互動問題", "數一次字數")

    # 5 AI 標示：只認「實際要貼的說明欄」——metadata 指名的說明欄 txt（缺檔算不通過）；沒有指名 txt 才看本頁的說明欄一節
    # 哪些 txt 是「說明欄」：檔名有「說明欄」的、寫在「說明欄」一節裡的、或跟「說明欄」寫在同一行的（檔案表那一列）
    near = "\n".join([b for _, b in find("說明欄")] + [x for x in text.splitlines() if "說明欄" in x])
    named_txt = sorted({n for n in file_refs(text, TXT_ANY) if "說明欄" in Path(n).name} | set(file_refs(near, TXT_ANY)))
    got_txt = {n: resolve(d, n) for n in named_txt}
    ok_txt = {Path(n).name for n, p in got_txt.items() if p is not None and has_path(n)}
    txts = [p for p in got_txt.values() if p is not None]
    # 只寫檔名的那一種，如果同一個檔名在別處寫了完整路徑而且找得到，就是同一個檔
    lost = [n for n, p in got_txt.items() if p is None and not (not has_path(n) and n in ok_txt)]
    if lost:
        add(False, "metadata 指名的說明欄 txt 找得到", "找不到：" + "、".join(lost))
    # 要有聲明本身：講「本片／全片」是 AI 生成的那一句。只有「AI 使用聲明」小標、或內容剛好提到 AI 生成（例「教你辨識 AI 生成圖片」）都不算
    # 句型照實際用過的聲明：「本片……（皆）由／都是／為 AI 生成」或「全片 AI 生成」。「本片教你辨識 AI 生成圖片」這種介紹句不算
    # 「本片」和「由 AI 生成」之間只能是在列舉片子的哪些部分（畫面、影片、配音…），不能有動詞——
    # 「本片教你判斷一張照片是否由 AI 生成」是課程介紹，不是聲明。範本裡固定的寫法：「本片畫面、影片與配音皆由 AI 生成，非真人演出。」
    part = r"(畫面|影片|影像|圖像|圖片|動畫|首幀|封面|聲音|音效|配音|對白|台詞|旁白|口白|歌曲|歌聲|歌|音樂|配樂|人物|角色|主持人|片例|素材|字幕|內容|全部|所有)"
    ai = re.compile(r"(本片|全片|本影片|這支影片|這支片)(的)?(" + part + r"|[、，,與及和])*\s*(皆|都|均|全)?(由|是|為)\s*AI\s*(生成|製作|產生)|全片\s*AI\s*(生成|製作|產生)")
    if named_txt:
        # 指名了幾份說明欄 txt，就每一份都要有（草稿有寫、實際上傳那份漏寫，不能算有）
        no_ai = [p.name for p in sorted(set(txts)) if not ai.search(p.read_text(encoding="utf-8"))]
        add(bool(txts) and not no_ai, "實際要貼的說明欄裡有 AI 生成標示", ("沒有標示的：" + "、".join(no_ai)) if no_ai else f"查的是：{'、'.join(named_txt)}（社群貼文裡寫的不算）")
        add(None, "另存的說明欄 txt 跟本頁「說明欄」一節講的是同一份", "、".join(named_txt))
    else:
        add(bool(ai.search("\n".join(b for _, b in find("說明欄")))), "實際要貼的說明欄裡有 AI 生成標示", "查的是：本頁「說明欄」一節（社群貼文裡寫的不算）")

    # 6 上傳設定：解析實際寫的值，有矛盾的寫法也算不通過
    # 一行裡常寫好幾個欄位（「瀏覽權限：私人。觀眾：非兒童內容。合成的內容：勾是。」），照句號、分號切開，一個欄位一個欄位看，
    # 不然「兒童內容：否」會被當成「合成的內容：否」
    up = [c for _, b in find("上傳設定", "checklist", "上傳前檢查", "上架檢查") for x in b.splitlines() for c in re.split(r"[。；;]", plain(x)) if c.strip()]
    pv = [x for x in up if "私人" in x or "瀏覽權限" in x]
    pv_ok, pv_bad = [x for x in pv if PV_OK.search(x)], [x for x in pv if PV_BAD.search(x)]
    # 切開之後，「改為公開」「設成公開」這種指示可能自己成一句（「瀏覽權限：私人。改為公開。」），也算矛盾
    pv_bad += [x for x in up if x not in pv and re.search(r"(改|設|換|調)[成為]?\s*公開|直接公開|公開發[布佈]", x) and "先問" not in x and "不要" not in x]
    add(bool(pv_ok) and not pv_bad, "上傳設定的瀏覽權限寫的是「私人」",
        f"矛盾或不是私人：{pv_bad[0].strip()[:40]}" if pv_bad else "" if pv_ok else "沒有寫「瀏覽權限：私人」或「預設私人」")
    sy = [x for x in up if SY_ANY.search(x)]
    sy_ok, sy_bad = [x for x in sy if SY_OK.search(x)], [x for x in sy if SY_BAD.search(x)]
    add(bool(sy_ok) and not sy_bad, "上傳設定寫的是「已變更或合成的內容」勾是",
        f"矛盾或不是「是」：{sy_bad[0].strip()[:40]}" if sy_bad else "" if sy_ok else "沒有寫這一項勾「是」")

    # 7 封面
    cover = d / "cover.png"
    if cover.is_file():
        try:
            w, h = Image.open(cover).size
            add((w, h) == (1280, 720), "cover.png 是 1280x720", f"{w}x{h}")
        except Exception as e:  # noqa: BLE001
            add(False, "cover.png 讀得了", f"{type(e).__name__}")
    else:
        add(False, "有 cover.png（使用者選定的那一張）", "還沒選就先放推薦的，metadata 註明「使用者還沒選」")
    cands, broken = cover_candidates(d)           # broken：連檔頭都讀不了的
    for p in list(cands):                         # 檔頭讀得到、像素資料壞掉的圖：也列為不通過，不讓程式中斷
        try:
            Image.open(p).convert("L").resize((32, 18)).tobytes()
        except Exception:  # noqa: BLE001
            broken.append(p.name)
            cands.remove(p)
    if broken:
        add(False, "封面圖檔都讀得了", "壞掉的：" + "、".join(broken))
    n = distinct_images(cands)
    add(n >= 3, "可上傳的封面有 3 張不一樣的", f"候選 {len(cands)} 個檔（剛好 16:9 的），看起來不一樣的 {n} 張（總覽圖、同一張存兩份都不算）")

    # 8 字幕：metadata 指名的 srt 要找得到。有寫路徑的照路徑找（不讓 youtube/ 裡的同名舊檔頂替）；只有檔名的在 youtube/ 找
    refs = file_refs(text, SRT_REF)
    found = {}
    for ref in refs:
        found[ref] = resolve(d, ref)
    ok_names = {Path(r).name for r, p in found.items() if p is not None and has_path(r)}
    # 只寫檔名的那一種，如果同一個檔名在別處寫了完整路徑而且找得到，就是同一個檔
    missing = [r for r, p in found.items() if p is None and not (not has_path(r) and r in ok_names)]
    srts = sorted({p for p in found.values() if p})
    if not refs:
        # metadata 完全沒提到 srt 時，才看 youtube/ 裡有什麼；一樣要真的在這支片的資料夾裡（連到別一集的捷徑不算）
        srts = sorted(p for p in d.glob("*.srt") if p.is_file() and p.resolve().is_relative_to(d.parent.resolve()))      # is_file：名字叫 x.srt 的資料夾、斷掉的連結不算
    if missing:
        add(False, "metadata 指名的 srt 找得到", "找不到：" + "、".join(missing[:3]))
    if not srts and not missing:
        add(False, "有 srt 字幕", "youtube/ 裡沒有，metadata 也沒有指到別處的 srt")
    for p in srts:
        good, bad = check_srt(p)
        add(good >= 1 and bad == 0, f"srt 每一段都有完整的起訖時間與台詞：{p.name}", f"{good} 段正常、{bad} 段有問題")

    add(None, "封面逐字看過（含字形）、手指數與左右手、縮到 320x180 主標還清楚")
    add(None, "說明欄主體 ≤300 字、前 100 字有主關鍵字、章節時間碼對過成片且第一章 0:00、結尾有 AI 聲明與 hashtag")
    add(None, "用了 MiniMax Music 3／Suno 的有寫配樂與歌的來源；畫面裡的真人若是 H3 生成的有寫")
    add(None, "srt 的段數跟成片的字幕句數對得上（上傳後在字幕編輯器看一眼）；三張封面是三個不同的概念")
    return (1 if any(r[0] == "不通過" for r in res) else 0), res


def tally(res):
    """各種結果各有幾筆（直接數，不用相減）。"""
    return {st: sum(r[0] == st for r in res) for st in ("沒檢查到", "不通過", "要人看", "通過")}


def report(target, rc, res):
    for st in ("沒檢查到", "不通過", "要人看", "通過"):
        for r in res:
            if r[0] == st:
                print(f"[{st}] {r[1]}" + (f"　—　{r[2]}" if r[2] else ""))
    n = tally(res)
    if n["沒檢查到"]:
        print(f"\n{target}：沒檢查到（回傳 2），這份上架包一項都還沒查")
    else:
        print(f"\n{target}：不通過 {n['不通過']}、要人看 {n['要人看']}（這支查不了，逐項看過才算完成）、通過 {n['通過']}")


# ---------- 自我測試：合成一份好的包，再逐項改壞 ----------
GOOD_MD = """# 〈測試片〉上架資料

## 檔案

| 項目 | 檔案 | 規格 |
|:---|:---|:---|
| 字幕 | `測試片_v1.srt` | 2 句 |
| 說明欄 | `說明欄_含免責聲明.txt` | 整份貼進說明欄 |

## 標題（10 個）

1. ★ 第一個標題，跟封面主標呼應
2. 第二個測試用的標題
3. 第三個測試用的標題
4. 第四個測試用的標題
5. 第五個測試用的標題
6. 第六個測試用的標題
7. 第七個測試用的標題
8. 第八個測試用的標題
9. 第九個測試用的標題
10. 第十個測試用的標題

## 說明欄

全文在 `說明欄_含免責聲明.txt`。這裡寫說明欄的重點與章節安排，內容取自成片台詞。

## SEO 關鍵字（15 個）

詞一、詞二、詞三、詞四、詞五、詞六、詞七、詞八、詞九、詞十、詞十一、詞十二、詞十三、詞十四、詞十五

```
詞一,詞二,詞三,詞四,詞五,詞六,詞七,詞八,詞九,詞十,詞十一,詞十二,詞十三,詞十四,詞十五
```

## 社群貼文

**Facebook／Instagram**

這是一則測試貼文，本文不放連結，結尾問一個問題：你會怎麼選？連結放在留言。

## 上傳設定

- 瀏覽權限：**私人**。觀眾：非兒童內容。「已變更或合成的內容」：勾**是**。
- 字幕：上傳 `測試片_v1.srt`，語言選中文（台灣）。
"""
GOOD_SRT = "1\n00:00:01,000 --> 00:00:02,000\n第一句\n\n2\n00:00:03,000 --> 00:00:04,500\n第二句\n"


def selftest():
    import shutil
    import tempfile
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("ERROR：這個 Python 沒有 Pillow，selftest 沒辦法跑。改用 C:\\AI\\Voice\\venv\\Scripts\\python.exe。")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="check_pack_selftest_"))
    ok = True

    def build(name):
        d = tmp / "短片" / name / "youtube"       # 跟專案一樣放在「短片/<片>/youtube」，往上找檔只會找到這支片的資料夾為止
        d.mkdir(parents=True)
        (d / "metadata.md").write_text(GOOD_MD, encoding="utf-8")
        (d / "測試片_v1.srt").write_text(GOOD_SRT, encoding="utf-8")
        (d / "說明欄_含免責聲明.txt").write_text("這是說明欄全文。\n本片為 AI 生成內容。配樂：MiniMax-Music3。\n", encoding="utf-8")
        for i, col in enumerate(((200, 40, 40), (40, 160, 60), (40, 60, 200))):
            im = Image.new("RGB", (1280, 720), col)
            ImageDraw.Draw(im).rectangle([100 + 300 * i, 100, 500 + 300 * i, 600], fill=(255, 255, 255))
            im.save(d / f"cover_{'ABC'[i]}.jpg")
            if i == 1:
                im.save(d / "cover.png")
        return d

    def edit(d, a, b, n=1):
        p = d / "metadata.md"
        t = p.read_text(encoding="utf-8")
        assert t.count(a) == n, (a, t.count(a))
        p.write_text(t.replace(a, b), encoding="utf-8")

    def expect(label, d, want_bad):
        """want_bad：應該出現在「不通過」項目名稱裡的關鍵字清單；空清單＝應該 0 不通過。"""
        nonlocal ok
        rc, res = check(d)
        bad = [r[1] for r in res if r[0] == "不通過"]
        good = (not want_bad and not bad and rc == 0) or (want_bad and rc == 1 and all(any(k in b for b in bad) for k in want_bad))
        ok &= bool(good)
        print(("  OK  " if good else "  FAIL") + f" {label}：不通過 {len(bad)} 項" + ("" if good else f" → {bad}（應含 {want_bad}）"))

    try:
        expect("好的包", build("good"), [])
        d = build("star10"); edit(d, "1. ★ 第一個標題", "1. 第一個標題"); edit(d, "10. 第十個測試用的標題", "10. ★ 第十個測試用的標題"); expect("★ 標在第 10 個", d, ["第 1 個標題標 ★"])
        d = build("t9"); edit(d, "10. 第十個測試用的標題\n", ""); expect("標題只有 9 個", d, ["標題剛好 10 個"])
        d = build("nodun"); edit(d, "詞一、詞二、詞三、詞四、詞五、詞六、詞七、詞八、詞九、詞十、詞十一、詞十二、詞十三、詞十四、詞十五\n", ""); expect("沒有頓號版", d, ["頓號版"])
        d = build("dup"); edit(d, "詞十四,詞十五", "詞十四,詞一"); expect("逗號版用重複的詞湊數", d, ["沒有重複"])
        d = build("diff"); edit(d, "詞十三、詞十四、詞十五", "詞十三"); expect("頓號版 13 個對逗號版 15 個", d, ["同一批詞"])
        d = build("emoji"); edit(d, "你會怎麼選？", "你會怎麼選？😀"); expect("社群貼文有表情符號", d, ["表情符號"])
        d = build("ai"); (d / "說明欄_含免責聲明.txt").write_text("沒有標示的說明欄", encoding="utf-8"); (d / "社群草稿.txt").write_text("全片 AI 生成", encoding="utf-8")
        expect("說明欄 txt 沒有 AI 標示（別的 txt 有）", d, ["AI 生成標示"])
        d = build("txtlost"); (d / "說明欄_含免責聲明.txt").unlink(); edit(d, "內容取自成片台詞。", "內容取自成片台詞。本片為 AI 生成內容。")
        expect("指名的說明欄 txt 不見了（本頁有 AI 標示也不行）", d, ["說明欄 txt 找得到"])
        d = build("pub1"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：公開（原為私人）。"); expect("瀏覽權限：公開（原為私人）", d, ["瀏覽權限"])
        d = build("pub2"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：**私人**（改為公開）。"); expect("瀏覽權限：私人（改為公開）", d, ["瀏覽權限"])
        d = build("pub3"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：非私人。"); expect("瀏覽權限：非私人", d, ["瀏覽權限"])
        d = build("pub4"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：**私人**。改為公開。"); expect("瀏覽權限：私人。改為公開。（分成兩句）", d, ["瀏覽權限"])
        d = build("pub5"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：**私人**。要改成公開之前先問使用者。"); expect("瀏覽權限：私人。要改成公開之前先問使用者。（應該通過）", d, [])
        d = build("syn1"); edit(d, "：勾**是**。", "：否。"); expect("合成的內容：否", d, ["已變更或合成"])
        d = build("syn2"); edit(d, "：勾**是**。", "：尚未勾是。"); expect("合成的內容：尚未勾是", d, ["已變更或合成"])
        d = build("syn3"); edit(d, "「已變更或合成的內容」：勾**是**。", ""); expect("沒有寫合成的內容那一項", d, ["已變更或合成"])
        d = build("syshort"); edit(d, "「已變更或合成的內容」：勾**是**。", "合成的內容：勾是。"); expect("寫成「合成的內容：勾是」（應該通過）", d, [])
        d = build("threads"); edit(d, "## 社群貼文", "## Threads"); edit(d, "**Facebook／Instagram**\n\n", ""); expect("社群那一節的標題只寫 Threads（應該通過）", d, [])
        d = build("sameline"); edit(d, "- 瀏覽權限：**私人**。觀眾：非兒童內容。「已變更或合成的內容」：勾**是**。", "- 瀏覽權限：私人。兒童內容：否。已變更或合成的內容：勾是。")
        expect("同一行寫「兒童內容：否。已變更或合成的內容：勾是。」（應該通過）", d, [])
        d = build("covbroken"); raw = (d / "cover_C.jpg").read_bytes(); (d / "cover_C.jpg").write_bytes(raw[:len(raw) // 3])
        expect("第三張封面檔頭完整、像素資料截斷", d, ["封面圖檔都讀得了"])
        d = build("covD"); (d / "cover_D.jpg").write_bytes(b"not an image at all")
        expect("三張好的封面之外多一張檔頭壞掉的 cover_D.jpg", d, ["封面圖檔都讀得了"])
        d = build("covhue")
        for nm, col in (("cover_A.jpg", (255, 0, 0)), ("cover_B.jpg", (0, 150, 0)), ("cover_C.jpg", (0, 0, 255))):
            im = Image.new("RGB", (1280, 720), (128, 128, 128)); ImageDraw.Draw(im).rectangle([200, 150, 1080, 570], fill=col); im.save(d / nm)
        Image.open(d / "cover_B.jpg").save(d / "cover.png")
        expect("三張封面版面一樣、只有配色不同（應該通過）", d, [])
        d = build("cov2"); (d / "cover_C.jpg").unlink(); shutil.copy(d / "cover_A.jpg", d / "cover_overview.jpg"); shutil.copy(d / "cover_B.jpg", d / "封面總覽.jpg")
        expect("只有兩張不同的封面＋總覽圖", d, ["3 張不一樣"])
        d = build("cov169"); (d / "cover_C.jpg").unlink(); Image.new("RGB", (1700, 1000), (10, 200, 200)).save(d / "cover_C.jpg"); expect("第三張是 1700x1000", d, ["3 張不一樣"])
        d = build("covsz"); Image.new("RGB", (1920, 1080), (40, 160, 60)).save(d / "cover.png"); expect("cover.png 是 1920x1080", d, ["1280x720"])
        d = build("srt1"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n\n2\n00:00:03,000 --> 00:00:04,000\n有台詞\n", encoding="utf-8")
        expect("srt 有一段只有時間碼", d, ["srt 每一段"])
        d = build("srt2"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n2\n00:00:03,000 --> 00:00:04,000\n有台詞\n", encoding="utf-8")
        expect("srt 兩段之間漏空行、第一段沒有台詞", d, ["srt 每一段"])
        d = build("srt3"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 -->\n有台詞\n", encoding="utf-8"); expect("srt 沒有結束時間", d, ["srt 每一段"])
        d = build("srt4"); (d / "測試片_v1.srt").write_text("", encoding="utf-8"); expect("srt 是空檔", d, ["srt 每一段"])
        d = build("srt5"); edit(d, "`測試片_v1.srt` | 2 句", "`cut/測試片_v1.srt` | 2 句"); expect("指名 cut/ 底下的 srt 不存在（youtube/ 有同名舊檔）", d, ["srt 找得到"])
        d = build("srt6"); (d / "測試片_v1.srt").unlink(); expect("指名的 srt 不見了", d, ["srt 找得到"])
        d = build("srt7"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一句\n\n2\n第二句（這一段漏了時間碼）\n\n3\n00:00:05,000 --> 00:00:06,000\n第三句\n", encoding="utf-8")
        expect("srt 中間一段漏了整行時間碼", d, ["srt 每一段"])
        d = build("srt8"); (d / "測試片_v1.srt").write_text("1\n00:00:05,000 --> 00:00:02,000\n起訖寫反\n", encoding="utf-8"); expect("srt 起訖時間寫反", d, ["srt 每一段"])
        d = build("srt9"); edit(d, "`測試片_v1.srt` | 2 句", "`cut/測試片_v1.srt` | 2 句"); other = tmp / "短片" / "cut"; other.mkdir(exist_ok=True); (other / "測試片_v1.srt").write_text(GOOD_SRT, encoding="utf-8")
        edit(d, "上傳 `測試片_v1.srt`", "上傳 `cut/測試片_v1.srt`"); (d / "測試片_v1.srt").unlink()
        expect("指名 cut/ 底下的 srt：這支片沒有，片資料夾外面有同路徑的舊檔", d, ["srt 找得到"])
        d = build("srt10"); edit(d, "`測試片_v1.srt` | 2 句", "`cut/測試片_v1.srt` | 2 句"); edit(d, "上傳 `測試片_v1.srt`", "上傳 `cut/測試片_v1.srt`")
        (d.parent / "cut").mkdir(); shutil.move(str(d / "測試片_v1.srt"), str(d.parent / "cut" / "測試片_v1.srt"))
        expect("指名 cut/ 底下的 srt：在這支片自己的 cut/ 裡（應該通過）", d, [])
        d = build("txtname"); edit(d, "| 說明欄 | `說明欄_含免責聲明.txt` |", "| 說明欄 | `description.txt` |"); edit(d, "全文在 `說明欄_含免責聲明.txt`。", "全文在 `description.txt`。本片畫面與配音皆由 AI 生成。")
        expect("說明欄一節指名 description.txt 但檔案不存在（本頁有聲明也不行）", d, ["說明欄 txt 找得到"])
        d = build("txtname2"); edit(d, "| 說明欄 | `說明欄_含免責聲明.txt` |", "| 說明欄 | `description.txt` |"); edit(d, "全文在 `說明欄_含免責聲明.txt`。", "全文在 `description.txt`。")
        shutil.move(str(d / "說明欄_含免責聲明.txt"), str(d / "description.txt")); expect("說明欄另存成 description.txt 而且有聲明（應該通過）", d, [])
        d = build("txtcase"); edit(d, "| 說明欄 | `說明欄_含免責聲明.txt` |", "| 說明欄 | `description.TXT` |"); edit(d, "全文在 `說明欄_含免責聲明.txt`。", "全文在 `description.TXT`。本片畫面與配音皆由 AI 生成。")
        expect("說明欄一節指名 description.TXT（大寫副檔名）但檔案不存在", d, ["說明欄 txt 找得到"])
        d = build("srtcase"); edit(d, "`測試片_v1.srt` | 2 句", "`測試片_v2.SRT` | 2 句"); edit(d, "上傳 `測試片_v1.srt`", "上傳 `測試片_v2.SRT`"); expect("指名 .SRT（大寫副檔名）但檔案不存在", d, ["srt 找得到"])
        d = build("txtpath"); edit(d, "| 說明欄 | `說明欄_含免責聲明.txt` |", "| 說明欄 | `新版/說明欄_含免責聲明.txt` |"); edit(d, "全文在 `說明欄_含免責聲明.txt`。", "全文在 `新版/說明欄_含免責聲明.txt`。")
        expect("指名 新版/ 底下的說明欄 txt 不存在（youtube/ 有同名舊檔）", d, ["說明欄 txt 找得到"])
        d = build("pvdef"); edit(d, "瀏覽權限：**私人**。", "瀏覽權限：預設私人。"); expect("瀏覽權限：預設私人（應該通過）", d, [])
        d = build("socurl"); edit(d, "這是一則測試貼文，本文不放連結，結尾問一個問題：你會怎麼選？連結放在留言。", "**第一則留言**\n\nYouTube：https://youtu.be/xxxxxxxxxxx\n課程頁：https://example.com/lesson")
        expect("社群貼文只剩第一則留言與網址", d, ["社群貼文有正文"])
        d = build("aihead"); (d / "說明欄_含免責聲明.txt").write_text("這是說明欄全文。\n【AI 使用聲明】\n\n#標籤", encoding="utf-8"); expect("說明欄只有「AI 使用聲明」小標、沒有聲明", d, ["AI 生成標示"])
        d = build("t1short"); edit(d, "1. ★ 第一個標題，跟封面主標呼應", "1. ★ 明天會下雨"); expect("第 1 個標題只有五個字（應該通過）", d, [])
        d = build("t1empty"); edit(d, "1. ★ 第一個標題，跟封面主標呼應", "1. ★"); expect("第 1 個標題只有 ★ 沒有字", d, ["標題剛好 10 個"])
        d = build("soccmt"); edit(d, "這是一則測試貼文，本文不放連結，結尾問一個問題：你會怎麼選？連結放在留言。",
                                  "**第一則留言**\n\n這門課一共五集，從一張圖做到一支片，每一集都有作業與講義可以下載，歡迎老師帶著學生一起做。https://example.com/lesson")
        expect("社群貼文沒有正文，但第一則留言寫了一段課程介紹", d, ["社群貼文有正文"])
        d = build("aitopic"); (d / "說明欄_含免責聲明.txt").write_text("本集教你辨識 AI 生成圖片的三個方法。\n#標籤", encoding="utf-8")
        expect("說明欄只是內容提到 AI 生成，沒有本片的聲明", d, ["AI 生成標示"])
        d = build("aitopic2"); (d / "說明欄_含免責聲明.txt").write_text("本片教你辨識 AI 生成圖片的三個方法。\n#標籤", encoding="utf-8")
        expect("說明欄寫「本片教你辨識 AI 生成圖片」，不是聲明", d, ["AI 生成標示"])
        d = build("aitopic3"); (d / "說明欄_含免責聲明.txt").write_text("本片教你判斷一張照片是否由 AI 生成。\n#標籤", encoding="utf-8")
        expect("說明欄寫「本片教你判斷一張照片是否由 AI 生成」，不是聲明", d, ["AI 生成標示"])
        d = build("clock"); edit(d, "你會怎麼選？", "你會怎麼選？⏰ 明晚八點首播"); expect("社群貼文有 ⏰", d, ["表情符號"])
        d = build("cmdkey"); edit(d, "你會怎麼選？", "你會怎麼選？在 Mac 上按 ⌘＋Z 復原，按 ⏎ 送出。"); expect("社群貼文有 ⌘ 與 ⏎（一般符號，應該通過）", d, [])
        d = build("steps"); edit(d, "你會怎麼選？", "你會怎麼選？❶ 開啟檔案，❷ 按下儲存，➀ 再確認一次 ✓"); expect("社群貼文有步驟編號 ❶❷➀ 與 ✓（一般符號，應該通過）", d, [])
        d = build("heart"); edit(d, "你會怎麼選？", "你會怎麼選？❤"); expect("社群貼文有 ❤", d, ["表情符號"])
        d = build("face"); edit(d, "你會怎麼選？", "你會怎麼選？🤣"); expect("社群貼文有笑到流淚的臉（U+1F923）", d, ["表情符號"])
        d = build("arrows"); edit(d, "你會怎麼選？", "你會怎麼選？檔案 ➡ 儲存，⬆ 回到最上面，→ 下一步"); expect("社群貼文有箭頭 ➡ ⬆ →（一般用法，應該通過）", d, [])
        d = build("star2"); edit(d, "你會怎麼選？", "你會怎麼選？⭐"); expect("社群貼文有 ⭐", d, ["表情符號"])
        for k, s in enumerate(("本片的影像與聲音由 AI 生成。", "本片的影像、歌曲與人物皆由 AI 生成，人物為虛構角色。", "本片為 AI 生成內容。",
                               "本片畫面、音效與配音皆由 AI 生成，非真人演出。", "本片的動畫、旁白、配樂與主持人影像皆由 AI 生成。")):
            d = build(f"aiok2{k}"); (d / "說明欄_含免責聲明.txt").write_text("說明欄全文。\n" + s, encoding="utf-8")
            expect(f"實際用過的聲明句型 {k + 4}（應該通過）", d, [])
        for k, s in enumerate(("本片畫面、影片與配音皆由 AI 生成，非真人演出。", "本片的片例、角色都是 AI 生成，不是真人演出。", "（全片 AI 生成）")):
            d = build(f"aiok{k}"); (d / "說明欄_含免責聲明.txt").write_text("說明欄全文。\n" + s, encoding="utf-8")
            expect(f"實際用過的聲明句型 {k + 1}（應該通過）", d, [])
        d = build("srt13"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一句\n2\n最後一段同時漏了空行與時間碼\n", encoding="utf-8")
        expect("srt 最後一段同時漏空行與時間碼（這支分不出來，列為已知限制）", d, [])
        d = build("srt14"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一行\n2\n第三行\n\n2\n00:00:03,000 --> 00:00:04,000\n第二段\n", encoding="utf-8")
        expect("srt 多行台詞裡恰有一行等於下一段序號（應該通過）", d, [])
        d = build("srt15"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一句\n\n2\n", encoding="utf-8")
        expect("srt 檔尾只剩一個孤伶伶的序號 2", d, ["srt 每一段"])
        d = build("srt11"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一句\n\n2\n最後一段漏了時間碼\n", encoding="utf-8")
        expect("srt 最後一段漏了整行時間碼", d, ["srt 每一段"])
        d = build("srt12"); (d / "測試片_v1.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\n第一行\n第二行\n3\n還是第一段的台詞\n\n2\n00:00:03,000 --> 00:00:04,000\n第二段\n", encoding="utf-8")
        expect("srt 多行字幕、台詞裡有一行數字（應該通過）", d, [])
        d = build("srtsp"); edit(d, "`測試片_v1.srt` | 2 句", "`新版 A/測試片_v1.srt` | 2 句"); edit(d, "上傳 `測試片_v1.srt`", "上傳 `新版 A/測試片_v1.srt`")
        (d / "A").mkdir(); shutil.copy(d / "測試片_v1.srt", d / "A" / "測試片_v1.srt")
        expect("指名「新版 A/」底下的 srt 不存在（A/ 與 youtube/ 有同名舊檔）", d, ["srt 找得到"])
        d = build("txt2"); edit(d, "全文在 `說明欄_含免責聲明.txt`。", "全文在 `說明欄_含免責聲明.txt`，草稿在 `說明欄_草稿.txt`。")
        (d / "說明欄_草稿.txt").write_text("本片為 AI 生成內容。", encoding="utf-8"); (d / "說明欄_含免責聲明.txt").write_text("實際上傳版，漏了標示。", encoding="utf-8")
        expect("兩份說明欄 txt：草稿有 AI 標示、實際上傳版沒有", d, ["AI 生成標示"])
        d = build("soc"); edit(d, "這是一則測試貼文，本文不放連結，結尾問一個問題：你會怎麼選？連結放在留言。", "待補"); expect("社群貼文是空的", d, ["社群貼文"])
        rc, res0 = check(tmp / "nope")
        good = rc == 2 and tally(res0)["通過"] == 0 and tally(res0)["沒檢查到"] == 1
        ok &= good
        print(("  OK  " if good else "  FAIL") + f" 路徑不存在：回傳 {rc}、通過 {tally(res0)['通過']} 筆")
        # 指名的字幕用「..」指到別支片的檔：不能拿別支片的檔來判通過
        other = build("otherfilm")
        d = build("escape"); (d / "測試片_v1.srt").unlink()
        edit(d, "`測試片_v1.srt` | 2 句", "`../../otherfilm/youtube/測試片_v1.srt` | 2 句"); edit(d, "上傳 `測試片_v1.srt`", "上傳 `../../otherfilm/youtube/測試片_v1.srt`")
        expect("指名的 srt 用 .. 指到別支片的檔", d, ["srt 找得到"])
        # 同一個系列的兩集：路徑從系列資料夾寫起。指到自己這一集的可以；指到另一集的不行
        a_ = build("series/ep1"); b_ = build("series/ep2")
        edit(a_, "`測試片_v1.srt` | 2 句", "`ep1/youtube/測試片_v1.srt` | 2 句"); edit(a_, "上傳 `測試片_v1.srt`", "上傳 `ep1/youtube/測試片_v1.srt`")
        expect("系列片：路徑從系列資料夾寫起、指到自己這一集（應該通過）", a_, [])
        (b_ / "測試片_v1.srt").unlink()
        edit(b_, "`測試片_v1.srt` | 2 句", "`ep1/youtube/測試片_v1.srt` | 2 句"); edit(b_, "上傳 `測試片_v1.srt`", "上傳 `ep1/youtube/測試片_v1.srt`")
        expect("系列片：第 2 集指名的是第 1 集的字幕", b_, ["srt 找得到"])
        # 字幕檔編碼壞掉（時間碼還在、台詞是壞位元組）：讀檔失敗要讓整次檢查回傳 2，不能當成正常
        d = build("srtenc"); (d / "測試片_v1.srt").write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\n\xff\xfe\xfa\xfb\n")
        try:
            check(d)
            good = False
        except UnicodeDecodeError:
            good = True          # main() 會接住這個例外、印原因、回傳 2
        ok &= good
        print(("  OK  " if good else "  FAIL") + " 字幕檔不是合法的 UTF-8：檢查中止（主程式回傳 2）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest " + ("全部通過" if ok else "有失敗"))
    return 0 if ok else 1


def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    if sys.argv[1] == "--selftest":
        return selftest()
    try:
        rc, res = check(sys.argv[1])
    except Exception as e:  # noqa: BLE001  讀檔失敗（被鎖住、權限、編碼）不要整支當掉，照「沒檢查到」回報
        print(f"ERROR：檢查到一半出錯，沒檢查完（{type(e).__name__}：{e}）")
        return 2
    report(sys.argv[1], rc, res)
    return rc


if __name__ == "__main__":
    sys.exit(main())
