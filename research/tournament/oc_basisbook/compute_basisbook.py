"""oc_basisbook: quarterly-basis MOMENTUM gate on BOOK LONGS (idea #61).

Per PLAN.md (pre-registered): rebuild forward_v205.research_books_d2 exactly
(as oc_dvolshort), join with v154 4h opens, apply the v410 BTC-only bear-long
filter as BASE (longs x0.5 when BTC 4h open < 1200-bar mean), then RULE = BASE
with LONG targets x0.5 on de-leveraging impulse bars
(mom = basis(T) - basis(T-7d) < walk-forward p20, BTC front-quarterly
annualised basis from qbasis_features_4h with close_time strictly < T).
Screen with open-to-open 4h returns and gate costs (maker 0.0002 per unit
turnover, each path own prev), exactly as oc_dvolshort/oc_bearshort.
Single light process (4h only, no 1m).

  python research/tournament/oc_basisbook/compute_basisbook.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
QB_PATH = CACHE / "qbasis_features_4h.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
POOL_START = pd.Timestamp("2020-08-01", tz="UTC")
MAKER = 0.0002
LONG_MULT = 0.5
LAG7 = np.int64(7 * 24 * 3600 * 1_000_000_000)


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


def basis_at(queries_ns: np.ndarray, ct_ns: np.ndarray, qb: np.ndarray) -> np.ndarray:
    """qb_front at max close_time strictly < T (literal PLAN rule, no fill-forward)."""
    j = np.searchsorted(ct_ns, queries_ns, side="left") - 1
    out = np.full(len(queries_ns), np.nan)
    ok = j >= 0
    out[ok] = qb[j[ok]]
    return out


def mom_for_times(Tns: np.ndarray, ct_ns: np.ndarray, qb: np.ndarray) -> np.ndarray:
    """mom(T) = basis(T) - basis(T - 7d), NaN iff either leg NaN."""
    b_now = basis_at(Tns, ct_ns, qb)
    b_lag = basis_at(Tns - LAG7, ct_ns, qb)
    return b_now - b_lag


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
    # ---- books / opens grid (exactly as oc_bearshort) ----
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

    # ---- v410 bear regime FIRST (BTC-only, causal, open[T] inclusive) ----
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    # ---- quarterly-basis momentum (BTC front, strict < T, both legs) ----
    q = pd.read_parquet(QB_PATH)
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    btc = q[q["sym"] == "BTCUSDT"].sort_values("close_time").reset_index(drop=True)
    btc = btc[btc["close_time"] < CUTOFF]
    ct_ns = btc["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qb = btc["qb_front"].to_numpy(float)
    print(f"qb BTC rows: {len(btc)} {btc['close_time'].min()}..{btc['close_time'].max()} "
          f"nonNaN={int(np.isfinite(qb).sum())}", flush=True)

    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    mom_grid = mom_for_times(grid_ns, ct_ns, qb)

    # Walk-forward p20 pools: engine 4h grid times in [POOL_START, A_k).
    pool_times = opens_full.index[
        (opens_full.index >= POOL_START) & (opens_full.index < ANCHORS[0])
    ].sort_values()
    # union with grid so later-year pools reuse one mom evaluation
    pool_all = pool_times.union(grid).sort_values()
    pool_ns = pool_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    mom_pool = mom_for_times(pool_ns, ct_ns, qb)
    pool_T = pd.to_datetime(pool_ns, utc=True, unit="ns")

    p20 = []
    n_train = []
    for k, a0 in enumerate(ANCHORS):
        tr = (pool_T < a0) & np.isfinite(mom_pool)
        n = int(tr.sum())
        n_train.append(n)
        assert n >= 100, f"year {k}: only {n} training mom values"
        p20.append(float(np.quantile(mom_pool[tr], 0.2)))
    print("p20 per year:", [round(v, 6) for v in p20], flush=True)
    print("n_train per year:", n_train, flush=True)

    bounds = ANCHORS + [LAST_BOUND]
    year_of_bar = np.zeros(len(grid), dtype=int)
    for k in range(5):
        m = (grid >= bounds[k]) & (grid < bounds[k + 1])
        year_of_bar[np.asarray(m)] = k
    p20_bar = np.array([p20[k] for k in year_of_bar])
    flagged = np.isfinite(mom_grid) & (mom_grid < p20_bar)

    # ---- BASE (v410) then RULE (mom long gate, sequential) ----
    w_raw = books_raw.to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * LONG_MULT, w_raw)
    gate = flagged[:, None] & (w_base > 0)
    w_rule = np.where(gate, w_base * LONG_MULT, w_base)

    r1 = fwd1.to_numpy(float)
    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_rule = w_rule * r1 - cost_rule

    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    # ---- per-(T,sym) panel (small) ----
    rows = []
    for j, s in enumerate(SYMS):
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w_raw": w_raw[:, j],
            "w_base": w_base[:, j],
            "w_rule": w_rule[:, j],
            "bear": bear,
            "mom": mom_grid,
            "flagged": flagged,
            "scaled": gate[:, j],
            "r1": r1[:, j],
            "cost_base": cost_base[:, j],
            "cost_rule": cost_rule[:, j],
            "pnl_base": pnl_base[:, j],
            "pnl_rule": pnl_rule[:, j],
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    # ---- per-year screen ----
    years = []
    keep_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp_b = rp_base[m]
        rp_r = rp_rule[m]
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        wbm = w_base[m]
        long_m = wbm > 0
        lp_b = float(pnl_base[m][wbm > 0].sum())
        lp_r = float(pnl_rule[m][wbm > 0].sum())
        pb = float(pnl_base[m].sum())
        pr = float(pnl_rule[m].sum())
        if pb > 0:
            keep_pass = bool(np.isfinite(pb) and np.isfinite(pr) and pr >= 0.97 * pb)
            keep_label = f"{(pr / pb):.4f}x"
        else:  # fallback (not expected; logged)
            keep_pass = bool(np.isfinite(pb) and np.isfinite(pr) and pr >= pb)
            keep_label = "base<=0_fallback"
        dd_pass = bool(np.isfinite(dd_b) and np.isfinite(dd_r) and dd_r <= dd_b + 1e-12)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "p20": round(p20[k], 6),
            "n_train": n_train[k],
            "coverage": round(float(np.isfinite(mom_grid[m]).mean()), 6),
            "share_flagged": round(float(flagged[m].mean()) if m.sum() else 0.0, 6),
            "n_long_base": int(long_m.sum()),
            "share_longs_scaled": round(float(gate[m][wbm > 0].mean()) if long_m.sum() else 0.0, 6),
            "long_pnl_base": round(lp_b, 6),
            "long_pnl_rule": round(lp_r, 6),
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "pnl_ratio": keep_label,
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "pnl_kept": keep_pass,
            "dd_not_worse": dd_pass,
        })
        keep_wins += int(keep_pass)
        dd_wins += int(dd_pass)

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    promising = bool(keep_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "basis": "qbasis_features_4h.parquet BTC qb_front (from data/raw/qbasis_20261003); "
                     "basis(T)=qb at max close_time<T strict; mom(T)=basis(T)-basis(T-7d), no ffill",
            "base": "v410 BTC-only bear filter FIRST: longs x0.5 when BTC open < 1200-bar mean "
                    "(rolling 1200, min 600, open[T] inclusive)",
            "rule": "impulse bars (mom < walk-forward p20, strictly below) -> BASE longs x0.5 "
                    "(bear+impulse longs 0.25x raw); shorts/flats/NaN unchanged",
            "pool": f"p20_k = 20th pct of mom over engine 4h grid times in [{POOL_START.date()}, A_k), "
                    "each bar once, strictly previous data",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; "
                    "worst week = min 42-bar return",
            "long_leg": "fixed membership w_base>0 (v410+mom touch longs only)",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()),
            "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6),
            "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_rule": round(float(rp_rule.sum()), 6),
        },
        "decision": {
            "pnl_kept_count": f"{keep_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    print("full_path:", res["full_path"])


if __name__ == "__main__":
    main()
