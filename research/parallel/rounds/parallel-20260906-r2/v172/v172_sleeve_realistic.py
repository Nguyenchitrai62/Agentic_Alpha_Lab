"""v172: v154 books + v170 execution + v171 dip-reversal sleeve with crash-aware slippage (registry v172).

Why: v171 (sleeve + v154) reached 5.96%/month but assumed 2 bps slippage per side; its largest events are crash minutes
(FTX, LUNA, 2024-08-05) where the book is thin. This version makes the fill cost depend on the minute's own range,
adds the audited 60-minute limit execution (v170) for the books, and keeps everything else as v171.
Fixed before running:
- Sleeve rule exactly as v171 (sigma from 360 4h bars, trigger minutes 16..238 at close <= -k sigma of the 4h open,
  size 0.25 per event, exit at the next 4h open, long pays that settlement's funding, taker fee 0.0005 each side).
- Slippage per side = max(0.0002, 0.25 * (high - low) / open) of the fill minute: entry minute m+1 of the holding bar,
  exit minute 0 of the next bar. k per anchor re-chosen from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe with THIS cost.
- Books: v154 on engine_real (all realism), target 0.25, 20% governor, execution v170 (W = 60 minutes).
- Primary row: books + sleeve (size 0.25, scaled by the governor g). Secondary rows: books alone (v170 check 3.802 /
  18.93), sleeve alone per anchor; sizes 0.15 and 0.20 as labelled ex-post sensitivities (not selectable).
Gate: >= 5%/month and full-path DD <= 20% on the primary row.

  python research/parallel/rounds/parallel-20260906-r2/v172/v172_sleeve_realistic.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
SIZES = (("primary_size025", 0.25), ("sensitivity_size020", 0.20), ("sensitivity_size015", 0.15))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v171 = _load("v171", HERE.parent / "v171/v171_intrabar_reversal.py")
v170 = _load("v170", HERE.parent / "v170/v170_exec_window.py")
er = v171.er
PD = er.PD


def cube_ohlc(G, cols):
    """open/high/low/close [i, minute, sym] of the 4h bar starting at G[i] + 4h (float32, forward-filled in a bar)."""
    starts = G + pd.Timedelta(hours=4)
    n = len(G)
    A = {k: np.full((n, 240, len(cols)), np.nan, dtype=np.float32) for k in ("open", "high", "low", "close")}
    pos = pd.Series(np.arange(n), index=starts)
    for j, s in enumerate(cols):
        d = Path("data/raw/btc_intraday_20260924") if s == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
        pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in sorted(d.glob(pat))])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time")
        T = m["open_time"].dt.floor("4h")
        i = pos.reindex(T).to_numpy()
        ok = ~np.isnan(i)
        off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
        for k in A:
            A[k][i[ok].astype(int), off[ok], j] = m[k].to_numpy(float)[ok]
    for k in A:
        X = A[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm, :])
            X[:, mm, :][miss] = X[:, mm - 1, :][miss]
    return A


def event_returns_real(G, cols, A):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L, C = A["open"], A["high"], A["low"], A["close"]
    path = C[:, 16:239, :] / o1[:, None, :] - 1
    # exit minute: minute 0 of the next holding bar = cube row i+1, minute 0
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    out = {}
    for k in v171.KGRID:
        thr = -k * sig
        hit = path <= thr[:, None, :]
        first = np.argmax(hit, axis=1) + 16
        ii, jj = np.nonzero(hit.any(axis=1) & np.isfinite(o2) & np.isfinite(thr))
        mm = first[ii, jj] + 1
        po = O[ii, mm, jj].astype(float)
        rng_in = (H[ii, mm, jj] - L[ii, mm, jj]).astype(float) / po
        s_in = np.maximum(0.0002, 0.25 * np.nan_to_num(rng_in))
        s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr[ii, jj]))
        r = np.zeros(o1.shape)
        ev = np.zeros(o1.shape, dtype=bool)
        val = o2[ii, jj] * (1 - s_out) / (po * (1 + s_in)) - 1 - 2 * v171.TAKER - fund[ii, jj]
        ok = np.isfinite(val)
        r[ii[ok], jj[ok]] = val[ok]
        ev[ii[ok], jj[ok]] = True
        out[k] = (r, ev)
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = cube_ohlc(G, cols)
    ev = event_returns_real(G, cols, A)
    del A
    sleeve, events, chosen = v171.sleeve_walk_forward(G, ev)
    print("chosen k", chosen, flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    out = {"version": "v172", "chosen": chosen, "reference": {"v170": (3.802, 18.93), "v171": (5.959, 21.85)}}
    base, base_net = v171.run_combined(books, ctx, sleeve * 0.0)
    out["books_alone_v170_exec"] = base
    print("books alone", base["monthly_pct"], base["full_path_dd"], flush=True)
    for key, size in SIZES:
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
    (HERE / "v172_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
