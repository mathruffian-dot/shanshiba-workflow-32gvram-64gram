# agent：讓 AI agent 接手製作

| 檔案 | 用途 |
|---|---|
| `CLAUDE.md範本.md` | 專案入口範本，改名 `CLAUDE.md` 放專案根目錄 |
| `skills/shanshiba-drama/` | 編劇技能：九階段流程、16:9 劇本格式、片段切分、審稿清單（改寫自 AI-drama-pound，MIT，見 NOTICE.md） |
| `skills/blender-previs/` | Blender 預演技能：需求訪談、鏡位契約、布置圖規則、提示詞包、檢查清單 |

技能放到專案的 `.claude/skills/` 底下，Claude Code 會自動載入。

> ⚠️ 兩個技能寫於專案早期（2026-08～09），references 裡還有幾處舊說法，用的時候以 `docs/` 為準（`shanshiba-drama/SKILL.md` 開頭已寫明怎麼對應）：
> - 「Seedance 2.5、每段 30 秒」→ 本機 H3、單鏡 ≤12 秒、對話靠切鏡
> - 「山獅霸」「角色資產/山獅霸/角色設定.md」→ 原頻道的例子，請換成你自己的角色設定檔
> - 「voice-clone 技能」→ BreezyVoice（`make_breezyvoice.cmd`）
> - 首幀 → 本 repo 預設 Qwen-Image-Edit 2511 附定妝照（原頻道用雲端 Image 2.5）；定稿用 DMAD 4 步
> - 「14 步＋EasyCache」→ 定稿不開 EasyCache

協作方法（知識庫分層、記憶、工作習慣）見 [docs/05_agent協作與知識庫.md](../docs/05_agent協作與知識庫.md)。
