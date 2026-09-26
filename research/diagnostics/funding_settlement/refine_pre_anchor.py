"""Refinement of the funding-settlement effects - PRE-ANCHOR DATA ONLY (< 2021-09-24), descriptive.

H1 (post-settlement rebound): condition = rate settled at S >= 0.0003 (published at S). Long from open(S+1m) to
close(S+59m); taker 0.0005 + 2 bps slippage each side -> net. Also the same with the PREVIOUS settled rate as condition.
H2 (pre-settlement squeeze): condition = PREVIOUS settled rate (S-8h, known) < -0.0001. Long from open(S-60m) to
close(S-1m) (exits before the settlement), same costs.
Per calendar half-year and per asset, gross and net bps with t-stats.

  python research/diagnostics/funding_settlement/refine_pre_anchor.py
"""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("es", HERE / "event_study_pre_anchor.py")
es = importlib.util.module_from_spec(spec)
spec.loader.exec_module(es)
COST = 2 * (0.0005 + 0.0002)


def st(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 8:
        return {"n": int(len(x))}
    return {"gross_bps": round(1e4 * x.mean(), 1), "net_bps": round(1e4 * (x.mean() - COST), 1),
            "t_gross": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2), "n": int(len(x))}


def main():
    rows = []
    for s in es.SYMS:
        m = es.load_1m(s)
        f = pd.read_parquet(es.ROOT / f"data/raw/xs_universe_20260924/{s}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("min")
        rate = pd.Series(f["fundingRate"].to_numpy(float), index=ft).groupby(level=0).last().sort_index()
        prev = rate.shift(1)
        rate = rate[(rate.index < es.CUT - pd.Timedelta(hours=5)) & (rate.index >= m.index[0] + pd.Timedelta(hours=2))]
        prev = prev.reindex(rate.index)
        o, c = m["open"], m["close"]
        S = rate.index
        h1 = c.reindex(S + pd.Timedelta(minutes=59)).to_numpy(float) / o.reindex(S + pd.Timedelta(minutes=1)).to_numpy(float) - 1
        h2 = c.reindex(S - pd.Timedelta(minutes=1)).to_numpy(float) / o.reindex(S - pd.Timedelta(minutes=60)).to_numpy(float) - 1
        rows.append(pd.DataFrame({"sym": s, "S": S, "rate": rate.to_numpy(), "prev": prev.to_numpy(), "h1": h1, "h2": h2}))
    d = pd.concat(rows, ignore_index=True)
    d["half"] = d["S"].dt.year.astype(str) + "H" + np.where(d["S"].dt.month <= 6, "1", "2")
    out = {}
    sel = {"H1_rate_ge3bp": (d.rate >= 0.0003, "h1"), "H1_prev_ge3bp": (d.prev >= 0.0003, "h1"),
           "H2_prev_lt_m1bp": (d.prev < -0.0001, "h2"), "H2_rate_lt_m1bp(lookahead, ref)": (d.rate < -0.0001, "h2")}
    for name, (mask, col) in sel.items():
        g = d[mask]
        out[name] = {"all": st(g[col]), "by_half": {h: st(x[col]) for h, x in g.groupby("half")},
                     "by_asset": {a: st(x[col]) for a, x in g.groupby("sym")}}
        print(name, out[name]["all"], flush=True)
        print("   half:", out[name]["by_half"], flush=True)
        print("   asset:", out[name]["by_asset"], flush=True)
    (HERE / "refine_pre_anchor.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
