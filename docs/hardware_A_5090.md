# 版本 A：現行做法（RTX 5090 32GB）

**狀態：已實際出片。** 以下數字都是本機實測（2026-09 至 10 月）。

## 硬體

| 項目 | 規格 |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 32GB（驅動 610.88） |
| CPU | Intel Core Ultra 7 270K Plus（24 核） |
| RAM | 96GB |
| 儲存 | 4TB NVMe（BIWIN NV7400，模型與工作檔）＋4TB 外接 |
| 分頁檔 | 42GB（系統碟） |
| OS | Windows 11 |

第二台（選用）：RTX 4080 Laptop 12GB／32GB RAM，只做不吃顯存的工作（劇本、剪接、ASR、QA、小型 LoRA 訓練），**不跑 H3**。

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
