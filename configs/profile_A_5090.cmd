@echo off
rem 版本 A：RTX 5090 32GB／96GB RAM（原專案實際設定）
rem 用法：在同一個命令列視窗先 call 這個檔，再跑 pipeline 腳本
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set IMG25_QUALITY=medium
echo [profile A] 5090: int8 text encoder, fp16 video VAE, shots up to 12 s
