"""Tests for scripts/heavy_slot.py (cross-process RAM-gated semaphore)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import heavy_slot as hs
from scripts.heavy_slot import heavy_slot, wait_for_ram

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "heavy_slot.py"

HOLDER_TMPL = (
    "import sys\n"
    "sys.path.insert(0, {root!r})\n"
    "import time\n"
    "from pathlib import Path\n"
    "from scripts.heavy_slot import heavy_slot\n"
    "ready = Path({ready!r})\n"
    "with heavy_slot({tag!r}, max_slots={max_slots}, min_free_gb=0, "
    "poll={poll}, timeout_h={timeout_h}, slots_dir={slots!r}):\n"
    "    ready.write_text('ready', encoding='utf-8')\n"
    "    time.sleep({hold_s})\n"
)


def _wait_ready(ready: Path, timeout: float = 30.0) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if ready.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"holder never signalled ready: {ready}")


def _start_holder(slots: Path, tag: str, hold_s: float,
                  max_slots: int = 1, poll: float = 0.05):
    ready = slots.parent / f"ready_{tag}.txt"
    if ready.exists():
        ready.unlink()
    code = HOLDER_TMPL.format(root=str(ROOT), ready=str(ready), tag=tag,
                              max_slots=max_slots, poll=poll,
                              timeout_h=120 / 3600, slots=str(slots),
                              hold_s=hold_s)
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(ROOT))
    _wait_ready(ready)
    return proc, ready


def test_two_processes_contend_for_one_slot(tmp_path):
    slots = tmp_path / "slots"
    proc, ready = _start_holder(slots, "holder-a", hold_s=3.0)
    try:
        t0 = time.monotonic()
        with heavy_slot("waiter-b", max_slots=1, min_free_gb=0, poll=0.05,
                        timeout_h=60 / 3600, slots_dir=slots):
            elapsed = time.monotonic() - t0
        # waiter must have blocked until the holder released (~3 s hold)
        assert elapsed >= 1.5, f"second process did not wait: {elapsed:.2f}s"
    finally:
        proc.wait(timeout=30)
    assert proc.returncode == 0


def test_crash_releases_slot(tmp_path):
    slots = tmp_path / "slots"
    proc, ready = _start_holder(slots, "holder-crash", hold_s=60.0)
    try:
        proc.kill()  # our own holder child only: simulates a crash
        proc.wait(timeout=15)
        t0 = time.monotonic()
        with heavy_slot("after-crash", max_slots=1, min_free_gb=0, poll=0.05,
                        timeout_h=30 / 3600, slots_dir=slots):
            pass
        assert time.monotonic() - t0 < 20
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=15)


def test_status_output(tmp_path, capsys):
    slots = tmp_path / "slots"
    assert hs.cmd_status(max_slots=1, slots_dir=slots) == 0
    out = capsys.readouterr().out
    assert "slot_0: FREE" in out
    assert "slot_1" in out  # leader-reserved slot is listed
    assert "free_ram_gb" in out
    with heavy_slot("status-tag", max_slots=1, min_free_gb=0, poll=0.05,
                    timeout_h=30 / 3600, slots_dir=slots):
        assert hs.cmd_status(max_slots=1, slots_dir=slots) == 0
        held = capsys.readouterr().out
    assert "HELD" in held and "status-tag" in held
    # CLI end-to-end over the same dir
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--max-slots", "1",
         "--slots-dir", str(slots)], capture_output=True, text=True,
        cwd=str(ROOT), timeout=60)
    assert proc.returncode == 0
    assert "free_ram_gb" in proc.stdout


def test_run_wraps_command(tmp_path):
    slots = tmp_path / "slots"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "run", "--tag", "run-tag",
         "--max-slots", "1", "--min-free-gb", "0", "--poll", "0.05",
         "--timeout-h", str(30 / 3600), "--slots-dir", str(slots),
         "--", sys.executable, "-c", "import sys; sys.exit(3)"],
        cwd=str(ROOT), timeout=60)
    assert proc.returncode == 3


def test_ram_gate_with_monkeypatched_reader(tmp_path, monkeypatch):
    slots = tmp_path / "slots"
    calls = {"n": 0}

    def reader():
        calls["n"] += 1
        return 0.1 if calls["n"] < 3 else 99.0

    monkeypatch.setattr(hs, "free_gb", reader)
    with heavy_slot("ram-wait", max_slots=1, min_free_gb=2.5, poll=0.05,
                    timeout_h=30 / 3600, slots_dir=slots):
        pass
    assert calls["n"] >= 3

    monkeypatch.setattr(hs, "free_gb", lambda: 0.0)
    with pytest.raises(TimeoutError):
        with heavy_slot("ram-timeout", max_slots=1, min_free_gb=2.5,
                        poll=0.05, timeout_h=0.5 / 3600, slots_dir=slots):
            pass  # pragma: no cover
    assert wait_for_ram(2.5, poll=0.05, timeout_h=0.5 / 3600,
                        reader=lambda: 99.0) == pytest.approx(99.0)


def test_leader_gets_reserved_slot(tmp_path):
    slots = tmp_path / "slots"
    with heavy_slot("worker", max_slots=1, min_free_gb=0, poll=0.05,
                    timeout_h=30 / 3600, slots_dir=slots):
        with heavy_slot("leader", max_slots=1, min_free_gb=0, poll=0.05,
                        timeout_h=30 / 3600, slots_dir=slots,
                        leader=True) as hold:
            assert hold.index == 1
