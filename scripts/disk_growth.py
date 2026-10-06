"""Disk-growth report for long-running artifacts (READ-ONLY).

Never writes to bot/state dirs, never signals processes, no credentials, no orders.
Only stats files and reads first/last JSONL timestamps + daily parquet names.

Usage:
    python scripts/disk_growth.py
    python scripts/disk_growth.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BOT_DIRS = [
    "artifacts/bot/paper",
    "artifacts/bot/paper_carry",
    "artifacts/bot/paper_d13bf",
    "artifacts/bot/paper_d17bf",
    "artifacts/bot/paper_d17bfg2",
    "artifacts/bot/paper_d17bfg2c",
    "artifacts/bot/paper_g2k20",
    "artifacts/bot/paper_g2k20c",
    "artifacts/bot/dry",
]

MB = 1024 * 1024


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


def stat_path(p: Path):
    try:
        st = p.stat()
        return {"exists": True, "size": st.st_size, "mtime": st.st_mtime}
    except OSError:
        return {"exists": False, "size": 0, "mtime": None}


def dir_size(p: Path) -> int:
    total = 0
    try:
        for dp, _, fns in os.walk(p):
            for fn in fns:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def jsonl_bytes_per_day(path: Path, keys=("t", "decision_bar_close", "generated_at")):
    """Estimate bytes/day from file size spread over first->last record timestamp."""
    try:
        size = path.stat().st_size
    except OSError:
        return {"n": 0, "span_h": None, "bytes_per_day": None}
    first_ts, last_ts, n = None, None, 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first_line, last_line = None, None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n += 1
                if first_line is None:
                    first_line = line
                last_line = line
        for ln in (first_line, last_line):
            pass
        ts = []
        for ln in ([first_line, last_line] if first_line else []):
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            for k in keys:
                t = parse_ts(o.get(k))
                if t is not None:
                    ts.append(t)
                    break
        if len(ts) == 2:
            first_ts, last_ts = ts[0], ts[1]
    except OSError:
        return {"n": n, "span_h": None, "bytes_per_day": None}
    if first_ts is None or last_ts is None:
        return {"n": n, "span_h": None, "bytes_per_day": None}
    span_s = (last_ts - first_ts).total_seconds()
    if span_s <= 0:
        return {"n": n, "span_h": 0.0, "bytes_per_day": None}
    return {"n": n, "span_h": span_s / 3600.0,
            "bytes_per_day": size / span_s * 86400.0}


def parquet_daily_totals(pattern: str):
    """Group parquet sizes by YYYY-MM-DD filename; read-only."""
    totals: dict[str, int] = {}
    for p in glob.glob(str(ROOT / pattern)):
        day = Path(p).stem  # YYYY-MM-DD
        try:
            totals[day] = totals.get(day, 0) + os.path.getsize(p)
        except OSError:
            pass
    return totals


def project(size_now: int, bytes_per_day: float | None, days: int):
    if bytes_per_day is None:
        return None
    return size_now + bytes_per_day * days


def is_whole_rewrite_json(path: Path) -> bool:
    """Heuristic: single JSON object (dict), not JSONL -> rewritten whole each cycle."""
    try:
        if path.stat().st_size > 5 * MB:
            return False
        o = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(o, dict)
    except (OSError, ValueError):
        return False


def collect() -> dict:
    items = []
    for d in BOT_DIRS:
        base = ROOT / d
        for fn in ("state.json", "exchange.json", "actions.jsonl",
                   "stdout.log", "runner.log"):
            p = base / fn
            st = stat_path(p)
            rate = None
            if fn in ("actions.jsonl", "stdout.log", "runner.log") and st["exists"]:
                rate = jsonl_bytes_per_day(p)
            items.append({"path": f"{d}/{fn}", **st,
                          "bytes_per_day": (rate or {}).get("bytes_per_day"),
                          "span_h": (rate or {}).get("span_h"),
                          "n_lines": (rate or {}).get("n"),
                          "whole_rewrite": is_whole_rewrite_json(p) if st["exists"] and fn in ("state.json", "exchange.json") else False})
        for pat in (f"{d}/_bak_*", f"{d}/state.json.bak_*"):
            for gp in glob.glob(str(ROOT / pat)):
                rel = os.path.relpath(gp, ROOT).replace(os.sep, "/")
                if os.path.isfile(gp):
                    st2 = stat_path(Path(gp))
                else:
                    st2 = {"exists": True, "size": dir_size(Path(gp)), "mtime": None}
                items.append({"path": rel, **st2,
                              "bytes_per_day": None, "span_h": None,
                              "n_lines": None, "whole_rewrite": False})
    extra_dirs = {
        "artifacts/bot/_kline_cache": dir_size(ROOT / "artifacts/bot/_kline_cache"),
        "artifacts/bot/_retired": dir_size(ROOT / "artifacts/bot/_retired"),
        "artifacts/backend_logs": dir_size(ROOT / "artifacts/backend_logs"),
        "artifacts/research/advisor_shadow": dir_size(ROOT / "artifacts/research/advisor_shadow"),
        "data/raw/liquidations_live": dir_size(ROOT / "data/raw/liquidations_live"),
        "data/raw/topbook_live": dir_size(ROOT / "data/raw/topbook_live"),
    }
    for k, v in extra_dirs.items():
        items.append({"path": k, "exists": True, "size": v, "mtime": None,
                      "bytes_per_day": None, "span_h": None, "n_lines": None,
                      "whole_rewrite": False})
    for fn in ("artifacts/web/app.db", "artifacts/web/app.db-wal",
               "artifacts/web/app.db-shm", "artifacts/web/backend.log",
               "artifacts/web/cloudflared_api.log",
               "artifacts/backend_logs/uvicorn_local.log",
               "artifacts/research/advisor_shadow/shadow.jsonl",
               "artifacts/research/advisor_shadow/loop.log"):
        p = ROOT / fn
        st = stat_path(p)
        rate = jsonl_bytes_per_day(p) if st["exists"] and fn.endswith((".jsonl", ".log")) else None
        items.append({"path": fn, **st,
                      "bytes_per_day": (rate or {}).get("bytes_per_day"),
                      "span_h": (rate or {}).get("span_h"),
                      "n_lines": (rate or {}).get("n"),
                      "whole_rewrite": False})
    topbook = parquet_daily_totals("data/raw/topbook_live/*/*/*.parquet")
    liq = parquet_daily_totals("data/raw/liquidations_live/*/*/*.parquet")
    liq2 = parquet_daily_totals("data/raw/liquidations_live/_coverage/*/*.parquet")
    for k, v in liq2.items():
        liq[k] = liq.get(k, 0) + v
    try:
        du = shutil.disk_usage(str(ROOT))
        disk = {"total": du.total, "used": du.used, "free": du.free}
    except OSError:
        disk = {"total": None, "used": None, "free": None}

    def proj_for(path_prefix, size, bpd):
        return {str(d): project(size, bpd, d) for d in (30, 180, 365)}

    summary = []
    for it in items:
        bpd = it.get("bytes_per_day")
        if bpd is not None:
            it["projection"] = proj_for(it["path"], it["size"], bpd)
        else:
            it["projection"] = None
        summary.append(it)
    return {"items": summary, "disk": disk,
            "topbook_daily": topbook, "liquidations_daily": liq}


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only disk growth report.")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = ap.parse_args()
    data = collect()
    if args.json:
        print(json.dumps(data, indent=1, default=str))
        return 0
    print(f"{'path':55s} {'size_MB':>9s} {'MB/day':>9s} {'proj30_MB':>10s} {'proj365_MB':>11s}  note")
    for it in data["items"]:
        if it["size"] == 0 and not it["exists"]:
            continue
        bpd = it.get("bytes_per_day")
        proj = it.get("projection") or {}
        note = ""
        if it.get("whole_rewrite"):
            note = "WHOLE-REWRITE each cycle"
        elif it["path"].endswith((".jsonl", ".log")) and bpd:
            note = f"append ~{it.get('n_lines')} lines/{(it.get('span_h') or 0):.1f}h"
        print(f"{it['path']:55s} {it['size']/MB:9.3f} "
              f"{(bpd/MB if bpd else 0):9.3f} "
              f"{((proj.get('30') or 0)/MB if proj.get('30') else 0):10.1f} "
              f"{((proj.get('365') or 0)/MB if proj.get('365') else 0):11.1f}  {note}")
    d = data["disk"]
    print(f"disk total={d['total']/1e9:.1f}GB used={d['used']/1e9:.1f}GB free={d['free']/1e9:.1f}GB")
    print(f"topbook parquet MB/day: {data['topbook_daily']}")
    print(f"liquidations parquet MB/day: {data['liquidations_daily']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
