"""Tests for scripts/restart_all.sh delegation to scripts/restart_all.ps1.

SAFE ONLY: the shell script is exercised exclusively via --dry-run (which
prints the plan + the powershell delegation command, starts nothing and runs
no health checks). The ps1 is checked statically. This module NEVER starts or
stops any process.
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "restart_all.sh"
PS1 = ROOT / "scripts" / "restart_all.ps1"

PS_BASE = "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1"


def _read(p: Path) -> str:
    assert p.exists(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def _bash() -> str:
    exe = shutil.which("bash")
    assert exe, "bash not found in PATH (required to run restart_all.sh --dry-run)"
    return exe


def _run_dry(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_bash(), str(SH), *args],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )


def test_scripts_exist():
    assert SH.exists() and PS1.exists()


def test_sh_delegates_real_starts_to_ps1_static():
    body = _read(SH)
    assert PS_BASE in body, "sh must delegate via the powershell ps1 command"
    assert "Win32_Process" in body, "sh must document the WMI detached-launch path"
    non_comment = "\n".join(
        ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "nohup" not in non_comment, "sh must not launch via nohup (incident fix)"


def test_ps1_starts_bots_with_start_process_not_wmi():
    # 2026-10-06: WMI-created bots died ~30 min after start (WMI host); the owner's
    # console path is a hidden Start-Process, agents use nohup from a foreground shell.
    body = _read(PS1)
    code_lines = [
        ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
    ]
    assert not any("Invoke-CimMethod" in ln for ln in code_lines)
    assert any("Start-Process cmd.exe" in ln for ln in code_lines)


def test_dry_run_default_maps_to_ps1_dryrun_without_only():
    cp = _run_dry("--dry-run")
    assert cp.returncode == 0, cp.stderr
    assert PS_BASE in cp.stdout
    assert "-DryRun" in cp.stdout
    assert "-Only" not in cp.stdout
    assert "started nothing" in cp.stdout.lower()


def test_dry_run_only_forms_map_to_ps1_only():
    cases = [
        (["--dry-run", "--only", "bots"], "-Only bots"),
        (["--dry-run", "--only=bots"], "-Only bots"),
        (["--dry-run", "bots"], "-Only bots"),
        (["--dry-run", "--only", "backend"], "-Only backend"),
        (["--dry-run", "--only=carry"], "-Only carry"),
        (["--dry-run", "carry"], "-Only carry"),
    ]
    for argv, expect in cases:
        cp = _run_dry(*argv)
        assert cp.returncode == 0, (argv, cp.stderr)
        assert expect in cp.stdout, (argv, cp.stdout)
        assert "-DryRun" in cp.stdout, (argv, cp.stdout)


def test_dry_run_starts_nothing():
    cp = _run_dry("--dry-run", "--only", "bots")
    assert cp.returncode == 0, cp.stderr
    assert "started nothing" in cp.stdout.lower()


def test_bad_only_rejected_without_starting():
    cp = _run_dry("--dry-run", "--only", "bogus")
    assert cp.returncode == 2
