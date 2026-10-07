"""oc_bookcoinwf: walk-forward per-coin book gating (idea #38, PLAN.md frozen first).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with v154 4h opens, screen with open-to-open 4h returns and 0.0005/unit
turnover costs. For year Y_k, trade only coins with cumulative book P&L over
ALL grid bars T with T < A_k - 7d (from 2020-08) strictly positive; year 1 has
empty history -> fall back to the full book. Single light process (4h only).

  python research/tournament/oc_bookcoinwf/compute_bookcoinwf.py
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
HIST_START = pd.Timestamp("2020-08-01", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
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
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)

    o = opens[SYMS]
    ot = opens.index
    fwd1 = o.shift(-1) / o - 1.0
    keep = (ot.shift(-1) <= CUTOFF)
    books, opens = books[keep], opens[keep]
    fwd1 = fwd1.reindex(books.index)
    valid1 = fwd1.notna().all(axis=1)
    books, opens = books[valid1], opens[valid1]
    fwd1 = fwd1.reindex(books.index)
    grid = books.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({
            "T": grid, "sym": s,
            "w": books[s].to_numpy(float),
            "r1": fwd1[s].reindex(grid).to_numpy(float),
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)

    w = panel["w"].to_numpy(float)
    r1 = panel["r1"].to_numpy(float)
    T = panel["T"].to_numpy()
    sym = panel["sym"].to_numpy()

    # Full-book turnover costs in grid order per sym (first bar prev = 0).
    cost = np.zeros(len(panel))
    for s in SYMS:
        sm = sym == s
        idx = np.where(sm)[0]
        order = np.argsort(T[idx])
        ii = idx[order]
        ww = w[ii]
        prev_w = np.concatenate([[0.0], ww[:-1]])
        cost[ii] = COST * np.abs(ww - prev_w)
    pnl = w * r1 - cost
    panel["cost"] = cost
    panel["pnl"] = pnl

    bounds = ANCHORS + [LAST_BOUND]
    year_m = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy()
              for k in range(5)]

    # History P&L per (anchor, coin) over H_k = {T < A_k - 7d}, same cells.
    hist_sums: list[dict] = []
    gated_sets: list[list] = []
    fallbacks: list[bool] = []
    for k, a0 in enumerate(ANCHORS):
        hm = (panel["T"] < a0 - EMBARGO) & (panel["T"] >= HIST_START)
        hm = hm.to_numpy()
        per = {}
        for s in SYMS:
            per[s] = float(np.sum(pnl[hm & (sym == s)])) if hm.sum() else 0.0
        hist_sums.append(per)
        if int(hm.sum()) == 0:
            gated_sets.append(list(SYMS))
            fallbacks.append(True)
        else:
            gated_sets.append([s for s in SYMS if per[s] > 0])
            fallbacks.append(False)

    # Gated weights: per year, keep gated coins, zero others.
    w_g = np.zeros(len(panel))
    for k in range(5):
        gset = set(gated_sets[k])
        m = year_m[k]
        for s in SYMS:
            sm = m & (sym == s)
            if s in gset:
                w_g[sm] = w[sm]
            else:
                w_g[sm] = 0.0

    cost_g = np.zeros(len(panel))
    for s in SYMS:
        sm = sym == s
        idx = np.where(sm)[0]
        order = np.argsort(T[idx])
        ii = idx[order]
        gg = w_g[ii]
        prev_g = np.concatenate([[0.0], gg[:-1]])
        cost_g[ii] = COST * np.abs(gg - prev_g)
    pnl_g = w_g * r1 - cost_g
    panel["w_g"] = w_g
    panel["cost_g"] = cost_g
    panel["pnl_g"] = pnl_g
    panel.to_parquet(HERE / "panel.parquet")

    years = []
    pnl_wins = 0
    dd_wins = 0
    bar = panel.groupby("T", sort=True)[["pnl", "pnl_g"]].sum().sort_index()
    bar_idx = bar.index
    for k, a0 in enumerate(ANCHORS):
        m = year_m[k]
        sel = np.asarray((bar_idx >= bounds[k]) & (bar_idx < bounds[k + 1]))
        rp = bar["pnl"].to_numpy()[sel]
        rp_g = bar["pnl_g"].to_numpy()[sel]
        eq = equity_path(rp)
        eq_g = equity_path(rp_g)
        dd, dd_g = max_dd(eq), max_dd(eq_g)
        ww, ww_g = worst_week(eq), worst_week(eq_g)
        tot = float(np.sum(pnl[m]))
        tot_g = float(np.sum(pnl_g[m]))
        per_full = {s: float(np.sum(pnl[m & (sym == s)])) for s in SYMS}
        per_g = {s: float(np.sum(pnl_g[m & (sym == s)])) for s in SYMS}
        row = {
            "year": str(a0.date()),
            "n_rows": int(m.sum()),
            "hist_sums": {s: round(hist_sums[k][s], 6) for s in SYMS},
            "gated_coins": gated_sets[k],
            "fallback": bool(fallbacks[k]),
            "per_coin_pnl": {s: round(per_full[s], 6) for s in SYMS},
            "per_coin_pnl_gated": {s: round(per_g[s], 6) for s in SYMS},
            "total_pnl": round(tot, 6),
            "total_pnl_gated": round(tot_g, 6),
            "worst_week": round(ww, 6),
            "worst_week_gated": round(ww_g, 6),
            "maxDD": round(dd, 6),
            "maxDD_gated": round(dd_g, 6),
            "pnl_not_lower": bool(tot_g >= tot),
            "dd_not_worse": bool(dd_g <= dd),
        }
        years.append(row)
        pnl_wins += int(row["pnl_not_lower"])
        dd_wins += int(row["dd_not_worse"])

    rp_full = bar["pnl"].to_numpy()
    rp_full_g = bar["pnl_g"].to_numpy()
    full_dd = max_dd(equity_path(rp_full))
    full_dd_g = max_dd(equity_path(rp_full_g))

    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "rule": "year Y: trade only coins with cumulative book P&L over T < anchor(Y)-7d (from 2020-08) > 0; year 1 empty history -> full book fallback",
            "costs": "0.0005 per unit turnover (|w - w_prev| per sym, first prev=0; gated path own chain)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
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
            "pnl_not_lower_count": f"{pnl_wins}/5",
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
