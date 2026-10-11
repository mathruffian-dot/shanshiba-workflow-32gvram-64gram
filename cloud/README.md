# cloud/：用 Google Colab 跑 H3（本機跑不動的人用）

**做法：本機準備、雲端只跑 H3。** 劇本、首幀、配音、剪接在你的電腦做；H3 影片整批送到 Google Colab 的 G4 顯卡跑，跑完下載回來。素材和成品一直都在你的硬碟，Colab 機器一關掉就清空。
本機連配音都跑不動（沒有 NVIDIA 顯卡、Mac）的人，可以用**全雲端模式**：整套環境裝在 Colab 上，整支片在雲端做完再下載。

> 所有數字都是 2026-10-10 在 Colab（Google AI Pro 帳號，每月 200 運算單元）實測。Colab 的方案、價格、可用顯卡隨時會變。

## ⚠️ 先讀：H3 授權與機房位置

- MiniMax H3 授權（第 I.5、V.4 條）**排除在美國、歐盟、英國、南韓使用**（含複製、執行、散布、展示 H3 與其產出）。
- 實測 Colab **G4 開機 30 次：美國 18 次（俄亥俄 17、拉斯維加斯 1）、歐盟荷蘭 12 次，從沒分到亞洲**；L4／A100 偶爾分到新加坡，但跑 H3 又慢又貴。
- 授權**沒有定義「使用」看使用者所在地還是機器所在地**；照字面，權重在美國／歐盟機器上被複製、執行，比較可能被認為不在授權範圍內。
- **要不要在 Colab 跑 H3 由你自己評估、風險自負**（這裡不是法律意見）。想確定可以照授權第 II 條寫信問 MiniMax。`colab_h3.py` 每次開機都會顯示機房國家並提醒。
- 替代：台灣或日本機房的雲端 GPU（例如台灣 GPUtw 的 RTX 5090／RTX PRO 6000、RunPod 日本 AP-JP-1），用同一套 `cloud/vm/setup_h3.py` 自己裝即可（未在本 repo 實測）。

## 1. 準備（一次）

1. 有一個 **Google AI 方案**（AI Pro 每月約 200 運算單元；**免費試用期間不發**）或在 Colab 買**隨用隨付**運算單元（100 個 US$10.49）。
2. 安裝 Colab CLI（Google 官方，Apache-2.0）：
   ```
   uv tool install google-colab-cli
   ```
3. **Windows 一定要修補**（官方只支援 Linux／macOS，Windows 上連 `colab version` 都會因 `import termios` 當掉）：
   ```
   python cloud/colab_cli_windows_patch.py
   ```
   只包住兩行 import（會留備份 `console.py.bak`），之後 new／exec／upload／download／stop 都正常；`colab console`、`colab ssh` 仍不能用（本工具不用）。更新 CLI 後要重跑。
4. 登入（要你自己在終端機做，瀏覽器裡選有方案的那個 Google 帳號、把授權碼貼回終端機）：
   ```
   colab usage
   ```
5. 確認：`python cloud/colab_h3.py check` 會顯示餘額。

> **預設 `start`＝完整安裝**（2026-10-11 起）：跟第一份 repo 完整版（32GB 顯卡＋64GB 記憶體）一樣，語音三環境、ComfyUI（H3、Qwen、Music 3、FlashVSR）、中文字型全部裝，約 10.5 分鐘、約 1.5 單元；G4 有 96GB 顯存，完整版的設定都跑得動。只要 H3 的人加 `--h3-only`（約 3.7 分鐘）。

## 2. 只有 H3 上雲端（本機能做首幀和配音）

