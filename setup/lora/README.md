# 角色 LoRA 訓練（選用，品質最好的首幀做法）

不訓練也能做片（用 Qwen-Image-Edit 附參考圖，見 `docs/07_本地角色與首幀.md`）。想讓角色更像、細節更好時再訓練。

## 1. 安裝 AI Toolkit（一次）

```
git clone https://github.com/ostris/ai-toolkit C:\AI\lora\ai-toolkit
cd C:\AI\lora\ai-toolkit && git checkout 60d0c28
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
原專案用的是 commit `60d0c28`、torch 2.13.0+cu130。訓練時會從 Hugging Face 下載 `Comfy-Org/Qwen-Image-2.1`（設定檔 `name_or_path`），第一次要等下載。

## 2. 產生訓練圖

```
C:\AI\H3\venv\Scripts\python.exe C:\AI\tools\make_lora_dataset.py --ref chars\yun.png --trigger yun_local --desc "the girl Xiaoyun, a bright 11-year-old Taiwanese schoolgirl with a short black bob haircut and straight bangs, round friendly face, wearing a plain white short-sleeve school shirt" --out C:\AI\lora\datasets\yun_local
```
- 會產生 25 張（定妝照本身＋24 種景別／角度／表情／場景）和同名 caption。
- **一定要逐張看**：刪掉臉不像、多手多腳、有字、穿錯衣服的圖。

## 3. 訓練

1. 複製 `qwen21_character_lora_template.yaml`，把 `__NAME__`、`__OUTPUT_DIR__`、`__DATASET_DIR__`、`__TRIGGER__`、`__DESC__` 換掉。
2. ComfyUI 先關掉（訓練要用整張顯卡）。
3. `C:\AI\lora\ai-toolkit\.venv\Scripts\python.exe C:\AI\lora\ai-toolkit\run.py <你的設定檔>.yaml`
4. 每 400 步存一次，`samples/` 有樣圖。用 1600 步那顆；樣圖已經很像也可以提早用 1200 步。

設定重點（原專案實際用的）：768 解析度、rank／alpha 32、學習率 1e-4、adamw8bit、梯度檢查點、底模量化 convrot8、`low_vram: true`、1600 步。

| 硬體 | 實測時間 | 來源 |
|---|---|---|
| RTX 4080 Laptop 12GB＋32GB RAM | 約 3 小時（1600 步） | 原專案第二台電腦實機訓練三個角色 |
| RTX 5090 模擬「16GB 顯卡＋32GB 記憶體、平常程式照開」 | **33 分鐘**（每步 1.13 秒）、顯存峰值 14.7GB、**記憶體最低只剩 0.5GB** | 2026-10-07 本 repo 驗證 |

## 4. 使用

把 `.safetensors` 複製到 `C:\AI\H3\ComfyUI-0.36.0\models\loras\`，生首幀：
```
C:\AI\H3\venv\Scripts\python.exe C:\AI\tools\gen_image.py --lora yun_local.safetensors:1.0 --prompt "yun_local, the girl Xiaoyun, <外觀照抄> <電影感句> <這一鏡>"
```
- 提示詞一定要有觸發詞＋外觀描述（只有觸發詞不保證像）。
- 單人 1.0；多人同框不要同時掛兩個 LoRA（會互相稀釋），改成先出構圖、再用 `qwen21_face_refine.py` 對每個人的框各掛自己的 LoRA 重繪。
- LoRA 的訓練圖若是灰底棚拍，生出的畫面光線會稍平；提示詞的光線句要寫足。

## 本 repo 驗證

2026-10-07，用 `pipeline/demo_local` 的角色「小芸」（本機 Qwen-Image 2.1 生的單張定妝照）：
- `make_lora_dataset.py` 產生 25 張，花 18.6 分鐘；目視刪掉 2 張（黑板上有字、臉看起來太成熟），剩 23 張。
- 在模擬的 16GB 顯卡＋32GB 記憶體下訓練 1600 步：33 分鐘、顯存 14.7GB、記憶體最低剩 0.5GB（**能跑完但非常極限：32GB 電腦訓練時務必關掉所有其他程式**）。
- 真實 16GB 卡算力較低，推估約 1–1.5 小時；原專案 12GB 筆電實測約 3 小時。
- 首幀效果（同 3 個場景、同 seed）：
  - 不附參考、不掛 LoRA：每張都是不同的女生 → 不能用。
  - Qwen-Image-Edit 附定妝照：三張都像。
  - 本地訓練的 LoRA：三張都像，2K、細節最好、構圖變化較多。
  → 兩條路都可用；想要最好畫質、或同一角色要拍很多鏡，就訓練 LoRA。

### 產生訓練圖時學到的
- 外觀描述要連下半身一起寫（例：navy pleated skirt）。沒寫的話，Qwen-Image-Edit 會在全身照裡隨機配裙子、長褲、短褲，LoRA 會學到不一致的下半身。
- 一定要逐張看：這次 25 張裡有 1 張黑板寫了字、1 張臉變成熟。
