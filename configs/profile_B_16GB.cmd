@echo off
rem 版本 B：16GB VRAM／64GB RAM（模擬推估，見 docs\hardware_B_16GB.md）
rem 另外：start_comfy.ps1 的啟動參數加 --reserve-vram 1.5；VAE 解碼當機再加 --disable-pinned-memory --disable-async-offload
rem 每鏡 spec 用 "draft": true（DMAD 4 步），單鏡 <= 158 格（6.6 秒）
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_int8_convrot.safetensors
set IMG25_QUALITY=medium
echo [profile B] 16GB: NVFP4 text encoder, int8 video VAE, shots up to 6.6 s, run one job at a time
