"""Ops: straddle paper loop in the restart scripts (OPENCODE_W_ops_restartstraddle).

The prospective straddle ledger runs as a self-looping process:
  .venv/Scripts/python.exe scripts/straddle_paper.py --equity 20000 --f 0.25 --tag straddle --interval 600
stdout appended to artifacts/bot/paper_straddle/stdout.log.
It lives in the carry scope (register_keepalive.ps1 calls restart_all.ps1
-Only bots and -Only carry, so no new -Only straddle scope).

SAFE ONLY: restart scripts are exercised exclusively via --dry-run / -DryRun
(which print the plan, start nothing, stop nothing). This module NEVER starts
or stops any process.

Observed -DryRun / --dry-run outputs (2026-10-07, pasted per assignment):

  $ bash scripts/restart_all.sh --dry-run
  POWERSHELL: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 -DryRun
  PLAN: start backend: .venv/Scripts/python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8724 --timeout-keep-alive 30 --no-access-log (local only, never the public tunnel)
  PLAN: advisor loop.sh retired (backend runs shadow) -> not started: bash artifacts/research/advisor_shadow/loop.sh
  PLAN: start paper bot paper: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --interval 25 (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot d17bf: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --interval 25 --tag d17bf (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot d13bf: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.3 --bear-book --interval 25 --tag d13bf (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot d17bfg2: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag d17bfg2 (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot g2k20: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 2.0 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag g2k20 (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot d17bfg2c: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start paper bot g2k20c: .venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 2.0 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag g2k20c (only if runner.lock free; backup+validate state.json; skip when already running)
  PLAN: start carry loop once: .venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry every 3600s (skip if running; skip when already running)
  PLAN: start straddle loop: .venv/Scripts/python.exe scripts/straddle_paper.py --equity 20000 --f 0.25 --tag straddle --interval 600 every 600s (skip if running; carry scope)
  PLAN: print health: scripts/bot_health.py for all runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c, g2k20c) + scripts/daily_status.py summary
  [restart_all] dry-run: plan only, started nothing (real starts delegate to restart_all.ps1 via WMI Win32_Process)

  $ bash scripts/restart_all.sh --dry-run --only carry
  POWERSHELL: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 -Only carry -DryRun
  PLAN: start carry loop once: .venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry every 3600s (skip if running; skip when already running)
  PLAN: start straddle loop: .venv/Scripts/python.exe scripts/straddle_paper.py --equity 20000 --f 0.25 --tag straddle --interval 600 every 600s (skip if running; carry scope)
  PLAN: print health: scripts/bot_health.py for all runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c, g2k20c) + scripts/daily_status.py summary
  [restart_all] dry-run: plan only, started nothing (real starts delegate to restart_all.ps1 via WMI Win32_Process)

  PS> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 -DryRun
  (live state 2026-10-07: backend healthy, all paper bots running, straddle loop running)
  [restart_all] backend healthy (/health OK, plan age 0.74h) -> skip start (local only, no tunnel)
  [restart_all] advisor loop.sh retired (backend runs shadow) -> not started
  [restart_all] bot paper already running (runner.lock held) -> skip
  [restart_all] bot d17bf already running (runner.lock held) -> skip
  [restart_all] bot d13bf already running (runner.lock held) -> skip
  [restart_all] bot d17bfg2 already running (runner.lock held) -> skip
  [restart_all] bot g2k20 already running (runner.lock held) -> skip
  [restart_all] bot d17bfg2c already running (runner.lock held) -> skip
  [restart_all] bot g2k20c already running (runner.lock held) -> skip
  PLAN: start carry loop once: .venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry every 3600s (skip if running)
  [restart_all] straddle loop already running -> skip
  PLAN: print health: scripts/bot_health.py for all six runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) + scripts/daily_status.py summary
  [restart_all] dry-run: plan only, started nothing

  PS> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 -DryRun -Only carry
  PLAN: start carry loop once: .venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry every 3600s (skip if running)
  [restart_all] straddle loop already running -> skip
  PLAN: print health: scripts/bot_health.py for all six runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) + scripts/daily_status.py summary
  [restart_all] dry-run: plan only, started nothing

  PS> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 -DryRun -Only bots
  (no straddle line: straddle lives in the carry scope, keepalive calls -Only bots + -Only carry)
  [restart_all] bot paper already running (runner.lock held) -> skip
  [restart_all] bot d17bf already running (runner.lock held) -> skip
  [restart_all] bot d13bf already running (runner.lock held) -> skip
  [restart_all] bot d17bfg2 already running (runner.lock held) -> skip
  [restart_all] bot g2k20 already running (runner.lock held) -> skip
  [restart_all] bot d17bfg2c already running (runner.lock held) -> skip
  [restart_all] bot g2k20c already running (runner.lock held) -> skip
  PLAN: print health: scripts/bot_health.py for all six runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) + scripts/daily_status.py summary
  [restart_all] dry-run: plan only, started nothing
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "restart_all.sh"
PS1 = ROOT / "scripts" / "restart_all.ps1"
KEEPALIVE = ROOT / "scripts" / "register_keepalive.ps1"

STRADDLE_CMD = (
    ".venv/Scripts/python.exe scripts/straddle_paper.py "
    "--equity 20000 --f 0.25 --tag straddle --interval 600"
)
STRADDLE_PATTERN = r"straddle_paper\.\*--tag straddle"
STRADDLE_LOG = "artifacts/bot/paper_straddle/stdout.log"


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


def test_straddle_canonical_command_in_both_shells():
    sh, ps = _read(SH), _read(PS1)
    assert STRADDLE_CMD in sh.replace("\\\\", "/"), "straddle command missing (sh)"
    assert STRADDLE_CMD in ps.replace("\\\\", "/"), "straddle command missing (ps1)"


def test_straddle_detected_by_cmdline_match_and_skips_when_running():
    ps = _read(PS1)
    assert re.search(STRADDLE_PATTERN, ps), (
        f"already-running match {STRADDLE_PATTERN!r} missing (restart_all.ps1)"
    )
    assert "straddle loop already running -> skip" in ps, (
        "idempotence skip branch missing (restart_all.ps1)"
    )
    # restart_all.sh delegates real starts to the ps1; it mirrors the guard as
    # a documented match plus a skip-if-running plan line (see dry-run tests).
    sh = _read(SH)
    assert re.search(STRADDLE_PATTERN, sh), (
        f"already-running match {STRADDLE_PATTERN!r} missing (restart_all.sh)"
    )
    assert "start straddle loop" in sh and "skip if running" in sh, (
        "straddle skip-if-running plan wording missing (restart_all.sh)"
    )


def test_straddle_uses_bot_launch_path_and_log():
    ps = _read(PS1)
    assert STRADDLE_LOG.replace("\\\\", "/") in ps.replace("\\\\", "/"), (
        "straddle stdout.log path missing (ps1)"
    )
    # same detached-launch method the script uses for bots
    assert "Start-Detached $py $straddleArgs" in ps, (
        "straddle must start via Start-Detached like the bots"
    )


def test_straddle_lives_in_carry_scope_not_new_only_scope():
    sh, ps = _read(SH), _read(PS1)
    # no new "-Only straddle" scope accepted: the --only/-Only validators still
    # allow only all|bots|backend|carry (prose may mention "no new -Only straddle scope")
    assert '@("all", "bots", "backend", "carry")' in ps, "ps1 -Only validator changed"
    assert 'all|bots|backend|carry' in sh, "sh --only validator changed"
    assert "all|carry) plan_line \"start straddle loop" in sh, (
        "straddle plan line must sit in the all|carry scope (sh)"
    )
    assert "all|bots) plan_line \"start straddle loop" not in sh, (
        "straddle plan line must NOT sit in the bots scope (sh)"
    )
    assert "carry scope" in sh and "carry scope" in ps, (
        "carry-scope placement must be documented in both shells"
    )
    keep = _read(KEEPALIVE)
    assert "restart_all.ps1" in keep and "-Only bots" in keep and "-Only carry" in keep, (
        "register_keepalive.ps1 must still call -Only bots and -Only carry"
    )


def test_sh_dry_run_prints_straddle_plan_line():
    cp = _run_dry("--dry-run")
    assert cp.returncode == 0, cp.stderr
    assert "start straddle loop" in cp.stdout, "straddle plan line missing (all)"
    assert STRADDLE_CMD in cp.stdout, "straddle command missing in plan (all)"
    assert "started nothing" in cp.stdout.lower()


def test_sh_dry_run_carry_scope_has_straddle_bots_scope_does_not():
    carry = _run_dry("--dry-run", "--only", "carry")
    assert carry.returncode == 0, carry.stderr
    assert "start straddle loop" in carry.stdout, "straddle plan missing (-Only carry)"
    bots = _run_dry("--dry-run", "--only", "bots")
    assert bots.returncode == 0, bots.stderr
    assert "start straddle loop" not in bots.stdout, (
        "straddle must NOT be in the bots scope (carry scope only)"
    )


def test_straddle_idempotence_model_mirrors_skip_if_running():
    """Mirror the scripts' skip-if-running rule against a fake process list."""

    def running(fake_procs, pattern):
        rx = re.compile(pattern)
        return any(rx.search(c) for c in fake_procs)

    live = [
        ".venv/Scripts/python.exe scripts/straddle_paper.py "
        "--equity 20000 --f 0.25 --tag straddle --interval 600"
    ]
    assert running(live, r"straddle_paper.*--tag straddle")
    assert not running([], r"straddle_paper.*--tag straddle")
    # a different tag must not match the straddle guard
    other = [".venv/Scripts/python.exe scripts/straddle_paper.py --tag other"]
    assert not running(other, r"straddle_paper.*--tag straddle")
