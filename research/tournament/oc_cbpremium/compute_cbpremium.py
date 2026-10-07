"""oc_cbpremium: Coinbase premium BOOK direction tilt (idea #60, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort /
oc_bearshort), join with v154 4h opens, apply the v410 BTC-only bear-long filter
as BASE (longs x0.5 when BTC 4h open < its 1200-bar mean), then RULE = BASE with
book LONG targets x1.15 when premium z > 1, x0.85 when z < -1, else x1.0
(all coins share the BTC-only signal; shorts/flats/NaN-z unchanged).
Premium feature exactly as oc_optctx.load_premium (inner join on hourly START,
prem = cb/bin - 1, mean24 rolling 24 min 20, z90 rolling 2160 min 1728 shift 1;
as-of strict end < T, i.e. end <= T - 1s). Screen with open-to-open 4h returns
and gate costs (maker 0.0002 per unit turnover, each path own prev), exactly as
oc_dvolshort/oc_bearshort. Single light process (4h + hourly only, no 1m).

  python research/tournament/oc_cbpremium/compute_cbpremium.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
LONG_MULT_BEAR = 0.5
UP_MULT = 1.15
DOWN_MULT = 0.85
Z_HI = 1.0
Z_LO = -1.0
NS = 1_000_000_000


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2 (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def load_premium() -> pd.DataFrame:
    """Hourly Coinbase/Binance premium grid exactly as oc_optctx.load_premium.

    Bar STARTs < CUTOFF only. Ends = start + 1h. mean24 rolling(24, min 20);
    cbprem_z90 rolling(2160, min 1728) mean/std shifted by one (history only).
    """
    cb = pd.read_parquet(CB).copy()
    cb["t"] = pd.to_datetime(cb["open_time"], utc=True)
    cb = cb[cb["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "cb"})
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "bin"})
    g = pd.merge(cb, h, on="t", how="inner").sort_values("t").reset_index(drop=True)
    g["prem"] = g["cb"] / g["bin"] - 1
    g["mean24"] = g["prem"].rolling(24, min_periods=20).mean()
    r = g["mean24"].rolling(2160, min_periods=1728)
    g["cbprem_z90"] = (g["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    g["end"] = g["t"] + pd.Timedelta(hours=1)
    return g


def asof_z(prem: pd.DataFrame, T: pd.DatetimeIndex) -> np.ndarray:
    """z(T) = cbprem_z90 of last premium row with end strictly before T (end <= T-1s)."""
    ends_ns = prem["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = prem["cbprem_z90"].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(ends_ns, Tns - NS, side="left") - 1
    out = np.full(len(T), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
    return out


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    return float(np.max(dd))


def worst_week(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 43:
        return float(eq[-1] / eq[0] - 1.0) if len(eq) > 1 else 0.0
    rets = eq[42:] / eq[:-42] - 1.0
    return float(np.min(rets))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def main() -> None:
    prem = load_premium()
    print(f"premium: rows={len(prem)} span={prem['t'].iloc[0]}..{prem['t'].iloc[-1]} "
          f"median_prem_bps={prem['prem'].median() * 1e4:.2f}", flush=True)

    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # v410 bear regime FIRST (BTC-only, causal at close of T, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    w_raw = books_raw[SYMS].to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * LONG_MULT_BEAR, w_raw)

    # Premium signal (one z per bar, all coins).
    zbar = asof_z(prem, grid)
    mult_bar = np.ones(len(grid))
    mult_bar[np.isfinite(zbar) & (zbar > Z_HI)] = UP_MULT
    mult_bar[np.isfinite(zbar) & (zbar < Z_LO)] = DOWN_MULT
    w_rule = np.where(w_base > 0, w_base * mult_bar[:, None], w_base)

    r1 = fwd1[SYMS].to_numpy(float)
    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_rule = w_rule * r1 - cost_rule

    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    # Per-(T,sym) panel (small).
    rows = []
    for j, s in enumerate(SYMS):
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w_raw": w_raw[:, j],
            "w_base": w_base[:, j],
            "w_rule": w_rule[:, j],
            "bear": bear,
            "z": zbar,
            "mult": mult_bar,
            "tilted": (w_base[:, j] > 0) & np.isfinite(zbar) & ((zbar > Z_HI) | (zbar < Z_LO)),
            "r1": r1[:, j],
            "cost_base": cost_base[:, j],
            "cost_rule": cost_rule[:, j],
            "pnl_base": pnl_base[:, j],
            "pnl_rule": pnl_rule[:, j],
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bounds = ANCHORS + [LAST_BOUND]
    grid_ts = pd.to_datetime(grid, utc=True)
    years = []
    pnl_wins = 0
    dd_wins = 0
    bar_base = pd.Series(rp_base, index=grid_ts).sort_index()
    bar_rule = pd.Series(rp_rule, index=grid_ts).sort_index()
    for k, a0 in enumerate(ANCHORS):
        sel = (grid_ts >= bounds[k]) & (grid_ts < bounds[k + 1])
        sel = np.asarray(sel)
        rp_b = rp_base[sel]
        rp_r = rp_rule[sel]
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        m_year = panel["T"].ge(bounds[k]) & panel["T"].lt(bounds[k + 1])
        m_year = m_year.to_numpy()
        wb = panel["w_base"].to_numpy(float)
        long_m = m_year & (wb > 0)
        long_b = float(np.sum(panel["pnl_base"].to_numpy()[long_m]))
        long_r = float(np.sum(panel["pnl_rule"].to_numpy()[long_m]))
        book_b = float(np.sum(panel["pnl_base"].to_numpy()[m_year]))
        book_r = float(np.sum(panel["pnl_rule"].to_numpy()[m_year]))
        bear_share = round(float(bear[sel].mean()), 6) if sel.size else 0.0
        zb = zbar[sel]
        wb_bar = w_base[sel]
        long_bar = wb_bar > 0
        n_long = int(long_bar.sum())
        up = int(((zb[:, None] > Z_HI) & long_bar & np.isfinite(zb[:, None])).sum())
        down = int(((zb[:, None] < Z_LO) & long_bar & np.isfinite(zb[:, None])).sum())
        cov = round(float(np.isfinite(zb).mean()), 6)
        row = {
            "year": str(a0.date()),
            "bear_share": bear_share,
            "coverage": cov,
            "n_bars": int(sel.sum()),
            "n_long_cells": n_long,
            "share_long_up": round(up / n_long, 6) if n_long else 0.0,
            "share_long_down": round(down / n_long, 6) if n_long else 0.0,
            "long_pnl_base": round(long_b, 6),
            "long_pnl_rule": round(long_r, 6),
            "book_pnl_base": round(book_b, 6),
            "book_pnl_rule": round(book_r, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "pnl_higher": bool(book_r > book_b),
            "dd_not_worse": bool(dd_r <= dd_b + 1e-12),
        }
        years.append(row)
        pnl_wins += int(row["pnl_higher"])
        dd_wins += int(row["dd_not_worse"])

    rp_full_b = rp_base
    rp_full_r = rp_rule
    full_dd_b = max_dd(equity_path(rp_full_b))
    full_dd_r = max_dd(equity_path(rp_full_r))

    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_bearshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter (longs x0.5 when BTC 4h open < 1200-bar mean)",
            "premium": "cb/bin-1 hourly inner join; mean24 rolling(24,min20); z90 rolling(2160,min1728) shift(1); as-of last row end<T (end<=T-1s)",
            "rule": "BASE longs x1.15 when z>1, x0.85 when z<-1, else x1.0 (all coins); shorts/flats/NaN-z unchanged",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0; each path own chain)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(pd.to_datetime(grid_ts.min())),
            "grid_end": str(pd.to_datetime(grid_ts.max())),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_rule": round(full_dd_r, 6),
            "book_pnl_base": round(float(np.sum(pnl_base)), 6),
            "book_pnl_rule": round(float(np.sum(pnl_rule)), 6),
        },
        "decision": {
            "pnl_higher_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
