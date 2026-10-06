# 《山獅霸的多重宇宙》片尾範本（2026-09-30 定稿，可重複使用）

頻道品牌：**山獅霸的多重宇宙**。每支短片片尾固定用這個結構（使用者指示「之後會重複使用」）：

1. **特寫照片＋AI 工具名單**：N 張片中特寫（緩推、下緣壓暗、淡入淡出），每張左下 2 行「工具・用途」，**每張停留 3.3 秒**（1.9 秒太短，使用者要求加長）。第一張上方小標「本片使用的 AI 工具」。
2. **大標題「山獅霸的多重宇宙」**：金色咒印法陣（`assets/seal_gold.png`，Image 2.5 生成的黑底光圖）慢轉，標楷體 176pt 逐字由光浮現、爆光定格，約 7.5 秒；配樂在這裡收尾。
3. **聲音**：配樂貫穿片尾（沒有人聲也要有音樂）；最後約 3.5 秒音樂淡出、畫面約 2.4 秒漸黑；標題爆光處疊一下低頻不重的 boom＋鐘聲（主片後製疊）。

## 用法
```
C:\AI\H3\venv\Scripts\python.exe render_ending.py config.json
```
`config_example.json` 是阿福〈三個絕招〉實際用的設定（5 張特寫＋工具名單）。把特寫靜幀放進 `frames/`、依本片實際工具修改 tools。輸出 1920×1080、24fps、無音訊。

## 名單規則
- 只列實際用到的工具；使用者指示**不列非商用授權工具**（例如 Breeze TTS 2、YuE2）——但授權義務不會因不列名消失，商用前要另外處理。
- **MiniMax Music 3** 官方 Community License 要求顯著標示「MiniMax-Music3」並揭露機器生成 → 有用到就要列，並在最後一張加「本片畫面、配音與配樂皆由 AI 生成」。
- 常用名單：MiniMax H3、OpenAI Image 2.5、VoxCPM2、MiniMax Music 3、faster-whisper、BS-RoFormer、NVIDIA RTX VSR、ComfyUI、Claude Code。

## 素材
- `assets/seal_gold.png`：Image 2.5 生成的金色法陣（黑底光圖）。其他三色法陣在 `templates/seals/`。
- 實際效果請看頻道任一支片的片尾。
