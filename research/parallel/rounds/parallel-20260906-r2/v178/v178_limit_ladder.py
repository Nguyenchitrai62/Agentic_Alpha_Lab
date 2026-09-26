"""v178: ladder of resting limit bids instead of a selected k (registry v178).

Why: the v175 audit found the walk-forward k choice knife-edge (2024/2025 Sharpe gaps of 0.0002 flip k between 3, 3.5
and 4 under harmless conventions). A ladder removes the selection step: bids at k = 2.5, 3, 3.5 and 4 sigma below the
4h open, each at a quarter of the sleeve size, all live in minutes 16..238, each filled at its own price on a 1m
trade-through with maker fee, all exited at the next 4h open (taker, crash-aware slippage, funding). Nothing is
chosen on data. Deeper drops fill more rungs (average cost falls as the drop deepens).
Fixed before running: sleeve per bar = sum over assets and rungs of 0.25/4 * r; everything else exactly v176 (sleeve
inside the portfolio vol target, sleeve_unit = sleeve/1.657, v154 books, v170 execution, engine_real, target 0.25,
governor). Primary: ladder. Reference v176 5.239 / 20.72.

  python research/parallel/rounds/parallel-20260906-r2/v178/v178_limit_ladder.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v176 = _load("v176", HERE.parent / "v176/v176_total_vol_target.py")
v175, v172, v171, v170, er = v176.v175, v176.v172, v176.v171, v176.v170, v176.er


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    ev = v175.limit_returns(G, cols, A)
    del A
    per_bar = sum(ev[k][0] for k in RUNGS) / len(RUNGS)  # [bar, asset] average rung return (0 where unfilled)
    sleeve = pd.Series(v171.SIZE * per_bar.sum(axis=1), index=G)
    fills = {k: ev[k][1] for k in RUNGS}
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    r = v176.run_total(books, ctx, sleeve / v176.S_REF)
    print("primary", r["monthly_pct"], "fullDD", r["full_path_dd"], "mean s", r["mean_scale"],
          [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    alone = []
    for a in v171.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = np.asarray((G >= a0) & (G < a0 + pd.Timedelta(days=365)))
        eqs = (1 + sleeve[mk]).cumprod()
        alone.append(dict(anchor=a, net_pct=round(100 * float(eqs.iloc[-1] - 1), 2),
                          dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2),
                          fills_per_rung={str(k): int(fills[k][mk].sum()) for k in RUNGS}))
    print("sleeve alone", alone, flush=True)
    out = {"version": "v178", "rungs": RUNGS, "primary_ladder": r, "sleeve_alone": alone, "reference_v176": (5.239, 20.72)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v178_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
