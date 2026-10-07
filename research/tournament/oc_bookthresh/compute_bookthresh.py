"""oc_bookthresh: book signal-strength threshold (idea #48, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
apply the v410 bear-long filter FIRST (longs x0.5 when BTC 4h open < 1200-bar
mean on FULL opens history) as BASE, then zero weak targets per coin:
w_rule[T,s] = 0 iff |w_base[T,s]| < q25_{k,s}, where q25 is the walk-forward
25th percentile of |w_base| over screened-panel rows U < A_k per coin
(year 0: empty pool -> rule inactive). Screen with open-to-open 4h returns
and gate costs (maker 0.0002 per unit turnover, each path own prev).
Single light process (4h inputs only, no 1m).

  python research/tournament/oc_bookthresh/compute_bookthresh.py
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
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens[SYMS].shift(-1) / opens[SYMS] - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # v410 bear filter FIRST (BTC-only, causal at close of T, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    w_raw = books_raw[SYMS].to_numpy(float)  # (n_bars, n_syms)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * 0.5, w_raw)
    r1 = fwd1[SYMS].to_numpy(float)

    # Walk-forward per-coin q25 of |w_base| over screened rows U < A_k (zeros incl).
    abase = np.abs(w_base)
    q25: dict[tuple[int, int], float] = {}
    for k, a0 in enumerate(ANCHORS):
        tr = np.asarray(grid < a0)
        for j in range(len(SYMS)):
            if int(tr.sum()) == 0:
                q25[(k, j)] = float("nan")
            else:
                q25[(k, j)] = float(np.quantile(abase[tr, j], 0.25))

    bounds = ANCHORS + [LAST_BOUND]
    year_of_bar = np.zeros(len(grid), dtype=int)
    for k in range(5):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        year_of_bar[m] = k

    # Rule: zero weak targets (strict <); year 0 inactive (NaN threshold).
    w_rule = w_base.copy()
    zeroed = np.zeros_like(w_base, dtype=bool)
    for k in range(5):
        m = year_of_bar == k
        for j in range(len(SYMS)):
            q = q25[(k, j)]
            if not np.isfinite(q):
                continue
            z = m & (np.abs(w_base[:, j]) < q)
            zeroed[z, j] = True
    w_rule[zeroed] = 0.0

    # Turnover costs in grid order per sym (first bar prev = 0; each path own prev).
    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_rule = w_rule * r1 - cost_rule

    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    # Per-(T,sym) panel (small).
    q25_mat = np.array([[q25[(k, j)] for j in range(len(SYMS))] for k in year_of_bar])
    rows = []
    for j, s in enumerate(SYMS):
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w_raw": w_raw[:, j],
            "w_base": w_base[:, j],
            "w_rule": w_rule[:, j],
            "bear": bear,
            "q25": q25_mat[:, j],
            "zeroed": zeroed[:, j],
            "r1": r1[:, j],
            "cost_base": cost_base[:, j],
            "cost_rule": cost_rule[:, j],
            "pnl_base": pnl_base[:, j],
            "pnl_rule": pnl_rule[:, j],
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    years = []
    pnl_wins = 0
    dd_wins = 0
    d_list = []
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp_b = rp_base[m]
        rp_r = rp_rule[m]
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        pb = float(pnl_base[m].sum())
        pr = float(pnl_rule[m].sum())
        cb = float(cost_base[m].sum())
        cr = float(cost_rule[m].sum())
        pnl_win = bool(pr > pb)
        dd_win = bool(np.isfinite(dd_b) and np.isfinite(dd_r) and dd_r <= dd_b + 1e-12)
        pnl_wins += int(pnl_win)
        dd_wins += int(dd_win)
        d_list.append(pr - pb)
        zb = zeroed[m]
        share_new = float(zb[w_base[m] != 0].mean()) if (w_base[m] != 0).sum() else 0.0
        per_coin = {}
        per_q = {}
        for j, s in enumerate(SYMS):
            per_q[s] = None if not np.isfinite(q25[(k, j)]) else round(float(q25[(k, j)]), 6)
            col = zb[:, j]
            base_col = w_base[m, j]
            per_coin[s] = round(float(col[base_col != 0].mean()) if (base_col != 0).sum() else 0.0, 6)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "share_bear": round(float(bear[m].mean()) if m.sum() else 0.0, 6),
            "q25": per_q,
            "share_rows_zeroed_new": round(float((zeroed[m] & (w_base[m] != 0)).mean()), 6),
            "share_nonzero_zeroed": round(share_new, 6),
            "zeroed_share_per_coin": per_coin,
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "d_pnl": round(pr - pb, 6),
            "pnl_higher": pnl_win,
            "turnover_cost_base": round(cb, 6),
            "turnover_cost_rule": round(cr, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_win,
        })

    # LOYO side row on the book-P&L effect (descriptive only, NOT part of verdict).
    d = np.array(d_list, dtype=float)
    loyo = []
    for h in range(5):
        tr = [d[k] for k in range(5) if k != h]
        mrt = float(np.mean(tr))
        loyo.append(bool(np.isfinite(mrt) and mrt > 0 and np.sign(d[h]) == np.sign(mrt)))
    loyo_n = int(sum(loyo))

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter FIRST: longs x0.5 when BTC open < 1200-bar mean (rolling 1200, min 600, open[T] inclusive; NaN->False)",
            "rule": "per-coin walk-forward signal-strength threshold: w_rule=0 iff |w_base| < q25_{k,s} (25th pct of |w_base| over screened rows U<A_k per coin, zeros incl); year 0 pool empty -> rule inactive",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()),
            "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "loyo_pnl": {"per_heldout": loyo, "count": f"{loyo_n}/5",
                     "note": "descriptive stability only (positive-effect sign agreement); NOT part of the verdict"},
        "full_path": {
            "maxDD_base": round(full_dd_b, 6),
            "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_rule": round(float(rp_rule.sum()), 6),
            "total_cost_base": round(float(cost_base.sum()), 6),
            "total_cost_rule": round(float(cost_rule.sum()), 6),
        },
        "decision": {
            "pnl_higher_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
            "rule": "PROMISING iff net book P&L higher (rule>base) in >=4/5 years AND maxDD not worse (rule<=base) in >=4/5",
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    print(res["loyo_pnl"])


if __name__ == "__main__":
    main()
