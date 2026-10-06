# agent：讓 AI agent 接手製作

| 檔案 | 用途 |
|---|---|
| `CLAUDE.md範本.md` | 專案入口範本，改名 `CLAUDE.md` 放專案根目錄 |
| `skills/shanshiba-drama/` | 編劇技能：九階段流程、16:9 劇本格式、片段切分、審稿清單（改寫自 AI-drama-pound，MIT，見 NOTICE.md） |
| `skills/blender-previs/` | Blender 預演技能：需求訪談、鏡位契約、布置圖規則、提示詞包、檢查清單 |

技能放到專案的 `.claude/skills/` 底下，Claude Code 會自動載入。

> ⚠️ 兩個技能寫於專案早期（2026-08～09），還有幾處舊說法，用的時候以 `docs/` 為準：
> - 「Seedance 2.5、每段 30 秒」→ 現行是本機 H3、單鏡 ≤12 秒、對話靠切鏡
> - 「Qwen-Image 2.1 生圖、768p→VSR」→ 現行首幀用 Image 2.5、定稿用 DMAD 4 步
> - 「14 步＋EasyCache」→ 定稿不開 EasyCache

協作方法（知識庫分層、記憶、工作習慣）見 [docs/05_agent協作與知識庫.md](../docs/05_agent協作與知識庫.md)。
