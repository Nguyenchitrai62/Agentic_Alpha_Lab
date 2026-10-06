"""Cycle-time sampler + ops summary for paper runners (read-only, never touches processes).

Sampler (state.json keeps only the LAST cycle, so poll it over time)::

    python scripts/cycle_stats.py artifacts/bot/paper artifacts/bot/paper_d17bf ... --sample 60 --every 20

Summary (actions.jsonl ops since a timestamp)::

    python scripts/cycle_stats.py --summary --since "2026-10-06T06:40:00+00:00" artifacts/bot/paper ...

Read-only: only reads state.json / actions.jsonl (+ PowerShell CIM for host RAM).
Never writes to bot dirs, never signals processes, never commits.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [
    "artifacts/bot/paper",
    "artifacts/bot/paper_d17bf",
    "artifacts/bot/paper_d17bfg2",
    "artifacts/bot/paper_g2k20",
    "artifacts/bot/paper_d13bf",
]
STAGE_KEYS = ("plan_ms", "kline_ms", "sync_ms", "decide_ms", "order_ms", "state_ms")
GAP_WARN_S = 120.0


def parse_ts(x):
    if x is None:
        return None
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def read_state(d: Path):
    """Read-only snapshot of one runner's state.json; returns dict or None fields."""
    p = d / "state.json"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {"ok": False, "mtime": None, "cycle_ms": None, "stages": None, "lock_wait_ms": None}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "mtime": mtime, "cycle_ms": None, "stages": None, "lock_wait_ms": None}
    try:
        cyc = s.get("last_cycle_ms")
        cyc = float(cyc) if cyc is not None else None
    except (TypeError, ValueError):
        cyc = None
    stages = s.get("last_cycle_stages_ms")
    stages = dict(stages) if isinstance(stages, dict) else None
    try:
        lw = s.get("last_cycle_lock_wait_ms")
        lw = float(lw) if lw is not None else None
    except (TypeError, ValueError):
        lw = None
    return {"ok": True, "mtime": mtime, "cycle_ms": cyc, "stages": stages, "lock_wait_ms": lw}