```
python cloud/colab_h3.py start --h3-only           # 開 G4、只裝 ComfyUI＋H3（約 3.5–4 分鐘）、開 2 個 ComfyUI
python cloud/colab_h3.py batch S01/spec.json S02/spec.json ...   # 打包上傳 → 雲端跑 → 成品下載回各 spec 旁邊
python cloud/colab_h3.py keepalive --minutes 20    # （選用）審片時保住機器
python cloud/colab_h3.py stop                      # 用完一定要關
```
- `batch` 吃的就是 `tools/h3_shot.py` 的分鏡 JSON；首幀、配音、參考圖等檔案會自動一起打包（相對路徑以 spec 所在資料夾為準）。成品放在 spec 旁邊：檔名是 `spec.json` 就放同一個資料夾，否則放在同名資料夾。
- **多鏡範本自動判斷**：`pipeline/template_local/make_film.py` 偵測到本機顯卡跑不動 H3（不到 15GB 顯存或 30GB 記憶體）時，h3／amb 兩步會自動整批送到 Colab；也可以用 `set H3_BACKEND=colab`（或 `local`、`both`＝本機＋Colab 一起跑，見 §3b）強制。只跑 h3 時本機不必開 ComfyUI。
- 沒開機就直接 `batch` 會自動先 `start`（預設完整安裝；只要 H3 就 `batch --h3-only …`）；加 `--stop-after` 跑完自動關機。

## 3. 全雲端（本機什麼都跑不動）

```
python cloud/colab_h3.py start                     # 預設＝完整安裝：語音三環境、ComfyUI（H3、Qwen、Music 3、FlashVSR）、中文字型（舊名 full-setup 也可以）
python cloud/colab_h3.py smoke                     # 跑 setup/smoke_test.py，結果下載到 setup/smoke_out_colab/
python cloud/colab_h3.py film pipeline/template_local chars masters frames   # 在雲端跑 make_film.py 指定階段，out/ 同步回本機
python cloud/colab_h3.py film pipeline/template_local voices h3 amb edl music ending cut review
python cloud/colab_h3.py stop
```
- **2026-10-10 新 agent 實測（只看本 repo、從零）**：`full-setup` **約 10.5 分鐘**（VM 端 540 秒；10 份模型清單約 8 分鐘）→ `smoke` 約 13 分鐘 → 範本片〈被狗吃掉的作業〉分三段 `film` 共約 28 分鐘，成片 38.5 秒 1080p、−15.9 LUFS，自審全過；G4 開機到關機約 54 分鐘、**約 8 個運算單元**。Colab 硬碟約 236GB，裝完剩約 40–80GB。
- 全雲端模式只有 1 個 ComfyUI，還要跟 Qwen、Music 3 輪流換模型，所以 H3 每鏡約 70 秒（smoke 第一支冷載入 230 秒），比「只有 H3 上雲端」的 42 秒慢。**`film` 現在跑到 h3／amb 時會自動改成 2 個 ComfyUI 錯開跑（`cloud/vm/parallel_h3.py`，`H3_PARALLEL=2`），跑完恢復 1 個**；長片才看得出差別。
- 範本可以直接跑 `pipeline/template_local`；做自己的片時照 `pipeline/template_local/README.md` 複製成 `pipeline/<片名>/`，再 `film pipeline/<片名> …`（資料夾一定要在 repo 裡面）。
- 每個人工關卡（首幀、H3 接觸表、成片）之間，`film` 會把 `out/` 下載回來給你看；改了要重做的檔案刪掉，再跑下一段，`film` 會把整個片子資料夾重新上傳，從斷點接著做。
- **本機設的 `ONLY`（只重做某幾鏡）、`ALLOW_REVIEW`、`UPSCALE` 會自動帶到 VM**；其他設定用 `--env KEY=VALUE`（例：`film pipeline/template_local h3 --env ONLY=S3`）。
- **VM 被收回（閒置約 20 分鐘）或你 `stop` 之後**：重新 `full-setup`（約 10 分鐘、約 1.5 單元），再 `film` 同一個資料夾就會從斷點接著做。
- 注意：雲端跑出來的 `out/*.json`（`voice_picks`、`amb`、`music_pick`、`edl`）裡存的是 `/content/...` 的雲端路徑；要在本機接著跑 `edl`／`cut` 得重跑前面那幾段，建議全程在雲端做完。
- smoke_test 在 Linux 上自動跳過 `rtx_vsr`（只有 Windows 有），其餘全部通過；Linux 的放大用 lanczos（`UPSCALE=lanczos`，預設）或 FlashVSR（`UPSCALE=flashvsr`）。片尾名單會依實際做法自動寫成「在 Google Colab 執行」、放大工具照實列名。

