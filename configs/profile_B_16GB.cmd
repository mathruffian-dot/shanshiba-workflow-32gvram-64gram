@echo off
rem 版本 B：16GB VRAM／64GB RAM（2026-10-07 在 5090 上模擬驗證：同模型逐格相同，見 docs\hardware_B_16GB.md）
rem 模型跟版本 A 一樣；差別只在啟動 ComfyUI 時加 --reserve-vram 1.5，且一次只跑一件 GPU 工作
rem VAE 解碼當機再加：--disable-pinned-memory --disable-async-offload
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set COMFY_EXTRA_ARGS=--reserve-vram 1.5
echo [profile B] 16GB VRAM + 64GB RAM: same models as A, start ComfyUI with %COMFY_EXTRA_ARGS%
