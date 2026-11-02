# 生歌、檢查、接法

## 先問：有沒有 Suno？

| 情況 | 用什麼 | 備註 |
|:--|:--|:--|
| 有 Suno 帳號 | **Suno**（網頁 Custom 模式，或 Kie.ai API） | 編曲最豐富、rap 最有攻擊性、會自帶刷碟聲。四場對決都用它 |
| 沒有 Suno | 先問使用者 → **YuE2 14 版**（`make_battle.py yue`，配方 `templates/song_yue2_v14/`） | ComfyUI 原生節點；比 Suno 平、攻擊性弱；權重 CC BY-NC |
| YuE2 也不行 | ACE-Step 1.5 XL（`tools/ace_song.py`） | 拍速最穩、MIT；人聲有金屬聲 |
| 本機沒顯卡 | Suno 最省事；沒有 Suno 就在 Colab 跑 YuE2 | Colab 完整安裝已預裝 YuE2：`colab_h3.py film <對決資料夾> yue` |

不要自己從 Suno 換成 YuE2：換之前一定問。

## Suno

1. `make_battle.py songtext` → `out/songtext/suno_A_lyrics.txt`、`suno_A_style.txt`（B 同理）。
2. **網頁**：Create → Custom，Lyrics 貼歌詞、Styles 貼風格，每人各生一首（一次 2 版）。**API**：`python kie_suno.py submit A` → `poll a1`（環境變數 `KIE_API_KEY`；每次 2 版約 12 點）。
3. 每人先抽 2 版，不滿意再改風格抽；挑好的放到 `song/A.mp3`、`song/B.mp3`。

### 風格寫法（英文，≤ 1000 字元）

依序寫：
1. 結構：`ONE CONTINUOUS RAP SONG by ONE rapper … EXACTLY 144 BPM`（有唱段就寫 `rap verse, then a short 4-line SUNG melodic hook, then back to rap`）。
2. 曲風＋招牌樂器（每場不同）：英國巴洛克 boom-bap＋大鍵琴、德國巴洛克 trap＋管風琴、G-funk＋里拉琴、爵士 boom-bap＋古琴洞簫、銅管進行曲 hard trap……
3. 前奏與收尾：A＝4 小節樂器前奏、`the beat STOPS DEAD on one huge hit (hard stop, no outro)`；B＝4 小節 DJ 刷碟前奏、`the LAST EIGHT LINES build gradually …（見第 6 點）… crowd roars 'OHHH' … rides out 4 bars with scratches`。
4. 聲音：`ONE SOLO MALE RAPPER only: a DEEP, RASPY baritone …` vs `a BRIGHT, SHARP young TENOR …`——**兩人一定要一低一高、個性不同**。
5. 咬字：`crystal-clear Mandarin rap with Taiwanese diction, every number clear`。
6. 殺招段：`The LAST EIGHT LINES build GRADUALLY at the same BPM, never faster: first two lines stripped back with no drums, a quiet restrained voice; then drums return; every two lines add one layer and the voice gets louder and higher; one beat of silence before the final line, which is the loudest moment of the song`（使用者 2026-11-01 要情緒慢慢堆）。**實測（〈瑜亮之戰〉16 版）：Suno 不太聽話**：長描述標籤幾乎沒用；短標籤 `[Breakdown: no drums, ...]`、`[Build-up: ...]`、`[Drop: shouted]` 約四分之一的版本會在殺句前真的空一拍，但人聲響度仍很平。做法：多抽，量伴奏有沒有收、殺句前有沒有空拍，挑有的版本給人聽；也可以用分軌做一版音量與濾波的後製當對照（這場使用者選 Suno 原版，沒選後製）。
7. negative：`slow ballad, mumble rap, autotune-heavy, female voice, choir, second rapper, duet, featuring, melisma, vocal runs, Indian scale`。

Suno 不吃藝人名字，要寫成特徵。範例見 `pipeline/template_battle/battle.json` 的 `suno_style`。

### 兩人聲音太像

