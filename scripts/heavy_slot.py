"""Cross-process heavy-job semaphore (RAM-gated).

Several workers run 4-phase engine jobs at once (~0.5-1.5 GB each) and starve
each other and the leader's own runs. Wrap heavy jobs with::

    from heavy_slot import heavy_slot

    with heavy_slot("oc_cmegap4p", max_slots=2, min_free_gb=2.5,
                    poll=30, timeout_h=6):
        ...  # run the engine phases here

Slot files live under ``artifacts/research/heavy_slots/slot_<n>.lock`` and
are held with an OS file lock (``msvcrt`` on Windows, ``fcntl`` elsewhere),
so a crashed process frees its slot automatically. Acquire also waits until
free RAM >= ``min_free_gb`` (``psutil`` when importable, else a PowerShell
``Win32_OperatingSystem.FreePhysicalMemory`` fallback, matching the existing
per-study RAM gates). Holder info (tag, pid, start time) is written into the
lock file for ``status``.

CLI::

    python scripts/heavy_slot.py status [--max-slots N] [--slots-dir DIR]
    python scripts/heavy_slot.py run --tag X [--leader] [--max-slots N]
        [--min-free-gb G] [--poll S] [--timeout-h H] [--slots-dir DIR]
        -- <cmd...>

``--leader`` takes a reserved extra slot (index ``max_slots``), so the
leader's own runs never deadlock behind two worker-held slots.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import msvcrt  # Windows
except ImportError:  # pragma: no cover - posix host
    msvcrt = None  # type: ignore

try:
    import fcntl  # posix
except ImportError:  # pragma: no cover - windows host
    fcntl = None  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLOT_DIR = ROOT / "artifacts" / "research" / "heavy_slots"


# ---------------------------------------------------------------------------
# free RAM
# ---------------------------------------------------------------------------

def free_gb() -> float:
    """Return free physical RAM in GiB (nan when unreadable)."""
    try:
        import psutil  # type: ignore

        return float(psutil.virtual_memory().available) / (1024.0 ** 3)
    except ImportError:
        pass
    except Exception:
        return float("nan")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True, text=True, timeout=60,
        ).stdout
        for token in out.strip().split():
            try:
                return float(token) / 1024.0 / 1024.0
            except ValueError:
                continue
        digits = "".join(c for c in out if c.isdigit())
        if digits:
            return float(digits) / 1024.0 / 1024.0
        return float("nan")
    except Exception:
        return float("nan")


def wait_for_ram(min_free_gb: float, poll: float, timeout_h: float,
                 reader=None) -> float:
    """Block until free RAM >= min_free_gb; return the observed value."""
    read = reader or free_gb
    if min_free_gb is None or min_free_gb <= 0:
        try:
            return float(read())
        except Exception:
            return float("nan")
    deadline = time.monotonic() + max(0.0, timeout_h) * 3600.0
    step = max(poll, 0.01)
    while True:
        try:
            g = float(read())
        except Exception:
            g = float("nan")
        if g != g:  # nan: unreadable -> proceed (matches legacy gates)
            print("[heavy_slot] free RAM unreadable; proceeding", flush=True)
            return g
        if g >= min_free_gb:
            return g
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"RAM gate: free {g:.2f} GiB < {min_free_gb:.2f} GiB "
                f"after {timeout_h} h")
        print(f"[heavy_slot] free RAM {g:.2f} GiB < {min_free_gb:.2f} GiB; "
              f"sleeping {step:g}s", flush=True)
        time.sleep(step)


# ---------------------------------------------------------------------------
# OS file locks
# ---------------------------------------------------------------------------

def _lock_nb(fh) -> bool:
    """Try a non-blocking exclusive lock on byte 0; True on success."""
    fh.seek(0, 2)
    if fh.tell() < 1:
        fh.write(b"\x00")
        fh.flush()
    fh.seek(0)
    try:
        if msvcrt is not None:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        elif fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:  # pragma: no cover - no lock primitive
            return False
        return True
    except (OSError, IOError):
        return False


def _unlock(fh) -> None:
    try:
        fh.seek(0)
        if msvcrt is not None:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def _read_holder(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except Exception:
        return {}
    try:
        info = json.loads(raw.decode("utf-8", "replace"))
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _slot_holders(slots_dir: Path, max_slots: int) -> list[tuple[int, Path, dict | None]]:
    """Return [(index, path, holder|None)] for slots 0..max_slots inclusive.

    Slot ``max_slots`` is the leader-reserved slot; it is listed too so
    ``status`` shows it. A slot counts as held only while its OS lock is
    taken; stale JSON in a free file is reported as free.
    """
    rows: list[tuple[int, Path, dict | None]] = []
    for i in range(max_slots + 1):
        path = slots_dir / f"slot_{i}.lock"
        if not path.exists():
            rows.append((i, path, None))
            continue
        try:
            fh = open(path, "a+b")
        except Exception:
            rows.append((i, path, None))
            continue
        try:
            if _lock_nb(fh):
                _unlock(fh)
                rows.append((i, path, None))
            else:
                rows.append((i, path, _read_holder(path)))
        finally:
            try:
                fh.close()
            except Exception:
                pass
    return rows


class SlotHold:
    """An acquired heavy slot; releases the OS lock on close/exit."""

    def __init__(self, tag: str, index: int, path: Path, fh, leader: bool):
        self.tag = tag
        self.index = index
        self.path = path
        self._fh = fh
        self.leader = leader

    def close(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            try:
                fh.seek(0)
                fh.truncate(0)
                fh.flush()
            except Exception:
                pass
            _unlock(fh)
        finally:
            try:
                fh.close()
            except Exception:
                pass

    def __enter__(self) -> "SlotHold":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class heavy_slot:  # noqa: N801 - spec-mandated lowercase factory name
    """Context manager: ``with heavy_slot("tag", max_slots=2, ...):``."""

    def __init__(self, tag: str, max_slots: int = 2,
                 min_free_gb: float = 2.5, poll: float = 30,
                 timeout_h: float = 6, leader: bool = False,
                 slots_dir: Path | str | None = None, _reader=None):
        self.tag = str(tag)
        self.max_slots = int(max_slots)
        self.min_free_gb = float(min_free_gb)
        self.poll = float(poll)
        self.timeout_h = float(timeout_h)
        self.leader = bool(leader)
        self.slots_dir = Path(slots_dir) if slots_dir else DEFAULT_SLOT_DIR
        self._reader = _reader
        self._hold: SlotHold | None = None
        if self.max_slots < 1:
            raise ValueError("max_slots must be >= 1")

    def _candidates(self) -> list[int]:
        normal = list(range(self.max_slots))
        if self.leader:
            return normal + [self.max_slots]  # reserved extra slot
        return normal

    def acquire(self) -> SlotHold:
        self.slots_dir.mkdir(parents=True, exist_ok=True)
        read = self._reader or free_gb
        deadline = time.monotonic() + max(0.0, self.timeout_h) * 3600.0
        step = max(self.poll, 0.01)
        while True:
            try:
                g = float(read())
            except Exception:
                g = float("nan")
            ram_ok = (g != g) or g >= self.min_free_gb
            if not ram_ok:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"heavy_slot[{self.tag}]: RAM gate free {g:.2f} GiB "
                        f"< {self.min_free_gb:.2f} GiB after "
                        f"{self.timeout_h} h")
                print(f"[heavy_slot:{self.tag}] free RAM {g:.2f} GiB < "
                      f"{self.min_free_gb:.2f} GiB; sleeping {step:g}s",
                      flush=True)
                time.sleep(step)
                continue
            for i in self._candidates():
                path = self.slots_dir / f"slot_{i}.lock"
                try:
                    fh = open(path, "a+b")
                except Exception:
                    continue
                if _lock_nb(fh):
                    info = {
                        "tag": self.tag,
                        "pid": os.getpid(),
                        "start": datetime.datetime.now(
                            datetime.timezone.utc).isoformat(),
                        "leader": self.leader,
                    }
                    try:
                        fh.seek(0)
                        fh.truncate(0)
                        fh.write(json.dumps(info).encode("utf-8"))
                        fh.flush()
                        try:
                            os.fsync(fh.fileno())
                        except Exception:
                            pass
                    except Exception:
                        pass
                    print(f"[heavy_slot:{self.tag}] acquired slot_{i} "
                          f"(free RAM {g:.2f} GiB)", flush=True)
                    return SlotHold(self.tag, i, path, fh, self.leader)
                try:
                    fh.close()
                except Exception:
                    pass
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"heavy_slot[{self.tag}]: no free slot "
                    f"(max_slots={self.max_slots}, leader={self.leader}) "
                    f"after {self.timeout_h} h")
            time.sleep(step)

    def __enter__(self) -> SlotHold:
        self._hold = self.acquire()
        return self._hold

    def __exit__(self, *exc) -> None:
        hold, self._hold = self._hold, None
        if hold is not None:
            hold.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_status(max_slots: int = 2, slots_dir: Path | str | None = None) -> int:
    sdir = Path(slots_dir) if slots_dir else DEFAULT_SLOT_DIR
    try:
        g = float(free_gb())
    except Exception:
        g = float("nan")
    rows = _slot_holders(sdir, int(max_slots))
    for i, path, holder in rows:
        role = " (leader-reserved)" if i == int(max_slots) else ""
        if holder is None:
            print(f"slot_{i}: FREE{role}")
        else:
            print(f"slot_{i}: HELD{role} tag={holder.get('tag', '?')} "
                  f"pid={holder.get('pid', '?')} "
                  f"since={holder.get('start', '?')}")
    if g != g:
        print("free_ram_gb: unknown")
    else:
        print(f"free_ram_gb: {g:.2f}")
    return 0


def cmd_run(args: argparse.Namespace, cmd: list[str]) -> int:
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("heavy_slot run: no command given (use -- <cmd...>)",
              file=sys.stderr)
        return 2
    with heavy_slot(args.tag, max_slots=args.max_slots,
                    min_free_gb=args.min_free_gb, poll=args.poll,
                    timeout_h=args.timeout_h, leader=args.leader,
                    slots_dir=args.slots_dir):
        proc = subprocess.run(cmd)
        return int(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="RAM-gated cross-process heavy-job semaphore.")
    p.add_argument("--slots-dir", default=None,
                   help="slot dir (default artifacts/research/heavy_slots)")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="list holders and free RAM")
    st.add_argument("--max-slots", type=int, default=2)
    st.add_argument("--slots-dir", default=None)
    rn = sub.add_parser("run", help="wrap a command in a heavy slot")
    rn.add_argument("--tag", required=True)
    rn.add_argument("--leader", action="store_true",
                    help="use the reserved extra slot when workers are full")
    rn.add_argument("--max-slots", type=int, default=2)
    rn.add_argument("--min-free-gb", type=float, default=2.5)
    rn.add_argument("--poll", type=float, default=30.0)
    rn.add_argument("--timeout-h", type=float, default=6.0)
    rn.add_argument("--slots-dir", default=None)
    rn.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="command after -- ")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "status":
        return cmd_status(max_slots=args.max_slots,
                          slots_dir=args.slots_dir)
    return cmd_run(args, list(args.cmd))


if __name__ == "__main__":
    raise SystemExit(main())