## 3b. 本機＋Colab 一起跑（本機有顯卡、也有 Google AI 訂閱）

```
set H3_BACKEND=both                                # Linux/Mac：export H3_BACKEND=both
python pipeline/template_local/make_film.py h3 amb # 或直接：python cloud/hybrid_h3.py out/h3/S01 out/h3/S02 ...
```
- **做法**（`cloud/hybrid_h3.py`）：所有鏡頭放進同一個佇列。本機從前面一支一支拿、馬上開跑；Colab（只裝 H3）開機約 3.5 分鐘後加入，每次從後面拿一批（預設最多 8 支）交給 `colab_h3.py batch`，做完再拿。不事先對半分，因為兩邊速度不同、雲端晚開始。**佇列快空時依兩邊實測速度估算雲端該拿幾支**（讓兩邊差不多同時做完，少於 2 支就不再派雲端）。雲端失敗的鏡頭放回佇列給本機重跑；做完在背景 `stop`（`HYBRID_KEEP=1` 不關，審片後重抽可以接著用）。
- **2026-10-11 實測**（直式短片 34 鏡、3370 格、DMAD 4 步，RTX 5090＋G4、每批 8 支）：**17.9 分鐘**完成（本機 15 支、雲端 19 支、失敗 0）；同一輪本機每格 0.58 秒 → 全部本機推算 32.6 分鐘，**省 45%**；Colab **1.97 單元**（含開機、關機）。G4 開機 216 秒（本機同時先做了 4 支）；每批 8 支約 304–314 秒，其中上傳、解壓、輪詢、下載約 70 秒。
- **這次修進工具的坑**：①最後一批雲端拿走 3 支、本機只剩 1 支 → 本機做完空等約 140 秒 → 改成依速度估算尾巴的分配；②每 45 秒輪詢一次 → 改 15 秒（`COLAB_POLL`）；③每批 4 支耗損占比太高 → 預設 8 支；④關機算進等待 → 改背景關機；⑤本機要用自己正式版的 `h3_shot.py` → `HYBRID_TOOLS` 指定資料夾；⑥機房每次不同（美國俄亥俄、荷蘭），都在授權排除地區；⑦中途要停：本機連 `h3_shot.py` 子程序和 ComfyUI 佇列一起清（`POST /queue {"clear": true}`、`POST /interrupt`），Colab 上的批次要另外 `stop`。
- **什麼時候值得**：鏡頭少於 `HYBRID_MIN`（預設 8）支會自動全部本機跑（不值得等雲端開機）；約 20 支以上才明顯快。少量重抽直接本機跑。
- **限制**：接力鏡頭（spec 有 `first_clip`）等兩邊做完才由本機照順序跑；本機顯卡跑 H3 時不能同時配音（配音要先做完）；雲端部分一樣有上面的 H3 授權地區問題。本機要先開 ComfyUI。
- 環境變數：`HYBRID_CHUNK`（雲端每批最多幾支，預設 8）、`HYBRID_MIN`（預設 8）、`HYBRID_KEEP=1`、`HYBRID_TOOLS`、`COLAB_NAME`、`COLAB_POLL`。

## 4. 實測：該租哪張卡

同一個鏡頭（90 格、1344×768、DMAD 4 步）、同一個 seed，與 RTX 5090 本機成品比較：

| GPU（Colab） | 顯存／記憶體 | 每小時運算單元 | 每支秒數 | 每支單元 | 跟 5090 成品比 |
|---|---|---|---|---|---|
| **G4＝RTX PRO 6000 Blackwell** | 96GB／176GB | **8.90** | **42**（模型留在顯存）／50（每支重載） | **0.10** | PSNR 45.9 dB |
| A100 40GB | 40GB／83GB | 5.30 | 210–270 | 0.31–0.40 | PSNR 45.8 dB |
| L4 | 22.5GB／52GB | 1.54 | 310–399 | 0.13–0.17 | PSNR 43–45 dB |
| T4 | 15GB／**12GB** | 1.07 | 記憶體太小，跑不了 | — | — |
| H100 | — | — | AI Pro 帳號不能開（「沒有配額或權限」） | — | — |

