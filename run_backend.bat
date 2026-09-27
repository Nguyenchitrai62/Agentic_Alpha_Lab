@echo off
rem Double-click to start the web backend + Cloudflare tunnel (see run_backend.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_backend.ps1" %*
pause
