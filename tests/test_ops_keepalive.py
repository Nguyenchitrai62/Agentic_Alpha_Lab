"""Static checks for scripts/register_keepalive.ps1 (no tasks created, no processes touched).

Run: .venv/Scripts/python.exe -m pytest tests/test_ops_keepalive.py -q
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "register_keepalive.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_default_interval():
    assert SCRIPT.exists(), "scripts/register_keepalive.ps1 must exist"
    t = _text()
    assert re.search(r"\$EveryMinutes\s*=\s*10\b", t), "default -EveryMinutes 10 required"


def test_no_auth_trading_flags_and_paper_only_actions():
    t = _text()
    assert "BOT_ALLOW_LIVE" not in t
    assert "testnet" not in t.lower()
    assert "--live" not in t.lower()
    assert "-Only bots" in t
    assert "-Only carry" in t
    assert "restart_all.ps1" in t
    assert "run_backend.ps1" in t
    assert "-Ensure" in t


def test_safe_task_settings():
    t = _text()
    assert "-MultipleInstances Parallel" in t, "IgnoreNew could stall the keepalive if bot children keep the task Running"
    assert "Interactive" in t, "run only when user is logged on"
    assert "ExecutionTimeLimit" in t
    assert "WorkingDirectory" in t or "working directory" in t.lower()
    assert "AlphaLabRunnersKeepAlive" in t
    assert "AlphaLabBackendWatchdog" in t
    assert "AlphaLabBackendKeepAlive" in t


def test_default_mode_changes_nothing_static():
    t = _text()
    # dispatch: Unregister / Register gated, otherwise Status
    assert "if ($Register -and $Unregister)" in t or "if ($Unregister" in t
    assert "Show-Status" in t
    m = re.search(r"function Show-Status \{(.*?)\n\}", t, re.S)
    assert m, "Show-Status function required"
    body = m.group(1)
    for verb in ("Register-ScheduledTask", "Unregister-ScheduledTask",
                 "Enable-ScheduledTask", "Set-ScheduledTask", "Stop-Process", "Start-Process"):
        assert verb not in body, f"Status path must not call {verb}"


def test_powershell_parses():
    pe = shutil.which("powershell.exe") or shutil.which("powershell")
    assert pe, "powershell required to prove the script parses"
    ps = f"[ScriptBlock]::Create((Get-Content -Path '{SCRIPT}' -Raw)) | Out-Null; exit 0"
    r = subprocess.run([pe, "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"powershell parse failed: {r.stderr[:2000]}"
