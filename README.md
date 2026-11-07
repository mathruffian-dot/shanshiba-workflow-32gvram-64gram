# 山獅霸的多重宇宙：AI 短片製作工作流（完整版：32GB VRAM＋64GB RAM）

YouTube 頻道「山獅霸的多重宇宙」的完整製作做法：每支片 1–3 分鐘、16:9、24fps，台灣校園奇幻喜劇。劇本由 AI agent（Claude Code）協作，角色、首幀、影片、配音、配樂全部用本機模型生成（原專案首幀用雲端 Image 2.5，本 repo 改為全本地），挑音、後製、自審全部腳本化；人只在劇本、首幀、成片三個關卡驗收。

> 私有分享版。原專案的本人照片、本人克隆聲音、API 金鑰、第三方素材、角色定妝照都沒有放進來。

## 饒舌對決三分鐘上手

兩位歷史人物各唱一整首歌互嗆、DJ 主持的 3–4 分鐘橫式影片（範例：〈微積分之戰〉牛頓 vs 萊布尼茲）。把 `agent/skills/rap-battle/` 複製到你專案的 `.claude/skills/`，跟 Claude Code 說「做一場饒舌對決」，它會帶你選題、寫歌詞、填 `battle.json`，再跑下面這些指令。**整場在 Colab 跑，你的電腦不需要顯卡**；每段跑完 `out/` 會同步回本機，看過再跑下一段。

先準備 Google AI Pro（或 Colab 運算單元）＋ Colab CLI（見 [cloud/README.md](cloud/README.md)），然後：
```
xcopy /E /I pipeline\template_battle pipeline\my_battle      # 複製範本（macOS／Linux：cp -r pipeline/template_battle pipeline/my_battle）
python cloud/colab_h3.py start                               # 開 G4＋完整安裝（含 YuE2、Ming-3.0-TTS），約 10 分鐘
```

### 基本版：全部在 Colab、不用任何金鑰（YuE2 生歌＋Qwen-Image 2.1 畫圖＋Ming 念 DJ）
```
python cloud/colab_h3.py film pipeline/my_battle yue                    # 每人抽 10 首、只留拍速對的 → 聽 out/yue/
python cloud/colab_h3.py film pipeline/my_battle songs dj audio         # 聽 out/audio/mix.wav
python cloud/colab_h3.py film pipeline/my_battle chars scenes frames    # 看 out/first/_sheet.jpg
python cloud/colab_h3.py film pipeline/my_battle specs h3               # 看 out/review/clips_*.jpg
python cloud/colab_h3.py film pipeline/my_battle cut review srt         # 看 out/cut/ 的完整成片
python cloud/colab_h3.py stop                                           # 一定要關：閒置的 G4 每小時照扣 8.9 單元
```
2026-10-29 在 Colab G4 從頭實測通過：一整場約 1.5–2 小時、15–18 運算單元。YuE2 的 rap 狠勁較弱、要多抽；Qwen 畫不出雙人對峙、場景裡的字會亂碼；**Qwen-Image 2.1 只能非商業使用**。

### 優化版：Suno 生歌＋Image 2.5 畫圖（要 Kie.ai 與 OpenAI 金鑰）
在 `battle.json` 加一行 `"image_backend": "img25"`，然後：
```
python cloud/colab_h3.py film pipeline/my_battle songtext               # 產生 out/songtext/suno_*.txt
set KIE_API_KEY=你的金鑰                                                  # macOS／Linux 用 export
cd pipeline/my_battle
python kie_suno.py submit A a1 && python kie_suno.py poll a1            # 每次 2 版，約 $0.06
python kie_suno.py submit B b1 && python kie_suno.py poll b1            # 聽 out/suno/，挑好的存成 song/A.mp3、song/B.mp3
cd ../..
set OPENAI_API_KEY=你的金鑰                                               # film 會自動帶到 VM，畫面上只顯示 ***
python cloud/colab_h3.py film pipeline/my_battle songs dj audio         # 聽 out/audio/mix.wav
python cloud/colab_h3.py film pipeline/my_battle chars scenes frames    # 看 out/first/_sheet.jpg
python cloud/colab_h3.py film pipeline/my_battle specs h3               # 看 out/review/clips_*.jpg
python cloud/colab_h3.py film pipeline/my_battle cut review srt         # 看 out/cut/ 的完整成片
python cloud/colab_h3.py stop
```
沒有 Kie：把 `out/songtext/suno_A_lyrics.txt`、`suno_A_style.txt` 貼到 Suno 網頁的 Custom 模式（B 同理）也一樣。Suno 編曲最豐富、rap 最兇；Image 2.5 畫得出雙人對峙和正確的字。原頻道兩場對決用的就是 Suno＋Image 2.5，但**範本的 Image 2.5 分支還沒在 Colab 從頭重跑過**。

