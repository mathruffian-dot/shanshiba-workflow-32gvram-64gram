# template_battle：饒舌對決範本（兩首歌 → 3–4 分鐘橫式對決影片）

兩位真實人物各唱一整首歌互嗆、DJ 主持、最後留言投票。`battle.json` 寫完整場（人物、歌詞、DJ 口白、擂台、閃回地點、字卡、每一鏡），`make_battle.py` 從兩首歌一路做到成片、手機版和自審。

**先讀編劇技能 `agent/skills/rap-battle/`**：選題、歌詞規則、生歌（Suno 為主、沒有 Suno 用 YuE2）、鏡表寫法、自審表都在那裡。

範例 `battle.json`＝原頻道〈微積分之戰〉牛頓 vs 萊布尼茲（2026-10-28，49 鏡、約 3 分 9 秒）。範本不附歌曲檔（Suno 生成），要跑範例請先用 `songtext` 的文字自己生兩首。

## 用法

1. 把整個 `template_battle/` 複製一份到 `pipeline/` 底下改名（例如 `pipeline/my_battle/`）。放在別的地方的話，把 `battle.json` 的 `repo_dir` 改成本 repo 根目錄（可以寫絕對路徑）。
2. 照技能寫好設計與歌詞，填進 `battle.json`（欄位見下）。
3. 生歌：
   ```
   <Voice venv>\python make_battle.py songtext
   ```
   - **有 Suno**：把 `out/songtext/suno_A_lyrics.txt`、`suno_A_style.txt` 貼到 Suno 網頁的 Custom 模式（B 同理），或用 `python kie_suno.py submit A`（環境變數 `KIE_API_KEY`）。
   - **沒有 Suno**：`make_battle.py yue`：YuE2 14 版（配方 `templates/song_yue2_v14/README.md`）每人抽 10 首 → 只留目標 BPM、逐句聽寫排序 → 第一名放到 `song/`。**一定要人聽 `out/yue/<A|B>/` 的候選**，換歌就轉檔覆蓋 `song/A.mp3`。
   - 挑好的歌放成 `song/A.mp3`、`song/B.mp3`（或改 `rappers.<A|B>.song`）。
4. 在同一個 cmd 視窗：
   ```
   set PYTHONUTF8=1
   call <repo>\configs\profile.cmd
   C:\AI\tools\start_comfy.cmd
   cd <repo>\pipeline\my_battle
   C:\AI\Voice\venv\Scripts\python.exe make_battle.py songs dj audio
   ```
   看 `out/song/songs_report.json`：逐句聽寫低分的句子去聽；`last_word_end`（最後一個字唱完）不對就在 `battle.json` 填秒數重跑。聽 `out/audio/mix.wav` 確認 A→B 的接點和 DJ 口白。
5. `make_battle.py chars scenes frames` → **人工關卡 1**：`out/chars/`（三人分得出來）、`out/scenes/arena.png`（配色、沒有字和旗子）、`out/first/_sheet.jpg`（每鏡首幀）。重畫：刪那張 png，那鏡加 `frame_seed_bump` 或改 `frame`，再跑 `frames`。
6. `make_battle.py specs h3` → **人工關卡 2**：`out/review/clips_*.jpg`（每鏡 4 格：換臉、多出人、旗子、自己切鏡、手糊）。重拍：那鏡加 `seed_bump`（會切鏡的再加 `last_first: true`），再跑 `specs h3`。
7. `make_battle.py cut review srt` → **人工關卡 3**：照技能的 `references/review-checklist.md` 看 `out/review/fc_v1/sheet_*.jpg`，**最後一定要人看完整成片** `out/cut/<片名>_v1_1920x1080.mp4`。改版：`--ver 2`。

### 沒有顯卡：整場在 Colab 跑

