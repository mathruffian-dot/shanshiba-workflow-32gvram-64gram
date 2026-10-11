#!/usr/bin/env bash
# Runs ON the Colab VM (started by cloud/colab_h3.py full-setup): the WHOLE local stack on Linux, for people whose computer
# cannot run anything locally - voice (VoxCPM2, faster-whisper, separator), BreezyVoice, Breeze TTS 2, ComfyUI (H3, Qwen-Image 2.1,
# Qwen-Edit 2511, Music 3, FlashVSR) + CJK fonts. Tested on a Colab L4 / G4 2026-10-10: setup/smoke_test.py passes everything
# except rtx_vsr (Windows only; Linux uses FlashVSR or lanczos). Models ~150 GB of the VM's ~236 GB disk.
# Usage: AI_ROOT=/content/AI REPO=/content/repo bash install_full.sh   (prints [full] lines, FULL_DONE at the end)
set -u
AI="${AI_ROOT:-/content/AI}"; REPO="${REPO:-/content/repo}"; C="$AI/H3/ComfyUI-0.36.0"
T0=$(date +%s); mark() { echo "[full] $1 = $(( $(date +%s) - T0 ))s"; }
# Windows pip-freeze lists -> drop only the exact Windows-only / torch-family names (torch comes from the PyTorch index with its
# Linux CUDA wheels). Careful: a prefix match would also drop torchmetrics, torchsde and the nvidia-*-cu12 libs Linux needs.
filt() { grep -viE '^(torch|torchaudio|torchvision|triton|triton-windows|nvidia-vfx|pywin32|pypiwin32|wmi)==' "$1"; }
export UV_HTTP_TIMEOUT=300
command -v uv >/dev/null || pip install -q uv
(apt-get -qq update && apt-get -qq install -y fonts-noto-cjk fonts-arphic-ukai >/dev/null 2>&1 && echo "[full] fonts OK") &

# --- models: ONE manifest at a time (several at once on an anonymous Hugging Face connection -> HTTP 429)
python - "$REPO/setup/downloads.json" <<'EOF'   # H3 core without the official NVFP4 encoder (the int8 one below is what we use)
import json, sys
json.dump([x for x in json.load(open(sys.argv[1], encoding="utf-8-sig")) if "nvfp4" not in x["destination"]],
          open("/content/downloads_h3core.json", "w"), indent=1)
EOF
(
  cd "$REPO/setup"
  for m in /content/downloads_h3core.json downloads_uncensored.json downloads_dmad.json downloads_qwen_image.json downloads_qwen_image_edit.json \
           downloads_music3.json downloads_flashvsr.json downloads_voxcpm2.json downloads_breezyvoice.json downloads_breeze_tts2.json; do
    t=$(date +%s)
    n=$(basename "$m")
    AI_ROOT="$AI" python download.py "$m" > "/content/dl_$n.log" 2>&1 && echo "[full] model $n OK $(( $(date +%s) - t ))s" \
      || echo "[full] model $n FAILED (re-run this script: verified files are skipped)"
  done
) &
DLPID=$!

# --- voice venv (VoxCPM2, faster-whisper, audio-separator, pron tools)
uv venv -q -p 3.12 "$AI/Voice/venv"; VP="$AI/Voice/venv/bin/python"
uv pip install -q --python "$VP" torch==2.14.0 torchaudio==2.11.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130 \
  && filt "$REPO/setup/env/requirements_voice_venv.txt" > /content/req_voice.txt \
  && uv pip install -q --python "$VP" --no-deps -r /content/req_voice.txt --index-strategy unsafe-best-match \
  && "$VP" -c "import voxcpm, faster_whisper, audio_separator, stable_whisper, parselmouth, pypinyin, opencc" && echo "[full] voice env OK" \
  || echo "[full] voice env FAILED"
# --- BreezyVoice (Python 3.10; winstub instead of pynini = same behaviour as the Windows install)
BV="$AI/BreezyVoice"
git clone -q --recurse-submodules https://github.com/mtkresearch/BreezyVoice "$BV/code" \
  && git -C "$BV/code" checkout -q d592c9d3e8927a0f53f68616387060dcd32a05ea && git -C "$BV/code" submodule update -q --init --recursive
