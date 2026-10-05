"""Tournament extension (leader 2026-10-05, the former hidden year is research data after v395): rebuild fills_U up to 2026-09-24.

Exactly the fills block of research/diagnostics/phase_agents/build_tables.py (v294 / v293 standalone dip-rung replica, rungs U = 2.0..5.0,
v293.MAJORS + v294.universe(), costs eu.MAKER / eu.TAKER / eu.FUND_LONG of v221's engine_user), only END = 2026-09-24 (last minute loaded
2026-09-23 23:59; the raw files end there). Output: research/tournament/ext/fills_U_ext.parquet + fills_check.json (overlap check vs fills_U).
  python research/tournament/ext/build_fills_ext.py
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE = Path(__file__).parent
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
END = pd.Timestamp("2026-09-24", tz="UTC")
OLD = ROOT / "research/diagnostics/phase_agents/fills_U.parquet"
CUT = pd.Timestamp("2025-09-17", tz="UTC")


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main():
    t0 = time.time()
    v294 = L("v294_pa", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    eu = L("v221_pa", RD / "v221/v221_grid_hysteresis.py").eu
    v293.RUNGS = U
    v293.END = END
    print("START", v293.START, "END", v293.END, "costs", eu.MAKER, eu.TAKER, eu.FUND_LONG, flush=True)
    fp = HERE / "fills_U_ext.parquet"
    btc = v293.Asset("BTCUSDT")
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = btc if s == "BTCUSDT" else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            parts.append(d.assign(sym=s))
        print("fills", s, len(d), "t_fill max", d.t_fill.max() if len(d) else None, f"{time.time() - t0:.0f}s", flush=True)
        del A
    del btc
    allf = pd.concat(parts, ignore_index=True)
    allf.to_parquet(fp)

    # overlap check vs the existing fills_U (rows with t_fill < CUT)
    old = pd.read_parquet(OLD)
    key = ["sym", "j", "r"]
    a, b = old[old.t_fill < CUT], allf[allf.t_fill < CUT]
    mg = a.merge(b, on=key, how="outer", suffixes=("_old", ""), indicator=True)
    chk = dict(rows_old=len(a), rows_new=len(b), only_old=int((mg._merge == "left_only").sum()), only_new=int((mg._merge == "right_only").sum()))
    both = mg[mg._merge == "both"]
    diff = {}
    for c in ["f", "y0.5", "y1.0", "y1.5"] + [f"x{q}" for q in range(7)]:
        x, y = both[c + "_old"].to_numpy(float), both[c].to_numpy(float)
        nan_mismatch = int((np.isnan(x) != np.isnan(y)).sum())
        diff[c] = dict(max_abs=float(np.nanmax(np.abs(x - y))) if len(x) else 0.0, nan_mismatch=nan_mismatch)
    for c in ("t_fill", "t_exit"):
        diff[c] = dict(mismatch=int((both[c + "_old"] != both[c]).sum()))
    chk["diff"] = diff
    chk["same_order_exact"] = bool(len(a) == len(b) and a.reset_index(drop=True).equals(b.reset_index(drop=True)))
    # whole old file (incl. its last week) for information
    mg2 = old.merge(allf, on=key, how="left", suffixes=("_old", ""), indicator=True)
    both2 = mg2[mg2._merge == "both"]
    chk["full_old_rows"], chk["full_old_rows_missing_in_new"] = len(old), int((mg2._merge == "left_only").sum())
    chk["full_old_y_maxdiff"] = float(np.nanmax(np.abs(both2[["y0.5", "y1.0", "y1.5"]].to_numpy(float) - both2[["y0.5_old", "y1.0_old", "y1.5_old"]].to_numpy(float))))
    chk["full_old_x_maxdiff"] = float(np.nanmax(np.abs(both2[[f"x{q}" for q in range(7)]].to_numpy(float) - both2[[f"x{q}_old" for q in range(7)]].to_numpy(float))))
    chk["full_old_texit_mismatch"] = int((both2.t_exit_old != both2.t_exit).sum())
    allf["year"] = allf.t_fill.dt.year
    chk["rows_total"] = len(allf)
    chk["t_fill_max"] = str(allf.t_fill.max())
    chk["rows_per_sym_year"] = {s: {str(k): int(v) for k, v in g.year.value_counts().sort_index().items()} for s, g in allf.groupby("sym")}
    chk["runtime_s"] = round(time.time() - t0)
    (HERE / "fills_check.json").write_text(json.dumps(chk, indent=1))
    print(json.dumps({k: v for k, v in chk.items() if k != "rows_per_sym_year"}, indent=1))


if __name__ == "__main__":
    main()
