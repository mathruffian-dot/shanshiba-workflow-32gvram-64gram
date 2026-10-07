@echo off
REM BreezyVoice one-shot: generate candidates (BreezyVoice venv) then auto-pick (Voice venv). Usage: make_breezyvoice.cmd jobs.json
REM See breezyvoice_batch.py / breezyvoice_pick.py headers. Keep this file ASCII-only (cmd reads it in the console codepage).
setlocal
set PYTHONUTF8=1
set PYTHONPATH=C:\AI\BreezyVoice\winstub;C:\AI\BreezyVoice\code;C:\AI\BreezyVoice\code\third_party\Matcha-TTS
C:\AI\BreezyVoice\venv\Scripts\python.exe C:\AI\tools\breezyvoice_batch.py %1 < NUL || exit /b 1
set PYTHONPATH=
C:\AI\Voice\venv\Scripts\python.exe C:\AI\tools\breezyvoice_pick.py %1
endlocal
