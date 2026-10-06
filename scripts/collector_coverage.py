"""Read-only coverage report for the live liquidation + top-of-book collector.

Reads ONLY (no network, no writes, no credentials, no orders):
  data/raw/liquidations_live/{venue}/{SYMBOL}/YYYY-MM-DD.parquet
  data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet
  data/raw/topbook_live/{venue}/{SYMBOL}/YYYY-MM-DD.parquet

Usage:
  .venv/Scripts/python.exe scripts/collector_coverage.py [--gap-min 5]

Prints: per-venue/per-stream hours covered vs expected, every gap > N min
with start/end UTC, events per hour by coin, file sizes and growth.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIQ = ROOT / "data" / "raw" / "liquidations_live"
TOP = ROOT / "data" / "raw" / "topbook_live"
VENUES = ("binance", "bybit")
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def ms_to_utc(ms: int) -> str:
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).isoformat()


def find_gaps(intervals: list[tuple[int, int]], gap_ms: int) -> list[dict]:
    """Sorted (start, end) coverage/sample points -> gaps strictly greater than gap_ms."""
    iv = sorted(intervals)
    out: list[dict] = []
    for (_, e), (s2, _) in zip(iv, iv[1:]):
        if s2 - e > gap_ms:
            out.append({"gap_start_ms": e, "gap_end_ms": s2, "gap_s": (s2 - e) / 1000})
    return out


def read_ms_column(files: list[Path], column: str) -> list[int]:
    import pandas as pd

    vals: list[int] = []
    for f in files:
        try:
            d = pd.read_parquet(f, columns=[column])
        except Exception:
            continue
        vals.extend(int(x) for x in d[column].dropna().tolist())
    return sorted(vals)


def summarize() -> dict:
    import pandas as pd

    gap_ms = ARGS_GAP_MS
    venues: dict[str, dict] = {}
    for venue in VENUES:
        cov_files = sorted((LIQ / "_coverage" / venue).glob("*.parquet"))
        rows: list[tuple[int, int]] = []
        for f in cov_files:
            try:
                d = pd.read_parquet(f, columns=["venue", "start_ms", "end_ms"])
            except Exception:
                continue
            for r in d.to_dict("records"):
                if str(r.get("venue")) != venue:
                    continue
                rows.append((int(r["start_ms"]), int(r["end_ms"])))
        rows.sort()
        covered_h = sum(e - s for s, e in rows) / 3.6e6 if rows else 0.0
        if rows:
            span_h = (rows[-1][1] - rows[0][0]) / 3.6e6
            span = (ms_to_utc(rows[0][0]), ms_to_utc(rows[-1][1]))
        else:
            span_h, span = 0.0, (None, None)
        gaps = [{"gap_start_utc": ms_to_utc(g["gap_start_ms"]),
                 "gap_end_utc": ms_to_utc(g["gap_end_ms"]),
                 "gap_s": round(g["gap_s"], 1)} for g in find_gaps(rows, gap_ms)]
        liq_rows = sum(len(read_ms_column([f], "event_time"))
                       for s in SYMBOLS for f in (LIQ / venue / s).glob("*.parquet"))
        tb_vals: list[int] = []
        for s in SYMBOLS:
            tb_vals.extend(read_ms_column(sorted((TOP / venue / s).glob("*.parquet")), "sample_time"))
        tb_vals.sort()
        tb_gaps = [{"gap_start_utc": ms_to_utc(a), "gap_end_utc": ms_to_utc(b),
                    "gap_s": round((b - a) / 1000, 1)}
                   for a, b in zip(tb_vals, tb_vals[1:]) if b - a > gap_ms]
        venues[venue] = {
            "covered_h": round(covered_h, 2), "span_h": round(span_h, 2),
            "span_utc": span, "liq_gaps": gaps, "liq_rows": liq_rows,
            "topbook_rows": len(tb_vals),
            "topbook_last_utc": ms_to_utc(tb_vals[-1]) if tb_vals else None,
            "topbook_gaps": tb_gaps,
        }
    by_coin: dict[str, dict] = {}
    for s in SYMBOLS:
        n = 0
        for venue in VENUES:
            n += sum(len(read_ms_column([f], "event_time"))
                     for f in (LIQ / venue / s).glob("*.parquet"))
        by_coin[s] = {"rows": n}
    sizes: dict[str, dict] = {}
    for name, base in (("liquidations", LIQ), ("topbook", TOP)):
        files = [p for p in base.rglob("*.parquet")]
        sizes[name] = {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}
    return {"venues": venues, "by_coin": by_coin, "sizes": sizes, "gap_min": gap_ms / 60000}


ARGS_GAP_MS = 5 * 60 * 1000


def main() -> int:
    global ARGS_GAP_MS
    ap = argparse.ArgumentParser(description="Read-only collector coverage report.")
    ap.add_argument("--gap-min", type=float, default=5.0)
    args = ap.parse_args()
    ARGS_GAP_MS = int(args.gap_min * 60 * 1000)
    rep = summarize()
    for venue, v in rep["venues"].items():
        pct = (100 * v["covered_h"] / v["span_h"]) if v["span_h"] else 0.0
        print(f"{venue}: covered {v['covered_h']}h / span {v['span_h']}h ({pct:.1f}%) "
              f"span {v['span_utc'][0]} -> {v['span_utc'][1]}")
        print(f"  liq rows={v['liq_rows']} gaps>{rep['gap_min']:.0f}m: {len(v['liq_gaps'])}")
        for g in v["liq_gaps"]:
            print(f"    GAP {g['gap_start_utc']} -> {g['gap_end_utc']} ({g['gap_s']:.0f}s)")
        print(f"  topbook rows={v['topbook_rows']} last={v['topbook_last_utc']} "
              f"gaps>{rep['gap_min']:.0f}m: {len(v['topbook_gaps'])}")
    cov = sum(v["covered_h"] for v in rep["venues"].values()) / max(len(rep["venues"]), 1)
    print("events per covered hour by coin (both venues):")
    for s, c in rep["by_coin"].items():
        print(f"  {s}: {c['rows']} rows = {c['rows'] / cov:.1f}/h" if cov else f"  {s}: {c['rows']} rows")
    for name, s in rep["sizes"].items():
        print(f"{name}: {s['files']} files, {s['bytes'] / 1024:.1f} KB total "
              f"({s['bytes'] / 1024 / 3:.1f} KB/day over ~3d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
