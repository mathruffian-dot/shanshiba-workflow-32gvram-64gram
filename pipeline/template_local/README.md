# template_local：全本地多鏡短片範本（做新片從這裡開始）

一個設定檔 `film.json` 寫完整支片（角色、場景、每一鏡、台詞、配樂、片尾），`make_film.py` 從角色定妝照一路做到成片和自審。全部本機模型，不需要任何雲端金鑰。

範例 `film.json` 是〈被狗吃掉的作業〉：7 鏡、正片約 28 秒＋片尾 9.5 秒。2026-10-07 一個沒看過本專案的 agent，只靠本 repo 做出這支片，之後把它寫的腳本整理成這個範本，再從零重跑驗證過（時間見最後一節）。

## 用法

1. 把整個 `template_local/` 複製一份到 `pipeline/` 底下，改名成你的片名，例如 `pipeline/my_film/`。如果複製到別的地方，請把 `film.json` 的 `repo_dir` 改成指向本 repo 根目錄（片尾範本在 `<repo>/templates/ending/`）。
2. 改 `film.json`（欄位說明見下一節）。劇本先用 `agent/skills/shanshiba-drama` 寫好、做完生成前試映（16 宮格草圖＋讀本，`tools/make_storyboard.py`、`tools/assemble_read.py`，見技能的 `references/table-read.md`），聽過說「通過」再把鏡表填進 `shots`。
3. 在同一個 cmd 視窗執行：
   ```
   set PYTHONUTF8=1
   call <repo>\configs\profile.cmd
   C:\AI\tools\start_comfy.cmd
   cd <repo>\pipeline\my_film
   C:\AI\H3\venv\Scripts\python.exe make_film.py chars masters frames
   ```
4. **人工關卡 1**：看 `out/first/_sheet.jpg`。臉、服裝要一致，不能多手多腳，背景不能有字，窗戶方向要對。不滿意的鏡：刪 `out/first/<鏡>.png`，在 `film.json` 的 `seeds` 加 `"frame_<鏡>": 新數字`，或改該鏡的 `frame` 描述，再跑 `frames`。
5. `make_film.py voices h3`
   - **2026-10-23 起預設 `voice_mode: "h3_ref"`**：`voices` 只用 Breeze 設計角色參考音（`out/voice/ref_<角色>.wav`），台詞由 H3 在 `h3` 階段拿參考音自己念；`h3` 結尾自動從成片分離人聲、聽寫、比對原文，結果寫在 `out/voice_picks.json`（`heard`、`match`）。⚠ 這個預設在本範本**還沒從頭實測**（原頻道已在 RTX 5090 實測 H3＋參考音）。
   - H3 念的和原文差太多時程式會停下來：在 `seeds` 加 `"h3_<鏡>": 新數字`、刪 `out/h3/<鏡>/clip.mp4`，再跑 `set ONLY=<鏡>` → `make_film.py h3`。抽 2–3 次都不對（常見：數字日期、H3 改成大陸用詞），在該句 `line` 加 `"voice_mode": "fixed"`，再跑 `voices h3`（改用 BreezyVoice 固定音軌）。
   - BreezyVoice（`fixed`）的句子 8 個候選都念錯時程式也會停下來：在該句加 `"tts"`，念錯的字後面標注音，例如 `"tts": "老師，連假[:ㄐㄧㄚ4]要去哪？"`。刪掉 `out/voice/bv` 再跑 `voices`。
   - 單字喊叫、同音字這類 ASR 本來就聽不準的句子，人聽過沒問題就用 `set ALLOW_REVIEW=1` 繼續。
6. **人工關卡 2**：看 `out/review/clips_<鏡>.jpg`（每鏡 6 格），檢查有沒有換臉、多出人、鏡頭漂移。不滿意就刪 `out/h3/<鏡>/clip.mp4`，在 `seeds` 加 `"h3_<鏡>": 新數字`，再跑 `set ONLY=S3 S5` → `make_film.py h3`。
7. `make_film.py amb edl music ending cut review`
8. **人工關卡 3**：看 `out/review/` 的自審結果，最後**一定要人看完整的** `out/cut/film_1080p.mp4`。
   - 只改剪接（`cut_in`、`tail`）：跑 `edl cut review`。
   - 換配樂：改 `music.seeds`，刪 `out/music`，跑 `music cut review`。

