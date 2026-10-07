@echo off
rem 版本 B 備案：16GB VRAM＋32–48GB RAM。文字編碼器換官方 NVFP4、影片 VAE 換 int8，省約 10GB 記憶體
rem 注意：同 seed 結果會跟版本 A 不同（像換一次抽卡）；4080 沒有原生 FP4，會比較慢
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_int8_convrot.safetensors
set COMFY_EXTRA_ARGS=--reserve-vram 1.5
echo [profile B lowRAM] NVFP4 text encoder + int8 video VAE, start ComfyUI with %COMFY_EXTRA_ARGS%
