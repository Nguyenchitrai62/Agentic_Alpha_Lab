"""OpenCode worker supervisor: keeps a queue of assignments running, restarts hung workers, reports completions.

usage: python scripts/oc_supervisor.py [--max N] [--minutes M]
Queue file artifacts/research/opencode_background/queue.json: [{"tag": ..., "assignment": "docs/opencode/....md"}, ...]
(append new tasks there at any time). State in queue_state.json; human-readable status in supervisor_status.md.
Rules: at most --max workers at once (launch stagger 20 s); a worker whose events.jsonl is still empty 5 minutes after launch, or
that wrote no event for 120 minutes, is killed and relaunched (at most 3 attempts). A task is DONE when its stderr log has "exit="
and its opencode process is gone. The supervisor exits (printing the transitions) as soon as at least one task finished or failed,
or after --minutes, so the caller is notified and can re-arm it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "artifacts/research/opencode_background"
QUEUE, STATE, STATUS = D / "queue.json", D / "queue_state.json", D / "supervisor_status.md"
BASH = "C:/Program Files/Git/bin/bash.exe" if Path("C:/Program Files/Git/bin/bash.exe").exists() else "bash"
EMPTY_MIN, STALL_MIN, MAX_TRIES, STAGGER_S = 5.0, 120.0, 3, 20


def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def opencode_procs() -> dict[str, int]:
    """title -> pid of running opencode.exe workers."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='opencode.exe'\" | ForEach-Object { "
          "$m=[regex]::Match($_.CommandLine,'--title\\s+\"?([^\" ]+)'); $_.ProcessId.ToString()+' '+$m.Groups[1].Value }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return {}
    res = {}
    for line in out.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2 and parts[1]:
            res[parts[1]] = int(parts[0])
    return res


def kill(pid: int):
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                   capture_output=True, timeout=60)


def launch(tag: str, assignment: str):
    env = {**os.environ, "COMMON": "docs/opencode/OPENCODE_VF_COMMON.md"}
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: survives the supervisor
    subprocess.Popen([BASH, "scripts/opencode_dispatch.sh", tag, assignment], cwd=str(ROOT), env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def run_files(tag: str):
    cur = D / f"{tag}.current"
    if not cur.exists():
        return None, None
    run = cur.read_text().strip()
    return D / f"{run}.events.jsonl", D / f"{run}.stderr.log"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--minutes", type=float, default=110)
    a = ap.parse_args()
    t_end = time.time() + a.minutes * 60
    transitions = []
    while True:
        queue = load(QUEUE, [])
        state = load(STATE, {})
        procs = opencode_procs()
        now = time.time()
        running = 0
        for task in queue:
            tag = task["tag"]
            st = state.setdefault(tag, {"status": "pending", "tries": 0})
            if st["status"] in ("done", "failed"):
                continue
            ev, er = run_files(tag)
            alive = tag in procs
            if st["status"] == "running":
                size = ev.stat().st_size if ev and ev.exists() else 0
                last = ev.stat().st_mtime if ev and ev.exists() else st["launched"]
                age_min = (now - st["launched"]) / 60
                finished = er is not None and er.exists() and "exit=" in er.read_text(errors="replace") and not alive
                if finished or (not alive and age_min > 2):
                    if size > 0:
                        st["status"] = "done"
                        transitions.append(f"DONE {tag} (events {size} B)")
                    elif st["tries"] < MAX_TRIES:
                        st["status"] = "pending"
                        transitions.append(f"RETRY {tag} (ended with empty events)")
                    else:
                        st["status"] = "failed"
                        transitions.append(f"FAILED {tag} (empty events after {st['tries']} tries)")
                    continue
                hung = (size == 0 and age_min > EMPTY_MIN) or (size > 0 and (now - last) / 60 > STALL_MIN)
                if hung:
                    if alive:
                        kill(procs[tag])
                    if st["tries"] < MAX_TRIES:
                        st["status"] = "pending"
                        transitions.append(f"RESTART {tag} (hung: events {size} B, age {age_min:.0f} min)")
                    else:
                        st["status"] = "failed"
                        transitions.append(f"FAILED {tag} (hung after {st['tries']} tries)")
                    continue
                running += 1
        for task in queue:
            tag = task["tag"]
            st = state[tag]
            if st["status"] == "pending" and running < a.max and tag not in procs:
                launch(tag, task["assignment"])
                st.update(status="running", tries=st["tries"] + 1, launched=time.time())
                running += 1
                time.sleep(STAGGER_S)
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
        rows = [f"| {t['tag']} | {state[t['tag']]['status']} | {state[t['tag']]['tries']} |" for t in queue]
        STATUS.write_text("| tag | status | tries |\n|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
        done_now = [x for x in transitions if x.startswith(("DONE", "FAILED"))]
        if done_now or time.time() > t_end:
            break
        time.sleep(60)
    print("\n".join(transitions) if transitions else "no transitions")
    summary = {s: sum(1 for v in load(STATE, {}).values() if v["status"] == s) for s in ("pending", "running", "done", "failed")}
    print("status:", summary)


if __name__ == "__main__":
    main()
