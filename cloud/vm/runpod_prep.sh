#!/bin/bash
# Runs ON a RunPod pod (started by cloud/runpod_h3.py start) BEFORE cloud/vm/setup_h3.py.
# The RunPod PyTorch template differs from Colab in three ways that matter for H3 (measured 2026-11-13):
#   1. Ubuntu 24.04 system Python refuses pip installs (PEP 668)  -> PIP/UV_BREAK_SYSTEM_PACKAGES=1 (also exported by runpod_h3.py)
#   2. no ffmpeg                                                    -> apt-get install ffmpeg
#   3. torch 2.8 cu128: comfy-kitchen turns its CUDA ops OFF ("need pytorch with cu130") and H3 runs 1.7-2x slower
#      -> torch 2.14 cu130 (the same build as the Windows install; the driver on RunPod Blackwell hosts supports CUDA 13.x)
# The scripts under cloud/vm/ use /content (Colab's folder) -> /content is a symlink to /workspace/content.
set -e
export PIP_BREAK_SYSTEM_PACKAGES=1 UV_BREAK_SYSTEM_PACKAGES=1
T0=$(date +%s); el(){ echo $(( $(date +%s) - T0 )); }
mkdir -p /workspace/content
[ -e /content ] || ln -s /workspace/content /content
command -v ffmpeg >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null; }
echo "[prep] ffmpeg $(el)s"
command -v uv >/dev/null || pip install -q uv
if ! python -c "import torch,sys; sys.exit(0 if torch.__version__.startswith('2.14') else 1)" 2>/dev/null; then
  uv pip install --python "$(command -v python)" -q torch==2.14.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
fi
echo "[prep] torch $(python -c 'import torch;print(torch.__version__, torch.version.cuda, torch.cuda.is_available())') $(el)s"
echo "PREP_DONE"