- **H3 只用 G4**：L4 每一步取樣約 33 秒、G4 約 4.4 秒（慢 7.5 倍，主因是晶片算力，不是記憶體），單元反而多 3 成；A100 吃不到這套 int8／FP16 累加加速，慢 4–5 倍、單元 3 倍。畫面都一樣，只差速度。
- G4 和 RTX 5090 是同一顆 GB202 晶片、記憶體頻寬相同，所以**單支速度跟 5090 一樣**；多出來的是顯存、記憶體和 48 核 CPU。

### 榨乾 G4（`setup_h3.py` 預設已套用）

| 設定 | 每小時幾支 | 每支單元 |
|---|---|---|
| 一次 1 支、`--cache-none`（Windows 原設定） | 71 | 0.125 |
| 一次 1 支、模型留在顯存 | 85（連續 24 支穩定） | 0.105 |
| 2 個 ComfyUI 同時開始 | 110，但 8 支失敗 1 支（兩邊同時載入文字編碼器，96GB 撞滿） | — |
| 3 個 ComfyUI | 101，每支 100–116 秒 | 0.088 |
| SageAttention | 每支 46 秒，比 comfy kitchen 的 42 秒慢 | — |
| **2 個 ComfyUI、各 `--reserve-vram 46`、第二個晚 30 秒開始** | **123（10/10 成功）** | **0.073** |

單一支 H3 時 GPU 沒滿載（存每格 PNG、ffmpeg 合成等 CPU 工作），兩支交錯可以補空檔；但要錯開，否則同時載入文字編碼器會撞滿顯存。以上都是同一個 90 格鏡頭的數字，實際片子長短不一，比例應該差不多。

## 5. 時間、費用、審片

| 項目 | 實測 |
|---|---|
| 從開機到可以跑 H3 | **約 3.5–4 分鐘**（下載 55GB 約 170 秒、裝套件約 165 秒，兩者同時進行） |
| 一支 30 鏡短片的 H3 | 約 15 分鐘（加開機約 20 分鐘、**約 3 單元**） |
| 200 運算單元 | 約 60 支 30 鏡短片（只算 H3） |
| 換算台幣 | 隨用隨付每單元約 NT$3.4 → G4 每小時約 NT$30；外租同級 RTX PRO 6000 約 NT$52–67／小時 |

- **Colab 閒置約 20 分鐘會自動收回機器**（實測：最後一次下指令後約 18–20 分鐘；機器上有程式在等待也一樣）。所以：
  - 忘了關機最多浪費約 3 單元；
  - 審片加修改 **4 分鐘內**能回來就開著（重開要等約 4 分鐘、約 0.55 單元，跟開著等差不多）；超過 20 分鐘沒動作機器會被收回，回來重新 `start` 即可；
  - 要多保一會用 `keepalive`（照樣扣單元）。
- `batch` 執行期間每 45 秒查一次進度，順便維持連線。H3 正在跑但完全不查進度會不會被收回，未測。
- 單元 **90 天後失效**；買太多用不完會浪費。

### Google 方案怎麼選

| 方案 | 價格 | Colab 單元 | 每單元 |
|---|---|---|---|
| 隨用隨付 | 100 個 US$10.49／500 個 US$52.49 | — | 約 US$0.105 |
| Colab Pro | US$10.49／月 | 100 | 約 US$0.105 |
| Colab Pro+ | US$52.49／月 | 600（方案頁；有第三方寫 500） | 約 US$0.0875 |
| Google AI Plus | NT$165／月 | 未公布 | — |
| Google AI Pro | NT$650／月 | 約 200 | 另含 5TB、Gemini 等 |
| Google AI Ultra | NT$3,300 起 | 未公布（含高階 GPU、背景執行） | — |

本來就用 Gemini 的人 → AI Pro（等於附送）；只為了 H3 偶爾做片 → 隨用隨付；量很大 → Pro+；**不建議為了 Colab 買 Ultra**（高階 GPU 不保證是 H100，G4 已是跑 H3 最划算的卡）。

