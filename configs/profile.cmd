@echo off
rem 32GB VRAM + 64GB RAM (full version). These are the values used in the original project.
rem Usage: in the same command window, call this file first, then run start_comfy and the pipeline scripts.
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set COMFY_EXTRA_ARGS=
echo [profile] 32GB VRAM + 64GB RAM: int8 text encoder, fp16 video VAE, shots up to 12 s
