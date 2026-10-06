# 專案共用音效庫（2026-10-03 建立）

> 起因：系列影片用程式合成的腳步聲、肚子叫很失敗；社群共識是人身相關音效要用真實錄音或 Foley 模型（見 [音效研究](../資源索引/AI短片/音效製作_社群做法_走路聲與肚子叫_20261003.md)）。
> 本庫全部是 **Freesound CC0**（用 `license:"Creative Commons 0"` 篩選取得；CC0＝可商用、免標示、可修改）。檔案是 Freesound 的 **hq 預覽 mp3**（約 128kbps，夠做短片混音；要更高音質可到各 `page` 網址登入後下載原檔）。清單、來源網址、備註在 [manifest.json](manifest.json)。

| 分類 | 檔案（時間長度） | 用途 |
|:---|:---|:---|
| 腳步 | `foot_leather_hard_surface_462179`（23s 皮鞋）、`foot_echo_hall_536290`（22s 走廊回音）、`foot_shoes_stone_637555`（7s）、`foot_docmartins_534635`（36s 皮靴）、`foot_tile_variations_834027`（6s，10 個變化）、`foot_laminate_830501`（38s）、`foot_quiet_rubber_613723`（18s 躡手躡腳） | 走廊、教室走路；躡手躡腳用 quiet_rubber |
| 肚子叫 | `stomach_growling_786693`（1.0s，單聲「咕嚕」，首選）、`stomach_growling_rumbles_447911`（2.0s）、`stomach_growl_PiSh_52293`（3.6s）、`stomach_long_intense_9_696404`（12s） | 「咕嚕咕嚕」＝786693 連播兩次（第二次降 2 個半音） |
| 翻頁 | `page_flip_683706`（9s）、`page_turn_144110`（1.7s）、`page_turn_860360`（0.3s） | 翻書、翻筆記 |
| 門 | `door_close_classroom_379896`（3s）、`door_close_classroom_204178`（10s） | 關教室門 |
| 窗鎖 | `window_handle_unlock_448393`（1.3s）、`window_click_slide_669069`（4s） | 扣窗鎖 |

## 用法
- 程式：`pipeline_post.py` 的 `lib()` 函式讀取（可指定起點、長度、增益、變速／變調）。
- 手動：用 ffmpeg 裁切，如 `ffmpeg -ss 3 -t 2 -i 腳步/foot_echo_hall_536290.mp3 out.wav`。
- 有動作的鏡頭**優先用 H3 原生音效**（沒台詞的鏡頭不給固定音軌，音效會與動作同步；見 `試行/H3原生音效_20261003/`）；H3 做不出來的（如肚子叫）用本庫。

## 使用限制與提醒
- 這些檔是公有領域貢獻（CC0），不需標示；建議仍保留 manifest 備查。
- 要新增素材時：到 Freesound 用 CC0 篩選，確認授權後下載，更新 manifest。不要把非 CC0 或授權不明的檔放進來。
- Sonniss GDC 2026 免費包（7.47GB）已查過：曲目清單 347 檔幾乎沒有適合學校腳步／肚子叫的素材，**未下載**。