照 `cloud/README.md` 開好 Colab（`python cloud/colab_h3.py start`＝完整安裝，已含 YuE2 與 Ming-3.0-TTS），把對決資料夾放在 repo 的 `pipeline/` 底下，分段跑、每段的 `out/` 會同步回你的電腦，人工關卡在本機看：
```
python cloud/colab_h3.py film pipeline/my_battle yue                 # 沒有 Suno：雲端 YuE2 生歌（有 Suno 就自己放 song/A.mp3、B.mp3，跳過這步）
python cloud/colab_h3.py film pipeline/my_battle songs dj audio      # 聽 out/yue 的候選、out/audio/mix.wav
python cloud/colab_h3.py film pipeline/my_battle chars scenes frames # 看 out/first/_sheet.jpg
python cloud/colab_h3.py film pipeline/my_battle specs h3            # 看 out/review/clips_*.jpg
python cloud/colab_h3.py film pipeline/my_battle cut review srt      # 看完整成片
python cloud/colab_h3.py stop
```
資料夾裡有 `battle.json`，`film` 就會改跑 `make_battle.py`。Colab 上放大用 lanczos（RTX VSR 只有 Windows）。`h3` 這段在 VM 上開 2 個 ComfyUI、第二個晚 30 秒開跑（`cloud/vm/parallel_h3.py`，跟 template_local 同一套；2026-10-29 補上，之前對決範本在雲端只用 1 個，這條還沒在 Colab 重跑過）。
- `film` 只同步 `out/` 回來：`yue` 選的歌放在 VM 的 `song/`，本機聽 `out/yue/<A|B>/`（排序在 `pick.json`）。要換歌就把那首轉成 `song/A.mp3` 放在本機資料夾，下一次 `film` 會一起上傳。
- `out/` 只上傳 VM 上沒有的檔；要重做某一鏡，照樣在 `battle.json` 加 `seed_bump`／`frame_seed_bump`（刪本機的檔不會刪到 VM 上的）。
- 跑完一定要 `stop`：閒置的 G4 每小時照扣 8.9 單元。

不給 stage 就從 `songs` 依序跑到 `srt`。已存在的輸出會跳過，中斷後重跑會接著做。還沒跑 H3 的鏡，`cut` 會用首幀靜態圖代替（沒有首幀就用灰底鏡號），可以先看節奏。

| 環境變數 | 用途 |
|---|---|
| `AI_ROOT`、`AI_TOOLS` | 安裝根目錄（預設 `C:\AI`）、工具目錄（預設 `C:\AI\tools`） |
| `COMFY_DIR` | ComfyUI 資料夾（`gen_image.py` 從它的 `output/` 拿圖） |
| `H3_BACKEND` | `local`｜`colab`｜`both`（同 template_local；不設就看顯卡自動選） |
| `UPSCALE` | `rtxvsr`（Windows 預設）｜`lanczos`（Linux／Colab） |
| `ONLY` | 只做這幾鏡（`frames`、`h3`），例如 `set ONLY=N04 L06` |
| `ALLOW_REVIEW=1` | DJ 口白候選聽寫都不準、但人聽過沒問題時繼續 |
| `DJ_TTS` | `ming`（預設，Ming-3.0-TTS，MIT 可商用）｜`breezyvoice`（舊做法） |
| `YUE_SEEDS` | `yue` 每人抽哪些 seed（預設 `1,2,…,10`） |
| `FONT_JHBD`、`FONT_KAI` | 字幕／字卡字型（預設微軟正黑體／標楷體，Linux 用 Noto CJK） |

## battle.json 欄位

