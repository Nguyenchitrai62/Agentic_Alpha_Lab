"""oc_longcap: total book-long cap (idea #46, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with the v154 4h opens, apply the audited v410 bear-long filter FIRST
(BASE = control), then cap the total LONG sum at 0.6 of equity per bar:
if L(T) = sum of positive BASE weights > 0.6, scale all longs by 0.6/L(T);
shorts/flats unchanged. Screen with open-to-open 4h returns and gate costs
(maker 0.0002 per unit turnover, each path with its own prev). Single light
process (4h inputs only, no 1m).

  python research/tournament/oc_longcap/compute_longcap.py
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
CAP = 0.6
WIN_START = pd.Timestamp("2023-04-17 00:00", tz="UTC")
WIN_END = pd.Timestamp("2023-06-15 12:00", tz="UTC")


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


def longsum_dist(L: np.ndarray) -> dict:
    L = np.asarray(L, dtype=float)
    return {
        "mean": round(float(np.mean(L)), 6),
        "p50": round(float(np.quantile(L, 0.50)), 6),
        "p75": round(float(np.quantile(L, 0.75)), 6),
        "p90": round(float(np.quantile(L, 0.90)), 6),
        "p95": round(float(np.quantile(L, 0.95)), 6),
        "p99": round(float(np.quantile(L, 0.99)), 6),
        "max": round(float(np.max(L)), 6),
        "share_gt_06": round(float((L > 0.6).mean()), 6),
        "share_gt_08": round(float((L > 0.8).mean()), 6),
        "share_gt_10": round(float((L > 1.0).mean()), 6),
        "mean_L_when_binding": round(float(L[L > 0.6].mean()), 6) if (L > 0.6).any() else None,
    }


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

    # Long cap at 0.6 (fixed): scale longs proportionally on binding bars.
    L = np.where(base > 0, base, 0.0).sum(axis=1)
    binding = L > CAP
    scale = np.ones(len(grid))
    scale[binding] = CAP / L[binding]
    capped = np.where(pos, base * scale[:, None], base)

    r1 = fwd1[SYMS].to_numpy(float)

    # Turnover costs in grid order per sym (first bar prev = 0), each path own prev.
    cost_b = np.zeros_like(base)
    cost_c = np.zeros_like(base)
    for j in range(len(SYMS)):
        wb, wc = base[:, j], capped[:, j]
        cost_b[:, j] = MAKER * np.abs(wb - np.concatenate([[0.0], wb[:-1]]))
        cost_c[:, j] = MAKER * np.abs(wc - np.concatenate([[0.0], wc[:-1]]))
    pnl_b = base * r1 - cost_b
    pnl_c = capped * r1 - cost_c

    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), len(grid)),
        "bear": np.repeat(bear, len(SYMS)),
        "L": np.repeat(L, len(SYMS)),
        "scale": np.repeat(scale, len(SYMS)),
        "binding": np.repeat(binding, len(SYMS)),
        "is_long": (base > 0).reshape(-1),
        "w_base": base.reshape(-1),
        "w_capped": capped.reshape(-1),
        "r1": r1.reshape(-1),
        "cost_base": cost_b.reshape(-1),
        "cost_capped": cost_c.reshape(-1),
        "pnl_base": pnl_b.reshape(-1),
        "pnl_capped": pnl_c.reshape(-1),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bar_b = pd.Series(pnl_b.sum(axis=1), index=grid)
    bar_c = pd.Series(pnl_c.sum(axis=1), index=grid)
    is_long = base > 0
    is_short = base < 0

    longsum_all = longsum_dist(L)
    mean_scale_binding = round(float(scale[binding].mean()), 6) if binding.any() else None
    longsum_all["mean_scale_when_binding"] = mean_scale_binding
    longsum_all["n_bars"] = int(len(grid))

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    ret_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp_b = bar_b.to_numpy()[m]
        rp_c = bar_c.to_numpy()[m]
        eq_b, eq_c = equity_path(rp_b), equity_path(rp_c)
        dd_b, dd_c = max_dd(eq_b), max_dd(eq_c)
        ww_b, ww_c = worst_week(eq_b), worst_week(eq_c)
        tot_b = float(np.sum(pnl_b[m]))
        tot_c = float(np.sum(pnl_c[m]))
        long_b = float(np.sum(pnl_b[m][is_long[m]]))
        long_c = float(np.sum(pnl_c[m][is_long[m]]))
        short_b = float(np.sum(pnl_b[m][is_short[m]]))
        short_c = float(np.sum(pnl_c[m][is_short[m]]))
        comp_b = float(eq_b[-1] - 1.0)
        comp_c = float(eq_c[-1] - 1.0)
        dd_ok = bool(dd_c <= dd_b)
        ret_ok = bool(tot_b > 0 and tot_c >= 0.95 * tot_b)
        row = {
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "binding_share": round(float(binding[m].mean()), 6),
            "longsum": longsum_dist(L[m]),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_capped": round(tot_c, 6),
            "retention": round(tot_c / tot_b, 6) if tot_b > 0 else None,
            "long_pnl_base": round(long_b, 6),
            "long_pnl_capped": round(long_c, 6),
            "short_pnl_base": round(short_b, 6),
            "short_pnl_capped": round(short_c, 6),
            "comp_base": round(comp_b, 6),
            "comp_capped": round(comp_c, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_capped": round(ww_c, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_capped": round(dd_c, 6),
            "dd_not_worse": dd_ok,
            "retention_ok": ret_ok,
        }
        years.append(row)
        dd_wins += int(dd_ok)
        ret_wins += int(ret_ok)

    # Gate-grind window 2023-04-17..06-15 (PLAN bounds, 4h grid).
    wm = np.asarray((grid >= WIN_START) & (grid < WIN_END))
    win = {
        "start": str(WIN_START),
        "end": str(WIN_END),
        "n_bars": int(wm.sum()),
        "binding_share": round(float(binding[wm].mean()), 6) if wm.any() else None,
        "book_pnl_base": round(float(np.sum(pnl_b[wm])), 6),
        "book_pnl_capped": round(float(np.sum(pnl_c[wm])), 6),
        "long_pnl_base": round(float(np.sum(pnl_b[wm][is_long[wm]])), 6),
        "long_pnl_capped": round(float(np.sum(pnl_c[wm][is_long[wm]])), 6),
    }

    full_dd_b = max_dd(equity_path(bar_b.to_numpy()))
    full_dd_c = max_dd(equity_path(bar_c.to_numpy()))

    dd_ind = np.array([y["dd_not_worse"] for y in years], dtype=bool)
    ret_ind = np.array([y["retention_ok"] for y in years], dtype=bool)
    loyo_dd = sum(bool(dd_ind[h] == (np.sum(dd_ind[np.arange(5) != h]) >= 3)) for h in range(5))
    loyo_ret = sum(bool(ret_ind[h] == (np.sum(ret_ind[np.arange(5) != h]) >= 3)) for h in range(5))

    promising = bool(dd_wins >= 4 and ret_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "rule": "CAPPED: per bar L = sum of positive BASE weights; if L > 0.6 scale all longs by 0.6/L; shorts/flats unchanged",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0; each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "window": "gate-grind window [2023-04-17 00:00, 2023-06-15 12:00) UTC on the 4h grid (linear net sums)",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "longsum_overall": longsum_all,
        "years": years,
        "window": win,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_capped": round(full_dd_c, 6),
            "total_pnl_base": round(float(np.sum(pnl_b)), 6),
            "total_pnl_capped": round(float(np.sum(pnl_c)), 6),
        },
        "loyo": {"dd_stability": f"{loyo_dd}/5", "retention_stability": f"{loyo_ret}/5"},
        "decision": {
            "dd_not_worse_count": f"{dd_wins}/5",
            "retention_ge95_count": f"{ret_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    print(json.dumps(res["loyo"], indent=1))
    print(json.dumps(longsum_all, indent=1))
    print(json.dumps(win, indent=1))
    for y in years:
        print({k: y[k] for k in (
            "year", "n_bars", "binding_share", "book_pnl_base", "book_pnl_capped",
            "retention", "long_pnl_base", "long_pnl_capped", "worst_week_base",
            "worst_week_capped", "maxDD_base", "maxDD_capped",
            "dd_not_worse", "retention_ok")})


if __name__ == "__main__":
    main()
