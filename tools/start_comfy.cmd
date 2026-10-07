@echo off
REM Start ComfyUI (H3 / Qwen / Music 3) on 127.0.0.1:8188 if it is not running yet. Returns once the server answers.
REM Run "call configs\profile.cmd" in the SAME window first, so COMFY_EXTRA_ARGS (e.g. --reserve-vram 1.5) is passed on.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_comfy.ps1" %*