## 6. 網路

- 55GB 模型是 Colab 機器直接下載，**不經過你家網路**。
- 經過你家網路的只有素材和成品：一張首幀約 1.5MB、一句配音約 0.4MB、一支 768p 成品約 3MB（FlashVSR 1080p 約 15MB）。`batch` 會把一整批打包成一個 zip 上傳、一個 zip 下載（Colab CLI 每個檔案往返要 2–5 秒，逐檔傳很慢）。

## 7. 踩坑紀錄（都已修進這套工具）

| 問題 | 原因 → 解法 |
|---|---|
| Windows 上 `colab` 一執行就當掉 | `import termios` → `colab_cli_windows_patch.py` |
| Git Bash 上傳到 `/content/...` 變成 `C:/.../PortableGit/content/...` | Git Bash 自動轉路徑 → 本工具用 Python 呼叫 CLI，不經過 Git Bash；自己在 Git Bash 下指令要 `MSYS_NO_PATHCONV=1` |
| `colab exec` 偶爾 `Connection was lost`／`Timeout waiting for reply` | CLI 連線不穩（機器其實正常）→ 自動重試；長工作一律在 VM 上 `nohup` 背景跑、再輪詢記錄檔 |
| 下載模型大量 `HTTP 429 Too Many Requests` | 舊 `download.py` 每 8MB 一個請求打 huggingface.co（26GB＝3,000 多次），多份清單同時跑就被限速 → 改寫 `download.py`：轉址只解析一次、每檔 16 段長串流、可續傳、429 退避；全雲端安裝一次只跑一份清單；可設 `HF_TOKEN` |
| 舊 `download.py` 大檔要兩倍硬碟 | 先存分段再合併 → 新版直接寫進同一個檔 |
| whisper：`libcublas.so.12` 找不到 | Linux 的 CUDA 12 函式庫是 pip 套件，安裝時被濾掉、執行時也不在搜尋路徑 → 安裝只濾掉 `名稱==` 完全相符的 Windows 套件；`tools/stt.py` 在 Linux 先預載 |
| BreezyVoice：`No module named torchmetrics` | 過濾 `^torch` 時連 torchmetrics 一起拿掉 → 同上 |
| 第 2、3 個 ComfyUI 啟動失敗 | 複製程式碼時「跳過 models 資料夾」連 `comfy/ldm/models`（程式碼）也跳過 → 只跳過最上層 |
| 字幕、片尾中文變方塊 | 字型寫死 Windows 路徑 → `tools/fonts.py`（Linux 用 Noto CJK／文鼎楷書，`install_full.sh` 會裝） |
| RTX VSR 在 Linux 不能用 | `nvvfx` 只有 Windows → `UPSCALE=lanczos`（預設）或 `flashvsr` |
| Colab 的 L4／A100 跑 H3 | 能跑但又慢又貴 → 只用 G4 |

## 8. 檔案

| 檔案 | 在哪執行 | 做什麼 |
|---|---|---|
| `colab_h3.py` | 你的電腦 | 開機、裝環境、批次跑 H3、保持連線、關機、全雲端 smoke／film（只用 Python 標準函式庫） |
| `hybrid_h3.py` | 你的電腦 | 本機＋Colab 一起跑 H3（共用佇列；`H3_BACKEND=both`；尚未實測） |
| `colab_cli_windows_patch.py` | 你的電腦（Windows） | 讓 Colab CLI 在 Windows 上能啟動 |
| `vm/setup_h3.py` | Colab | ComfyUI 0.37＋H3＋DMAD，開 1–3 個 ComfyUI（預設 2 個、錯開） |
| `vm/run_batch.py` | Colab | 把一批鏡頭分給各個 ComfyUI 跑，寫進度、打包成品 |
| `vm/install_full.sh` | Colab | 全雲端：語音三環境＋ComfyUI 全套＋字型＋全部模型 |

已有類似但只做「上傳參考圖＋提示詞 → Colab 跑 H3 → 下載」的開源工具：[killkli/minimax-h3-colab-skill](https://github.com/killkli/minimax-h3-colab-skill)（Codex 技能）。
