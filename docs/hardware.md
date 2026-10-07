# 硬體說明：32GB VRAM＋64GB RAM（完整版）

**狀態：原專案實際出片用的設定**（RTX 5090 32GB＋96GB RAM，2026-09 至 10 月）。64GB 記憶體是否足夠，2026-10-07 另外模擬驗證過（見下一節）。以下數字除特別註明外都是本機實測。

顯卡只有 16GB 的請看 [shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram) 或 [shanshiba-workflow-16gvram-32gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-32gram)。

## 64GB 記憶體夠不夠（2026-10-07 模擬）

原專案的電腦是 96GB。為了確認 64GB 也行，在這台電腦**平常的程式照常開著**的情況下，另外鎖住記憶體，讓整台只剩「64GB 扣掉常駐程式」的可用量，並讓 ComfyUI 以為總記憶體只有 64GB：

| 常駐程式假設 | ComfyUI 可用 | 對白中景 158 格 | 雙人近景 107 格 | 畫面 | 記憶體最低剩 |
|---|---|---|---|---|---|
| 8GB | 56GB | 76.9 秒 | 46.8 秒 | 跟 96GB **逐格相同** | 48.5GB |
| 12GB | 52GB | 78.6 秒 | 56.9 秒 | 跟 96GB **逐格相同** | 45.3GB |

速度和 96GB 時一樣（77.8／49.7 秒）。**64GB 記憶體綽綽有餘**，32GB 顯卡時模型幾乎都放在顯卡上，ComfyUI 只多用約 8GB 系統記憶體。

## 硬體

| 項目 | 規格 |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 32GB（驅動 610.88） |
| CPU | Intel Core Ultra 7 270K Plus（24 核） |
| RAM | 96GB（64GB 已驗證足夠） |
| 儲存 | 4TB NVMe（BIWIN NV7400，模型與工作檔）＋4TB 外接 |
| 分頁檔 | 42GB（系統碟） |
| OS | Windows 11 |

第二台（選用）：RTX 4080 Laptop 12GB／32GB RAM，只做不吃顯存的工作（劇本、剪接、ASR、QA、小型 LoRA 訓練），**不跑 H3**。

## 所有本地模型（2026-10-07，記憶體限制成 64GB、平常程式照開、常駐假設 12GB）

| 元件 | 用途 | 秒數 | 顯存峰值 | 記憶體最低剩 | 輸出跟 96GB 不設限時 |
|---|---|---|---|---|---|
| Qwen-Image 2.1（2K、50 步） | 角色定妝照 | 56.6 | 20.0GB | 48.7GB | **逐位元相同** |
| Qwen-Image 2.1＋參考圖 | — | 58.4 | 20.9GB | 47.6GB | 逐位元相同 |
| Qwen-Image 2.1＋角色 LoRA | LoRA 首幀 | 54.7 | 17.6GB | 47.3GB | 逐位元相同 |
| Qwen 逐人局部重繪 | 多人鏡修臉 | 8.9 | 15.6GB | 47.6GB | 逐位元相同 |
| Qwen-Image-Edit 2511＋參考圖 | 首幀（預設） | 46.7 | 28.7GB | 47.8GB | 逐位元相同 |
| MiniMax Music 3（60 秒曲） | 配樂 | 45.2 | 27.1GB | 47.7GB | 逐位元相同 |
| H3（107 格、DMAD） | 影片 | 59.0 | 30.4GB | 46.2GB | 逐位元相同 |
| VoxCPM2 | 配音 | 19.8 | 6.9GB | 36.3GB | 逐位元相同 |
| Breeze TTS 2 | 台灣腔參考、聲音設計 | 39.2 | 8.9GB | 43.1GB | 每次都略不同（它本身的特性） |
| faster-whisper large-v3 | 聽寫校對 | 4.5 | 4.8GB | 45.6GB | 逐位元相同 |
| 聲調比對 | 挑配音 | 4.4 | 2.6GB | 46.3GB | 分數相同 |
| BS-RoFormer | 配樂去人聲 | 12.3 | 4.1GB | 46.8GB | 逐位元相同 |
| RTX VSR | 1080p 放大 | 6.6 | 1.6GB | 47.1GB | 逐位元相同 |
| FlashVSR v1.1 | 2 倍放大 | 126.2 | 7.5GB | 33.9GB | 逐位元相同 |

（32GB 顯卡時 ComfyUI 會盡量把模型留在顯卡上，所以顯存數字大；這是快取，不是最低需求。）

## 全本地示範片從零跑完（`pipeline/demo_local/run_demo.py`，2026-10-07，常駐程式 12GB）

