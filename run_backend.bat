@echo off
rem Double-click: runs the backend + tunnel in this window with live logs. Close the window or press Ctrl+C to stop.
rem Options: run_backend.bat -Background ^| -Status ^| -Stop ^| -AccessLog  (see run_backend.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_backend.ps1" %*
pause
