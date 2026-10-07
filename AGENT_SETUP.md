# AGENT_SETUP：給 AI agent 的安裝手冊

> 寫給 Claude Code、Codex 等 AI agent：照順序做，每一步做完都有「怎麼確認成功」。人也可以照著做。
> 全程只在 Windows 11＋NVIDIA 顯卡上驗證過。所有影像、聲音、音樂都在本機生成；agent 本身可以用雲端模型。

## 0. 先確認這台電腦用哪一份 repo

```
python setup\detect_hardware.py
```

| 顯卡 | 記憶體 | 該用的 repo |
|---|---|---|
| 32GB（RTX 5090） | 64GB 以上 | `shanshiba-workflow-32gvram-64gram` |
| 16GB（RTX 4080／5070 Ti／5080） | 64GB | `shanshiba-workflow-16gvram-64gram` |
| 16GB | 32GB | `shanshiba-workflow-16gvram-32gram` |
| 12GB 以下，或記憶體不到 32GB | — | **H3 跑不動，不要安裝** |

如果推薦的不是目前這份 repo，**停下來告訴使用者**，請他換對應的 repo。三份的流程一樣，差在 `docs/hardware.md` 和 `configs/profile.cmd`。

再讀 `docs/hardware.md`，了解這個配置的預期速度、顯存、記憶體和風險。

## 1. 前置軟體

| 項目 | 版本（原專案） | 怎麼確認 |
|---|---|---|
| Windows | 11 | `winver` |
| NVIDIA 驅動 | 610.88（要支援 CUDA 13.0） | `nvidia-smi` 右上角 CUDA Version ≥ 13.0 |
| Python | 3.12（3.12.10–3.12.14 都可）；BreezyVoice 另需 3.10（用 uv 安裝即可） | `py -3.12 --version` |
| uv | 任意（裝 Python 3.10 與 BreezyVoice 環境用：`pip install uv`） | `uv --version` |
| Git | 任意 | `git --version` |
| ffmpeg／ffprobe | 9.0.1 full build，要在 PATH | `ffmpeg -version` |
| 硬碟 | C 槽至少 250GB 可用（必要模型約 150GB），NVMe SSD | `detect_hardware.py` |
| 分頁檔 | Windows 預設「系統管理」即可，不要設成固定的小數字 | 系統 → 進階系統設定 → 效能 → 虛擬記憶體（**這是系統設定，要請使用者自己確認或改**） |

## 2. 資料夾與四個 Python 環境

所有程式假設安裝在 `C:\AI`。**ComfyUI 資料夾名稱請照抄 `ComfyUI-0.36.0`**（裡面放的是 0.37.0，名稱是歷史原因，很多腳本寫死這個路徑）。

**順序很重要：先做完第 2 節（尤其是 clone ComfyUI），再做第 3 節下載模型。** 部分模型清單會寫進 `ComfyUI-0.36.0\models\`，先下載的話資料夾已經存在，`git clone` 會因為目錄不是空的而失敗。

**套件一律用 uv 裝**（比 pip 快很多；2026-10-07 全新安裝實測，pip 下載部分大檔只有 100–200 kB/s，H3 環境卡了 20 分鐘以上，改 uv 1.5 分鐘裝完）。四份清單都是原專案 `pip freeze` 的完整結果，所以都加 `--no-deps` 照清單裝，不要讓 pip／uv 自己重新解依賴（語音環境的 voxcpm 依賴會跟鎖定的 fsspec 衝突，照清單裝則沒問題）。uv 也卡住時，見文末常見問題。

```
mkdir C:\AI\H3  C:\AI\Voice  C:\AI\BreezeTTS  C:\AI\BreezyVoice  C:\AI\tools
```

### 2a. 主環境 C:\AI\H3（ComfyUI、H3、Qwen-Image、Music 3、放大）

```
git clone https://github.com/comfyanonymous/ComfyUI C:\AI\H3\ComfyUI-0.36.0
cd C:\AI\H3\ComfyUI-0.36.0 && git checkout v0.37.0
py -3.12 -m venv C:\AI\H3\venv
uv pip install --python C:\AI\H3\venv\Scripts\python.exe --no-deps -r <repo>\setup\env\requirements_h3_venv.txt --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match
copy <repo>\setup\extra_model_paths.yaml C:\AI\H3\ComfyUI-0.36.0\extra_model_paths.yaml
```
自訂節點照 `setup\custom_nodes.txt` clone 到 `ComfyUI-0.36.0\custom_nodes\` 並 checkout 指定 commit。**節點自己的 requirements.txt 不用另外裝**（需要的套件，例如 triton-windows、nvidia-vfx，已經在上面的清單裡）。
確認：`C:\AI\H3\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"` → `2.14.0+cu130 True`

