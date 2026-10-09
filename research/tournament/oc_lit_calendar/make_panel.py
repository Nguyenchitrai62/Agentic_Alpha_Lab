"""oc_lit_calendar panel builder (LIGHT: 4h opens only, no 1m, one process).

PLAN-fixed calendar flags for H1 (TOM), H2 (overnight), H7 (halving clock).
Per-(T,sym) rows on the v154 4h grid; flags are global (same across syms).
The engine (run_engine.py) joins these flags onto its STANDARD book index by T
and applies side-conditional multipliers after the bear filter (v426 order).

Grid: artifacts/research/engine_real/opens_v154.parquet index, restricted to
[2021-09-24, 2026-09-24). Columns: T, sym + tom_in, on_in (21-23 overlap),
onwide_in (21-01 overlap), halv_in ([400,900]), halv525_in ([525,900]).

  .venv/Scripts/python.exe research/tournament/oc_lit_calendar/make_panel.py
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OPENS = ROOT / "artifacts/research/engine_real/opens_v154.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
GRID_LO = pd.Timestamp("2021-09-24", tz="UTC")
GRID_HI = pd.Timestamp("2026-09-24", tz="UTC")  # exclusive
HALVINGS = [_dt.date(2012, 11, 28), _dt.date(2016, 7, 9),
            _dt.date(2020, 5, 11), _dt.date(2024, 4, 19)]


def tom_days(year: int, month: int) -> set[_dt.date]:
    """TOM UTC dates for one month: {L-1, L, 1st, 2nd, 3rd} (PLAN-fixed)."""
    import calendar as _cal
    last = _cal.monthrange(year, month)[1]
    out = {_dt.date(year, month, last - 1), _dt.date(year, month, last),
           _dt.date(year, month, 1), _dt.date(year, month, 2),
           _dt.date(year, month, 3)}
    return out


def build_tom_set(lo: _dt.date, hi: _dt.date) -> set[_dt.date]:
    """All TOM dates covering [lo, hi] (plus neighbour months for safety)."""
    s: set[_dt.date] = set()
    y, m = lo.year, lo.month
    # walk months from one before lo to one after hi
    cur = _dt.date(y, m, 1)
    if m == 1:
        cur = _dt.date(y - 1, 12, 1)
    else:
        cur = _dt.date(y, m - 1, 1)
    while cur <= hi:
        s |= tom_days(cur.year, cur.month)
        if cur.month == 12:
            cur = _dt.date(cur.year + 1, 1, 1)
        else:
            cur = _dt.date(cur.year, cur.month + 1, 1)
    return s


def days_since_halving(d: _dt.date) -> int:
    """D(T) = (date - last halving <= date).days (PLAN-fixed)."""
    past = [h for h in HALVINGS if h <= d]
    assert past, d
    return (d - max(past)).days


def flags_for_grid(grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Pure calendar flags per bar start T (uses only T itself)."""
    dates = [t.date() for t in grid]
    tom_set = build_tom_set(min(dates), max(dates))
    tom_in = np.array([d in tom_set for d in dates], dtype=bool)
    hours = np.asarray(grid.hour)
    on_in = hours == 20  # [T,T+4h) overlaps [21,23)
    onwide_in = (hours == 20) | (hours == 0)  # overlaps [21,01)
    D = np.array([days_since_halving(d) for d in dates], dtype=np.int64)
    halv_in = (D >= 400) & (D <= 900)
    halv525_in = (D >= 525) & (D <= 900)
    return pd.DataFrame({"tom_in": tom_in, "on_in": on_in,
                         "onwide_in": onwide_in, "halv_in": halv_in,
                         "halv525_in": halv525_in, "D": D}, index=grid)


def main() -> None:
    opens = pd.read_parquet(OPENS)
    grid = pd.to_datetime(opens.index, utc=True).sort_values()
    grid = grid[(grid >= GRID_LO) & (grid < GRID_HI)]
    print(f"grid {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)
    fl = flags_for_grid(grid)
    n = len(grid)
    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), n),
        "tom_in": np.repeat(fl["tom_in"].to_numpy(), len(SYMS)),
        "on_in": np.repeat(fl["on_in"].to_numpy(), len(SYMS)),
        "onwide_in": np.repeat(fl["onwide_in"].to_numpy(), len(SYMS)),
        "halv_in": np.repeat(fl["halv_in"].to_numpy(), len(SYMS)),
        "halv525_in": np.repeat(fl["halv525_in"].to_numpy(), len(SYMS)),
        "D": np.repeat(fl["D"].to_numpy(), len(SYMS)),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")
    info = {
        "grid_start": str(grid.min()), "grid_end": str(grid.max()),
        "n_bars": int(n), "n_panel": int(len(panel)),
        "tom_share": round(float(fl["tom_in"].mean()), 6),
        "on_share": round(float(fl["on_in"].mean()), 6),
        "onwide_share": round(float(fl["onwide_in"].mean()), 6),
        "halv_share": round(float(fl["halv_in"].mean()), 6),
        "halv525_share": round(float(fl["halv525_in"].mean()), 6),
        "halvings": [str(h) for h in HALVINGS],
    }
    (HERE / "tmp" / "panel_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1), flush=True)


if __name__ == "__main__":
    main()
