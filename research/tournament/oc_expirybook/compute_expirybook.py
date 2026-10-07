"""oc_expirybook: options-expiry 48h gate on the BOOK (idea #62, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with the v154 4h opens, apply the audited v410 bear-long filter FIRST
(BASE = control), then halve ALL book targets on holding bars starting in
[E - 48h, E) for Deribit monthly BTC expiry E = last Friday of month 08:00 UTC
(RULE). Screen with open-to-open 4h returns and oc_dvolshort costs
(maker 0.0002 per unit turnover, each path own prev). Single light process
(4h inputs only, no 1m).

  python research/tournament/oc_expirybook/compute_expirybook.py
"""
from __future__ import annotations

import calendar
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
MAKER = 0.0002


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


def expiry(y: int, m: int) -> pd.Timestamp:
    """Last Friday of month m, 08:00 UTC (Deribit monthly expiry)."""
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7  # Friday == 4
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


def expiries() -> pd.DataFrame:
    rows = []
    for y in range(2021, 2027):
        for mm in range(1, 13):
            e = expiry(y, mm)
            if e < pd.Timestamp("2021-01-01", tz="UTC") or e >= CUTOFF + pd.Timedelta(days=1):
                continue
            rows.append(dict(E=e))
    return pd.DataFrame(rows)


def in_expiry_window(t: pd.DatetimeIndex, exp: pd.DataFrame) -> np.ndarray:
    """Vectorised flag: T in [E - 48h, E) for some expiry E (pure timestamps)."""
    ti = t.astype("int64").to_numpy()
    H = np.int64(3_600_000_000_000)
    flag = np.zeros(len(t), bool)
    for r in exp.itertuples():
        e = np.int64(r.E.value)
        flag |= (ti >= e - np.int64(48) * H) & (ti < e)
    return flag


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
    exp = expiries()
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
    print(f"expiries: {len(exp)} {exp['E'].min()}..{exp['E'].max()}", flush=True)

    # Bear filter FIRST (v410): BASE is the control path.
    bear = bear_flags(opens_full, grid)
    w0 = books_raw[SYMS].to_numpy(float)  # (n_bars, 5)
    base = w0.copy()
    pos = w0 > 0
    base[bear[:, None] & pos] = 0.5 * w0[bear[:, None] & pos]

    # Expiry 48h gate: holding bars starting in [E-48h, E) -> x0.5 both sides.
    inexp = in_expiry_window(grid, exp)
    rule = base.copy()
    rule[inexp, :] = 0.5 * base[inexp, :]

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
        "in_exp": np.repeat(inexp, len(SYMS)),
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
    wx = inexp

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    ret_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp_b = bar_b.to_numpy()[m]
        rp_r = bar_r.to_numpy()[m]
        eq_b, eq_r = equity_path(rp_b), equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        tot_b = float(np.sum(pnl_b[m]))
        tot_r = float(np.sum(pnl_r[m]))
        win_b = float(np.sum(pnl_b[m][wx[m]]))
        win_r = float(np.sum(pnl_r[m][wx[m]]))
        out_b = float(np.sum(pnl_b[m][~wx[m]]))
        out_r = float(np.sum(pnl_r[m][~wx[m]]))
        cost_tot_b = float(np.sum(cost_b[m]))
        cost_tot_r = float(np.sum(cost_r[m]))
        comp_b = float(eq_b[-1] - 1.0)
        comp_r = float(eq_r[-1] - 1.0)
        dd_ok = bool(dd_r <= dd_b)
        if tot_b > 0:
            ret = tot_r / tot_b
            ret_ok = bool(tot_r >= 0.98 * tot_b)
        else:
            ret = None
            ret_ok = bool(tot_r >= tot_b)
        row = {
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "n_exp_bars": int(wx[m].sum()),
            "exp_share": round(float(wx[m].mean()), 6),
            "win_pnl_base": round(win_b, 6),
            "win_pnl_rule": round(win_r, 6),
            "out_pnl_base": round(out_b, 6),
            "out_pnl_rule": round(out_r, 6),
            "cost_base": round(cost_tot_b, 6),
            "cost_rule": round(cost_tot_r, 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_rule": round(tot_r, 6),
            "retention": round(ret, 6) if ret is not None else None,
            "comp_base": round(comp_b, 6),
            "comp_rule": round(comp_r, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_ok,
            "retention_ge98": ret_ok,
        }
        years.append(row)
        dd_wins += int(dd_ok)
        ret_wins += int(ret_ok)

    full_dd_b = max_dd(equity_path(bar_b.to_numpy()))
    full_dd_r = max_dd(equity_path(bar_r.to_numpy()))

    promising = bool(dd_wins >= 4 and ret_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "rule": "RULE: holding bars starting in [E-48h, E) for E = last Friday of month 08:00 UTC -> target x0.5 both sides, else BASE",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0; each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "expiries": f"{len(exp)} monthly expiries 2021-01..2026-09",
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
        "decision": {
            "dd_not_worse_count": f"{dd_wins}/5",
            "retention_ge98_count": f"{ret_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print({k: y[k] for k in (
            "year", "n_bars", "n_exp_bars", "exp_share", "win_pnl_base",
            "win_pnl_rule", "book_pnl_base", "book_pnl_rule", "retention",
            "worst_week_base", "worst_week_rule", "maxDD_base",
            "maxDD_rule", "dd_not_worse", "retention_ge98")})


if __name__ == "__main__":
    main()