| 階段 | 秒數 | 顯存峰值 | 記憶體最低剩 |
|---|---|---|---|
| 角色定妝照 2 張（Qwen 2.1） | 26.6 | 15.5GB | 48.2GB |
| 首幀 4 張（Qwen-Image-Edit，含雙人鏡） | 215.7 | 29.0GB | 47.4GB |
| 配音（Breeze 設計聲音＋VoxCPM2 候選＋聽寫＋聲調比對） | 272.2 | 15.2GB | 36.4GB |
| H3 4 鏡（DMAD） | 259.1 | 30.6GB | 36.9GB |
| 配樂＋去人聲 | 53.6 | 27.6GB | 45.1GB |
| 放大＋剪接＋字幕 | 31.3 | 9.9GB | 45.2GB |
| **合計** | **約 14 分鐘**（5090 運算速度） | | |

成片 17 秒：兩個角色每鏡長得一樣、三句台詞聽寫全對。

## 模型組合

| 用途 | 檔案 | 大小 |
|---|---|---|
| H3 主模型 | `minimax_h3_ref2va_pruned_int8_convrot` | 19.53 GiB |
| H3 文字編碼器 | `qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot` | 24.55 GiB |
| H3 影片 VAE | `minimax_h3_video_vae_fp16` | 4.85 GiB |
| H3 音訊 VAE | `minimax_h3_audio_vae_fp32` | 0.56 GiB |
| DMAD 4 步 LoRA | `dmad_h3_4step_lora_critic_comfy`（自行轉檔） | 1.82 GiB |
| 配樂 | MiniMax Music 3 int8＋文字編碼器＋VAE | 11.1 GiB |
| 本機生圖（選用） | Qwen-Image 2.1 int8＋qwen3vl 8B | 15.5 GiB |

H3 整組約 51 GiB；ComfyUI Dynamic VRAM 讓它在 32GB 顯存裡常駐＋快取，峰值顯示約 31.7GB（那是填滿快取，不是最低需求）。

## 生成設定

| 項目 | 設定 |
|---|---|
| 解析度 | 1344×768（直式小格 768×1344） |
| 幀數 | 17n+5，單鏡 ≤12 秒（約 294 格） |
| 日常定稿 | **DMAD 4 步**：euler、shift 影片 12／音訊 2 |
| 特殊鏡 | 14 步 res_multistep（舞蹈骨架、群舞、細膩表情） |
| 注意力 | comfy kitchen INT8（快 35–43%） |
| 啟動旗標 | `--fast fp16_accumulation`（再快 11%） |
| EasyCache | 關（定稿） |
| 輸出 | PNG 影格 → CRF 12 重編 |
| 放大 | 近景 RTX VSR ULTRA、全景 FlashVSR |

## 實測耗時

| 工作 | 時間 |
|---|---|
| H3 DMAD 4 步 | 每 100 格約 49 秒（5 秒鏡約 1 分鐘） |
| H3 14 步 | 每鏡約 109–115 秒 |
| 一支 41 鏡的片（DMAD） | 約 41 分鐘 |
| 一支 30 鏡的片（14 步） | 約 54 分鐘 |
| H3 原生 1920×1088 | 768p 的 3.3 倍（約 26 分／鏡），乾淨但表演會變 |
| H3 兩段精修到 1080p | 約 29 分／鏡，最穩但慢 |
| RTX VSR 1080p | 每鏡約 6–10 秒 |
| FlashVSR x2 | 約 2.6 分／鏡 |
| Image 2.5 首幀 | 每張約 30–60 秒（雲端，3 路並行） |
| Qwen-Image 2.1 2K／50 步 | 約 62 秒／張 |
| MiniMax Music 3 60 秒曲 | 約 45 秒 |
| VoxCPM2 | 每句數秒，顯存峰值約 6GB |
| 首幀審過到成片 | 約 3–4 小時（大多是 GPU 自己跑，可過夜） |

## 加速實測摘要（同 seed 並排）

| 做法 | 結果 | 採用 |
|---|---|---|
| 步數 20→14 | −25% | 已被 DMAD 取代 |
| comfy kitchen INT8 注意力 | −35～43%，PSNR 31–42 dB、目視無差 | ✅ 預設 |
| `--fast fp16_accumulation` | −11%，PSNR 42 dB | ✅ 預設 |
| DMAD 4 步 LoRA | −49～58%，8 類鏡頭目視無差 | ✅ 定稿 |
| BlockSparseAttention | 再快一些，但手部略軟 | 只做預覽 |
| EasyCache | −29～40%，但近景糊、靜止鏡雜訊 | ❌ |
| FastH3 4 步 LoRA | −53%，手部、複雜鏡構圖漂移 | ❌ |
| 未剪枝主模型 | 畫質無差、慢 0–8% | ❌ |
| SageAttention | torch 2.14 直接當掉 | ❌ |
| SoL-Refiner 精修 | 較銳但改臉、改嘴型 | ❌ |
