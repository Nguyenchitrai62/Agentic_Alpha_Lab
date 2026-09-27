@echo off
rem Double-click to open the local frontend (see run_frontend.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_frontend.ps1" %*
pause
