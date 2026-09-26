"""v175: dip sleeve entered with resting limit bids instead of market orders (registry v175).

Why: with crash-aware taker slippage (v172) only k = 4 pays, because market entries in crash minutes are expensive.
A resting limit bid at open(T) * (1 - k sigma) is placed after the v170 book execution window and filled only on a
trade-through, at the limit price with the maker fee - realistic for a resting order (queue position is irrelevant when
the price trades below the limit), and adverse selection is fully in the price path (the return starts at the limit).
Fixed before running:
- Holding bar T = t + 4h; sigma as v171/v172 (360 4h returns ending at t). Limit bid L = open(T) * (1 - k sigma), live
  in minutes 16..238; filled at L in the first minute whose 1m LOW < L (strict trade-through); maker fee 0.0002.
  Exit at the next 4h open by taker: open(T + 4h) * (1 - s_out), s_out = max(0.0002, 0.25 * range/open of that minute),
  fee 0.0005; the long pays the funding settled at T + 4h. r = exit / L - 1 - 0.0007 - funding.
- k per anchor from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe (same procedure as v171/v172), size 0.25, governor-scaled.
- Primary: books (engine_real, v170 execution, target 0.25, governor) + limit dip sleeve. Secondary: sleeve alone per
  anchor; limit sleeve at size 0.15 (labelled sensitivity). Reference v172 (taker entry) 4.597 / 22.42.

  python research/parallel/rounds/parallel-20260906-r2/v175/v175_limit_dip_sleeve.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MAKER = 0.0002


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v172 = _load("v172", HERE.parent / "v172/v172_sleeve_realistic.py")
v171, v170, er = v172.v171, v172.v170, v172.er
PD = er.PD


def limit_returns(G, cols, A):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L = A["open"], A["high"], A["low"]
    low = L[:, 16:239, :].astype(float)
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    out = {}
    for k in v171.KGRID:
        lim = o1 * (1 - k * sig)
        filled = (low < lim[:, None, :]).any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr))
        val = o2 * (1 - s_out) / lim - 1 - MAKER - v171.TAKER - fund
        r = np.where(filled, val, 0.0)
        r = np.nan_to_num(r)
        out[k] = (r, filled)
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    ev = limit_returns(G, cols, A)
    del A
    sleeve, events, chosen = v171.sleeve_walk_forward(G, ev)
    print("chosen k", chosen, flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    out = {"version": "v175", "chosen": chosen, "reference_v172": (4.597, 22.42)}
    for key, size in (("primary_size025", 0.25), ("sensitivity_size015", 0.15)):
        r, _ = v171.run_combined(books, ctx, sleeve * (size / v171.SIZE))
        out[key] = r
        print(key, r["monthly_pct"], "fullDD", r["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    alone = []
    for a in v171.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (sleeve.index >= a0) & (sleeve.index < a0 + pd.Timedelta(days=365))
        eqs = (1 + sleeve[mk]).cumprod()
        alone.append(dict(anchor=a, k=chosen[a]["k"], net_pct=round(100 * float(eqs.iloc[-1] - 1), 2),
                          dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2), events=int(events[mk].sum())))
    out["sleeve_alone"] = alone
    print("sleeve alone", alone, flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v175_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
