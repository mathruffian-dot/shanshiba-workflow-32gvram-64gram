#!/usr/bin/env bash
# GPU 排隊（〈連假後第一天〉起的標準版；〈D-7〉當時是手動逐步跑）。每 60 秒看一次：GPU 使用率 < 20% 且 ComfyUI 佇列是空的，連續 3 次才算空閒；
# 空閒後請 ComfyUI 釋放顯存，再確認顯存 < 12GB（別的程式沒佔著）才開工。
# 依序：配音候選（VoxCPM2＋edge 參考）→ Breeze 候選 → 挑音 →（等 frames_ok 檔，首幀審過才有）→ H3 出片。
# 每步寫 queue.log；任一步失敗就停。
cd "$(dirname "$0")"
LOG=queue.log
say() { echo "$(date '+%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
VOICE=C:/AI/Voice/venv/Scripts/python.exe
BREEZE=C:/AI/BreezeTTS/venv/Scripts/python.exe
BZ=C:/AI/tools/breeze_batch.py
H3PY=C:/AI/H3/venv/Scripts/python.exe

comfy_busy() {
  curl -s --max-time 5 http://127.0.0.1:8188/queue | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['queue_running'])+len(d['queue_pending']))" 2>/dev/null || echo 0
}

wait_gpu() {
  say "等待 GPU 空閒（$1）"
  while true; do
    local ok=0
    while [ $ok -lt 3 ]; do
      util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | tr -d ' ')
      if [ "$util" -lt 20 ] && [ "$(comfy_busy)" = "0" ]; then ok=$((ok+1)); else ok=0; fi
      sleep 60
    done
    curl -s -X POST http://127.0.0.1:8188/free -H "Content-Type: application/json" -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
    sleep 15
    mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
    if [ "$mem" -lt 12000 ]; then say "GPU 空閒（顯存 ${mem}MiB），開始：$1"; return; fi
    say "使用率低但顯存仍被佔 ${mem}MiB，繼續等"
  done
}

step() { local name=$1; shift; say "▶ $name"; "$@" >> "$name.log" 2>&1 || { say "✗ $name 失敗，見 $name.log"; exit 1; }; say "✓ $name"; }

if [ ! -f voice_state.json ]; then
  wait_gpu "配音"
  step voice1 "$VOICE" voice_stage1.py --n 6
  step breeze "$BREEZE" "$BZ" breeze_jobs.json
  step pick "$VOICE" voice_pick.py
fi
while [ ! -f frames_ok ]; do sleep 60; done
say "首幀已審過（frames_ok）"
wait_gpu "H3"
step gen1 "$H3PY" pipeline_gen.py
say "QUEUE_DONE"
