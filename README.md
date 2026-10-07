# 山獅霸的多重宇宙：本機 AI 短片製作工作流

YouTube 頻道「山獅霸的多重宇宙」的完整製作做法。每支片 1–3 分鐘、16:9、24fps，台灣校園奇幻喜劇。
**劇本由 AI agent（Claude Code）協作寫，畫面首幀用 OpenAI Image 2.5，影片與音效用本機 MiniMax H3 生成，配音、挑音、配樂、後製、自審全部腳本化**，人只在三個關卡驗收：劇本、首幀、成片。

> 這是私有分享版。原專案裡的本人照片、本人克隆聲音、API 金鑰、第三方素材都沒有放進來；角色定妝照也沒放（見[第 6 節](#6-這個-repo-沒有放的東西)）。

## 1. 先選版本

| | 版本 A：現行做法 | 版本 B：低需求版 |
|---|---|---|
| 硬體 | RTX 5090 32GB／96GB RAM | 16GB VRAM／64GB RAM（4080、5070 Ti、5080） |
| 狀態 | **已實際出片 8 支以上** | **5090 上模擬驗證過**（2026-10-07）；真實卡速度未實測 |
| 模型 | 剪枝 int8 H3＋int8 文字編碼器 | **跟 A 一樣**（記憶體 48GB 以下才換 NVFP4） |
| 畫面 | — | 同 seed **跟 A 逐格相同**（顯存峰值約 14.4GB） |
| 單鏡長度 | ≤12 秒 | ≤12 秒（260 格實測可跑） |
| 一支 40 鏡的片 | H3 約 41 分鐘 | 推估 1.5–2 小時 |
| 說明 | [docs/hardware_A_5090.md](docs/hardware_A_5090.md) | [docs/hardware_B_16GB.md](docs/hardware_B_16GB.md) |

兩版的**流程與模型完全一樣**，版本 B 只是啟動 ComfyUI 時加 `--reserve-vram 1.5`、一次只跑一件 GPU 工作。切換用 [configs/](configs/) 裡的設定檔。

## 2. 流程一覽

```
選題 → 劇本 ─✅─→ Blender 布置圖 → 首幀（Image 2.5）─✅─→ 配音候選 → 自動挑音
     → H3 生成（DMAD 4 步）→ RTX VSR 放大 → 後製（名片、字卡、音效、配樂、字幕）
     → 組裝 → 片尾 → 自審五遍 → 封面＋YouTube 資訊 ─✅─→ 上片
                                           ✅ = 人工驗收關卡
```

每一步用哪支腳本、輸入輸出是什麼：[docs/02_端到端流程.md](docs/02_端到端流程.md)。

## 3. 目錄

```
README.md
docs/
  01_總覽與架構.md          三層架構、為什麼這樣分
  02_端到端流程.md          逐步驟：工具、產出、耗時、人工關卡
  03_規則與踩坑.md          所有規則（附理由）＋踩坑對策
  04_自審清單.md            review.py 五遍＋常退件清單
  05_agent協作與知識庫.md   讓 AI agent 長期接手的做法
  06_安裝.md                環境、模型、資料夾慣例
  hardware_A_5090.md        版本 A：硬體、模型、實測耗時
  hardware_B_16GB.md        版本 B：調整方式、風險、驗證狀態
tools/                      全域工具（放到 C:\AI\tools）
  h3_shot.py ⭐             分鏡 JSON → 官方格式提示詞 → 格式檢查 → H3 生成
  img25.py                  OpenAI Image 2.5 生圖／編輯
  pron_check.py／pron_compare.py  中文配音聲調審核
  ...（完整清單見 docs/06_安裝.md）
pipeline/example_D-7/       一支真實短片〈D-7〉的全套製作腳本（可直接複製改表格）
templates/                  片尾範本、咒印法陣素材
agent/                      CLAUDE.md 範本、編劇技能、Blender 預演技能
configs/                    版本 A／B 的環境變數
```

## 4. 最快上手

1. 照 [docs/06_安裝.md](docs/06_安裝.md) 裝好 ComfyUI＋H3、Voice 環境、Breeze TTS，把 `tools/` 複製到 `C:\AI\tools`。
2. 套用版本設定：`configs\profile_A_5090.cmd` 或 `configs\profile_B_16GB.cmd`（記憶體 48GB 以下用 `profile_B_16GB_lowRAM.cmd`），再執行 `tools\start_comfy.cmd`。
3. 把 `pipeline/example_D-7/` 複製成新片資料夾，改四張表：`gen_frames.py` 的 SHOTS、`voice_plan.py` 的 LINES、`plan_h3.py` 的 SHOTS、`assemble.py` 的 SEGS。
4. 依序跑：`gen_frames.py` → 審首幀、建 `frames_ok` → `run_queue.sh`（配音→挑音→H3）→ `music_scenes.py` → `assemble.py --vsr` → `review.py`。

建議讓 AI agent 來跑：把 [agent/CLAUDE.md範本.md](agent/CLAUDE.md範本.md) 放進專案根目錄，它會照規則做、自審、寫紀錄。

## 5. 最重要的十條經驗

1. **H3 提示詞一律用官方六段格式**，用 `h3_shot.py` 從 JSON 組，不手寫。
2. **預設只給首幀**；多人鏡加身份參考圖會多長出一個人。
3. **DMAD 4 步就是定稿**：抽到滿意的直接用，同 seed 換 14 步畫面會不同。
4. **單鏡 ≤12 秒**；15 秒會漂移、自己切鏡。
5. **不說話的鏡頭給靜音引導音軌**，否則角色會自己嘟囔。
6. **畫面上的中文一律後製疊字**，H3 會把字寫成亂碼。
7. **台灣腔配音**：Breeze 設計聲音 → VoxCPM2 生成 → 跟台灣國語參考音比聲調挑最好的；念不準就換同音字。
8. **低頭、轉身後臉會換人** → 用 Image 2.5 生尾幀鎖住。
9. **先做最難的一鏡再批次**，不要整片生完才發現共通問題。
10. **不合格就重拍到合格**，不靠剪掉躲；給人看並排影片，數字只當備註。

## 6. 這個 repo 沒有放的東西

| 東西 | 原因 | 你要自己準備 |
|---|---|---|
| 角色定妝照、轉面圖、表情表 | 頻道角色資產 | 用 Image 2.5 為自己的角色做一組（見 [03_規則與踩坑.md](docs/03_規則與踩坑.md) §3） |
| 配音參考音 | 含本人授權克隆聲音 | 自己錄或用 Breeze 設計 |
| 模型權重 | 檔案大、各有授權 | 照 [06_安裝.md](docs/06_安裝.md) 下載 |
| 成片影片 | 檔案大 | 看頻道 |
| OpenAI 金鑰 | — | 設環境變數 `OPENAI_API_KEY` |

## 7. 授權提醒

- MiniMax H3、MiniMax Music 3：各有社群授權（H3 排除部分國家地區、Music 3 要求標示與 AI 揭露、有營收上限），商用前自己讀原文。
- Breeze TTS 2、YuE2：**非商用**。
- 片尾要揭露 AI 生成；YouTube Studio 的「合成內容」要勾選。
- 本 repo 程式碼：私有分享，未經同意請勿再散布。