- 兩人的聲音描述拉開（低沉沙啞 vs 明亮尖銳），兩首都生完用聲紋比對（CAM++，越低越像兩個人；0.7 左右可以接受）。
- 還是太像：Suno 的 persona（用某一版的聲音當角色）鎖住其中一人的聲音再生。

## YuE2（沒有 Suno 時）

一條指令（配方照 `templates/song_yue2_v14/README.md`）：
```
make_battle.py yue                           # songtext → 每人 YuE2 抽 YUE_SEEDS 首（預設 10）→ 只留目標 BPM、逐句聽寫排序 → 第一名放 song/
python cloud/colab_h3.py film pipeline/my_battle yue   # 沒有顯卡：同一件事在 Colab 跑，out/ 同步回來
```
- 目標 BPM 讀 `yue_style` 裡的「144 BPM」（或填 `rappers.<A|B>.yue_bpm`）；約一半會跑掉，全掉就多抽（`YUE_SEEDS=11,12,…,20`）。
- 第一名只是聽寫初篩，**人聽過 `out/yue/<A|B>/` 的候選再定**；換歌就把那首轉檔覆蓋 `song/A.mp3`，再跑 `songs`。
- YuE2 沒有器樂前奏、刷碟不一定有：A 停在拍上→B 的接法照樣能用，但前奏很短時 DJ 口白會把音樂往後推（範本自動處理）。

## 檢查（`make_battle.py songs` 自動做）

- BS-RoFormer 分人聲 → 歌詞強制對齊 → **逐句**聽寫、BPM、最後一個字唱完的時間。
- **不要整首直接聽寫**：rap 會讓聽寫幻覺出「中文字幕志願者」之類的字，連好的歌都量成 0。
- rap 的逐句聽寫天生偏低：人工確認全對的 Suno 歌也只有 0.63–0.80。看低分句（< 0.5）是唱錯還是只是聽寫不準，**最後一定要人聽**。
- 對齊出來的段數跟歌詞句數不同＝歌詞跟送去生歌的不一樣，先修。
- 最後一個字的時間不對（Suno 自己在後面加喊聲）→ `rappers.<A|B>.last_word_end` 填秒數。
- **冷僻專有名詞（堯舜這類）Suno 每版都唱歪**（2026-11-01〈人性之辯〉：10 版全唱成「老鑽／藥犯／老殘」）→ 寫歌詞時就先查聽寫，或改常用字同音（字幕再換回）。歌已定稿才發現：**Kie `replace-section` 局部重唱**（最短 10 秒、每次 2 版，同音字當歌詞，例「姚 順」）→ 分人聲、逐句聽寫挑最清楚的 → **只把那幾個字的人聲剪回定稿**（定稿混音＋〔新人聲－舊人聲〕，兩端 25 ms 交叉淡化、對齊候選與定稿的時間差），伴奏和其他句不動、時間軸不變，只重拍唱那句的對嘴鏡。重唱窗外的部分 Suno 會整段重生（窗後完全不同），不能整首換。