| 欄位 | 說明 |
|---|---|
| `title` | 片名（片名卡、成片檔名） |
| `image_backend` | `qwen`（預設，本機 Qwen-Image 2.1／Qwen-Image-Edit 2511，最多 3 張參考圖）或 `img25`（OpenAI Image 2.5，`tools/img25.py`，要金鑰，最多 5 張） |
| `seed0` | H3 seed 的起點（每鏡再依鏡號加） |
| `rappers.A/B` | `name`、`short`、`team`（例：金方）、`tagline`（VS 卡小字）、`color`／`glow`（字幕、特效、字卡的己方顏色 RGB）、`look`（外觀完整描述，每張首幀照抄）、`person`（man／woman）、`pronoun`、`desc`（H3 用的短描述）、`song`、`suno_style`、`suno_negative`、`yue_style`、`lyrics`（見技能 `references/lyrics.md`）、`intro_card`（直排名牌 `[[文字, 字級], …]`）、`last_word_end`（選填）、`yue_bpm`（選填，`yue` 挑歌的目標 BPM；沒填讀 `yue_style` 的「NNN BPM」） |
| `dj` | `name`、`short`（字幕名）、`color`、`look`、`desc`、`person`、`pronoun`、`voice_design`（Breeze 設計參考音的描述；要營利就自己錄 `out/voice/ref_K.wav`）、`voice_sample`（參考音念的句子＝逐字稿）、`lines`（`open`／`switch`／`verdict`（選填）／`end`）、`end_beats`（片尾三拍大字）、`tts`（選填，念錯的句子改寫法：Ming 用同音字）、`intro_card` |
| `arena` | `master`（擂台空景提示詞，左右兩半＝兩人的配色）、`keep`（首幀用的擂台鎖定句，`{ref}`＝參考圖編號）、`light`、`setting`／`style`／`keep_h3`（H3 用） |
| `places.<地點>` | 閃回／插入鏡的地點：`light`（首幀光線）、`setting`（H3）、`era`（`period`／`modern`）、`text`（畫面裡有要保持不變的字） |
| `style_modern`、`style_period`、`film_look`、`no_text` | 插入鏡的 H3 風格句、首幀電影感句、不要字的句子 |
| `audience`、`audience_desc` | 觀眾外觀（首幀）、H3 短描述 |
| `cards.<代號>` | 講白字卡：`lines`（`[[文字, 顏色]]`，顏色 `A`／`B`／`J`／`ink`）、`accent`、`size`；或 `image`（自己畫好的 PNG，例如精準的數學圖） |
| `vote` | 投票卡：`A`、`B`（挺誰打什麼字）、`title`、`sub`、`note` |
| `show_replace` | 歌詞→字幕的替換表（國字數字→阿拉伯數字、同音字→原字） |
| `flash_scenes` | 切進這些地點時閃白（其他插入鏡直接切） |
| `locked` | 鏡頭鎖死不推近的鏡號 |
| `crowd_sfx` | 觀眾歡呼音效資料夾（預設 `sfx/歡呼`） |
| `tail_ring` | 預設 `true`：殺句後留殘響、補伴奏破洞、B 前奏淡入，不會突然切斷 |
| `verdict_bed` | 預設 `true`：DJ 收尾口白很長時，用 A 的前奏伴奏壓低墊底 |
| `lang` | `zh`（預設）｜`en`：英文對決的對齊、聽寫、H3 台詞語言 |
| `bpm` | 抓拍子的先驗（慢歌要給，不然會抓成兩倍速） |
| `film_look_insert`、`arena_only` | 插入鏡專用的電影感句；`no_text` 裡只屬於擂台的句子（插入鏡會拿掉，空景才不會畫出饒舌手或舞台地板） |
| `rappers.B.end_on_hold`、`rappers.B.keep_stop` | 最後一句後面有長音、自己收掉：唱到底就結束，不換伴奏分軌；最後一個音跟音樂一起停：人聲慢一點收，那個空檔不補 |
| `rappers.<A\|B>.align_from` | 前奏有 Suno 自己加的喊話時，對齊前把這秒數之前靜音 |
| `shots[]` | 每一鏡，見下表 |

每一鏡（`shots[]`）：

| 欄位 | 說明 |
|---|---|
| `id` | 鏡號 |
| `at` | 開始時間：秒數｜`["A", i]`（A 第 i 句開口前 0.12 秒）｜`["dj", "switch", -0.3]`｜`["mark", "a_stop", 0.3]`（`a_first`、`a_stop`、`a_end`、`b_zero`、`b_first`、`b_last`、`music_end`）。結束＝下一鏡的開始。**範例的秒數是照 Suno 原曲的前奏長度寫的**：換歌（例如改用 YuE2，前奏長短不同）後 `frames` 會先檢查，列出順序反掉或太短的鏡，照提示改 `at` |
| `kind` | `sing`（對嘴；`voice: "dj"`＝對 DJ 口白）或 `silent` |
| `scene` | `arena` 或 `places` 的地點 |
| `subj` | 畫面裡的人：`A`、`B`、`K`（DJ）、`T`（觀眾）。**只放畫面裡要演戲的人**；雙人鏡第一位是唱的人 |
| `dist` | `ECU`／`CU`／`MCU`／`MS`／`WIDE` |
| `frame` | 首幀描述（英文，畫動作開始前的姿勢） |
| `action` | H3 動作（`Starting from <Picture 1>, …`，慢而清楚的手勢） |
| `gfx`、`card` | 這鏡要疊的字卡代號、直排名牌（`A`／`B`／`K`） |
| `still`、`custom` | 首幀靜態慢推、自己做的影片檔 |
| `last_first`、`calm`、`draft`、`cons`、`seed_bump`、`frame_seed_bump` | 尾幀＝首幀（防切鏡）、慢動作、`false`＝14 步、額外限制句、換 H3 seed、換首幀 seed |

## 自審與修歌工具

都在本資料夾執行（Voice venv）。怎麼用、什麼時候用，見技能 `references/review-checklist.md` 第 H 節。

