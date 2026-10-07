"""oc_bookfunding: funding-crowding tilt for BOOK longs (idea #56, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort),
join with v154 4h opens, apply the v410 BTC-only bear-long filter FIRST
(longs x0.5 when BTC 4h open < its 1200-bar mean), then the tilt: per (T,sym),
F7[T,s] = mean settled funding over [T-7d, T) (strictly before T, >=14
settlements else NaN); q80_k[s] = walk-forward 80th percentile of F7 over
[FEAT_START, A_k) per coin; tilt_on = isfinite(F7) and F7 > q80; while ON,
base longs x0.75, shorts unchanged. Screen with open-to-open 4h returns and
gate costs (maker 0.0002 per unit turnover, each path own prev), exactly as
oc_dvolshort/oc_bookcoinbrake. Single light process (4h + funding only, no 1m).

  python research/tournament/oc_bookfunding/compute_bookfunding.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
PREM = ROOT / "data/raw/binance_premium_20260928"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")
MAKER = 0.0002
D7 = pd.Timedelta(days=7)
MIN_SETTLE = 14


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


def load_funding() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per sym: (settlement_ns sorted int64, rates float64), all history."""
    out = {}
    for s in SYMS:
        df = pd.read_parquet(PREM / f"{s}_funding.parquet")
        c = pd.to_datetime(df["calc_time"], utc=True).sort_values()
        order = np.argsort(pd.to_datetime(df["calc_time"], utc=True).to_numpy())
        df = df.iloc[order].reset_index(drop=True)
        cns = pd.to_datetime(df["calc_time"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        r = df["last_funding_rate"].to_numpy(float)
        # sort by time (stable)
        o = np.argsort(cns, kind="stable")
        out[s] = (cns[o], r[o])
    return out


def f7_for_times(Tns: np.ndarray, cns: np.ndarray, rates: np.ndarray) -> np.ndarray:
    """Mean rate over [T-7d, T), >= MIN_SETTLE settlements else NaN."""
    ns7 = D7.to_timedelta64().astype("timedelta64[ns]").astype(np.int64)
    cs = np.cumsum(np.concatenate([[0.0], rates]))
    # left = first idx with cns >= T-7d ; right = first idx with cns >= T (strict <T)
    left = np.searchsorted(cns, Tns - ns7, side="left")
    right = np.searchsorted(cns, Tns, side="left")
    n = right - left
    sums = cs[right] - cs[left]
    out = np.full(len(Tns), np.nan)
    ok = n >= MIN_SETTLE
    out[ok] = sums[ok] / n[ok]
    return out


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
    funding = load_funding()
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

    # F7 on T_all (pre-anchor 4h grid + book grid) per coin, then walk-forward q80.
    pre = opens_full.index[(opens_full.index >= FEAT_START) & (opens_full.index < ANCHORS[0])].sort_values()
    T_all = pre.union(grid).sort_values()
    Tns_all = T_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    F_all: dict[str, np.ndarray] = {}
    for s in SYMS:
        cns, rates = funding[s]
        F_all[s] = f7_for_times(Tns_all, cns, rates)
    F_series = {s: pd.Series(F_all[s], index=T_all) for s in SYMS}

    Tns_grid = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    F_grid = np.empty((len(grid), len(SYMS)))
    for j, s in enumerate(SYMS):
        cns, rates = funding[s]
        F_grid[:, j] = f7_for_times(Tns_grid, cns, rates)

    q80: list[dict[str, float]] = []
    for k, a0 in enumerate(ANCHORS):
        qk = {}
        for s in SYMS:
            tr = F_series[s][(T_all >= FEAT_START) & (T_all < a0)].to_numpy(float)
            tr = tr[np.isfinite(tr)]
            assert tr.size >= 100, f"year {k} {s}: only {tr.size} training values"
            qk[s] = float(np.quantile(tr, 0.8))
        q80.append(qk)

    bounds = ANCHORS + [LAST_BOUND]
    year_idx = np.zeros(len(grid), dtype=int)
    for k in range(5):
        year_idx[(grid >= bounds[k]) & (grid < bounds[k + 1])] = k
    qmat = np.empty_like(F_grid)
    for k in range(5):
        for j, s in enumerate(SYMS):
            qmat[year_idx == k, j] = q80[k][s]

    tilt_on = np.isfinite(F_grid) & (F_grid > qmat)
    w_rule = np.where(tilt_on & (w_base > 0), w_base * 0.75, w_base)

    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_rule = w_rule * r1 - cost_rule

    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    rows = []
    for j, s in enumerate(SYMS):
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w_raw": w_raw[:, j],
            "w_base": w_base[:, j],
            "w_rule": w_rule[:, j],
            "bear": bear,
            "tilt_on": tilt_on[:, j],
            "F7": F_grid[:, j],
            "q80": qmat[:, j],
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
    gm = (grid >= bounds[0]) & (grid < bounds[-1])
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
        base_long = (w_base[m] > 0)
        lbl = float(pnl_base[m][base_long].sum()) if base_long.sum() else 0.0
        lrl = float(pnl_rule[m][base_long].sum()) if base_long.sum() else 0.0
        dd_pass = bool(np.isfinite(dd_b) and np.isfinite(dd_r) and dd_r <= dd_b + 1e-12)
        if np.isfinite(pb) and np.isfinite(pr):
            pnl_pass = bool(pr >= 0.97 * pb) if pb >= 0 else bool(pr >= pb / 0.97)
        else:
            pnl_pass = False
        tilt_share = float(tilt_on[m][base_long].mean()) if base_long.sum() else 0.0
        cov = float(np.isfinite(F_grid[m]).mean())
        per_coin = {s: round(float(tilt_on[m, j][w_base[m, j] > 0].mean()) if (w_base[m, j] > 0).sum() else 0.0, 6)
                    for j, s in enumerate(SYMS)}
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "q80": {s: round(q80[k][s], 9) for s in SYMS},
            "coverage_F7": round(cov, 6),
            "share_bear": round(float(bear[m].mean()) if m.sum() else 0.0, 6),
            "tilt_on_share_base_longs": round(tilt_share, 6),
            "tilt_on_share_per_coin": per_coin,
            "long_pnl_base": round(lbl, 6),
            "long_pnl_rule": round(lrl, 6),
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_pass,
            "pnl_ge97": pnl_pass,
        })
        dd_wins += int(dd_pass)
        pnl_wins += int(pnl_pass)

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter FIRST: longs x0.5 when BTC open < 1200-bar mean (rolling 1200, min 600, open[T] inclusive)",
            "funding": "data/raw/binance_premium_20260928/*_funding.parquet (calc_time settlement, last_funding_rate)",
            "feature": "F7[T,s]=mean settled funding over [T-7d,T) strictly before T, >=14 settlements else NaN",
            "rule": "per-coin walk-forward q80 over [2021-06-30,A_k) finite F7; tilt_on=F7>q80; while ON base longs x0.75, shorts unchanged",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return; long leg over fixed w_base>0",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "feat_start": str(FEAT_START),
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
            "pnl_ge97_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    print(res["full_path"])


if __name__ == "__main__":
    main()