### 2b. 語音環境 C:\AI\Voice（VoxCPM2、faster-whisper、分軌、聲調比對）

```
py -3.12 -m venv C:\AI\Voice\venv
uv pip install --python C:\AI\Voice\venv\Scripts\python.exe --no-deps -r <repo>\setup\env\requirements_voice_venv.txt --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match
```
確認：`C:\AI\Voice\venv\Scripts\python.exe -c "import voxcpm, faster_whisper, audio_separator, stable_whisper, edge_tts;print('ok')"` → `ok`

### 2c. Breeze TTS 2 環境 C:\AI\BreezeTTS（只用來「設計新角色的參考音」）

```
git clone https://github.com/breezeblue-ai/breeze-tts C:\AI\BreezeTTS\breeze-tts
py -3.12 -m venv C:\AI\BreezeTTS\venv
uv pip install --python C:\AI\BreezeTTS\venv\Scripts\python.exe --no-deps -r <repo>\setup\env\requirements_breeze_venv.txt --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
```
（Breeze 用 cu128 的 torch，跟另外兩個環境不同，這是原專案實際狀態。）

### 2d. BreezyVoice 環境 C:\AI\BreezyVoice（⭐ 所有台詞配音）

BreezyVoice（聯發科＋台大，Apache-2.0）是本工作流的台詞配音引擎：用角色參考音念任何台詞，台灣國語腔，念不準的字可直接標注音。官方只支援 Linux，下面是原專案在 Windows 上實際跑通的裝法：

```
git clone --recurse-submodules https://github.com/mtkresearch/BreezyVoice C:\AI\BreezyVoice\code
cd C:\AI\BreezyVoice\code && git checkout d592c9d3e8927a0f53f68616387060dcd32a05ea && git submodule update --init --recursive
uv python install 3.10
uv venv --python 3.10 C:\AI\BreezyVoice\venv
uv pip install --python C:\AI\BreezyVoice\venv\Scripts\python.exe "setuptools<70" wheel
uv pip install --python C:\AI\BreezyVoice\venv\Scripts\python.exe --no-build-isolation --no-deps -r <repo>\setup\env\requirements_breezyvoice_venv.txt --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128
xcopy /E /I <repo>\setup\breezyvoice\winstub C:\AI\BreezyVoice\winstub
```
- 一定要 `--no-deps` 照清單裝：`g2pw` 會要求編不起來的舊版 transformers；`openai-whisper` 要先有 `setuptools<70` 再用 `--no-build-isolation` 建置；`HyperPyYAML` 要 `ruamel.yaml<0.18`（清單已鎖）。
- `winstub`：官方的文字正規化（WeTextProcessing）需要 pynini，Windows 裝不了，用這個直通替身取代。**它不會把數字轉成國字**，`breezyvoice_batch.py` 會自動轉阿拉伯整數，其他（小數、英文縮寫）請在台詞裡寫成國字。
- 第一次執行會自動下載 g2pW 注音模型（607MB，到 `C:\AI\BreezyVoice\code\G2PWModel`）和 bert-base-chinese 的 tokenizer（不到 1MB）。
- 確認：`C:\AI\BreezyVoice\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"` → `2.7.1+cu128 True`

### 2e. 工具

```
xcopy /E /I <repo>\tools C:\AI\tools
```