| 工具 | 用途 |
|---|---|
| `lyric_audit.py [A B]` | 全曲逐句聽寫，用拼音比。對齊分數高不代表字唱對 |
| `gap_check.py <A\|B>` | 列人聲無聲段並比對原唱：原唱有聲、成品沒聲的一定要修 |
| `level_scan.py` | 全片音量掃描，抓突然變小聲或破洞 |
| `motion_check.py` | 每鏡動作量。尾幀＝首幀常把人鎖死 |
| `finger_sheet.py [--clips] [鏡號]` | 手部放大表。`--clips` 看 H3 成片：首幀 5 根，拍動作時可能多長一根 |
| `voice_diff.py 檔案…` | 候選人聲跟前面各場比聲紋、音高（`BATTLE_FILMS`＝放各場對決的資料夾） |
| `suno_replace.py submit …` | Suno 局部重唱，只換唱歪的那幾個字（`SUNO_SRC=標籤:第幾版`、`SUNO_PROMPT`、`SUNO_PART`） |
| `run_shared.py stage…` | 跟別的工作共用 GPU 時跑 `make_battle.py`，不卸載別人的模型 |
| `colab_only.py [鏡號…]` | 本機 H3 被別的工作佔著時只用 Colab 拍：多帳號（`COLAB_HOMES`）共用佇列、失敗重試一輪、做完關機；看到同名 VM 已開著就不碰（確定是自己的才設 `COLAB_REUSE=1`） |
| `dj_align.py` | DJ 口白逐字對齊，鏡頭切點與 DJ 字幕都用它；換口白檔要重跑 |
| `resing_lines.py <A|B> <窗開始> <窗結束> <候選…>` | 局部重唱候選逐句聽寫比對（人聲、混音各一次），量窗外時間差與多唱 |

換了歌要先跑 `audio` 再跑 `specs`、`cut`；漏跑的話 `make_battle.py` 會停下來提醒。

## 輸出（`out/`）

`songtext/` 生歌用文字、`song/` 分軌＋對齊＋報告、`voice/` DJ 參考音與口白、`audio/` 全片音軌（`mix.wav`、`vocals.wav`、`dj.wav`、`timeline.json`）、`chars/`、`scenes/`、`first/`（首幀＋提示詞＋接觸表）、`h3/<鏡>/`（spec、clip）、`post/`（放大、片段、字卡、特效事件）、`cut/`（成片、手機版、字幕檔）、`review/`、`timing.json`。

## 驗證紀錄

2026-10-28～29，RTX 5090 32GB，用原頻道〈微積分之戰〉的兩首 Suno 歌（牛頓 vs 萊布尼茲）＋本資料夾的 `battle.json`，從 `songs` 一路跑到 `srt`，首幀用本機 Qwen-Image-Edit 2511（`IMG=qwen`）。

**做出來的東西**：186.3 秒 1920×1080 成片＋27.2 MB 手機版＋srt，49 鏡（43 鏡 H3、其餘字卡／靜態），−16.0 LUFS、AAC 後真峰值 −2.1 dBTP。

| 階段 | 時間 | 備註 |
|---|---|---|
| songs | 27 秒 | 分軌、對齊、逐句聽寫；最後一字的時間跟原片手工挑的差 0.05／0.26 秒 |
| dj | 數分鐘 | 當時 BreezyVoice 每句 8 個候選；2026-10-29 改 Ming 後 191 秒，見下方「DJ 關卡」 |
| audio | 數秒 | A 停在 77.717 秒、B 從 79.179 秒、音樂到 174.784 秒，**跟原片手工剪的完全一致** |
| chars＋scenes | 約 2 分 | |
| frames（43 張） | 每張中位數 48 秒 → 約 35 分 | 實測 3.7 小時是因為同時有別的程式（Breeze TTS）佔顯存，最慢一張 1 小時 53 分。**跑 frames／h3 時不要同時跑別的 GPU 工作** |
| h3（43 鏡，DMAD 4 步） | 49 分（平均約 69 秒／鏡） | |
| cut | 約 11 分 | RTX VSR 放大＋特效逐格疊字（佔大部分時間） |
| review | 44 秒 | |

**實測發現、已修進程式的：**

- 最後一字時間：Suno 會在最後一句後面加觀眾喊聲，用「人聲還有聲音」判斷會多算 14 秒 → 改成對齊的最後一字＋最多延長 0.3 秒。
- 首幀用 Qwen 時，擂台參考圖要放**第一張**，不然雙人鏡會畫在灰色攝影棚。
- 響度：加了觀眾聲以後要再量一次 → 量 → 固定增益 → 限幅迴圈到 −16 LUFS。觀眾音效裡的拍手尖峰可達平均值的 13 倍，限幅器擋得住取樣峰值，但壓成 AAC 後真峰值衝到 +4.2 dBTP → 觀眾音效先軟壓到平均值的 4 倍，修後 −2.1 dBTP。
- 首幀「臉比角色多」自動警告（Qwen 會在單人鏡多畫一個人；這次抓到 N05、L08，另外 F01、F03 是劇情本來就有旁人）。

