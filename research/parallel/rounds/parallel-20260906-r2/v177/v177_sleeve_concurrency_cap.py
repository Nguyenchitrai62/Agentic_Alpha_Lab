"""v177: cap the number of simultaneous dip-sleeve positions per 4h bar (registry v177).

Why: in a market-wide crash all five majors trigger the v175 limit bids in the same bar, so the sleeve holds up to
5 x 0.25 = 1.25x equity long exactly when the books are also losing; v176's full-path DD (20.72%, 2021) comes from such
bars. A concurrency cap is a plain risk rule (not fitted): per holding bar, only the first two limit fills in time order
are taken (ties at the same minute broken by the column order BNB, BTC, ETH, SOL, XRP); later fills in that bar are
cancelled. Causal: a live system knows how many of its bids have filled so far.
Fixed before running: everything else as v176 (v175 limit rule, same walk-forward k - re-chosen with the cap applied,
sleeve_unit = sleeve / 1.657 inside the portfolio vol target, v154 books, v170 execution, engine_real, target 0.25,
governor). Primary: v176 + cap 2. Reference v176 5.239 / 20.72.

  python research/parallel/rounds/parallel-20260906-r2/v177/v177_sleeve_concurrency_cap.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CAP_FILLS = 2


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v176 = _load("v176", HERE.parent / "v176/v176_total_vol_target.py")
v175, v172, v171, v170, er = v176.v175, v176.v172, v176.v171, v176.v170, v176.er
PD = er.PD


def capped_limit_returns(G, cols, A):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L = A["open"], A["high"], A["low"]
    low = L[:, 16:239, :].astype(float)
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr))
    out = {}
    for k in v171.KGRID:
        lim = o1 * (1 - k * sig)
        hit = low < lim[:, None, :]
        filled = hit.any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        fmin = np.where(filled, np.argmax(hit, axis=1), 10_000)
        # rank fills inside each bar by (minute, column order); keep the first CAP_FILLS
        key = fmin * 10 + np.arange(len(cols))[None, :]
        order = np.argsort(key, axis=1)
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(len(cols))[None, :].repeat(len(G), 0), axis=1)
        keep = filled & (rank < CAP_FILLS)
        val = o2 * (1 - s_out) / lim - 1 - v175.MAKER - v171.TAKER - fund
        out[k] = (np.nan_to_num(np.where(keep, val, 0.0)), keep)
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    ev = capped_limit_returns(G, cols, A)
    del A
    sleeve, events, chosen = v171.sleeve_walk_forward(G, ev)
    print("chosen k", chosen, flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    r = v176.run_total(books, ctx, sleeve / v176.S_REF)
    print("primary", r["monthly_pct"], "fullDD", r["full_path_dd"], "mean s", r["mean_scale"],
          [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    alone = []
    for a in v171.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (sleeve.index >= a0) & (sleeve.index < a0 + pd.Timedelta(days=365))
        eqs = (1 + sleeve[mk]).cumprod()
        alone.append(dict(anchor=a, k=chosen[a]["k"], net_pct=round(100 * float(eqs.iloc[-1] - 1), 2),
                          dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2), events=int(events[mk].sum())))
    print("sleeve alone", alone, flush=True)
    out = {"version": "v177", "chosen": chosen, "primary_cap2": r, "sleeve_alone": alone, "reference_v176": (5.239, 20.72)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v177_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
