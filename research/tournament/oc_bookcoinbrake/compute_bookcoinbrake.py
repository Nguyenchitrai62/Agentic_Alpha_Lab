"""oc_bookcoinbrake: per-coin book drawdown brake (idea #45, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with v154 4h opens, apply the v410 BTC-only bear-long filter FIRST
(longs x0.5 when BTC 4h open < its 1200-bar mean), then the latching per-coin
brake: S30[T,s] = trailing-30d sum of BASE net cells (rows < T); M[T,s] =
median(|S30|) over trailing 365d (rows < T, min 200); enter when S30 < -2*M,
exit when S30 > 0; while ON, longs x0.5, shorts unchanged. Screen with
open-to-open 4h returns and gate costs (maker 0.0002 per unit turnover, each
path own prev), exactly as oc_dvolshort. Single light process (4h only, no 1m).

  python research/tournament/oc_bookcoinbrake/compute_bookcoinbrake.py
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
D30 = pd.Timedelta(days=30)
D365 = pd.Timedelta(days=365)
MIN_M = 200


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

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # v410 bear filter FIRST (BTC-only, causal at close of T, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    w_raw = books_raw.to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * 0.5, w_raw)

    r1 = fwd1.to_numpy(float)
    # Turnover costs with each path's OWN prev (first prev = 0).
    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    pnl_base = w_base * r1 - cost_base

    # S30[T,s]: time-based trailing-30d sum of BASE net cells over rows < T.
    times = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ns30 = D30.to_timedelta64().astype("timedelta64[ns]").astype(np.int64)
    ns365 = D365.to_timedelta64().astype("timedelta64[ns]").astype(np.int64)
    csum = np.vstack([np.zeros((1, pnl_base.shape[1])), np.cumsum(pnl_base, axis=0)])
    S30 = np.empty_like(pnl_base)
    for i in range(len(grid)):
        left = int(np.searchsorted(times, times[i] - ns30, side="left"))
        S30[i] = csum[i] - csum[left]

    # M[T,s]: median(|S30|) over rows in [T-365d, T), min MIN_M values.
    M = np.full_like(pnl_base, np.nan)
    absS = np.abs(S30)
    for i in range(len(grid)):
        left = int(np.searchsorted(times, times[i] - ns365, side="left"))
        if i - left >= MIN_M:
            win = absS[left:i]
            M[i] = np.median(win, axis=0)

    # Latching brake per coin in grid order (initial OFF).
    brake_on = np.zeros_like(w_base, dtype=bool)
    state = np.zeros(w_base.shape[1], dtype=bool)
    for i in range(len(grid)):
        s, m = S30[i], M[i]
        turn_on = np.isfinite(s) & np.isfinite(m) & (s < -2.0 * m)
        turn_off = np.isfinite(s) & (s > 0.0)
        state = np.where(state, ~turn_off, turn_on)
        brake_on[i] = state

    w_rule = np.where(brake_on & (w_base > 0), w_base * 0.5, w_base)
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
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
            "brake_on": brake_on[:, j],
            "S30": S30[:, j],
            "M": M[:, j],
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
    years = []
    dd_wins = 0
    pnl_wins = 0
    gm = np.asarray((grid >= bounds[0]) & (grid < bounds[-1]))
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
        dd_pass = bool(np.isfinite(dd_b) and np.isfinite(dd_r) and dd_r <= dd_b + 1e-12)
        if np.isfinite(pb) and np.isfinite(pr):
            pnl_pass = bool(pr >= 0.95 * pb) if pb >= 0 else bool(pr >= 1.05 * pb)
        else:
            pnl_pass = False
        share = {}
        for j, s in enumerate(SYMS):
            share[s] = round(float(brake_on[m, j].mean()) if m.sum() else 0.0, 6)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "share_bear": round(float(bear[m].mean()) if m.sum() else 0.0, 6),
            "brake_on_share": share,
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_pass,
            "pnl_ge95": pnl_pass,
        })
        dd_wins += int(dd_pass)
        pnl_wins += int(pnl_pass)

    wm = np.asarray((grid >= WIN0) & (grid < WIN1))
    wlb = float(pnl_base[wm][w_base[wm] > 0].sum()) if wm.sum() else 0.0
    wlr = float(pnl_rule[wm][w_base[wm] > 0].sum()) if wm.sum() else 0.0
    win = {
        "window": "2023-04-17..2023-06-15",
        "n_bars": int(np.sum(wm)),
        "book_loss_base": round(float(pnl_base[wm].sum()), 6),
        "book_loss_rule": round(float(pnl_rule[wm].sum()), 6),
        "long_loss_base": round(wlb, 6),
        "long_loss_rule": round(wlr, 6),
    }
    win["delta_rule_minus_base"] = round(win["book_loss_rule"] - win["book_loss_base"], 6)

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    promising = bool(dd_wins >= 4 and pnl_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter FIRST: longs x0.5 when BTC open < 1200-bar mean (rolling 1200, min 600, open[T] inclusive)",
            "rule": "per-coin latching brake: S30=sum of BASE net cells over [T-30d,T); M=median(|S30|) over [T-365d,T) min 200; enter S30<-2*M, exit S30>0; while ON longs x0.5, shorts unchanged",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "window": "[2023-04-17, 2023-06-15) linear net sums; long leg over w_base>0 fixed membership",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()),
            "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "window_W": win,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6),
            "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_rule": round(float(rp_rule.sum()), 6),
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


if __name__ == "__main__":
    main()
