# 16gb_sim：硬體模擬驗證的程式與原始數據（2026-10-07）

這些是原專案在 RTX 5090（32GB VRAM／96GB RAM）上「模擬」較小硬體時用的程式，留著讓你知道數字怎麼來、也能照同樣方法自己驗證。

| 檔案 | 用途 |
|---|---|
| `hog.py` | 佔住指定 MiB 的顯存（模擬 16GB 卡） |
| `ram_hog.py` | 鎖住指定 GB 的實體記憶體（Windows VirtualLock，不會被換到分頁檔），模擬小記憶體電腦 |
| `comfy_ramcap.py` | 讓 ComfyUI 以為總記憶體只有 N GB（借用它給 Linux 容器用的上限邏輯）；`RAMCAP_GB=32` |
| `run_test.py`、`long_test.py` | H3 三組比較（原設定／16GB 同模型／16GB＋NVFP4）、260 格長鏡頭 |
| `run_32g.py` | 32GB／64GB 記憶體下的 H3 比較 |
| `run_tier.py` | 三種配置下逐一跑 13 個本地元件 |
| `tier_summary.md` | 元件結果總表 |
| `results_*.json` | 原始數據：秒數（ComfyUI /history 或牆鐘）、顯存峰值、記憶體最低值、輸出雜湊 |

注意：`run_test.py`／`run_32g.py`／`run_tier.py` 裡的鏡頭路徑指向原專案的片子（`短片/阿禾出場介紹_20261006/h3/...`），repo 沒有附這些素材；要自己驗證時換成你自己的 shot spec。安裝後的一般驗證請用 `setup/smoke_test.py`（不需要任何素材）。

模擬的限制：運算單元仍是 5090（所以秒數不等於真實 16GB 卡）、PCIe 5.0、這台的 NVMe 很快、分頁檔起始大小不同。
