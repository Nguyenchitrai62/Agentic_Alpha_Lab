"""oc_coinbear: per-coin bear-book filter (idea #44, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as
oc_dvolshort/oc_bookic), join with the v154 4h opens, apply the audited
v410 BTC-only bear-long filter as BASE (longs x0.5 when BTC 4h open <
its 1200-bar mean), and RULE = longs x0.5 when (BTC bear OR the coin's
own 4h open < its own 1200-bar mean). Shorts/flat unchanged in both.
Screen with open-to-open 4h returns and gate costs (maker 0.0002 per unit
turnover, each path with its own prev), exactly as oc_dvolshort.
Single light process (4h inputs only, no 1m).

  python research/tournament/oc_coinbear/compute_coinbear.py
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
WIN0 = pd.Timestamp("2023-04-17", tz="UTC")
WIN1 = pd.Timestamp("2023-06-15", tz="UTC")


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


def build_bears(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> dict[str, pd.Series]:
    """Per-coin bear flags, causal, mirrored from v410 (rolling 1200, min 600).

    MA1200_s[T] = mean(open_s[T-1199..T]) on the FULL history, then
    reindexed to grid. bear_s = open < MA (strict, NaN -> False).
    Flag at T uses open[T] inclusive (known at close of T, as v410).
    """
    out: dict[str, pd.Series] = {}
    for s in SYMS:
        o = opens_full[s].sort_index()
        ma = o.rolling(1200, min_periods=600).mean()
        bear_full = (o < ma).fillna(False)
        out[s] = bear_full.reindex(grid).fillna(False).astype(bool)
    return out


def apply_filters(
    books: pd.DataFrame, bears: dict[str, pd.Series]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """BASE (v410 BTC-only) and RULE (per-coin OR) filtered weights + newly mask."""
    arr = books.to_numpy()
    btc = bears["BTCUSDT"].to_numpy()[:, None]
    own = np.column_stack([bears[s].to_numpy() for s in books.columns])
    base_arr = np.where(btc & (arr > 0), arr * 0.5, arr)
    rule_arr = np.where((btc | (own > 0)) & (arr > 0), arr * 0.5, arr)
    idx, cols = books.index, books.columns
    base = pd.DataFrame(base_arr, index=idx, columns=cols)
    rule = pd.DataFrame(rule_arr, index=idx, columns=cols)
    newly = pd.DataFrame(
        ((own > 0) & ~(btc > 0)) & (arr > 0), index=idx, columns=cols
    )
    return base, rule, newly


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


def turnover_cost(w: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Maker cost per cell with the path's OWN prev (first prev = 0)."""
    prev = w.shift(1).fillna(0.0)
    to = (w - prev).abs()
    return MAKER * to, to.sum(axis=1)