## 3. 下載模型（全部鎖定版本、逐檔驗證雜湊、可續傳）

cmd 視窗：
```
cd <repo>\setup
for %f in (downloads.json downloads_uncensored.json downloads_dmad.json downloads_qwen_image.json downloads_qwen_image_edit.json downloads_music3.json downloads_voxcpm2.json downloads_breeze_tts2.json downloads_breezyvoice.json downloads_flashvsr.json) do C:\AI\H3\venv\Scripts\python.exe download.py %f
```
（寫進 .bat 檔要把 `%f` 改成 `%%f`。）PowerShell：
```
cd <repo>\setup
foreach ($f in 'downloads.json','downloads_uncensored.json','downloads_dmad.json','downloads_qwen_image.json','downloads_qwen_image_edit.json','downloads_music3.json','downloads_voxcpm2.json','downloads_breeze_tts2.json','downloads_breezyvoice.json','downloads_flashvsr.json') { C:\AI\H3\venv\Scripts\python.exe download.py $f }
```
每份清單跑完會印 `downloaded N, already present M, failed K`，全部成功才印 `ALL DOWNLOADS VERIFIED`（有失敗時結束碼非 0，重跑會從斷點續傳、已驗證的檔案自動跳過）。大檔用 SHA-256 驗證，小設定檔用 Hugging Face 公布的 git 雜湊驗證。

| 清單 | 內容 | 大小 |
|---|---|---|
| `downloads.json` | H3 主模型（剪枝 int8）、官方 NVFP4 文字編碼器、影音 VAE | 約 41GB |
| `downloads_uncensored.json` | H3 文字編碼器 int8（**本工作流實際使用的那顆**） | 24.6GB |
| `downloads_dmad.json` | DMAD 4 步 LoRA（下載後要轉檔，見下） | 2.6GB |
| `downloads_qwen_image.json` | Qwen-Image 2.1 int8＋文字編碼器＋VAE（角色定妝照、LoRA 首幀） | 16.1GB |
| `downloads_qwen_image_edit.json` | Qwen-Image-Edit 2511 fp8＋文字編碼器＋VAE（**預設的首幀做法**） | 28.1GB |
| `downloads_music3.json` | MiniMax Music 3 | 11.1GB |
| `downloads_voxcpm2.json` | VoxCPM2 主權重 | 4.6GB（另需同 repo 的 config／tokenizer 小檔，見下） |
| `downloads_breeze_tts2.json` | Breeze TTS 2（含 tokenizer、audio_tokenizer；只用來設計新角色的參考音） | 7.1GB |
| `downloads_breezyvoice.json` | BreezyVoice-300M（**台詞配音**） | 3.0GB |
| `downloads_flashvsr.json` | FlashVSR v1.1 | 6.3GB |
| 選用 | `downloads_action_loras.json`（動作 LoRA）、`downloads_funcontrol.json`（舞蹈骨架控制） | — |

另外四個會自動下載的：
- VoxCPM2 小檔：`C:\AI\Voice\venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download as s; s('openbmb/VoxCPM2', revision='32279effe8c19989596f05d353d1447f51d9e915', local_dir=r'C:\AI\Voice\models\VoxCPM2')"`
- faster-whisper large-v3：`C:\AI\Voice\venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', download_root='C:/AI/Voice/models/whisper')"`
- g2pW 注音模型：第一次跑 BreezyVoice 時自動下載（見 2d）。
- BS-RoFormer：第一次跑 `audio-separator` 時自動下載到 `C:\AI\Voice\models\separator`（`smoke_test.py` 會觸發）。

DMAD 轉檔：
```
C:\AI\H3\venv\Scripts\python.exe C:\AI\tools\dmad_lora_convert.py C:\AI\H3\ComfyUI-0.36.0\models\loras\dmad_raw\dmad_minimax_h3_4step_lora_critic.safetensors C:\AI\H3\ComfyUI-0.36.0\models\loras\dmad_h3_4step_lora_critic_comfy.safetensors
```
（只需要 `lora_critic` 這一顆；`full_critic` 實測構圖會漂，不用。）

