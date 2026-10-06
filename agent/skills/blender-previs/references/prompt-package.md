# 提示詞與素材包（交付包）

> **2026-09-28 起：實際送 H3 的提示詞一律用 `C:\AI\tools\make_shot.cmd`（`h3_shot.py`）產生**，不要手抄下面的範本。把本技能產出的首幀、Blender 鏡位影片（`camera_video`）、聲音（`audio.voice_ref` 或 `audio.fixed`）、每鏡動作與台詞寫進分鏡 JSON，工具會組成官方六段格式（段名**要有冒號**、`<Subject N> (S1)`、`<d>[Chinese]…</d>`、畫外音 `says in an off-screen voiceover … lips remain completely closed`、環境音不寫台詞、無配樂寫 `N/A`）並做格式檢查。下面 v5 範本保留作為**內容**參考（每個參考素材要寫清楚用途），格式以工具為準。說明見 `C:\AI\tools\README.md` §2b。

## 一個已修好的關鍵缺陷

早期版本的 `build_prompt()` 把參考影片接進去，卻**沒有定義 `<Video 1>` 的用途**，模型不知道那只是鏡位參考。修正後必須在 `subject_definitions` 明確說明每個參考的角色。**這是已記錄的實際缺失，新片不要再犯。**

## 提示詞結構（v5 已驗證）

```
subject_definitions
<Picture 1> is the exact photographic first frame, supplying real human identities, skin,
clothing, room materials, lighting and camera composition.
<Video 1> is ONLY a Blender camera and spatial-layout guide. Its low-poly figures and colors
are proxies, NOT characters or visual style. Ignore proxy material, shape and rigid-body
stillness; keep the camera path and spatial relationships.
<Audio 1> is the exact final vocal track, including all pauses and silence, to be copied
unchanged.

summary
[keyframe completion + reference generation + audio reuse] One continuous real live-action
Taiwanese dramatic film shot, not animation.

retention_analysis
<Picture 1>: fully_preserved - identities, real clothing, layout, lighting.
<Video 1>: partially_preserved - camera trajectory and room geometry only, discard mannequin
appearance and stiffness.
<Audio 1>: fully_copy - precise waveform, timing and pauses.

detailed_description
Real camera cinematography, natural skin detail and cloth. [Shot 1] Begin exactly from
<Picture 1>. <本鏡動作> <本鏡台詞或靜默>. The real human lips, jaw, cheeks, breathing,
eye-lines and subtle expressions belong to one coherent performance, not a photograph with
only a moving mouth. Maintain the original seats throughout.
One shot only; no cuts, portraits, inserts or new people. Follow the guide camera while
retaining the photographic first-frame composition. No text or graphics.

overall_soundscape
Reuse <Audio 1> exactly with its silence; no additional speech.

non_diegetic_music
None.
```

## 台詞寫法

| 情況 | 寫法 |
|:---|:---|
| 有說話者 | `The <角色> (S1) says exactly: <d>[Chinese] <台詞></d>` |
| 說話者在畫面外 | `The <角色> is OFFSCREEN (S1) and asks: <d>[Chinese] <台詞></d>` |
| 無人或靜默 | `No physical speaker. The guide audio is silence. Keep visible mouths quiet.` |

## 靜止鏡的相機契約（必加）

```
CAMERA CONTRACT: Completely locked tripod at the first-frame position, same lens, same
framing for the entire shot. No pan, track, orbit, push, zoom or change of viewpoint.
Keep the same visible people and background from beginning to end. Any other person remains
physically offscreen; nobody enters. Natural facial performance, not a frozen frame.
```

**只有真的做過 keyframe 運鏡的鏡頭才能不寫這句。** 標 locked 卻寫推進是已記錄的自相矛盾。

## 逐鏡加註（依實際問題）

| 鏡頭類型 | 加註 |
|:---|:---|
| 多人同框 | `Both men must stay visible simultaneously, friend LEFT and teacher RIGHT, throughout the complete shot.` |
| 只該出現一人 | `Only the <角色> is visible. The other remains outside the frame to the right. Exactly one visible person.` |
| 道具不可舉起 | `hand quietly tucks paper below the crop, without raising or displaying it.` |
| 實體道具帽 | `is a real sewn costume prop with rigid resin button eyes and sewn muzzle: these have no eyelids, no blinking or animal expressions. Only the real human face beneath it performs.` |

## 對嘴相關（本專案的實際界線）

- **配音先定稿**，畫面與引導用同一份音訊；**不要用後換聲音掩蓋不同步**。
- 凍結實際 audio latent（v5 腳本 version ≥ 4）比只靠引導更穩。
- **長靜默**（說話→停頓→再說話）要另外處理：依音訊 RMS 找出靜默段，在該段中央加入**完整參考畫面的閉口引導**，並在提示詞寫明時段。D1 長停頓、D2 片首開口經此改善（抽查，非逐音素認證）。
- 過多首尾／中間錨點會讓表演僵硬：**只在需要的區間設錨點**。
- **未量測音素同步就照實寫「未做逐音素認證」**，不可寫成完美對嘴。

## 素材包內容

```
<片名>/交付包/
├── 提示詞_<鏡號>.txt            每鏡完整提示詞
├── 素材/
│   ├── refs/<鏡號>/image.png    該鏡第一幀參考
│   ├── guide/<鏡號>.mp4         Blender 運鏡或靜止 guide（512×288）
│   ├── guide/<鏡號>.png         布置圖靜幀
│   └── audio/<鏡號>/dialogue.wav 該鏡配音
├── 逐鏡參數.json                 frames / lens / motion / seed / 版本
└── 限制與未驗證.md
```

## 其他目標模型

本專案預設 H3。若交外部模型（例 Seedance），**另存一份該模型的提示詞**，不要直接沿用 H3 的 `<Picture 1>` 標籤語法；共用的是**素材與鏡位契約**，不是提示詞字串。
