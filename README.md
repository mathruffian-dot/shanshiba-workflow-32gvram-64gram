# 山獅霸的多重宇宙：AI 短片製作工作流（完整版：32GB VRAM＋64GB RAM）

YouTube 頻道「山獅霸的多重宇宙」的完整製作做法：每支片 1–3 分鐘、16:9、24fps，台灣校園奇幻喜劇。劇本由 AI agent（Claude Code）協作，角色、首幀、影片、配音、配樂全部用本機模型生成（原專案首幀用雲端 Image 2.5，本 repo 改為全本地），挑音、後製、自審全部腳本化；人只在劇本、首幀、成片三個關卡驗收。

> 私有分享版。原專案的本人照片、本人克隆聲音、API 金鑰、第三方素材、角色定妝照都沒有放進來。

## 1. 這份是給誰的

| 項目 | 內容 |
|---|---|
| 顯卡 | 32GB：RTX 5090（或其他 32GB 顯卡） |
| 記憶體 | 64GB 以上 |
| 硬碟 | NVMe SSD，模型約 145GB＋工作空間 |
| 狀態 | **原專案實際出片 8 支以上**（RTX 5090＋96GB）；64GB 記憶體 2026-10-07 模擬驗證：畫面逐格相同、速度相同 |
| 一支 40 鏡的片 | H3 部分約 41 分鐘；首幀審過到成片約 3–4 小時（大多是 GPU 自己跑，可過夜） |

詳細：[docs/hardware.md](docs/hardware.md)

## 三個硬體版本

同一套工作流，依硬體分成三份 repo，內容只差在硬體說明與設定檔：

| repo | 硬體 | 顯卡 | 記憶體 |
|---|---|---|---|
| **→ 本 repo** | 32GB VRAM＋64GB RAM | RTX 5090 32GB（或其他 32GB 顯卡） | 64GB 以上 |
| [shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram) | 16GB VRAM＋64GB RAM | RTX 4080／5070 Ti／5080 16GB | 64GB |
| [shanshiba-workflow-16gvram-32gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-32gram) | 16GB VRAM＋32GB RAM | RTX 4080／5070 Ti／5080 16GB | 32GB |

> ⚠️ **本 repo 預設給非商業用途**（教學、研究、個人創作）。用到的 **Qwen-Image 2.1、Breeze TTS 2 只能非商業使用**；要營利請照 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 換掉這兩個（例如生圖改用雲端 Image 2.5）。另外**MiniMax H3 的授權排除美國、歐盟、英國、南韓**；MiniMax H3／Music 3 要求公開內容標示 AI 生成。本 repo 不含任何模型權重。

## 2. 流程一覽

```
選題 → 劇本 ─✅─→ 角色定妝照（Qwen-Image 2.1）→ 首幀（Qwen-Image-Edit）─✅─→ 配音候選 → 自動挑音
     → H3 生成（DMAD 4 步）→ RTX VSR 放大 → 後製（名片、字卡、音效、配樂、字幕）
     → 組裝 → 片尾 → 自審五遍 → 封面＋YouTube 資訊 ─✅─→ 上片
                                           ✅ = 人工驗收關卡
```

全部在本機生成（只有挑音用的「台灣國語答案卷」edge-tts 需要連網，沒網路可改用本地 Breeze）。
每一步用哪支腳本、輸入輸出是什麼：[docs/02_端到端流程.md](docs/02_端到端流程.md)；本地角色與首幀做法：[docs/07_本地角色與首幀.md](docs/07_本地角色與首幀.md)。

**裝好之後先跑全本地示範片** `pipeline/demo_local/run_demo.py`：從零做兩個角色、4 鏡、配音、配樂，約 17 秒成片，證明整條工作流在你的電腦上能跑通。

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
  07_本地角色與首幀.md      不用雲端：Qwen 做角色與首幀（兩種做法）
  hardware.md               ⭐ 你這個硬體版本：模型組合、啟動參數、實測數據、風險
tools/                      全域工具（放到 C:\AI\tools）
  h3_shot.py ⭐             分鏡 JSON → 官方格式提示詞 → 格式檢查 → H3 生成
  img25.py                  OpenAI Image 2.5 生圖／編輯
  pron_check.py／pron_compare.py  中文配音聲調審核
  ...（完整清單見 docs/06_安裝.md）
pipeline/demo_local/        ⭐ 全本地示範片（裝好就能跑，不需要任何素材）
pipeline/example_D-7/       原專案一支真實短片〈D-7〉的全套腳本（首幀當時用雲端 Image 2.5；全本地請參考 demo_local 換掉首幀那步）
setup/                      模型下載清單（鎖定版本＋SHA-256）
templates/                  片尾範本、咒印法陣素材
agent/                      CLAUDE.md 範本、編劇技能、Blender 預演技能
configs/profile.cmd         這個硬體版本的環境變數
```

## 4. 最快上手

0. **AI agent 請先讀 [AGENT_SETUP.md](AGENT_SETUP.md)**，它會一步步帶你檢查硬體、安裝、下載、驗證。
1. 照 [AGENT_SETUP.md](AGENT_SETUP.md) 裝好 ComfyUI＋H3、Voice 環境、Breeze TTS，把 `tools/` 複製到 `C:\AI\tools`。
2. 先讀 [docs/hardware.md](docs/hardware.md)，再 `call configs\profile.cmd` 套用這個硬體版本的設定，然後執行 `tools\start_comfy.cmd`。
3. 跑 `setup\smoke_test.py` 與 `pipeline\demo_local\run_demo.py` 確認全部正常。
4. 把 `pipeline/example_D-7/` 複製成新片資料夾，改四張表：`gen_frames.py` 的 SHOTS、`voice_plan.py` 的 LINES、`plan_h3.py` 的 SHOTS、`assemble.py` 的 SEGS。
5. 依序跑：`gen_frames.py`（全本地時改用 demo_local 的首幀寫法） → 審首幀、建 `frames_ok` → `run_queue.sh`（配音→挑音→H3）→ `music_scenes.py` → `assemble.py --vsr` → `review.py`。

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
| OpenAI 金鑰（選用） | 預設不用；想改用雲端 Image 2.5 生首幀才需要 | 設環境變數 `OPENAI_API_KEY`，用 `tools/img25.py` |

## 7. 授權

| 內容 | 授權 | 檔案 |
|---|---|---|
| 本 repo 的程式碼（`*.py`、`*.ps1`、`*.cmd`、`*.sh`、設定檔） | **MIT** | [LICENSE](LICENSE) |
| 本 repo 的文件與素材（`*.md`、技能文字、範例圖） | **CC BY-NC 4.0**（姓名標示、非商業） | [LICENSE-docs.md](LICENSE-docs.md) |
| 用到的模型與第三方工具 | 各自的授權（**不隨本 repo 散布，自行下載**） | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

fork 或轉載時請保留這三個檔案。用這套工作流做出來的影片要遵守各模型的條款，特別是：MiniMax H3 的使用地區限制、MiniMax Music 3 的標示與 AI 揭露、Breeze TTS 2 的非商用限制（細節見 THIRD_PARTY_NOTICES.md）。
