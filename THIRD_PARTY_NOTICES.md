# THIRD_PARTY_NOTICES：第三方模型與工具授權

> 2026-10-07 依各官方頁面查核整理。**本 repo 不含任何模型權重**，只提供下載清單（`setup/downloads_*.json`）；下載與使用前請自行閱讀並同意各自的授權。
> 這是授權條文整理，**不是法律意見**。頻道若要營利，請先就下方「⚠️」項目找律師確認，或寫信向權利方取得書面授權。

## ⚠️ 先看這四件事

1. **非商業限制**（本 repo 的預設就是非商業用途）：以下三者**只能非商業使用**，有廣告、贊助、會員收入的頻道不能直接用，要換成下方「營利時的替換方向」：
   - **Qwen-Image 2.1**（Qwen Research License）：本 repo 用它生「角色定妝照」與「LoRA 首幀」。可商用的替代：Qwen-Image-Edit 2511（Apache-2.0）。
   - **Breeze TTS 2**（BreezeBlue Research and Non-Commercial License v1.1，**自己架設產生的聲音也算**）：本 repo 只用它「設計角色參考音」；每句台詞由 BreezyVoice（Apache-2.0）念。條款另禁止用其產出訓練／微調／蒸餾其他模型；拿它設計出來的聲音當 BreezyVoice 的零樣本參考音是否違約，條文沒寫清楚。要營利請把角色參考音換成可商用來源（VoxCPM2 聲音設計或真人錄音）。
   - **YuE2**（CC BY-NC 4.0，選用的歌曲模型）。
2. **MiniMax H3 地區限制**：授權不允許在**美國、歐盟、英國、南韓**使用，條文（第 I.5、V.4 條）也涵蓋在這些地區散布或展示 H3 本身與其產出。公開影片在這些地區看得到，屬灰色地帶，請自行評估。
3. **AI 生成標示**：MiniMax H3、MiniMax Music 3 的使用規範要求公開發布的內容**清楚標示為機器生成**；商業產品上要顯著標示「MiniMax H3」「MiniMax-Music3」。
4. **不得冒充真人**：VoxCPM2、Breeze、H3 都禁止未經本人同意模仿真人的臉或聲音；BreezyVoice 的參考音也請只用你有權利的聲音。

## 模型

