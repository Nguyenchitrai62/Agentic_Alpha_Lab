"""oc_skewbook2: options-skew filter on BOOK LONGS (idea #59, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
apply the v410 bear filter FIRST (longs x0.5 when BTC 4h open < 1200-bar mean),
then gate longs x0.75 when BTC skew_z90 (exactly as oc_optctx) exceeds its
walk-forward 80th percentile. Screen = open-to-open 4h returns with gate costs
(maker 0.0002/unit turnover), per-year reset equity paths, maxDD + worst week.
Single light process (4h + options-4h inputs only, no 1m).

  python research/tournament/oc_skewbook2/compute_skewbook2.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
OPT = ROOT / "data/raw/deribit_opt_20260926"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
SKEW_START = pd.Timestamp("2019-06-01", tz="UTC")
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
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


def load_options() -> pd.DataFrame:
    """BTC 4h options grid, bars with START < CUTOFF; skew + skew_z90 exactly as oc_optctx."""
    g = pd.read_parquet(OPT / "BTC_options_4h.parquet").copy()
    g["bar"] = pd.to_datetime(g["bar"], utc=True)
    g = g[g["bar"] < CUTOFF].sort_values("bar").reset_index(drop=True)
    g["end"] = g["bar"] + pd.Timedelta(hours=4)
    g["skew"] = g["iv_otm_put"] - g["iv_otm_call"]
    r = g["skew"].rolling(540, min_periods=432)
    g["skew_z90"] = (g["skew"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    return g


def skew_z90_for_times(Tns: np.ndarray, grid: pd.DataFrame) -> np.ndarray:
    """As-of skew_z90 at times T: last options bar with end strictly before T.

    Strict rule exactly as oc_optctx: end < T, i.e. end <= T - 1s
    (searchsorted side='left' on T - 1s). NaN where no earlier bar exists.
    """
    ends = grid["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = grid["skew_z90"].to_numpy(float)
    ii = np.searchsorted(ends, Tns - NS, side="left") - 1
    out = np.full(len(Tns), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
    return out


def bear_for_times(grid_idx: pd.DatetimeIndex) -> pd.Series:
    """v410 bear mask exactly: btc < btc.rolling(1200, min_periods=600).mean().

    Computed on the full opens BTCUSDT history (causal, includes current bar),
    then aligned to the requested index.
    """
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid_idx)
    return bear.fillna(False).astype(bool)


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
    opt = load_options()
    n_nan_bar = int(opt["skew_z90"].isna().sum())
    print(f"options: bars={len(opt)} span={opt['bar'].iloc[0]}..{opt['bar'].iloc[-1]} "
          f"skew_z90 NaN bars={n_nan_bar}", flush=True)

    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)

    o = opens[SYMS]
    ot = opens.index
    fwd1 = o.shift(-1) / o - 1.0
    exit1_ok = (ot.shift(-1) <= CUTOFF)
    books, opens = books[exit1_ok], opens[exit1_ok]
    fwd1 = fwd1.reindex(books.index)
    valid1 = fwd1.notna().all(axis=1)
    books, opens = books[valid1], opens[valid1]
    fwd1 = fwd1.reindex(books.index)
    grid = books.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # v410 bear filter first (base book).
    bear = bear_for_times(grid)
    w_raw = books
    w_base = books.copy()
    for s in SYMS:
        m = bear & (books[s] > 0)
        w_base.loc[m, s] = 0.5 * books.loc[m, s]
    print(f"bear share of bars: {float(bear.mean()):.4f}", flush=True)

    # Skew z at book-grid T (market-wide, same for all syms).
    Tns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    zT = skew_z90_for_times(Tns, opt)

    # Walk-forward q80 pool: per-T z on the 4h opens grid in [SKEW_START, A_k).
    pool_idx = opens_full.index[(opens_full.index >= SKEW_START)
                                & (opens_full.index < CUTOFF)].sort_values()
    pool_Tns = pool_idx.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    pool_z = skew_z90_for_times(pool_Tns, opt)
    pool_T = pd.to_datetime(pool_idx, utc=True)

    q80 = []
    for k, a0 in enumerate(ANCHORS):
        tr = (pool_T < a0) & np.isfinite(pool_z)
        assert int(tr.sum()) >= 100, f"year {k}: only {int(tr.sum())} training values"
        q80.append(float(np.quantile(pool_z[tr], 0.8)))

    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({
            "T": grid, "sym": s,
            "w": books[s].to_numpy(float),
            "w_base": w_base[s].to_numpy(float),
            "r1": fwd1[s].reindex(grid).to_numpy(float),
            "z": zT,
            "bear": bear.to_numpy(bool),
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)

    w = panel["w"].to_numpy(float)
    wb = panel["w_base"].to_numpy(float)
    r1 = panel["r1"].to_numpy(float)
    z = panel["z"].to_numpy(float)
    T = panel["T"].to_numpy()
    sym = panel["sym"].to_numpy()

    bounds = ANCHORS + [LAST_BOUND]
    year_m = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy()
              for k in range(5)]

    gated_mask = np.zeros(len(panel), dtype=bool)
    w_g = wb.copy()
    for k in range(5):
        m = year_m[k] & (wb > 0) & np.isfinite(z) & (z > q80[k])
        gated_mask[m] = True
    w_g[gated_mask] = 0.75 * wb[gated_mask]

    cost = np.zeros(len(panel))
    cost_g = np.zeros(len(panel))
    for s in SYMS:
        sm = sym == s
        idx = np.where(sm)[0]
        order = np.argsort(T[idx])
        ii = idx[order]
        bb, gg = wb[ii], w_g[ii]
        prev_b = np.concatenate([[0.0], bb[:-1]])
        prev_g = np.concatenate([[0.0], gg[:-1]])
        cost[ii] = MAKER * np.abs(bb - prev_b)
        cost_g[ii] = MAKER * np.abs(gg - prev_g)

    pnl = wb * r1 - cost
    pnl_g = w_g * r1 - cost_g
    panel["w_g"] = w_g
    panel["gated"] = gated_mask
    panel["cost"] = cost
    panel["cost_g"] = cost_g
    panel["pnl"] = pnl
    panel["pnl_g"] = pnl_g
    panel.to_parquet(HERE / "panel.parquet")

    years = []
    pnl_wins = 0
    dd_wins = 0
    bar = panel.groupby("T", sort=True)[["pnl", "pnl_g"]].sum().sort_index()
    bar_idx = bar.index
    for k, a0 in enumerate(ANCHORS):
        m = year_m[k]
        sel = (bar_idx >= bounds[k]) & (bar_idx < bounds[k + 1])
        sel = np.asarray(sel)
        rp = bar["pnl"].to_numpy()[sel]
        rp_g = bar["pnl_g"].to_numpy()[sel]
        eq = equity_path(rp)
        eq_g = equity_path(rp_g)
        dd, dd_g = max_dd(eq), max_dd(eq_g)
        ww, ww_g = worst_week(eq), worst_week(eq_g)
        tot, tot_g = float(np.sum(pnl[m])), float(np.sum(pnl_g[m]))
        ratio = (tot_g / tot) if tot != 0 else (float("nan") if tot_g != 0 else 1.0)
        long_m = m & (wb > 0)
        row = {
            "year": str(a0.date()),
            "q80": round(q80[k], 6),
            "coverage": round(float(np.isfinite(z[m]).mean()), 6),
            "n_rows": int(m.sum()),
            "n_long": int(long_m.sum()),
            "share_long_gated": round(float(gated_mask[long_m].mean()) if long_m.sum() else 0.0, 6),
            "share_rows_gated": round(float(gated_mask[m].mean()), 6),
            "total_pnl": round(tot, 6),
            "total_pnl_gated": round(tot_g, 6),
            "pnl_ratio": round(ratio, 6) if np.isfinite(ratio) else None,
            "pnl_kept": bool(tot_g >= 0.97 * tot) if tot >= 0 else bool(tot_g >= tot),
            "worst_week": round(ww, 6),
            "worst_week_gated": round(ww_g, 6),
            "maxDD": round(dd, 6),
            "maxDD_gated": round(dd_g, 6),
            "dd_not_worse": bool(dd_g <= dd),
        }
        years.append(row)
        pnl_wins += int(row["pnl_kept"])
        dd_wins += int(row["dd_not_worse"])

    rp_full = bar["pnl"].to_numpy()
    rp_full_g = bar["pnl_g"].to_numpy()
    full_dd = max_dd(equity_path(rp_full))
    full_dd_g = max_dd(equity_path(rp_full_g))

    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_bookic)",
            "bear": "v410 first: longs x0.5 when BTC 4h open < 1200-bar mean (min_periods=600)",
            "opens": "engine_real opens_v154.parquet",
            "options": "data/raw/deribit_opt_20260926/BTC_options_4h.parquet (bar=START, bar<CUTOFF)",
            "skew": "skew=iv_otm_put-iv_otm_call; skew_z90=(skew-mean(prior<=540))/std(ddof=1), min 432, std==0->NaN, current excluded",
            "asof": "last options bar with end strictly before T (end<=T-1s); 4h T -> bar [T-8h,T-4h)",
            "rule": "base longs with z > walk-forward q80 -> weight x0.75; shorts/flats/NaN-z unchanged",
            "costs": "maker 0.0002 per unit turnover (|w-w_prev| per sym, first prev=0; gated path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF), "skew_start": str(SKEW_START),
            "grid_start": str(panel["T"].min()), "grid_end": str(panel["T"].max()),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD": round(full_dd, 6), "maxDD_gated": round(full_dd_g, 6),
            "total_pnl": round(float(rp_full.sum()), 6),
            "total_pnl_gated": round(float(rp_full_g.sum()), 6),
        },
        "decision": {
            "pnl_kept_count": f"{pnl_wins}/5",
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