不給 stage 就是全部依序跑。每一步已經存在的檔案都會跳過，所以中斷後重跑會從斷點接著做。

## film.json 欄位

| 欄位 | 說明 |
|---|---|
| `title` | 片名（片尾標題） |
| `repo_dir` | 本 repo 根目錄，相對於這個資料夾（放在 `pipeline/<片名>/` 時用預設 `../..`） |
| `cine` | 每張首幀開頭的電影感句（底片、鏡頭、光線、調色）。光線要寫具體，只寫 soft daylight 會變平淡白光 |
| `set_sentence` | 場景參考圖那句，`{n}` 會換成場景圖的編號（角色數＋1） |
| `frame_suffix` | 每張首幀結尾（不要字、不要浮水印…） |
| `voice_mode` | 台詞聲音：`"h3_ref"`（預設，H3 拿角色參考音自己念）或 `"fixed"`（舊做法：BreezyVoice 配音當固定音軌）。單句可在 `line` 裡另設 |
| `h3` | H3 共用設定：`style`、`setting`、`soundscape`（不寫台詞）、`camera`、`constraints`（每鏡都加的限制） |
| `chars.<代號>` | `name`（字幕顯示）、`look`（**完整外觀描述**，每張首幀都會照抄）、`voice_design`（Breeze 設計聲音的描述）、`voice_sample`（設計聲音時念的句子，也是 BreezyVoice 的參考逐字稿）、`h3_voice`、`edge_voice`（挑音用的台灣國語答案卷聲音）、`sub_color`（字幕顏色，ASS 格式 `&H00BBGGRR`） |
| `masters.<名稱>` | 場景母版（空景）提示詞。同一個場景的鏡頭都裁同一張母版，空間才一致 |
| `shots[]` | 每一鏡，見下表 |
| `seeds` | 想換的 seed：`char_<角色>`、`master_<名稱>`、`frame_<鏡>`、`h3_<鏡>`、`voice_<角色>` |
| `music` | `caption`（純器樂描述，寫明 Vocal: NONE）、`seeds`（抽幾首，挑人聲殘留最少的） |
| `mix` | `say_lead`（台詞比畫面提前幾秒，預設 0.2）、`default_tail`、`music_under_lines`（台詞期間配樂音量，0.15–0.30）、`music_bed_rms`、`target_lufs` |
| `ending` | 片尾：`closeups`（拿哪幾鏡的首幀當特寫）、`cards`（每張卡最多 3 行工具）、`card_dur`、`title_dur`；不要片尾就刪掉這個欄位 |

每一鏡（`shots[]`）：

| 欄位 | 說明 |
|---|---|
| `id` | 鏡號 |
| `refs` | 畫面裡的角色代號（依序對應 `<image1>`、`<image2>`…）。**只放畫面裡要演戲的人**，有定義但不入鏡的角色 H3 會把他叫進畫面 |
| `scene` | `[母版名稱, [x0, y0, x1, y1]]`：從母版裁哪一塊當場景參考（0–1 比例） |
| `dur` | 秒數（4–12）。有台詞時會自動延長：`h3_ref` 到「開口時間＋估計台詞長度（每秒約 4 字）＋1.2 秒」，`fixed` 到「開口時間＋配音長度＋0.8 秒」 |
| `line` | `{"who", "text", "at"}`：誰說、字幕文字、第幾秒開口（`h3_ref` 時只是參考，實際開口時間由聽寫抓）；`"voice_mode"`（選填）這句改用別的模式；`"tts"`（選填）是送給 BreezyVoice 的寫法（可加注音）。沒台詞寫 `null`（H3 會收到靜音音軌，角色不會自己嘟囔） |
| `frame` | 首幀描述：景別、角色在哪、做什麼、表情、窗戶在畫面哪一邊 |
| `action` | H3 的動作描述（沒台詞的鏡頭寫明 He does not speak）。**2026-10-23 起照官方結構寫 50–150 字**：「Starting from <Picture 1>, …」首幀定錨→動作開始→持續發展→結果，寫身體部位、幅度、次數（見 `docs/02` §6「動作寫法」；一句話版動作量只有 1/2.7）。範例 film.json 的 7 鏡已改成新寫法，2026-10-24 從頭重跑驗證過（推眼鏡、抓頭、滑進椅子等動作都照描述演出） |
| `extra_constraints` | 這一鏡額外的限制 |
| `amb`、`amb_seed` | `true`＝這鏡需要動作音效（翻書包、腳步）：另拍一支 H3 原生音效版，聽寫確認沒有人聲才取它的音軌；有人聲就換 `amb_seed` 或改用 `sfx/` 的音效 |
| `cut_in` | 剪掉鏡頭開頭幾秒（H3 常晚開口） |
| `cut_out` | `"full"`＝用到鏡尾；不寫＝台詞結束＋`tail` 秒 |
| `tail` | 台詞後留幾秒反應（喜劇停頓） |