cp -r "$REPO/setup/breezyvoice/winstub" "$BV/winstub"
uv venv -q -p 3.10 "$BV/venv"; BP="$BV/venv/bin/python"
uv pip install -q --python "$BP" "setuptools<70" wheel \
  && uv pip install -q --python "$BP" torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128 \
  && filt "$REPO/setup/env/requirements_breezyvoice_venv.txt" > /content/req_bv.txt \
  && uv pip install -q --python "$BP" --no-build-isolation --no-deps -r /content/req_bv.txt --index-strategy unsafe-best-match \
  && echo "[full] breezyvoice env OK" || echo "[full] breezyvoice env FAILED"
# --- Breeze TTS 2 (only for designing new reference voices)
git clone -q https://github.com/breezeblue-ai/breeze-tts "$AI/BreezeTTS/breeze-tts"
uv venv -q -p 3.12 "$AI/BreezeTTS/venv"; RP="$AI/BreezeTTS/venv/bin/python"
uv pip install -q --python "$RP" torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128 \
  && filt "$REPO/setup/env/requirements_breeze_venv.txt" > /content/req_breeze.txt \
  && uv pip install -q --python "$RP" --no-deps -r /content/req_breeze.txt --index-strategy unsafe-best-match \
  && echo "[full] breeze env OK" || echo "[full] breeze env FAILED"
mark voice_envs

# --- ComfyUI 0.37.0 + FlashVSR node on the VM's python (keeps Colab's torch)
if [ ! -f "$C/main.py" ]; then
  git clone -q --depth 1 --branch v0.37.0 https://github.com/comfyanonymous/ComfyUI /content/ComfyUI_src && mkdir -p "$C" && cp -rn /content/ComfyUI_src/. "$C/"
  git clone -q https://github.com/lihaoyun6/ComfyUI-FlashVSR_Ultra_Fast "$C/custom_nodes/ComfyUI-FlashVSR_Ultra_Fast" \
    && git -C "$C/custom_nodes/ComfyUI-FlashVSR_Ultra_Fast" checkout -q 4820b3f
  grep -viE '^(torch|torchvision|torchaudio)([=<> ]|$)' "$C/requirements.txt" > /content/req_comfy.txt
  [ -f "$C/custom_nodes/ComfyUI-FlashVSR_Ultra_Fast/requirements.txt" ] && \
    grep -viE '^(torch|torchvision|torchaudio)([=<> ]|$)' "$C/custom_nodes/ComfyUI-FlashVSR_Ultra_Fast/requirements.txt" >> /content/req_comfy.txt
  uv pip install --system -q -r /content/req_comfy.txt comfy-kitchen==0.2.35 && echo "[full] comfy OK" || echo "[full] comfy FAILED"
  sed "s#C:/AI/H3/models#$AI/H3/models#" "$REPO/setup/extra_model_paths.yaml" > "$C/extra_model_paths.yaml"
fi
mark comfy

# --- small auto-downloads
"$VP" -c "from huggingface_hub import snapshot_download as s; s('openbmb/VoxCPM2', revision='32279effe8c19989596f05d353d1447f51d9e915', local_dir='$AI/Voice/models/VoxCPM2')" >/dev/null 2>&1 && echo "[full] voxcpm small files OK"
"$VP" -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', download_root='$AI/Voice/models/whisper')" >/dev/null 2>&1 && echo "[full] whisper OK"
wait $DLPID
python "$REPO/tools/dmad_lora_convert.py" "$C/models/loras/dmad_raw/dmad_minimax_h3_4step_lora_critic.safetensors" \
       "$C/models/loras/dmad_h3_4step_lora_critic_comfy.safetensors" >/dev/null && echo "[full] dmad converted"

# --- one ComfyUI, models stay loaded (no --cache-none: the VM has the memory)
pkill -f 'main.py --listen'; sleep 2
cd "$C" && nohup python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch --preview-method none --fast fp16_accumulation \
  > /content/comfy_0.log 2>&1 &
for i in $(seq 1 300); do curl -s -o /dev/null http://127.0.0.1:8188/system_stats && break; sleep 1; done
echo "{\"instances\": [{\"dir\": \"$C\", \"port\": 8188}], \"encoder\": \"heretic\", \"full\": true}" > /content/h3_state.json
df -h /content | tail -1
mark ALL
echo FULL_DONE