**本機 Qwen 首幀的已知限制（人工關卡 1 要看）：**

- 雙人對峙鏡（D01–D03）兩人都面向鏡頭並肩站，畫不出側臉互瞪；要對峙感就在 `battle.json` 設 `"image_backend": "img25"`，或改成兩個單人鏡對切。
- 偶爾把首幀畫成左右兩格拼圖（L06），H3 會照著演成分割畫面 → 刪掉重畫。
- 場景裡的字（書名、議會橫幅）是亂碼 → 首幀描述別要求寫字，要字就後製字卡。
- 道具會在第一格出現、之後消失（N02 的三角帽）→ 首幀別放這鏡用不到的配件。

**H3 自審**：`review` 的「構圖漂走」清單 21 鏡，大多是唱歌鏡的手勢與走位誤報；真的有問題的是 T03（觀眾鏡中途溶接到另一個舞台約 1 秒）和 L09（側面轉成正面），兩個都在清單裡。硬切（相鄰格差 > 門檻）這次 0 鏡。

**DJ 關卡**：DJ 口白當時用 BreezyVoice 念，「微積分」被聽寫成「我積分／為積分／危機分」，8 個候選都沒過，`dj` 階段照設計停下來，用 `ALLOW_REVIEW=1` 繼續。**2026-10-29 起 DJ 改用 Ming-3.0-TTS**（原專案試聽「聲音非常的好，也沒有大陸腔」，MIT 可商用）：同樣 4 句、同一個參考音，每句 4 個候選，**4 句第一輪全部聽寫正確（含「微積分」）**，本機 191 秒。你自己的片遇到不合格的句子，先聽那一句；真的念錯就在 `dj.tts` 換同音字或換說法。

### 2026-10-29 Colab 全雲端驗證（基本版：YuE2＋Qwen＋Ming，全部在 Colab 跑）

G4（RTX PRO 6000 96GB，荷蘭機房），用本資料夾的 `battle.json`（同一份歌詞），**沒有 Suno**：`yue` 在雲端生兩首歌，之後一路跑到 `srt`。為了省運算單元，首幀和 H3 只做 4 鏡（`ONLY=W01 N01 L02 D01`），其餘 45 鏡用首幀靜態圖／鏡號代替。

| 階段 | 時間 | 備註 |
|---|---|---|
| `start`（完整安裝） | 564 秒 | 新加的 YuE2（4 GB）、Ming（3 GB）下載各 13、8 秒，Ming 節點裝在同一份 ComfyUI |
| yue（每人 10 首） | 524 秒 | 拍速對的：A 1／10 首、B 7／10 首；逐句聽寫 0.50／0.53（Suno 原曲約 0.63–0.80），有幾句含糊 → 要多抽、人聽 |
| songs | 57 秒 | 兩首都對齊成功 |
| dj（Ming） | 114 秒 | 4 句第一輪全部聽寫正確 |
| chars＋scenes | 132 秒 | |
| frames（4 鏡） | 317 秒 | 含載入 Qwen；之後每張約 48 秒 |
| h3（4 鏡） | 429 秒 | 第一鏡含載入模型 296 秒，之後每鏡 42–46 秒 |
| cut | 132 秒 | lanczos 放大（45 鏡是靜態圖，整場全 H3 約 10 分） |
| review | 32 秒 | |

成片 179.9 秒、−16.0 LUFS、手機版 26.6 MB。這次連修 bug 重跑共用了 13.8 個運算單元；**整場 49 鏡估計約 1.5–2 小時、15–18 單元**（首幀約 35 分、H3 約 32 分）。

實測發現、已修進程式的：
- `colab_h3.py film` 遇到有 `battle.json` 的資料夾改跑 `make_battle.py`，而且用 Voice 環境（系統 Python 沒有 opencc、stable-ts）。
- `film` 改成增量上傳：`out/` 只傳 VM 上沒有或大小不同的檔（`yue` 同步回來後整包 380 MB，上傳被斷線），`out/` 以外的設定、程式每次都傳。
- Voice 環境補 `opencv-python-headless`（字卡避臉要用；原本本機是剛好被別的套件帶進來）。
- 字卡避臉的臉偵測：沒有 YuNet 模型就自動下載（約 230 KB，OpenCV 官方 opencv_zoo）；OpenCV 5 已經沒有 Haar，原本的備案會直接當掉。
- 換歌之後鏡頭時間會跑掉（YuE2 的前奏比 Suno 短）：`frames` 會先列出順序反掉的鏡，照提示改 `at`。