## 4. 啟動與自我驗證

在**同一個 cmd 視窗**依序執行（`profile.cmd` 設定的環境變數只在這個視窗有效）：
```
set PYTHONUTF8=1
call <repo>\configs\profile.cmd
C:\AI\tools\start_comfy.cmd
C:\AI\H3\venv\Scripts\python.exe <repo>\setup\smoke_test.py
```
`smoke_test.py` 會自己設計一個聲音、生一張首幀，跑完 Breeze（設計聲音）→ BreezyVoice（念台詞＋自動挑選）→ VoxCPM2（備用引擎）→ faster-whisper → 聲調比對 → Qwen-Image 2.1 → Music 3 → BS-RoFormer → H3 → RTX VSR → FlashVSR，最後印出每一步 OK／FAIL 和秒數。
- 全部 OK，且每步時間在 `docs/hardware.md` 列的範圍內（真實顯卡比 5090 慢是正常的），就算安裝完成。完整版 14 步；`--quick` 跳過 FlashVSR，13 步。
- 2026-10-07 全新安裝實測（另一個 agent 只看本 repo、在清空的 `C:\AI` 從零安裝，RTX 5090）：完整版 14 步全部 OK，共 500 秒；第一次跑 BreezyVoice 會先下載 g2pW 注音模型，那一步多約 45 秒。
- 打開 `setup\smoke_out\h3\clip.mp4` 看：畫面清楚、嘴型有跟著台詞動。

## 5. 跑全本地示範片

```
C:\AI\H3\venv\Scripts\python.exe <repo>\pipeline\demo_local\run_demo.py
```
從零做兩個角色、4 鏡首幀、配音、H3、配樂，輸出 `pipeline\demo_local\out\cut\demo_1080p.mp4`（約 17 秒）。2026-10-07 全新安裝實測 12.8 分鐘（RTX 5090）；「16GB 顯卡＋32GB 記憶體」模擬條件下約 15 分鐘（5090 運算速度；真實 16GB 卡推估 30–40 分鐘）。看成片確認：兩個角色每鏡長得一樣、嘴型跟著台詞、字幕念的跟聲音一致。

## 6. 開始做片

讀 `docs/02_端到端流程.md`、`docs/03_規則與踩坑.md`，把 `agent/CLAUDE.md範本.md` 放到使用者的專案根目錄改名 `CLAUDE.md`，再照 `pipeline/README.md` 開第一支片。

## 常見問題

| 症狀 | 處理 |
|---|---|
| `ComfyUI not reachable` | 先 `call configs\profile.cmd`，再 `C:\AI\tools\start_comfy.cmd` |
| 跑 H3 時整台電腦卡住 | 關掉瀏覽器等大程式；確認沒有兩個 GPU 工作同時跑 |
| 「分頁檔太小」（Windows error 1455） | 請使用者把分頁檔改回「系統管理」或設 64GB 以上 |
| VAE 解碼時當掉 | `configs\profile.cmd` 的 `COMFY_EXTRA_ARGS` 加 `--disable-pinned-memory --disable-async-offload` |
| faster-whisper 找不到 cuBLAS | 用 `stt.py`（它會自動把 venv 裡 nvidia 的 DLL 加進路徑） |
| 裝套件時某個大檔（例如 `nvidia-cudnn-cu12` 700MB）下載只有幾百 kB/s、卡很久 | 確認用的是 `uv pip install`；還是卡住就先用瀏覽器或多連線下載工具把那個 wheel 抓下來，`uv pip install --python <venv> --no-deps <wheel檔>` 先裝它，再重跑整份清單 |
| 指令輸出的中文變亂碼 | 先 `set PYTHONUTF8=1`（或在 Git Bash 用 `export PYTHONUTF8=1`）；不影響結果，只影響顯示 |
| 下載清單印出 `failed` | 再跑一次同一份清單（會續傳）；一直失敗就檢查網路能不能連 huggingface.co |