def free_mem_kb():
    """Host free RAM via PowerShell CIM (KB); None when unavailable. Read-only probe."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True, text=True, timeout=15,
        )
        txt = (out.stdout or "").strip().splitlines()
        for line in txt:
            line = line.strip()
            if line.isdigit():
                return int(line)
        return None
    except Exception:
        return None


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo))


def summarize_samples(samples, dirs):
    """Per-runner median/p95/max, dominant stage, mtime gaps; plus RAM correlation."""
    stats = {}
    for d in dirs:
        rows = [s for s in samples if s["dir"] == d]
        cycs = sorted(s["cycle_ms"] for s in rows if s["cycle_ms"] is not None)
        stage_mean = {}
        for k in STAGE_KEYS:
            vs = [float(s["stages"][k]) for s in rows
                  if s.get("stages") and isinstance(s["stages"].get(k), (int, float))]
            stage_mean[k] = sum(vs) / len(vs) if vs else 0.0
        dom = max(stage_mean, key=lambda k: stage_mean[k]) if rows else None
        gaps = [s["gap_s"] for s in rows if s.get("gap_s") is not None]
        stats[d] = {
            "n": len(rows),
            "n_cycles": len(cycs),
            "median_ms": percentile(cycs, 0.5),
            "p95_ms": percentile(cycs, 0.95),
            "max_ms": max(cycs) if cycs else None,
            "dominant_stage": dom,
            "stage_mean_ms": {k: round(v, 1) for k, v in stage_mean.items()},
            "max_gap_s": max(gaps) if gaps else None,
            "gaps_over_2min": sum(1 for g in gaps if g > GAP_WARN_S),
        }
    # RAM correlation: mean cycle_ms per tick vs free mem per tick
    ticks = sorted({s["tick"] for s in samples})
    xs, ys = [], []
    for t in ticks:
        rows = [s for s in samples if s["tick"] == t]
        mems = [s["free_mem_kb"] for s in rows if s.get("free_mem_kb") is not None]
        cyc = [s["cycle_ms"] for s in rows if s.get("cycle_ms") is not None]
        if mems and cyc:
            xs.append(sum(mems) / len(mems))
            ys.append(sum(cyc) / len(cyc))
    corr = pearson(xs, ys)
    return stats, corr


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if den == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / den


def run_sampler(dirs, n, every, no_ram=False, sleep_fn=None):
    sleep_fn = sleep_fn or time.sleep
    samples = []
    for tick in range(n):
        wall = time.time()
        mem = None if no_ram else free_mem_kb()
        for d in dirs:
            snap = read_state(Path(d))
            gap = (wall - snap["mtime"]) if snap["mtime"] else None
            samples.append({
                "tick": tick,
                "wall": datetime.fromtimestamp(wall, tz=timezone.utc).isoformat(),
                "dir": d,
                "cycle_ms": snap["cycle_ms"],
                "stages": snap["stages"],
                "lock_wait_ms": snap["lock_wait_ms"],
                "mtime": (datetime.fromtimestamp(snap["mtime"], tz=timezone.utc).isoformat()
                          if snap["mtime"] else None),
                "gap_s": round(gap, 1) if gap is not None else None,
                "free_mem_kb": mem,
            })
        if tick < n - 1:
            sleep_fn(every)
    return samples


def summarize_actions(dirs, since):
    """Count slow_cycle / lock_wait / rate_limit / error ops in actions.jsonl with t >= since."""
    out = {}
    for d in dirs:
        p = Path(d) / "actions.jsonl"
        rec = {"slow_cycle": 0, "lock_wait": 0, "rate_limit": 0, "errors": 0, "scanned": 0}
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            out[d] = {"error": "missing actions.jsonl", **rec}
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = parse_ts(r.get("t"))
            if t is None or t < since:
                continue
            rec["scanned"] += 1
            op = r.get("op")
            if op == "slow_cycle":
                rec["slow_cycle"] += 1
            elif op == "lock_wait":
                rec["lock_wait"] += 1
            if op in ("error", "cycle_error"):
                rec["errors"] += 1
                note = str(r.get("note") or r.get("call") or "")
                if "10006" in note or "rate limit" in note.lower():
                    rec["rate_limit"] += 1
            elif op == "rate_limit":
                rec["rate_limit"] += 1
        out[d] = rec
    return out


def fmt_sampler(stats, corr):
    lines = []
    for d, s in stats.items():
        med = "n/a" if s["median_ms"] is None else f"{s['median_ms']:.0f}"
        p95 = "n/a" if s["p95_ms"] is None else f"{s['p95_ms']:.0f}"
        mx = "n/a" if s["max_ms"] is None else f"{s['max_ms']:.0f}"
        gap = "n/a" if s["max_gap_s"] is None else f"{s['max_gap_s']:.0f}s"
        lines.append(f"{d}: med/p95/max={med}/{p95}/{mx}ms dom={s['dominant_stage']} "
                     f"max_gap={gap} gaps>2min={s['gaps_over_2min']}")
    if corr is None:
        lines.append("RAM: no correlation assessable (constant RAM or <3 ticks)")
    else:
        verdict = "correlates (|r|>=0.5)" if abs(corr) >= 0.5 else "no correlation (|r|<0.5)"
        lines.append(f"RAM free vs mean cycle: r={corr:+.2f} -> {verdict}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only cycle-time sampler + ops summary.")
    ap.add_argument("dirs", nargs="*", default=DEFAULT_DIRS,
                    help="bot state dirs (default: five paper runners)")
    ap.add_argument("--sample", type=int, default=0, help="sampler ticks N (0 = no sampling)")
    ap.add_argument("--every", type=float, default=20.0, help="seconds between sampler ticks")
    ap.add_argument("--summary", action="store_true", help="summarize actions.jsonl ops")
    ap.add_argument("--since", default=None, help="ISO timestamp lower bound for --summary")
    ap.add_argument("--no-ram", action="store_true", help="skip PowerShell CIM RAM probe")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    a = ap.parse_args(argv)
    dirs = [str(Path(x)) for x in a.dirs]
    rc = 0
    if a.summary:
        since = parse_ts(a.since) if a.since else datetime(1970, 1, 1, tzinfo=timezone.utc)
        if since is None:
            print(f"bad --since {a.since!r}", file=sys.stderr)
            return 2
        res = summarize_actions(dirs, since)
        if a.json:
            print(json.dumps({"since": since.isoformat(), "dirs": res}, indent=1))
        else:
            for d, r in res.items():
                print(f"{d}: slow_cycle={r['slow_cycle']} lock_wait={r['lock_wait']} "
                      f"rate_limit={r['rate_limit']} errors={r['errors']} (n={r['scanned']})")
    if a.sample and a.sample > 0:
        samples = run_sampler(dirs, a.sample, a.every, no_ram=a.no_ram)
        stats, corr = summarize_samples(samples, dirs)
        if a.json:
            print(json.dumps({"samples": samples, "stats": stats, "ram_corr": corr}, indent=1, default=str))
        else:
            print(fmt_sampler(stats, corr))
        if any((s["max_gap_s"] or 0) > GAP_WARN_S for s in stats.values()):
            rc = 1
    if not a.summary and not (a.sample and a.sample > 0):
        ap.error("nothing to do: pass --sample N and/or --summary")
    return rc


if __name__ == "__main__":
    sys.exit(main())
