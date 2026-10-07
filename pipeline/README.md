# pipeline：每支片的製作腳本

`example_D-7/` 是〈D-7〉（段考三種學生，2026-10-05，120 秒）實際用過的全套腳本，只把寫死的個人路徑改成 `C:\AI\tools` 慣例。

## 開新片

1. 複製整個資料夾，改名 `<片名>_<日期>/`，放在專案的 `短片/` 底下。腳本用 `HERE.parents[1]`（專案根目錄）找 `角色資產/`、`音效庫/`、`templates/seals/`，所以把本 repo 的 `templates/` 也複製到專案根目錄，`sfx/` 複製到專案根目錄並改名 `音效庫/`。
2. 改這幾張表，其他通常不用動：

| 檔案 | 改什麼 |
|---|---|
| `劇本.md` | 你的劇本與鏡表 |
| `blender/make_plan.py` | 機位與站位（不做預演可略） |
| `gen_frames.py` | `REF`（角色定妝照路徑）、`KEEP`（角色外觀鎖定句）、`SHOTS`（每鏡首幀描述） |
| `voice_plan.py` | `REFS`（各角色參考音）、`LINES`（台詞）、`TTS`（同音字替換；**新片改用 BreezyVoice＋注音標記，見 docs/02 第 4–5 步**） |
| `plan_h3.py` | `SUBJ`（角色英文描述與聲音）、`S(...)` 每鏡動作／台詞秒數／長度 |
| `assemble.py` | `SEGS`（剪接順序與段落類型）、`VO`（旁白位置）、`build_audio` 的音效時間點 |
| `music_scenes.py` | `SC`（每段配樂的風格描述與起訖段落） |
| `ending/config.json` | 片尾特寫圖與工具名單 |

3. 新片建議在 `pipeline_gen.py` 的 `make_spec` 把 `steps=14` 改成加上 `draft=True`（DMAD 4 步；〈D-7〉時還沒定案）。

## 執行順序

```
H3 venv:    python gen_frames.py                 # 首幀 → 人工審 → 建空檔 frames_ok
bash:       ./run_queue.sh                        # 等 GPU 空 → 配音 → Breeze → 挑音 → H3
H3 venv:    python assemble.py --ver 1 --vsr      # 先跑一次產生 post/starts.json
H3 venv:    python music_scenes.py                # 依片長生配樂
H3 venv:    python ../../templates/ending/render_ending.py ending/config.json
H3 venv:    python assemble.py --ver 1 --vsr      # 有配樂、有片尾的完整版
H3 venv:    python review.py cut/<片名>_v1_1080p.mp4
Voice venv: python review.py cut/<片名>_v1_1080p.mp4 --asr
```

重拍單鏡：`python pipeline_gen.py --retake S07`，再 `python assemble.py --ver 2 --vsr S07`。

## 檔案一覽

| 檔案 | 用途 |
|---|---|
| `gen_frames.py` | Image 2.5 首幀（3 路並行，舊圖自動移到 `first/old/`） |
| `sheet_frames.py`、`clip_sheet.py` | 首幀總覽圖、H3 片段抽格表（給人審） |
| `voice_plan.py`、`voice_stage1.py`、`voice_pick.py` | 配音候選與自動挑音 |
| `voice_more.py`、`voice_robust.py` | 單句補候選、疊環境音測可懂度 |
| `plan_h3.py`、`pipeline_gen.py` | H3 逐鏡設定與批次生成＋品檢＋換 seed |
| `run_queue.sh` | GPU 排隊與串接 |
| `post_fx.py` | 字卡、咒印名片、手機畫面、調色 |
| `music_scenes.py` | MiniMax Music 3 分段配樂 |
| `assemble.py` | 剪接、混音、字幕、輸出 1080p＋手機版 |
| `review.py` | 自審五遍 |
| `youtube/make_youtube.py` | 封面與 srt 字幕 |
| `製作紀錄.md` | 這支片實際遇到的問題與修法 |