## 輸出（`out/`）

`chars/` 定妝照、`masters/` 場景母版與每鏡裁切、`first/` 首幀與 `_sheet.jpg`、`voice/` 角色參考音、答案卷與 `bv/`（候選、`picks.json`、選中的台詞）、`h3/<鏡>/` 每鏡 spec、提示詞與 clip、`music/`、`ending/`、`post/`（`edl.json` 時間軸、放大片段、混音、字幕）、`cut/film_1080p.mp4` 成片＋手機版、`review/` 自審、`timing.json` 各階段時間。

## 驗證紀錄

- 2026-10-07 原始版（agent 自己寫的 film.py／post.py）：約 45 分鐘做完，成片 6 句聽寫全對、−15.8 LUFS、峰值 −2.0 dBFS。
- 2026-10-07 整理成本範本後，在 RTX 5090 從零重跑（`make_film.py` 不帶參數一次跑完）：**共 28.7 分鐘**，成片 37.7 秒。

| 階段 | 秒數 | 備註 |
|---|---|---|
| chars | 26 | 2 張定妝照 |
| masters | 118 | 2 張 2K 場景母版 |
| frames | 605 | 7 張首幀，每張附 2 張參考圖約 85 秒 |
| voices | 231 | 2 個角色聲音設計＋6 句 × 8 候選＋自動挑選，6 句全部合格 |
| h3 | 414 | 7 鏡 DMAD，每鏡約 1 分鐘 |
| amb | 59 | S2 原生音效版，聽寫確認沒有人聲 |
| music | 124 | 3 首，挑人聲殘留最少的 |
| ending | 66 | |
| cut | 65 | VSR、剪接、混音、字幕、手機版 |
| review | 15 | |

自審結果：響度 −15.7 LUFS、峰值 −2.1 dBFS；沒有黑畫面、定格、切點明暗跳動、台詞重疊或被鏡尾切掉；雜訊 7 鏡都 ok；成片聽寫 6 句裡 5 句 1.00，「是……鄰居的狗」聽成「鄰居的歌」（0.80，挑音階段聽寫正確，混音後的成片要人聽確認）。

- **2026-10-24 現行預設重跑**（`voice_mode: "h3_ref"`＝H3 拿 Breeze 設計的參考音自己念、action 照官方結構寫 75–101 字、修剪點對齊 1/24 秒；RTX 5090、ComfyUI 0.40、工具用 repo 的 `tools/`）：**共約 27 分鐘**，成片 29.5 秒＋片尾 9.5 秒＝39.0 秒（影像、聲音都是 39.000 秒）。

| 階段 | 秒數 | 備註 |
|---|---|---|
| chars | 26 | |
| masters | 124 | |
| frames | 556 | |
| voices | 86 | 只做 2 個角色參考音（台詞改由 H3 念，不再每句 8 候選） |
| h3 | 564 | 7 鏡 DMAD＋每鏡分離人聲、聽寫比對：6 句全部相似度 1.00 |
| amb | 65 | |
| music | 134 | |
| ending | 71 | |
| cut | 65 | |
| review | 17 | |

自審結果：響度 −15.7 LUFS、峰值 −1.9 dBFS；沒有黑畫面、定格、切點明暗跳動、台詞重疊或被鏡尾切掉；成片聽寫 6 句全部 1.00。抽幀：推眼鏡再放下手、抓頭、慢慢滑進椅子等動作都照 action 演出，臉與服裝穩定、沒有多出人。
