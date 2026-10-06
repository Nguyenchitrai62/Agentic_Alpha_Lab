"""OpenCode watchdog: kills hung workers so their own background task ends and the leader re-dispatches them.

usage: python scripts/oc_watchdog.py [--minutes 110]
Every 2 minutes, for every running opencode.exe worker (title = tag): its run is artifacts/research/opencode_background/<tag>.current.
Hung = events.jsonl still empty 6 minutes after the run started, or no new event for 150 minutes. A hung worker is killed and logged
to artifacts/research/opencode_background/watchdog.log. The watchdog exits after the first kill (so the leader is notified) or after
--minutes; it never launches workers (each worker is the leader's own visible background task).
"""
from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "artifacts/research/opencode_background"
EMPTY_MIN, STALL_MIN = 6.0, 150.0


def procs() -> dict[str, int]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='opencode.exe'\" | ForEach-Object { "
          "$m=[regex]::Match($_.CommandLine,'--title\\s+\"?([^\" ]+)'); $_.ProcessId.ToString()+' '+$m.Groups[1].Value }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
    res = {}
    for line in out.splitlines():
        p = line.strip().split(" ", 1)
        if len(p) == 2 and p[1]:
            res[p[1]] = int(p[0])
    return res


def run_start(run: str) -> float:
    try:  # run name = <tag>_<YYYYmmddTHHMMSSZ>
        return datetime.strptime(run.rsplit("_", 1)[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return time.time()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=110)
    a = ap.parse_args()
    t_end = time.time() + a.minutes * 60
    killed = []
    while time.time() < t_end and not killed:
        now = time.time()
        for tag, pid in procs().items():
            cur = D / f"{tag}.current"
            if not cur.exists():
                continue
            run = cur.read_text().strip()
            ev = D / f"{run}.events.jsonl"
            size = ev.stat().st_size if ev.exists() else 0
            age = (now - run_start(run)) / 60
            idle = (now - ev.stat().st_mtime) / 60 if ev.exists() and size else age
            if (size == 0 and age > EMPTY_MIN) or (size > 0 and idle > STALL_MIN):
                subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                               capture_output=True, timeout=60)
                msg = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} killed {tag} pid {pid} (events {size} B, age {age:.0f} min, idle {idle:.0f} min)"
                killed.append(msg)
                with open(D / "watchdog.log", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
        if not killed:
            time.sleep(120)
    print("\n".join(killed) if killed else "no hung workers")


if __name__ == "__main__":
    main()