| 項目 | 授權 | 商用 | 主要義務與限制 | 來源 |
|---|---|---|---|---|
| MiniMax H3（Ref2VA 權重，含 Comfy-Org 重新打包版） | MiniMax H3 Community License Agreement（2026-08-02） | 可以（年營收 > 2,000 萬美元需書面授權） | 排除美、歐盟、英、南韓；商業產品顯著標示「MiniMax H3」；公開內容標示機器生成；不得用產出改進其他 AI 模型；轉散布須附授權全文與 NOTICE：「MiniMax H3 is licensed under the MiniMax H3 Community License Agreement, Copyright © 2026 MiniMax. All Rights Reserved.」產出歸使用者 | https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE |
| DMAD 4 步 LoRA（`minimax_h3/`） | 沿用 MiniMax H3 Community License（衍生作品） | 同 H3 | 同 H3 | https://huggingface.co/ZhengmingYu/DMAD |
| H3 Fun ControlNet patches | 沿用 MiniMax H3 Community License | 同 H3 | 同 H3 | https://huggingface.co/alibaba-pai/MiniMax-H3-Fun-Controlnet-Union-2.0 |
| Qwen3-VL-32B Heretic 文字編碼器（ethanfel，INT8 ConvRot） | Apache-2.0（上游 Qwen3-VL-32B-Instruct 亦 Apache-2.0） | 可以 | 保留授權；與 H3 併用時 H3 使用規範照樣適用 | https://huggingface.co/ethanfel/Qwen3-VL-32B-Ultra-Heretic-H3-ComfyUI-INT8-ConvRot |
| **Qwen-Image 2.1**（含 Comfy-Org 版） | **Qwen RESEARCH LICENSE AGREEMENT** | **不可以**（僅研究／評估；商用請洽 model-business@notice.qwencloud.com） | 轉散布附授權全文與聲明「Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026 Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.」；用它做或改進模型須標「Built with Qwen」 | https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE |
| Qwen-Image-Edit 2511（含 Comfy-Org 版）、Qwen2.5-VL-7B 文字編碼器 | Apache-2.0 | 可以 | 保留授權與 NOTICE | https://huggingface.co/Qwen/Qwen-Image-Edit-2511 |
| MiniMax Music 3 | MiniMax-Music3 COMMUNITY LICENSE（2026-08-06）；Comfy-Org 版標示的 Apache-2.0 **與原始授權不符，以原始為準** | 可以（年營收 > 2,000 萬美元需授權） | 保留聲明；商業產品顯著標示「MiniMax-Music3」；公開內容標示機器生成；不得冒充他人 | https://huggingface.co/MiniMaxAI/MiniMax-Music3/blob/main/LICENSE |
| VoxCPM2（權重與程式碼） | Apache-2.0 | 可以 | 嚴禁冒充他人、詐騙、假訊息；強烈建議標示 AI 生成 | https://huggingface.co/openbmb/VoxCPM2 |
| **Breeze TTS 2** 權重（含自架產出） | **BreezeBlue Research and Non-Commercial License v1.1** | **不可以**（官方付費 API 的產出才可商用） | 不得用產出訓練／微調／蒸餾非 BreezeBlue 模型；參考音須有權利、不得未經同意模仿真人；NOTICE：「Breeze TTS 2 is licensed under the BreezeBlue Research and Non-Commercial License Agreement. Copyright (c) 2026 RESONIA, INC. All Rights Reserved.」 | https://huggingface.co/BreezeBlue/Breeze-TTS-2/blob/main/LICENSE |
| **BreezyVoice-300M**（聯發科 MediaTek Research＋台大；權重與程式碼） | Apache-2.0 | 可以 | 保留授權與 NOTICE；參考音須有權利 | https://huggingface.co/MediaTek-Research/BreezyVoice-300M 、https://github.com/mtkresearch/BreezyVoice |
| g2pW 注音模型（G2PWModel-v2-onnx，BreezyVoice 第一次執行時自動下載）＋bert-base-chinese tokenizer | Apache-2.0 | 可以 | 保留授權 | https://github.com/GitYCC/g2pW |
| Whisper large-v3（openai）／faster-whisper-large-v3（Systran 轉檔） | Apache-2.0／MIT | 可以 | 保留授權 | https://huggingface.co/Systran/faster-whisper-large-v3 |
| BS-RoFormer `model_bs_roformer_ep_317_sdr_12.9755`（viperx 訓練） | **未標示授權** | 不明 | 只附下載連結，不轉散布，自行評估 | https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md |
| FlashVSR v1.1 | Apache-2.0（含 Wan2.1 VAE，Apache-2.0） | 可以 | 保留授權 | https://huggingface.co/JunhaoZhuang/FlashVSR-v1.1 |
| 動作 LoRA：JOKER141 Combat-Base-V2、GunFu、Motion-Continuity-Repair；RunningHubAI speed-slider-1.1 | **未標示授權**（等同保留所有權利）；同時是 H3 衍生作品 | 不明 | 只附連結、不轉散布；至少須遵守 H3 授權 | https://huggingface.co/JOKER141 、https://huggingface.co/RunningHubAI/rh-h3-speed-slider-1.1-lora |
| SDPose（Comfy-Org 打包）、RT-DETRv4 | MIT／Apache-2.0（SD 底模授權未查） | 大致可以 | 保留授權 | https://huggingface.co/Comfy-Org/SDPose |
| YuE2（選用） | CC BY-NC 4.0 | 不可以 | 署名、非商業 | https://huggingface.co/m-a-p |
| OpenAI Image 2.5 API（選用，雲端） | OpenAI Services Agreement | 可以 | 產出歸客戶（第 4.1 條）；另須遵守 Usage Policies | https://cdn.openai.com/osa/openai-services-agreement.pdf |

## 軟體

| 項目 | 授權 | 對本 repo 的影響 | 來源 |
|---|---|---|---|
| ComfyUI | GPL-3.0 | 本 repo 不含 ComfyUI；大多數腳本只透過 HTTP API 呼叫它。**`tools/flashvsr_cli.py` 執行時會直接 import ComfyUI 與 FlashVSR 節點（GPL-3.0）的程式碼，因此該檔以 GPL-3.0-or-later 授權** | https://github.com/comfyanonymous/ComfyUI |
| ComfyUI-FlashVSR_Ultra_Fast 節點 | GPL-3.0 | 同上 | https://github.com/lihaoyun6/ComfyUI-FlashVSR_Ultra_Fast |
| Nvidia_RTX_Nodes_ComfyUI | Apache-2.0 | — | https://github.com/Comfy-Org/Nvidia_RTX_Nodes_ComfyUI |
| nvidia-vfx（RTX Video Super Resolution） | NVIDIA 專有授權 | 不可放進 repo，請使用者自行 `pip install` | https://pypi.org/project/nvidia-vfx/ |
| ostris/ai-toolkit | MIT（Copyright (c) 2024 Ostris, LLC） | 保留聲明 | https://github.com/ostris/ai-toolkit |
| faster-whisper | MIT | — | https://github.com/SYSTRAN/faster-whisper |
| CosyVoice（BreezyVoice 程式碼的上游）、g2pw 套件 | Apache-2.0 | 隨 BreezyVoice 安裝，不在本 repo | https://github.com/FunAudioLLM/CosyVoice |
| Matcha-TTS（BreezyVoice 的 submodule） | MIT（Copyright (c) 2023 Shivam Mehta） | 隨 BreezyVoice 安裝，不在本 repo | https://github.com/shivammehta25/Matcha-TTS |
| `setup/breezyvoice/winstub`（取代 WeTextProcessing 的直通替身） | 本 repo 原創，MIT | 不含 WeTextProcessing 程式碼 | — |
| python-audio-separator | MIT（README 請使用者標註 UVR 專案） | 建議在片尾或說明欄標註 | https://github.com/nomadkaraoke/python-audio-separator |
| edge-tts | LGPL-3.0（套件）；**微軟朗讀服務沒有公開授權第三方使用** | 本 repo 只用它產生「發音對照」參考音、不放進成片；離線替代為 Breeze（同樣非商用） | https://github.com/rany2/edge-tts |
| Blender | GPL（只約束程式本身；算出的圖與 .blend 歸使用者） | 無 | https://www.blender.org/about/license/ |
| POUND0423/AI-drama-pound | MIT（Copyright (c) 2026 POUND0423） | `agent/skills/shanshiba-drama/` 改寫自此，已附原授權全文 | https://github.com/POUND0423/AI-drama-pound |

