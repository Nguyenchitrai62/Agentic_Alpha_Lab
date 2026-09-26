# Runs the current best research pipeline (v205) and prints the actions for the current 4h bar.
# Research output only - no orders are placed. Usage (from the repo root):
#   .\run.ps1                 # assumes the account is at its peak (governor g = 1), equity 10000 USDT
#   .\run.ps1 -Dd 0.08 -Equity 5000
param(
    [double]$Dd = 0.0,
    [double]$Equity = 10000
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$env:PYTHONUTF8 = "1"
& ".\.venv\Scripts\python.exe" "scripts\v197_advisor.py" --dd $Dd --equity $Equity