- **整首對齊可能把幾句壓成 0.1 秒**（前奏長、某段含糊時；〈瑜亮之戰〉孔明 1–4、21–24 句）：看 `align_*.json` 每句長度，太短的只取那段人聲重新對齊，同時更新 `words`，字幕韻腳才對得上。
- **Suno 常自己把副歌多唱一遍**（2026-11-02〈瑜亮之戰〉周瑜：歌詞只寫一遍，實際唱兩遍；v1 把第二遍當器樂段，放觀眾鏡、沒字幕，使用者一看就抓到）→ `songs` 階段會印「⚠ 人聲還在唱，但歌詞沒對到」；照實把那幾句補進歌詞（後面句子的編號要跟著移）和字幕，並拍唱的人本人。**說「器樂段」前先看人聲分軌，不要憑對齊結果判斷**。
- **Suno 也會在開口前自加「喔耶」長音**：對齊把它算進第一句，字幕會早出現。要嘛剪掉（人聲分軌歸零），要嘛對齊列加 `show_start`（字幕從真正開口的字開始）。
- **Suno 會多唱字，對齊不會告訴你**（2026-11-02〈瑜亮之戰〉孔明「那把火**車**」「站在船上**想**看戲」，使用者抓到）：對齊只對我給的字，多唱的字會被吃進那句。`align_*.json` 的 `ok` 低於 0.3 的句子一定要查，不能當成氣音段聽寫不準；**逐句切窗（前後多 0.3 秒）聽寫混音、比字數**，整首連續聽寫在前奏和分軌上會幻聽。局部重唱也一樣會多唱：候選除了字對，**句與句的空檔也要單獨切窗聽寫、看頻譜**（〈瑜亮之戰〉有一版字全對，但空檔多唱「欸欸、哇哇哇」）。候選唱得比原版快時，**不要把人聲搬開留空**（〈瑜亮之戰〉v3、v4 使用者：聲音不見了、異常）：人聲連音樂整段用候選的，它提早幾小節進下一句，就接回原版同一句、全曲少那幾小節，重拍受影響的對嘴鏡。
- **人聲分軌裡可能混著音樂，伴奏分軌也可能有破洞**（2026-11-02〈瑜亮之戰〉使用者抓到兩處）：①氣音段、沒鼓段的音樂底常被分到人聲軌，清人聲會一起清掉，停頓變成無聲（1:16「聲音不見了」）；所以不要只清人聲，要換就人聲連音樂整段換；自己鋪的低音底手機喇叭放不出來（〈瑜亮之戰〉v4 量起來有 −27 dB，使用者還是聽不到）。②Suno 在前奏自加喊話時，分人聲會連音樂挖掉，而前奏用的是伴奏分軌，留下破洞（1:56、0:08）；用前一小節同拍位補。**每版都掃全片音量，要先濾掉 300 Hz 以下（手機喇叭放不出來）再量，單聲道：50 毫秒低於 −42 dB 持續 0.1 秒以上、或相鄰半秒掉 8 dB 以上的地方，逐一確認。不要為了特效壓音樂（使用者：音樂突然變小聲）。**
- 局部重唱**要在最終混音上聽寫**：分軌上聽寫對，混音裡可能還是錯（〈瑜亮之戰〉「傳」分軌是「賺」、混音是「穿」，換同音字「篆」再抽才過）。單字剪不乾淨就換整句，換到有對嘴的句子要重拍那一鏡。
- **副歌不好聽，只換副歌**：`replace-section` 窗對齊小節線、每次 2 版，只把窗內接回定稿（前後 30 ms 交叉淡化）。Suno 可能把原本唱兩遍的副歌改成慢慢唱一遍；若把下一段也唱進窗內就淘汰。

## 兩首怎麼接（`make_battle.py audio` 自動做）

1. A 整首：前奏改用伴奏分軌（拿掉 Suno 前奏裡含糊的喊話，免得跟 DJ 開場口白打架）。
2. A 最後一個字唱完後的**第一拍重拍收**：留 0.25 秒原音＋0.6 秒短衰減，**不淡出**。
3. **正好 1 小節後** B 那首的第一拍進來（B 自帶 DJ 刷碟前奏，換場口白壓在上面）。
4. B 最後一個字後換伴奏分軌（Suno 常自己再唱），走到「最後一句的小節線＋8 小節」，最後 2 小節淡出。
5. DJ：開場口白在 1 秒開始（塞不下就整段音樂往後延）、換場口白在 B 開口前 1.2 秒講完、定論口白在 B 唱完 3.2 秒後、片尾口白在音樂結束後；口白期間音樂壓 −5 dB。
6. 兩人饒舌段調成一樣大聲；兩首 BPM 不同時 A→B 會接不準，盡量同 BPM（前四場三場 144、一場 94）。

Suno 的 extend 生的「自然尾奏」接起來不好，不要用；需要收尾就寫進 B 歌詞的 `[Outro]`。
