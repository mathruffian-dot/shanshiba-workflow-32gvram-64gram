# 來源標註

本技能的流程骨架（八階段編劇流程、劇本格式規範、審閱清單結構）改寫自：

**[POUND0423/AI-drama-pound](https://github.com/POUND0423/AI-drama-pound)** — `ai-short-drama-screenwriter`，MIT License，v0.1.0（2026-08-26）。

## 本專案的改動

| 項目 | 原版 | 本版 |
|:---|:---|:---|
| 平台 | OpenAI Codex（`~/.agents/skills/`） | Claude Code（專案內 `.claude/skills/`） |
| 畫面比例 | 豎屏 9:16 | **16:9 橫式** |
| 篇幅結構 | 8–12 集連續短劇 | **單支 1–2 分鐘，獨立成篇** |
| 角色 | 每次從零設計 | **固定主角山獅霸**，引用專案 Character Bible |
| 技術限制 | 無 | **Seedance 2.5 可行性檢查**（避開快動作、單一說話者） |
| 階段數 | 8 | **9**（新增〈片段切分與素材備料〉） |
| 新增檔案 | — | `references/segmentation.md` |

原專案的 `agents/openai.yaml` 未沿用（Claude Code 不使用該格式）。
