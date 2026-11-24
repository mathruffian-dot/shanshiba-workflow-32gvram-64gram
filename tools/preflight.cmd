@echo off
rem Pre-delivery checklist (film level). Usage: see the header of preflight.py
rem   preflight check <film.mp4> / sign <film.mp4> <item> --by .. --result pass|reject --note ".." / status <film.mp4> / selftest
"C:\AI\Voice\venv\Scripts\python.exe" "%~dp0preflight.py" %*
