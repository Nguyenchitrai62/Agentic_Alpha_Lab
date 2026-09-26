"""v173: learned rebound model for the intrabar dip sleeve (registry v173).

Why: with crash-aware slippage (v172) the fixed rule only pays at k = 4 (about 100 events/year). A model that uses the
state at the trigger minute (speed and breadth of the drop, volume, taker flow, minute range, trend, funding, the
books' own position) may separate drops that rebound from drops that continue, and trade more of them.
Fixed before running:
- Candidate points: for each holding bar T (= t + 4h) and asset, the first minute m in 16..238 where the 1m close / 4h
  open - 1 crosses -c sigma for c in (2, 3, 4) (up to 3 points per bar and asset). Entry/exit/costs exactly as v172
  (entry minute m+1 open, exit next 4h open, slippage max(2 bps, 0.25 * minute range), taker 0.0005 x 2, funding).
- Features known at the close of minute m: depth (sigma units), c, m/240, 5- and 15-minute return (sigma units), volume
  of the last 5 minutes / mean 1m volume over minutes 0..m-6 of the bar, taker-buy share of the last 15 minutes, range
  of minute m / sigma, breadth (number of other majors at <= -2 sigma at minute m), BTC depth (sigma units), trend
  (4h open / mean of the last 42 4h opens - 1), 1-day return (sigma units), last settled funding rate, asset code.
  (The v154 book weight is built but not used: books start in 2021-09, so it is constant in the first training set;
  dropped before any result was seen.)
- Target: the net event return. Model per anchor: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03,
  max_iter=300, min_samples_leaf=50, l2_regularization=1.0, random_state=0) on candidate points with T + 4h < anchor - 1
  day (from 2020-02-01 + 30 d).
- Policy: per bar and asset, take the first candidate point (in time) whose prediction > 0; size 0.25; one position per
  bar and asset. Primary: v154 books (engine_real, v170 execution, target 0.25, governor) + model sleeve * g.
  Secondary: model sleeve alone per anchor; Spearman IC of predictions vs realised on all test candidate points;
  reference v172 (rule sleeve) 4.597 / 22.42.

  python research/parallel/rounds/parallel-20260906-r2/v173/v173_rebound_model.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
CS = (2.0, 3.0, 4.0)
FEATS = ["depth", "c", "minute", "r5", "r15", "vspike", "taker15", "rng", "breadth", "btc_depth", "trend", "r1d",
         "funding", "asset"]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v172 = _load("v172", HERE.parent / "v172/v172_sleeve_realistic.py")
v171, v170, er = v172.v171, v172.v170, v172.er
PD = er.PD


def cube(G, cols):
    starts = G + pd.Timedelta(hours=4)
    n = len(G)
    keys = ("open", "high", "low", "close", "volume", "taker_buy_volume")
    A = {k: np.full((n, 240, len(cols)), np.nan, dtype=np.float32) for k in keys}
    pos = pd.Series(np.arange(n), index=starts)
    for j, s in enumerate(cols):
        d = Path("data/raw/btc_intraday_20260924") if s == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
        pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
        m = pd.concat([pd.read_parquet(f, columns=["open_time", *keys]) for f in sorted(d.glob(pat))])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time")
        T = m["open_time"].dt.floor("4h")
        i = pos.reindex(T).to_numpy()
        ok = ~np.isnan(i)
        off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
        for k in keys:
            A[k][i[ok].astype(int), off[ok], j] = m[k].to_numpy(float)[ok]
    for k in ("open", "high", "low", "close"):
        X = A[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm, :])
            X[:, mm, :][miss] = X[:, mm - 1, :][miss]
    for k in ("volume", "taker_buy_volume"):
        A[k] = np.nan_to_num(A[k])
    return A


def candidates(G, cols, A, books):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    trend = (opens / opens.rolling(42, min_periods=42).mean() - 1).shift(-1).to_numpy()  # at T: uses opens <= T
    r1d = (opens.shift(-1) / opens.shift(5) - 1).to_numpy()  # open(T) / open(T - 24h) - 1
    fset = np.column_stack([er.funding_at_bar_open(s, G).to_numpy() for s in cols])
    last_f = pd.DataFrame(fset, index=G).replace(0.0, np.nan).ffill().fillna(0.0).to_numpy()  # settled at or before t
    fund_exit = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    bw = books.reindex(G).fillna(0.0)[cols].to_numpy()
    O, H, L, C, V, TB = (A[k] for k in ("open", "high", "low", "close", "volume", "taker_buy_volume"))
    dep = C / o1[:, None, :] - 1
    dep_s = dep / sig[:, None, :]
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    bi = cols.index("BTCUSDT")
    rows = []
    for c in CS:
        hit = dep_s[:, 16:239, :] <= -c
        any_ = hit.any(axis=1)
        first = np.argmax(hit, axis=1) + 16
        ii, jj = np.nonzero(any_ & np.isfinite(o2) & np.isfinite(sig))
        mm = first[ii, jj]
        s = sig[ii, jj]
        po = O[ii, mm + 1, jj].astype(float)
        s_in = np.maximum(0.0002, 0.25 * np.nan_to_num((H[ii, mm + 1, jj] - L[ii, mm + 1, jj]) / po))
        s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr[ii, jj]))
        y = o2[ii, jj] * (1 - s_out) / (po * (1 + s_in)) - 1 - 0.001 - fund_exit[ii, jj]
        v5 = np.array([V[a, m - 4:m + 1, b].sum() for a, m, b in zip(ii, mm, jj)])
        vbase = np.array([V[a, 0:m - 5, b].mean() * 5 for a, m, b in zip(ii, mm, jj)])
        v15 = np.array([V[a, m - 14:m + 1, b].sum() for a, m, b in zip(ii, mm, jj)])
        tb15 = np.array([TB[a, m - 14:m + 1, b].sum() for a, m, b in zip(ii, mm, jj)])
        rows.append(pd.DataFrame({
            "i": ii, "j": jj, "minute_idx": mm, "c": c, "y": y,
            "depth": dep_s[ii, mm, jj], "minute": mm / 240.0,
            "r5": (C[ii, mm, jj] / C[ii, mm - 5, jj] - 1) / s, "r15": (C[ii, mm, jj] / C[ii, mm - 15, jj] - 1) / s,
            "vspike": v5 / np.maximum(vbase, 1e-9), "taker15": tb15 / np.maximum(v15, 1e-9),
            "rng": (H[ii, mm, jj] - L[ii, mm, jj]) / C[ii, mm, jj] / s,
            "breadth": (dep_s[ii, mm, :] <= -2).sum(axis=1) - 1, "btc_depth": dep_s[ii, mm, bi],
            "trend": trend[ii, jj], "r1d": r1d[ii, jj] / s, "funding": last_f[ii, jj], "book_w": bw[ii, jj], "asset": jj}))
    d = pd.concat(rows, ignore_index=True)
    d["T"] = G[d["i"].to_numpy()] + pd.Timedelta(hours=4)
    return d[np.isfinite(d["y"])].reset_index(drop=True)


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = cube(G, cols)
    d = candidates(G, cols, A, books)
    del A
    print("candidate points", len(d), d.groupby("c").size().to_dict(), flush=True)
    sleeve = pd.Series(0.0, index=G)
    ic, alone, n_taken = {}, [], {}
    for a in v171.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        tr = d[(d["T"] + pd.Timedelta(hours=4) < a0 - pd.Timedelta(days=1)) & (d["T"] >= v171.START + pd.Timedelta(days=30))]
        te = d[(d["T"] - pd.Timedelta(hours=4) >= a0) & (d["T"] - pd.Timedelta(hours=4) < a0 + pd.Timedelta(days=365))].copy()
        mdl = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
                                            l2_regularization=1.0, random_state=0).fit(tr[FEATS], tr["y"])
        te["pred"] = mdl.predict(te[FEATS])
        ic[a] = round(float(te["pred"].corr(te["y"], method="spearman")), 4)
        take = te[te["pred"] > 0].sort_values("minute_idx").groupby(["i", "j"], as_index=False).first()
        n_taken[a] = int(len(take))
        bar = take.groupby("i")["y"].sum() * v171.SIZE
        sleeve.iloc[bar.index.to_numpy()] = bar.to_numpy()
        mk = (G >= a0) & (G < a0 + pd.Timedelta(days=365))
        eqs = (1 + sleeve[mk]).cumprod()
        alone.append(dict(anchor=a, train_points=int(len(tr)), test_points=int(len(te)), taken=n_taken[a], ic=ic[a],
                          mean_taken_bps=round(1e4 * float(take["y"].mean()), 1) if len(take) else None,
                          net_pct=round(100 * float(eqs.iloc[-1] - 1), 2), dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2)))
        print(alone[-1], flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    prim, _ = v171.run_combined(books, ctx, sleeve)
    print("primary", prim["monthly_pct"], "fullDD", prim["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in prim["yearly"]], flush=True)
    out = {"version": "v173", "primary_books_plus_model_sleeve": prim, "sleeve_alone": alone, "ic": ic,
           "reference": {"v172": (4.597, 22.42), "v170_books": (3.802, 18.93)}}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v173_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
