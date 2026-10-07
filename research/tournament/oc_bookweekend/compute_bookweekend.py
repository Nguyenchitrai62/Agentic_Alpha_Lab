"""oc_bookweekend: book flat on weekends (idea #50, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with the v154 4h opens, apply the audited v410 bear-long filter FIRST
(BASE = control), then force RULE weights to 0 on holding bars starting
between Sat 00:00 and Mon 00:00 UTC (weekday 5/6). Screen with open-to-open
4h returns and assignment costs (0.0005 per unit turnover, each path own
prev). Single light process (4h inputs only, no 1m).

  python research/tournament/oc_bookweekend/compute_bookweekend.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0005


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


def bear_flags(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> np.ndarray:
    """v410 bear flag on the FULL BTC opens history, reindexed to grid."""
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid)
    return bear.fillna(False).to_numpy(bool)


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
    bear = bear_flags(opens_full, grid)
    w0 = books_raw[SYMS].to_numpy(float)  # (n_bars, 5)
    base = w0.copy()
    pos = w0 > 0
    base[bear[:, None] & pos] = 0.5 * w0[bear[:, None] & pos]

    # Weekend-flat rule: holding bars starting Sat 00:00 .. Mon 00:00 -> 0.
    weekend = np.asarray(grid.weekday) >= 5
    rule = base.copy()
    rule[weekend, :] = 0.0

    r1 = fwd1[SYMS].to_numpy(float)

    # Turnover costs in grid order per sym (first bar prev = 0), each path own prev.
    cost_b = np.zeros_like(base)
    cost_r = np.zeros_like(base)
    for j in range(len(SYMS)):
        wb, wr = base[:, j], rule[:, j]
        cost_b[:, j] = MAKER * np.abs(wb - np.concatenate([[0.0], wb[:-1]]))
        cost_r[:, j] = MAKER * np.abs(wr - np.concatenate([[0.0], wr[:-1]]))
    pnl_b = base * r1 - cost_b
    pnl_r = rule * r1 - cost_r

    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), len(grid)),
        "bear": np.repeat(bear, len(SYMS)),
        "weekend": np.repeat(weekend, len(SYMS)),
        "w_raw": w0.reshape(-1),
        "w_base": base.reshape(-1),
        "w_rule": rule.reshape(-1),
        "r1": r1.reshape(-1),
        "cost_base": cost_b.reshape(-1),
        "cost_rule": cost_r.reshape(-1),
        "pnl_base": pnl_b.reshape(-1),
        "pnl_rule": pnl_r.reshape(-1),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bar_b = pd.Series(pnl_b.sum(axis=1), index=grid)
    bar_r = pd.Series(pnl_r.sum(axis=1), index=grid)
    wk = weekend

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    pnl_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp_b = bar_b.to_numpy()[m]
        rp_r = bar_r.to_numpy()[m]
        eq_b, eq_r = equity_path(rp_b), equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        tot_b = float(np.sum(pnl_b[m]))
        tot_r = float(np.sum(pnl_r[m]))
        wend_b = float(np.sum(pnl_b[m][wk[m]]))
        wday_b = float(np.sum(pnl_b[m][~wk[m]]))
        cost_tot_b = float(np.sum(cost_b[m]))
        cost_tot_r = float(np.sum(cost_r[m]))
        comp_b = float(eq_b[-1] - 1.0)
        comp_r = float(eq_r[-1] - 1.0)
        pnl_ok = bool(tot_r >= tot_b)
        dd_ok = bool(dd_r <= dd_b)
        row = {
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "weekend_share": round(float(wk[m].mean()), 6),
            "base_weekend_pnl": round(wend_b, 6),
            "base_weekday_pnl": round(wday_b, 6),
            "cost_base": round(cost_tot_b, 6),
            "cost_rule": round(cost_tot_r, 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_rule": round(tot_r, 6),
            "comp_base": round(comp_b, 6),
            "comp_rule": round(comp_r, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "pnl_not_lower": pnl_ok,
            "dd_not_worse": dd_ok,
        }
        years.append(row)
        pnl_wins += int(pnl_ok)
        dd_wins += int(dd_ok)

    full_dd_b = max_dd(equity_path(bar_b.to_numpy()))
    full_dd_r = max_dd(equity_path(bar_r.to_numpy()))

    pnl_ind = np.array([y["pnl_not_lower"] for y in years], dtype=bool)
    dd_ind = np.array([y["dd_not_worse"] for y in years], dtype=bool)
    loyo_pnl = sum(bool(pnl_ind[h] == (np.sum(pnl_ind[np.arange(5) != h]) >= 3)) for h in range(5))
    loyo_dd = sum(bool(dd_ind[h] == (np.sum(dd_ind[np.arange(5) != h]) >= 3)) for h in range(5))

    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "rule": "RULE: holding bars starting Sat 00:00..Mon 00:00 UTC (weekday 5/6) -> target 0, else BASE",
            "costs": "0.0005 per unit turnover (|w - w_prev| per sym, first prev=0; each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "weekend_cost_note": "cost of bar T attributed to bar T: Sat-00:00 close cost in weekend leg, Mon-00:00 reopen cost in weekday leg",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(np.sum(pnl_b)), 6),
            "total_pnl_rule": round(float(np.sum(pnl_r)), 6),
        },
        "loyo": {"pnl_stability": f"{loyo_pnl}/5", "dd_stability": f"{loyo_dd}/5"},
        "decision": {
            "pnl_not_lower_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    print(json.dumps(res["loyo"], indent=1))
    for y in years:
        print({k: y[k] for k in (
            "year", "n_bars", "weekend_share", "base_weekend_pnl",
            "base_weekday_pnl", "book_pnl_base", "book_pnl_rule",
            "worst_week_base", "worst_week_rule", "maxDD_base",
            "maxDD_rule", "pnl_not_lower", "dd_not_worse")})


if __name__ == "__main__":
    main()
