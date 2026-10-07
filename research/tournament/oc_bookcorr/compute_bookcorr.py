"""oc_bookcorr: correlation-scaled book exposure (idea #43, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
apply the audited v410 bear-long filter FIRST (BASE = control), then scale ALL
book targets by s(T) = clip(1.5 - rho(T), 0.5, 1.0) where rho(T) = mean pairwise
Pearson correlation of the majors' 4h log returns over the 180 bars strictly
before T. Screen with open-to-open 4h returns and gate costs (maker 0.0002 per
unit turnover, each path with its own prev). Dip stream via harness5.load
exactly as oc_idea7; combined book+dip context on the per-year LINEAR cumsum
path (oc_bullbook convention). Single light process (4h + fills only, no 1m).

  python research/tournament/oc_bookcorr/compute_bookcorr.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
WIN = 180
MIN_OVERLAP = 120
MIN_PAIRS = 8


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_bookic.compute_bookic.research_books_d2 (same files, same math)."""
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


def bear_flags(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.Series:
    """v410 bear flag on the FULL BTC opens history, reindexed to grid."""
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid)
    return bear.fillna(False)


def rho_for_grid(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.Series:
    """Mean pairwise Pearson correlation of majors' 4h log returns.

    lr_c[j] = ln(open_c[j]/open_c[j-1]) on the FULL opens history. At grid bar
    T (full-history position p): window rows [p-180, p-1], i.e. 180 returns
    ending at the bar BEFORE T (every input open is at time < T). Per pair
    Pearson over pairwise-complete points (>= 120 required); rho = mean of
    valid pairs (>= 8/10 required, else NaN).
    """
    o = opens_full[SYMS].sort_index()
    lr = np.log(o / o.shift(1)).to_numpy(float)  # (N, 5), NaN where missing
    full_idx = o.index
    pos = full_idx.get_indexer(grid)  # position of each grid T in full history
    assert (pos >= WIN).all(), "grid needs a full 180-bar window before every T"
    rho = np.full(len(grid), np.nan)
    for i, p in enumerate(pos):
        w = lr[p - WIN:p]  # rows [p-180, p-1], strictly before T
        cpairs = []
        for a in range(5):
            for b in range(a + 1, 5):
                m = np.isfinite(w[:, a]) & np.isfinite(w[:, b])
                if int(m.sum()) >= MIN_OVERLAP:
                    xa, xb = w[m, a], w[m, b]
                    sa, sb = xa.std(ddof=1), xb.std(ddof=1)
                    if sa > 0 and sb > 0:
                        cpairs.append(float(np.corrcoef(xa, xb)[0, 1]))
        if len(cpairs) >= MIN_PAIRS:
            rho[i] = float(np.mean(cpairs))
    return pd.Series(rho, index=grid)


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


def linear_dd(path: np.ndarray) -> float:
    """Peak-to-trough decline of a linear cumsum path (native units)."""
    x = np.asarray(path, dtype=float)
    if len(x) == 0:
        return float("nan")
    return float(np.max(np.maximum.accumulate(x) - x))


def main() -> None:
    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid)

    o = opens.reindex(grid)[SYMS]
    ot = grid
    fwd1 = o.shift(-1) / o - 1.0
    exit1_ok = (ot.shift(-1) <= CUTOFF)
    keep = np.asarray(exit1_ok)
    books_raw, fwd1 = books_raw[keep], fwd1[keep]
    valid1 = fwd1.notna().all(axis=1)
    books_raw, fwd1 = books_raw[valid1], fwd1[valid1]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # Bear filter FIRST (v410): BASE is the control path.
    bear = bear_flags(opens_full, grid).to_numpy(bool)
    w0 = books_raw[SYMS].to_numpy(float)  # (n_bars, 5)
    base = w0.copy()
    neg = w0 <= 0
    base[bear[:, None] & ~neg] = 0.5 * w0[bear[:, None] & ~neg]

    # Correlation scale (rows < t only).
    rho = rho_for_grid(opens_full, grid).to_numpy(float)
    scale = np.clip(1.5 - rho, 0.5, 1.0)
    scale[~np.isfinite(rho)] = 1.0
    scaled = base * scale[:, None]

    r1 = fwd1[SYMS].to_numpy(float)

    # Turnover costs in grid order per sym (first bar prev = 0), each path own prev.
    cost_b = np.zeros_like(w0)
    cost_s = np.zeros_like(w0)
    for j in range(len(SYMS)):
        wb, ws = base[:, j], scaled[:, j]
        cost_b[:, j] = MAKER * np.abs(wb - np.concatenate([[0.0], wb[:-1]]))
        cost_s[:, j] = MAKER * np.abs(ws - np.concatenate([[0.0], ws[:-1]]))
    pnl_b = base * r1 - cost_b
    pnl_s = scaled * r1 - cost_s

    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), len(grid)),
        "bear": np.repeat(bear, len(SYMS)),
        "rho": np.repeat(rho, len(SYMS)),
        "scale": np.repeat(scale, len(SYMS)),
        "w0": w0.reshape(-1),
        "w_base": base.reshape(-1),
        "w_scaled": scaled.reshape(-1),
        "r1": r1.reshape(-1),
        "cost_base": cost_b.reshape(-1),
        "cost_scaled": cost_s.reshape(-1),
        "pnl_base": pnl_b.reshape(-1),
        "pnl_scaled": pnl_s.reshape(-1),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bar_b = pd.Series(pnl_b.sum(axis=1), index=grid)  # per-bar portfolio return
    bar_s = pd.Series(pnl_s.sum(axis=1), index=grid)

    # Dip stream exactly as oc_idea7 (harness5.load, majors x R2, y_dep).
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    is_r2 = d["sym"].isin(H5.MAJORS) & d["k"].isin(H5.R2) & d["size_dep"].notna()
    dd = d.loc[is_r2, ["T", "size_dep", "y_dep"]].copy()
    dd["dip"] = dd["size_dep"].to_numpy(float) * dd["y_dep"].to_numpy(float)
    dd["day"] = dd["T"].dt.floor("D")
    dip_daily = dd.groupby("day")["dip"].sum()

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    ret_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        m = np.asarray(m)
        rp_b = bar_b.to_numpy()[m]
        rp_s = bar_s.to_numpy()[m]
        eq_b, eq_s = equity_path(rp_b), equity_path(rp_s)
        dd_b, dd_s = max_dd(eq_b), max_dd(eq_s)
        ww_b, ww_s = worst_week(eq_b), worst_week(eq_s)
        tot_b = float(np.sum(pnl_b[m]))
        tot_s = float(np.sum(pnl_s[m]))
        comp_b = float(eq_b[-1] - 1.0)
        comp_s = float(eq_s[-1] - 1.0)
        # Combined book+dip daily context (linear cumsum path, native units).
        days = pd.date_range(bounds[k], bounds[k + 1] - pd.Timedelta(days=1), freq="D", tz="UTC")
        days = days[(days >= grid[m].min().floor("D")) & (days <= grid[m].max().floor("D"))]
        bday = bar_b.groupby(bar_b.index.floor("D")).sum()
        bd_b = bday.reindex(days, fill_value=0.0).to_numpy(float)
        # book-daily for scaled: recompute per-bar then group (same days)
        sday = bar_s.groupby(bar_s.index.floor("D")).sum()
        bd_s = sday.reindex(days, fill_value=0.0).to_numpy(float)
        dday = dip_daily.reindex(days, fill_value=0.0).to_numpy(float)
        comb_b = linear_dd(np.cumsum(bd_b + dday))
        comb_s = linear_dd(np.cumsum(bd_s + dday))
        wday_b = float(np.min(bd_b + dday)) if len(days) else float("nan")
        wday_s = float(np.min(bd_s + dday)) if len(days) else float("nan")
        dd_ok = bool(dd_s < dd_b)
        ret_ok = bool(tot_b > 0 and tot_s >= 0.9 * tot_b)
        row = {
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "rho_coverage": round(float(np.isfinite(rho[m]).mean()), 6),
            "mean_rho": round(float(np.nanmean(rho[m])), 6),
            "avg_scale": round(float(scale[m].mean()), 6),
            "share_scaled": round(float((scale[m] < 1.0).mean()), 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_scaled": round(tot_s, 6),
            "retention": round(tot_s / tot_b, 6) if tot_b > 0 else None,
            "comp_base": round(comp_b, 6),
            "comp_scaled": round(comp_s, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_scaled": round(ww_s, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_scaled": round(dd_s, 6),
            "dd_improves": dd_ok,
            "retention_ok": ret_ok,
            "dip_sum": round(float(dday.sum()), 6),
            "combDD_base": round(comb_b, 6),
            "combDD_scaled": round(comb_s, 6),
            "comb_worst_day_base": round(wday_b, 6),
            "comb_worst_day_scaled": round(wday_s, 6),
        }
        years.append(row)
        dd_wins += int(dd_ok)
        ret_wins += int(ret_ok)

    # Full-path context (compounded from year-1 start, no reset).
    full_dd_b = max_dd(equity_path(bar_b.to_numpy()))
    full_dd_s = max_dd(equity_path(bar_s.to_numpy()))

    # LOYO stability (descriptive): held-out indicator == majority of other four.
    dd_ind = np.array([y["dd_improves"] for y in years], dtype=bool)
    ret_ind = np.array([y["retention_ok"] for y in years], dtype=bool)
    loyo_dd = sum(bool(dd_ind[h] == (np.sum(dd_ind[np.arange(5) != h]) >= 3)) for h in range(5))
    loyo_ret = sum(bool(ret_ind[h] == (np.sum(ret_ind[np.arange(5) != h]) >= 3)) for h in range(5))

    promising = bool(dd_wins >= 4 and ret_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_bookic)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "rule": "SCALED = BASE * clip(1.5 - rho, 0.5, 1.0); rho = mean pairwise Pearson of majors' 4h log returns over 180 bars strictly before T (>=120 overlap/pair, >=8/10 pairs else NaN->scale 1.0)",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0; each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "combined": "dip = harness5.load BOT rungs sum(size_dep*y_dep) by UTC day; book daily = sum(rp) by UTC day; combined = sum; per-year LINEAR cumsum peak-to-trough (native units, oc_bullbook convention; dip identical in both variants)",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_scaled": round(full_dd_s, 6),
            "total_pnl_base": round(float(np.sum(pnl_b)), 6),
            "total_pnl_scaled": round(float(np.sum(pnl_s)), 6),
        },
        "loyo": {"dd_stability": f"{loyo_dd}/5", "retention_stability": f"{loyo_ret}/5"},
        "decision": {
            "dd_improve_count": f"{dd_wins}/5",
            "retention_ge90_count": f"{ret_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    print(json.dumps(res["loyo"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