## 本 repo 的定位：非商業使用

本工作流預設給**非商業**用途（教學、研究、個人創作、非營利頻道），所以預設用 Qwen-Image 2.1 與 Breeze TTS 2（只用於設計角色參考音；台詞由可商用的 BreezyVoice 念）。**要營利（廣告、贊助、會員、接案）就必須換掉非商用的元件**，方向如下：

| 環節 | 本 repo 預設（非商用） | 營利時的替換方向 | 本 repo 驗證狀態 |
|---|---|---|---|
| 角色定妝照、LoRA 首幀 | Qwen-Image 2.1 | 雲端 OpenAI Image 2.5（`tools/img25.py`，產出歸使用者，依 OpenAI 條款）；或向 Qwen 申請商業授權 | Image 2.5 是原專案實際出片用的首幀工具；替換後的整條流程未在本 repo 重測 |
| 首幀（附參考圖） | Qwen-Image-Edit 2511 | 不用換（Apache-2.0） | 已測 |
| 台詞配音 | BreezyVoice | 不用換（Apache-2.0） | 已測：三種硬體配置都通過；2026-10-07 整片 53 句台灣國語腔調分數 0.85（舊做法 Breeze／VoxCPM2 0.80） |
| 角色參考音（聲音設計） | Breeze TTS 2 | VoxCPM2 文字聲音設計（`gen_voice.py --design --control "描述"`，Apache-2.0）或自己有權利的真人錄音，再交給 BreezyVoice | VoxCPM2 聲音設計已能產生聲音；設計出的聲音台灣腔夠不夠未系統比較 |
| 挑音的發音對照 | edge-tts | 自己錄標準音，或只靠聽寫（ASR）挑 | 未測 |
| H3、Music 3 | — | 不用換，但要遵守地區限制、標示 AI 生成、商業顯著標示模型名稱 | — |

### 台灣腔、可商用的聲音工具（2026-10-07 依官方頁面整理；BreezyVoice 已實測並成為本 repo 預設，其餘未實測）

| 選項 | 本機／雲端 | 授權 | 台灣腔證據 | 備註 |
|---|---|---|---|---|
| **BreezyVoice（聯發科＋台大）＝本 repo 預設** | 本機 | Apache-2.0（程式與權重） | 強：官方專為台灣華語設計，注音控制、破音字處理；本 repo 實測腔調分數最高 | 參考音克隆；沒有文字聲音設計；底子是 CosyVoice 1。https://github.com/mtkresearch/BreezyVoice |
| BreezeBlue 官方付費 API（Breeze TTS 2 雲端版） | 雲端 | 經官方平台產生的音訊可商用（模型卡與價格頁說法不一致，訂閱前請向官方確認） | 與本 repo 用的 Breeze TTS 2 同一模型 | https://breezeblue.ai/pricing |
| Microsoft Azure Speech zh-TW | 雲端 | 付費可商用 | 強：官方「Taiwanese Mandarin」 | 只有 3 個聲音、沒有童聲 |
| VoAI 絕好聲創 | 雲端 | 商用條款未查到 | 強：主打台灣口音 | 快速克隆、多位配音員。https://www.voai.ai/ |
| VoxCPM2＋自己訓練的台灣腔 LoRA | 本機 | Apache-2.0 | 視訓練資料 | 用自己有權利的台灣腔錄音 5–10 分鐘；**不能拿 Breeze 自架產出當訓練資料** |

不能商用（權重非商用授權）：F5-TTS、MaskGCT、Llasa、Spark-TTS（權重 CC BY-NC-SA）、Fish-Speech／OpenAudio。