def main() -> None:
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

    bears = build_bears(opens_full, grid)
    base, rule, newly = apply_filters(books_raw, bears)

    cost_base, _ = turnover_cost(base)
    cost_rule, _ = turnover_cost(rule)
    pnl_base = base * fwd1 - cost_base
    pnl_rule = rule * fwd1 - cost_rule
    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    # Per-(T,sym) panel (small): raw/base/rule weights, flags, forwards, net cells.
    rows = []
    btc_bear = bears["BTCUSDT"].to_numpy()
    for s in SYMS:
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w": books_raw[s].to_numpy(float),
            "w_base": base[s].to_numpy(float),
            "w_rule": rule[s].to_numpy(float),
            "btc_bear": btc_bear,
            "own_bear": bears[s].to_numpy(),
            "newly": newly[s].to_numpy(),
            "r1": fwd1[s].to_numpy(float),
            "cost_base": cost_base[s].to_numpy(float),
            "cost_rule": cost_rule[s].to_numpy(float),
            "pnl_base": pnl_base[s].to_numpy(float),
            "pnl_rule": pnl_rule[s].to_numpy(float),
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    w_raw = books_raw.to_numpy()
    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    pnl_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        rp_b = rp_base[m].to_numpy(float)
        rp_r = rp_rule[m].to_numpy(float)
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        pb = float(pnl_base[m].sum().sum())
        pr = float(pnl_rule[m].sum().sum())
        long_m = books_raw[m] > 0
        lb = float(pnl_base[m][long_m].sum().sum())
        lr = float(pnl_rule[m][long_m].sum().sum())
        nm = newly[m]
        share_newly = float(nm.sum().sum() / nm.size) if nm.size else 0.0
        n_long = int(long_m.sum().sum())
        share_newly_long = float(nm[long_m].sum().sum() / n_long) if n_long else 0.0
        dd_pass = bool(dd_r <= dd_b + 1e-12)
        if pb >= 0:
            pnl_pass = bool(pr >= 0.95 * pb)
        else:
            pnl_pass = bool(pr >= 1.05 * pb)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "share_btc_bear": round(float(btc_bear[m].mean()), 6),
            "share_newly_halved": round(share_newly, 6),
            "share_newly_of_longs": round(share_newly_long, 6),
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "long_pnl_base": round(lb, 6),
            "long_pnl_rule": round(lr, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_pass,
            "pnl_ge95": pnl_pass,
        })
        dd_wins += int(dd_pass)
        pnl_wins += int(pnl_pass)

    # Gate window [2023-04-17, 2023-06-15): linear net sums BASE vs RULE.
    wm = (grid >= WIN0) & (grid < WIN1)
    win = {
        "window": "2023-04-17..2023-06-15",
        "n_bars": int(np.sum(wm)),
        "book_loss_base": round(float(pnl_base[wm].sum().sum()), 6),
        "book_loss_rule": round(float(pnl_rule[wm].sum().sum()), 6),
        "long_loss_base": round(float(pnl_base[wm][books_raw[wm] > 0].sum().sum()), 6),
        "long_loss_rule": round(float(pnl_rule[wm][books_raw[wm] > 0].sum().sum()), 6),
    }
    win["delta_rule_minus_base"] = round(win["book_loss_rule"] - win["book_loss_base"], 6)

    # Full-path context (compounded from year-1 start, no reset).
    full_dd_b = max_dd(equity_path(rp_base.to_numpy(float)))
    full_dd_r = max_dd(equity_path(rp_rule.to_numpy(float)))

    # LOYO descriptive (no fitted parameter; rule identical in every fold).
    d = np.array([y["book_pnl_rule"] - y["book_pnl_base"] for y in years], float)
    e = np.array([y["maxDD_base"] - y["maxDD_rule"] for y in years], float)
    # Pre-registered form: hold iff same sign as training mean (NaN -> fail);
    # DD hold additionally requires the training mean improvement > 0.
    loyo_p2, loyo_d2 = [], []
    for h in range(5):
        mp = float(np.mean(np.delete(d, h)))
        md = float(np.mean(np.delete(e, h)))
        hp = bool(np.isfinite(d[h]) and np.isfinite(mp) and np.sign(d[h]) == np.sign(mp))
        hd = bool(np.isfinite(e[h]) and np.isfinite(md) and md > 0 and np.sign(e[h]) == np.sign(md))
        loyo_p2.append(hp)
        loyo_d2.append(hd)

    promising = bool(dd_wins >= 4 and pnl_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_bookic)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only: longs x0.5 when BTC open < 1200-bar mean",
            "rule": "per-coin: longs x0.5 when (BTC bear OR own open < own 1200-bar mean)",
            "ma": "rolling(1200, min_periods=600).mean() on FULL per-coin opens history; open[T] inclusive (causal at close of T); NaN -> False",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "long_leg": "net cells summed over ORIGINAL raw w>0 (fixed membership)",
            "window": "[2023-04-17, 2023-06-15) linear net sums",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()),
            "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "window_W2": win,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6),
            "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_rule": round(float(rp_rule.sum()), 6),
        },
        "loyo": {
            "d_pnl_rule_minus_base": [round(float(x), 6) for x in d],
            "e_dd_base_minus_rule": [round(float(x), 6) for x in e],
            "loyo_pnl": f"{sum(loyo_p2)}/5",
            "loyo_dd": f"{sum(loyo_d2)}/5",
            "loyo_pnl_hold": loyo_p2,
            "loyo_dd_hold": loyo_d2,
        },
        "decision": {
            "dd_not_worse_count": f"{dd_wins}/5",
            "pnl_ge95_count": f"{pnl_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    print(win)
    print(res["full_path"], res["loyo"])


if __name__ == "__main__":
    main()
