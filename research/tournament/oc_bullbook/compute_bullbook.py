"""oc_bullbook: bull-regime book boost (idea #26, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as
oc_dvolshort), join with v154 4h opens, apply the audited v410 bear-long
filter (longs x0.5 in bear) as BASE, then BOOST = BASE with longs x1.25 on
bullboost rows (BTC 4h open > its 1200-bar mean AND 180-bar return > 0).
Screen with open-to-open 4h returns and 0.05% per unit L1 turnover (each
path with its own prev). Book path compounded per-bar per year (as
oc_dvolshort); dip stream via harness5.load (as oc_idea7) for the combined
daily maxDD context. Single light process (4h + fills only, no 1m).

  python research/tournament/oc_bullbook/compute_bullbook.py
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
YEAR_END = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
COST = 0.0005


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


def build_regimes(opens_full: pd.DataFrame, grid: pd.DatetimeIndex):
    """Causal bull/bear + 180-bar confirmation, mirrored from v410/oc_bullshort.

    MA1200[T] = mean(BTC_open[T-1199..T]) on the FULL history, then reindexed
    to grid. bear = open < MA, bull = open > MA (strict, NaN -> neither).
    ret180 = open[T]/open[T-180]-1 on the FULL history. bullboost = bull & ret180>0.
    """
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    ret180_full = btc / btc.shift(180) - 1.0
    bear = (btc < ma).fillna(False).reindex(grid).fillna(False)
    bull = (btc > ma).fillna(False).reindex(grid).fillna(False)
    ret180 = ret180_full.reindex(grid)
    bullboost = (bull & (ret180 > 0)).fillna(False)
    return bear, bull, ret180, bullboost


def apply_filters(books: pd.DataFrame, bear: pd.Series, bullboost: pd.Series):
    """BASE = bear-long x0.5; BOOST = BASE + bullboost-long x1.25 (PLAN.md)."""
    arr = books.to_numpy()
    bear_arr = bear.to_numpy()[:, None]
    boost_arr = bullboost.to_numpy()[:, None]
    base_arr = np.where(bear_arr & (arr > 0), arr * 0.5, arr)
    boost_arr_w = np.where(boost_arr & (base_arr > 0), base_arr * 1.25, base_arr)
    idx, cols = books.index, books.columns
    return (pd.DataFrame(base_arr, index=idx, columns=cols),
            pd.DataFrame(boost_arr_w, index=idx, columns=cols))


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def worst_week(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 43:
        return float(eq[-1] / eq[0] - 1.0) if len(eq) > 1 else 0.0
    return float(np.min(eq[42:] / eq[:-42] - 1.0))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def main() -> None:
    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens[SYMS].shift(-1) / opens[SYMS] - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    bear, bull, ret180, bullboost = build_regimes(opens_full, grid)
    w_base, w_boost = apply_filters(books_raw, bear, bullboost)

    # Turnover costs in grid order per sym (first bar prev = 0; own-path prev).
    panel = pd.DataFrame({"T": grid})
    cost, cost_g = {}, {}
    for name, w in (("base", w_base), ("boost", w_boost)):
        prev = w.shift(1).fillna(0.0)
        c = (COST * (w - prev).abs())
        if name == "base":
            cost = c
        else:
            cost_g = c
    pnl_base = w_base * fwd1 - cost
    pnl_boost = w_boost * fwd1 - cost_g
    rp_base = pnl_base.sum(axis=1)
    rp_boost = pnl_boost.sum(axis=1)

    bounds = ANCHORS + [YEAR_END]
    masks = [((grid >= bounds[k]) & (grid < bounds[k + 1])) for k in range(5)]

    long_rows = (books_raw > 0)
    years = []
    pnl_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray(masks[k])
        bear_m = bear.to_numpy()[m]
        bullboost_m = bullboost.to_numpy()[m]
        long_m = long_rows.to_numpy()[m]
        rpb = rp_base[m].to_numpy(float)
        rpg = rp_boost[m].to_numpy(float)
        eqb, eqg = equity_path(rpb), equity_path(rpg)
        ddb, ddg = max_dd(eqb), max_dd(eqg)
        wwb, wwg = worst_week(eqb), worst_week(eqg)
        tot_b = float(pnl_base[m].to_numpy().sum())
        tot_g = float(pnl_boost[m].to_numpy().sum())
        lng_b = float(pnl_base[m].where(long_rows[m]).sum().sum())
        lng_g = float(pnl_boost[m].where(long_rows[m]).sum().sum())
        ret_b = float(eqb[-1] - 1.0)
        ret_g = float(eqg[-1] - 1.0)
        pnl_win = bool(tot_g > tot_b)
        dd_win = bool(ddg < ddb)
        pnl_wins += int(pnl_win)
        dd_wins += int(dd_win)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "share_bear": round(float(bear_m.mean()), 6),
            "share_bullboost": round(float(bullboost_m.mean()), 6),
            "share_long_boosted": round(float((bullboost_m[:, None] & long_m).mean()), 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_boost": round(tot_g, 6),
            "d_pnl": round(tot_g - tot_b, 6),
            "pnl_higher": pnl_win,
            "book_ret_base": round(ret_b, 6),
            "book_ret_boost": round(ret_g, 6),
            "long_pnl_base": round(lng_b, 6),
            "long_pnl_boost": round(lng_g, 6),
            "worst_week_base": round(wwb, 6),
            "worst_week_boost": round(wwg, 6),
            "maxDD_base": round(ddb, 6),
            "maxDD_boost": round(ddg, 6),
            "dd_not_worse": dd_win,
        })

    # LOYO stability side row on the book-P&L effect (no fitted param; descriptive).
    d = np.array([y["d_pnl"] for y in years], dtype=float)
    loyo = []
    for h in range(5):
        tr = [d[k] for k in range(5) if k != h]
        mrt = float(np.mean(tr))
        loyo.append(bool(np.isfinite(mrt) and mrt > 0 and np.sign(d[h]) == np.sign(mrt)))
    loyo_n = int(sum(loyo))

    # Full-path context (compounded from year-1 start, no reset).
    full_dd_b = max_dd(equity_path(rp_base.to_numpy(float)))
    full_dd_g = max_dd(equity_path(rp_boost.to_numpy(float)))

    # --- Combined (book + dip) daily maxDD context ---
    # Dip stream exactly as oc_idea7: harness5.load, majors + size_dep (BOT rungs), y_dep.
    dip = H5.load()
    dip["T"] = pd.to_datetime(dip["T"], utc=True)
    is_bot = dip["sym"].isin(H5.MAJORS) & dip["size_dep"].notna()
    dip = dip[is_bot & (dip["T"] >= ANCHORS[0]) & (dip["T"] < CUTOFF)].copy()
    dip["dv"] = dip["size_dep"].to_numpy(float) * dip["y_dep"].to_numpy(float)
    dip_daily = dip.groupby(dip["T"].dt.floor("D"))["dv"].sum()
    book_daily_b = rp_base.groupby(rp_base.index.floor("D")).sum()
    book_daily_g = rp_boost.groupby(rp_boost.index.floor("D")).sum()
    all_days = dip_daily.index.union(book_daily_b.index).union(book_daily_g.index).sort_values()
    dd_b = dip_daily.reindex(all_days).fillna(0.0)
    bb_b = book_daily_b.reindex(all_days).fillna(0.0)
    bb_g = book_daily_g.reindex(all_days).fillna(0.0)
    # Linear cumulative path (POST-HOC FIX, see REPORT.md): dip daily sums are
    # size*y native units, NOT fractions of equity (observed days < -1), so
    # compounding (1+C) is invalid. Combined context uses the per-year linear
    # path L[d] = cumsum(C) reset to 0 and peak-to-trough decline in units.
    def lin_dd(path: np.ndarray) -> float:
        if len(path) == 0:
            return float("nan")
        peak = np.maximum.accumulate(np.concatenate([[0.0], path]))
        return float(np.max(peak - np.concatenate([[0.0], path])))
    combined = []
    for k, a0 in enumerate(ANCHORS):
        dm = (all_days >= bounds[k]) & (all_days < bounds[k + 1])
        cb = (bb_b[dm] + dd_b[dm]).to_numpy(float)
        cg = (bb_g[dm] + dd_b[dm]).to_numpy(float)
        wd_b = float(pd.Series(cb).min()) if len(cb) else float("nan")
        wd_g = float(pd.Series(cg).min()) if len(cg) else float("nan")
        ddb_c, ddg_c = lin_dd(cb), lin_dd(cg)
        combined.append({
            "year": str(a0.date()),
            "n_days": int(dm.sum()),
            "dip_daily_sum": round(float(dd_b[dm].sum()), 6),
            "book_daily_sum_base": round(float(bb_b[dm].sum()), 6),
            "book_daily_sum_boost": round(float(bb_g[dm].sum()), 6),
            "comb_maxDD_base": round(ddb_c, 6),
            "comb_maxDD_boost": round(ddg_c, 6),
            "comb_dd_not_worse": bool(ddg_c < ddb_c),
            "comb_worst_day_base": round(wd_b, 6),
            "comb_worst_day_boost": round(wd_g, 6),
        })

    promising = bool(pnl_wins >= 4 and dd_wins >= 3)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_bookic)",
            "opens": "engine_real opens_v154.parquet",
            "rule": "BASE: longs x0.5 in bear (BTC open < 1200-bar mean); BOOST: BASE + longs x1.25 where BTC open > 1200-bar mean AND 180-bar return > 0",
            "ma": "rolling(1200, min_periods=600) on full BTC history, strict inequalities, NaN -> neither",
            "costs": "0.0005 per unit L1 turnover (|w - w_prev| per sym, first prev=0, own-path prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "dip": "harness5.load majors+size_dep (BOT rungs), y_dep exact net; daily sums by UTC day; combined daily = book daily + dip daily; combined path LINEAR cumsum (dip units are not equity fractions, compounding invalid) with peak-to-trough decline in native units (vectorised-screen context, NOT engine equity)",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
        },
        "years": years,
        "loyo_pnl": {"per_heldout": loyo, "count": f"{loyo_n}/5",
                     "note": "descriptive stability only (no fitted parameter); NOT part of the verdict"},
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_boost": round(full_dd_g, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_boost": round(float(rp_boost.sum()), 6),
        },
        "combined_daily": combined,
        "totals": {
            "total_turnover_base": round(float(cost.sum().sum()), 6) if hasattr(cost, "sum") else None,
        },
        "decision": {
            "pnl_higher_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
            "rule": "PROMISING iff book P&L higher in >=4/5 years AND book maxDD not worse in >=3/5",
        },
    }
    # turnover/cost totals (cost frames hold per-cell costs)
    res["totals"] = {
        "total_turnover_base": round(float(((w_base - w_base.shift(1).fillna(0.0)).abs().sum().sum())), 4),
        "total_turnover_boost": round(float(((w_boost - w_boost.shift(1).fillna(0.0)).abs().sum().sum())), 4),
        "total_cost_base": round(float(cost.sum().sum()), 6),
        "total_cost_boost": round(float(cost_g.sum().sum()), 6),
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    for c in combined:
        print(c)


if __name__ == "__main__":
    main()