有顯卡想在本機跑：同樣的 stage 改成 `make_battle.py <stage…>`，詳見 [pipeline/template_battle/README.md](pipeline/template_battle/README.md)。

## 1. 這份是給誰的

| 項目 | 內容 |
|---|---|
| 顯卡 | 32GB：RTX 5090（或其他 32GB 顯卡） |
| 記憶體 | 64GB 以上 |
| 硬碟 | NVMe SSD，模型約 145GB＋工作空間 |
| 狀態 | **原專案實際出片 8 支以上**（RTX 5090＋96GB）；64GB 記憶體 2026-10-07 模擬驗證：畫面逐格相同、速度相同 |
| 一支 40 鏡的片 | H3 部分約 41 分鐘；首幀審過到成片約 3–4 小時（大多是 GPU 自己跑，可過夜） |

詳細：[docs/hardware.md](docs/hardware.md)

## 四個版本

同一套工作流，依硬體分成四份 repo，內容只差在硬體說明與設定檔（每一份都有 cloud/，本機跑不動時可以把 H3 送到 Colab）：

| repo | 硬體 | 顯卡 | 記憶體 |
|---|---|---|---|
| **→ 本 repo** | 32GB VRAM＋64GB RAM | RTX 5090 32GB（或其他 32GB 顯卡） | 64GB 以上 |
| [shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram) | 16GB VRAM＋64GB RAM | RTX 4080／5070 Ti／5080 16GB | 64GB |
| [shanshiba-workflow-16gvram-32gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-32gram) | 16GB VRAM＋32GB RAM | RTX 4080／5070 Ti／5080 16GB | 32GB |
| [shanshiba-workflow-colab](https://github.com/mathruffian-dot/shanshiba-workflow-colab) | Google Colab 雲端 | 不需要（H3 用 Colab G4；有 8–12GB 顯卡可本機做配音、首幀） | 不限 |

> ⚠️ **本 repo 預設給非商業用途**（教學、研究、個人創作）。用到的 **Qwen-Image 2.1、Breeze TTS 2 只能非商業使用**；要營利請照 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 換掉這兩個（例如生圖改用雲端 Image 2.5、角色參考音改用 VoxCPM2 聲音設計或真人錄音）。台詞配音用的 BreezyVoice 是 Apache-2.0，可商用。另外**MiniMax H3 的授權排除美國、歐盟、英國、南韓**；MiniMax H3／Music 3 要求公開內容標示 AI 生成。本 repo 不含任何模型權重。

## 2. 流程一覽

```
選題 → 劇本 ─✅─→ 角色定妝照（Qwen-Image 2.1）→ 首幀（Qwen-Image-Edit）─✅─→ 角色參考音（Breeze 設計，一次）
     → H3 生成（DMAD 4 步，台詞由 H3 拿角色參考音自己念）→ 聽寫比對台詞 → RTX VSR 放大 → 後製（名片、字卡、音效、配樂、字幕）
     → 組裝 → 片尾 → 自審五遍 → 封面＋YouTube 資訊 ─✅─→ 上片
                                           ✅ = 人工驗收關卡
```

全部在本機生成（只有 BreezyVoice 備案挑音用的「台灣國語答案卷」edge-tts 需要連網，沒網路可改用本地 Breeze）。

> **2026-10-23 預設改變：畫面內的台詞改成「H3 自己念＋角色參考音」**（h3_shot spec 的 `audio.voice_ref`），不再先用 BreezyVoice 配音當固定音軌。原頻道在 RTX 5090 實測（同一場戲三鏡）：聲音像參考音的程度和 TTS 差不多（聲紋 0.66 對 0.68）、三鏡最像同一個人（0.75）、表演比固定音軌生動。BreezyVoice 固定音軌改當備案（H3 念錯抽不出來、數字日期難字、要精準時間點的聲畫同步）。⚠ **本 repo 的成片範本 `make_film.py` 已改成這個預設，但還沒在本 repo 從頭實測**；遇到問題可在 `film.json` 設 `"voice_mode": "fixed"` 退回舊做法。
> **2026-10-24 新增（選用）：遠景小臉精修 `tools/face_refine.py`**。遠景裡臉小於約 50 px 的角色，放大前追臉、用 H3 低強度重畫臉再貼回，原頻道 3 鏡實測 25–30 px 的臉從一團糊變成認得出本人、不閃，每鏡約 30 秒（只在 ComfyUI 0.40＋RTX 5090 測過；要另裝節點與 23GB 模型，見 [docs/06_安裝.md](docs/06_安裝.md)）。同日也實測了社群微調模型 Singularity V2，**不採用**（參考音較不像本人、會改掉首幀背景），結果在 [docs/03_規則與踩坑.md](docs/03_規則與踩坑.md)。

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
  make_breezyvoice.cmd      台詞配音備案：BreezyVoice 每句 8 候選 → 聽寫＋腔調自動挑（預設改由 H3 自己念）
  gen_image.py              本機 Qwen-Image 2.1／Qwen-Image-Edit 生圖（`--turbo`＝8 步草稿模式）
  make_whitemodel.py        舞蹈／武打：原片 → 灰色白模影片，當 H3 動作參考
  make_narration.py         口播／旁白：BreezyVoice 一次念 2–3 句、停頓照標點、自動挑候選
  cosy_vc.py                換聲：Seedance 等雲端影片的台詞換成角色音色，字的時間不變（選用）
  vc_swap.py                換字：念錯的字用 Ming 角色聲音重念、接回原位置再整句換聲，不重拍影片（選用）
  start_comfy.cmd           啟動 ComfyUI
  img25.py                  OpenAI Image 2.5 生圖／編輯（選用，雲端）
  pron_check.py／pron_compare.py  中文配音聲調審核
  ...（完整清單見 docs/06_安裝.md）
pipeline/template_local/    ⭐ 做新片的範本：改 film.json → make_film.py 從角色做到成片＋自審
pipeline/demo_local/        全本地示範片（4 鏡，安裝驗證用，不需要任何素材）
pipeline/example_D-7/       原專案一支真實短片〈D-7〉的全套腳本（參考用：首幀用雲端 Image 2.5、舊配音流程，不能直接照跑）
setup/                      安裝：模型下載清單（鎖定版本＋逐檔雜湊）、套件清單、smoke_test、硬體偵測
cloud/                      ⭐ 本機跑不動時：H3（或整套流程）送到 Google Colab G4 跑（colab_h3.py；見 cloud/README.md）
sfx/                        58 個 Freesound CC0 音效（腳步、翻頁、門、球、歡呼…）
templates/                  片尾範本、咒印法陣素材
agent/                      CLAUDE.md 範本、編劇技能、Blender 預演技能
configs/profile.cmd         這個硬體版本的環境變數
```

## 4. 最快上手

0. **AI agent 請先讀 [AGENT_SETUP.md](AGENT_SETUP.md)**，它會一步步帶你檢查硬體、安裝、下載、驗證。`python setup/detect_hardware.py` 會列出每個元件建議在本機還是雲端跑；**本機跑不動 H3 → [cloud/README.md](cloud/README.md)**（用 Google AI 方案的 Colab 運算單元跑）。
1. 照 [AGENT_SETUP.md](AGENT_SETUP.md) 裝好 ComfyUI＋H3、Voice 環境、Breeze TTS、BreezyVoice，把 `tools/` 複製到 `C:\AI\tools`。
2. 先讀 [docs/hardware.md](docs/hardware.md)，再在同一個 cmd 視窗 `call configs\profile.cmd` 套用這個硬體版本的設定，然後執行 `C:\AI\tools\start_comfy.cmd`。
3. 跑 `setup\smoke_test.py` 與 `pipeline\demo_local\run_demo.py` 確認全部正常。
4. 開始做自己的片，照下面的檢查表一步一步來（2026-10-07 實測：一個沒看過本專案的 agent 照這個 repo，約 45 分鐘做出 7 鏡、28 秒的片）。

| # | 步驟 | 工具 | 看哪份文件 | 產出 | 要人工看嗎 |
|---|---|---|---|---|---|
| 1 | 劇本＋鏡表（每鏡 ≤12 秒） | `agent/skills/shanshiba-drama` | SKILL.md 開頭的版本說明、`docs/03` | `劇本.md` | ✅ 確認劇本 |
| 1.5 | 生成前試映：16 宮格分鏡草圖＋**文字讀本**（不做 TTS；用字數估片長與每鏡 H3 鏡長＝字數÷3＋2 秒） | `make_storyboard.py`（要 OpenAI 金鑰，沒有就跳過草圖）、`assemble_read.py` | `agent/skills/shanshiba-drama/references/table-read.md` | `preview/讀本試映.mp4`、`讀本_timeline.json` | ✅ 看完說「通過」才做首幀 |
| 2 | 角色定妝照（單張、灰底、半身） | `gen_image.py`（Qwen-Image 2.1） | `docs/07` §1 | `chars/<角色>.png` | ✅ 挑一張定案 |
| 3 | 場景母版（空景，之後裁成各鏡景別） | `gen_image.py` | `docs/07` §4 | `masters/*.png` | |
| 4 | 首幀（附定妝照＋母版裁切，**每鏡照抄角色完整外觀描述**） | `gen_image.py --model qwen-edit --ref` | `docs/07` §2–3 | `first/<鏡>.png` | ✅ 逐張看：臉、服裝、多手多腳、背景有沒有字 |
| 5 | 角色聲音（一次） | `breeze_batch.py`（設計參考音） | `docs/03` §5 | `voice/ref_<角色>.wav` | ✅ 聽一次、定案後不換 |
| 6 | H3 每鏡（DMAD 4 步、只給首幀；**有台詞給角色參考音 `audio.voice_ref`、H3 自己念**（兩三人對話同鏡用 `voice_refs` 各給參考音）；看得到臉又沒台詞的鏡給靜音；**`action` 照官方結構寫 50–120 字具體動作**，動作鏡首幀畫動作開始前） | `h3_shot.py`（spec 加 `"draft": true`） | `docs/02` §6「動作寫法」、`docs/03` §4–5、`tools/examples/` | `h3/<鏡>/clip.mp4` | ✅ 抽格看：換臉、多人、鏡頭漂移；**聽寫比對台詞**（H3 會改用詞） |
| 7 | 配樂（純器樂、多抽幾個 seed，挑人聲殘留最少的） | `gen_music3.py` → `audio-separator` | `docs/02` §9 | `music/*.flac` | |
| 8 | 放大、剪接（H3 自己念的台詞不提前；BreezyVoice 備案台詞提前 0.2 秒）、配樂壓低（台詞期間 15–30%）、響度、字幕 | `upscale_vsr.py`、ffmpeg | `docs/02` §7、§10（**響度指令照抄，`alimiter` 要 `level=false`**） | `cut/<片名>_1080p.mp4` | |
| 9 | 片尾（工具名單＋AI 生成標示） | `templates/ending/render_ending.py` | `templates/ending/README.md` | `ending.mp4` | |
| 10 | 自審五遍（抽格、ASR、雜訊、黑畫面與響度、切點） | 參考 `pipeline/example_D-7/review.py`、`noise_scan.py`、`stt.py`、`framecheck.py`（每秒一格）、`clipcheck.py`、`flashcheck.py` | `docs/04_自審清單.md` | `review/` | ✅ 最後一定給人看成片 |

**最快的做法：複製 [`pipeline/template_local/`](pipeline/template_local/README.md)，只改 `film.json`**，`make_film.py` 會把上面 2–10 步全部做完（已附一支 7 鏡範例片的設定，從零重跑驗證過）。`pipeline/demo_local/` 是 4 鏡的最小安裝驗證；`pipeline/example_D-7/` 是原頻道一支 120 秒成片的完整腳本，可參考剪接與自審寫法，但它用雲端 Image 2.5 首幀和舊配音流程，**不能直接照跑**。

建議讓 AI agent 來跑：把 [agent/CLAUDE.md範本.md](agent/CLAUDE.md範本.md) 放進專案根目錄，它會照規則做、自審、寫紀錄。

## 5. 最重要的十條經驗

1. **H3 提示詞一律用官方六段格式**，用 `h3_shot.py` 從 JSON 組，不手寫。
2. **預設只給首幀**；多人鏡加身份參考圖會多長出一個人。
3. **DMAD 4 步就是定稿**：抽到滿意的直接用，同 seed 換 14 步畫面會不同。
4. **單鏡 ≤12 秒**；15 秒會漂移、自己切鏡。
5. **不說話的鏡頭給靜音引導音軌**，否則角色會自己嘟囔。
6. **畫面上的中文一律後製疊字**，H3 會把字寫成亂碼。
7. **台詞讓 H3 拿角色參考音自己念**（2026-10-23 起）：Breeze 設計角色聲音（一次）→ spec 寫 `audio.voice_ref` → 聽寫比對原文（H3 會改用詞，例：「二十四號」→「二十四日」）、抽 2 個 seed。念錯抽不出來的句子才改用 **BreezyVoice** 固定音軌（每句 8 候選、念不準的字標注音 `連假[:ㄐㄧㄚ4]`）。
8. **低頭、轉身後臉會換人** → 再生一張「動作結束時」的畫面當尾幀鎖住（原頻道用 Image 2.5；本地可用 Qwen-Image-Edit 附定妝照）。
9. **先做最難的一鏡再批次**，不要整片生完才發現共通問題。
10. **不合格就重拍到合格**，不靠剪掉躲；給人看並排影片，數字只當備註。

## 6. 這個 repo 沒有放的東西

| 東西 | 原因 | 你要自己準備 |
|---|---|---|
| 原頻道的角色定妝照、轉面圖、表情表 | 頻道角色資產 | 用本機 Qwen-Image 2.1 為自己的角色做單張半身定妝照（見 [07_本地角色與首幀.md](docs/07_本地角色與首幀.md)） |
| 配音參考音 | 含本人授權克隆聲音 | 自己錄或用 Breeze 設計；台詞預設由 H3 拿參考音自己念，BreezyVoice 為備案 |
| 模型權重 | 檔案大、各有授權 | 照 [AGENT_SETUP.md](AGENT_SETUP.md) 第 3 節下載（約 150GB） |
| 成片影片 | 檔案大 | 看頻道 |
| OpenAI 金鑰（選用） | 預設不用；想改用雲端 Image 2.5 生首幀才需要 | 設環境變數 `OPENAI_API_KEY`，用 `tools/img25.py` |
| Kie.ai 金鑰（選用） | 想用雲端 Seedance 2.5 生影片才需要（約 63 點／秒，200 點 ≈ 1 美元） | 設環境變數 `KIE_API_KEY`，用 `tools/sd25_shot.py`；有台詞的鏡一定給角色參考音 |
| Google AI 方案／Colab 運算單元（選用） | 本機跑不動 H3 時才需要 | 見 [cloud/README.md](cloud/README.md) |

（音效有附：`sfx/` 裡 58 個 Freesound CC0 音效。）

## 7. 授權

| 內容 | 授權 | 檔案 |
|---|---|---|
| 本 repo 的程式碼（`*.py`、`*.ps1`、`*.cmd`、`*.sh`、設定檔） | **MIT** | [LICENSE](LICENSE) |
| 本 repo 的文件與素材（`*.md`、技能文字、範例圖） | **CC BY-NC 4.0**（姓名標示、非商業） | [LICENSE-docs.md](LICENSE-docs.md) |
| 用到的模型與第三方工具 | 各自的授權（**不隨本 repo 散布，自行下載**） | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

fork 或轉載時請保留這三個檔案。用這套工作流做出來的影片要遵守各模型的條款，特別是：MiniMax H3 的使用地區限制、MiniMax Music 3 的標示與 AI 揭露、Breeze TTS 2 的非商用限制（細節見 THIRD_PARTY_NOTICES.md）。
