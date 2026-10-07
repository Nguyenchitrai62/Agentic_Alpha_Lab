"""oc_usdtshort: USDT/USD premium BOOK SHORT-leg tilt (idea #74, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort /
oc_usdtprem), join with v154 4h opens, apply the v410 BTC-only bear-long filter
as BASE (longs x0.5 when BTC 4h open < its 1200-bar mean), then RULE = BASE with
book SHORT targets x1.15 when USDT-premium z < -1, x0.85 when z > 1, else x1.0
(all coins share the single market-wide signal; longs/flats/NaN-z unchanged).
USDT feature: prem = close - 1, mean24 rolling 24 min 20, z90 rolling 2160
min 1728 shift 1; as-of strict end < T (end <= T - 1s). Screen with
open-to-open 4h returns and gate costs (0.0005 per unit turnover, each path own
prev), oc_dvolshort mechanics at the assignment's cost. Placebo: 500 seeded
block-shuffles by run over the full bar-mult series (permute (value,length)
run pairs, seeds 9100+i, as oc_premexpo did); gates = placebo p95 (P&L) / p05
(DD). Single light process (4h + hourly only, no 1m).

  python research/tournament/oc_usdtshort/compute_usdtshort.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
USDT = ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0005  # 0.05% per unit turnover (assignment; oc_dvolshort mechanics)
LONG_MULT_BEAR = 0.5
UP_SHORT = 1.15  # applied when z < -1 (outflow favours shorts)
DOWN_SHORT = 0.85  # applied when z > 1 (inflow fades shorts)
Z_HI = 1.0
Z_LO = -1.0
NS = 1_000_000_000
N_PLACEBO = 500
FULL_SEED_BASE = 9100


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


def load_usdt() -> pd.DataFrame:
    """Hourly USDT/USD premium grid (PLAN-fixed math, identical to oc_usdtprem)."""
    u = pd.read_parquet(USDT).copy()
    u["t"] = pd.to_datetime(u["open_time"], utc=True)
    u = u[u["t"] < CUTOFF].sort_values("t").reset_index(drop=True)
    u["prem"] = pd.to_numeric(u["close"], errors="coerce") - 1.0
    u["mean24"] = u["prem"].rolling(24, min_periods=20).mean()
    r = u["mean24"].rolling(2160, min_periods=1728)
    u["usdt_z90"] = (u["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    u["end"] = u["t"] + pd.Timedelta(hours=1)
    return u


def asof_z(usdt: pd.DataFrame, T: pd.DatetimeIndex) -> np.ndarray:
    """z(T) = usdt_z90 of last USDT row with end strictly before T (end <= T-1s)."""
    ends_ns = usdt["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = usdt["usdt_z90"].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(ends_ns, Tns - NS, side="left") - 1
    out = np.full(len(T), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
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


def turnover_cost(w: np.ndarray) -> np.ndarray:
    """MAKER * |w - w_prev| per sym, first prev = 0. w: (n, 5) time-ordered."""
    prev = np.vstack([np.zeros((1, w.shape[1])), w[:-1, :]])
    return MAKER * np.abs(w - prev)


def runs_of(mult: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Maximal constant-value runs -> (values, lengths). Exact equality (assigned levels)."""
    mult = np.asarray(mult, dtype=float)
    if len(mult) == 0:
        return np.array([]), np.array([], dtype=int)
    change = np.empty(len(mult), dtype=bool)
    change[0] = True
    change[1:] = mult[1:] != mult[:-1]
    starts = np.where(change)[0]
    lengths = np.diff(np.append(starts, len(mult)))
    return mult[starts], lengths.astype(int)


def shuffle_runs(mult: np.ndarray, seed: int) -> np.ndarray:
    vals, lens = runs_of(mult)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(vals))
    return np.repeat(vals[perm], lens[perm])


def main() -> None:
    usdt = load_usdt()
    print(f"usdt: rows={len(usdt)} span={usdt['t'].iloc[0]}..{usdt['t'].iloc[-1]} "
          f"median_prem_bps={usdt['prem'].median() * 1e4:.2f}", flush=True)

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

    # v410 bear regime FIRST (BTC-only, causal at close of T, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    w_raw = books_raw[SYMS].to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * LONG_MULT_BEAR, w_raw)

    # USDT short signal (one z per bar, all coins; mirror orientation vs longs).
    zbar = asof_z(usdt, grid)
    mult_bar = np.ones(len(grid))
    mult_bar[np.isfinite(zbar) & (zbar < Z_LO)] = UP_SHORT
    mult_bar[np.isfinite(zbar) & (zbar > Z_HI)] = DOWN_SHORT
    w_rule = np.where(w_base < 0, w_base * mult_bar[:, None], w_base)

    r1 = fwd1[SYMS].to_numpy(float)
    cost_base = turnover_cost(w_base)
    cost_rule = turnover_cost(w_rule)
    pnl_base = w_base * r1 - cost_base
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
            "z": zbar,
            "mult": mult_bar,
            "tilted": (w_base[:, j] < 0) & np.isfinite(zbar)
                      & ((zbar < Z_LO) | (zbar > Z_HI)),
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
    grid_ts = pd.to_datetime(grid, utc=True)
    years = []
    pnl_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        sel = (grid_ts >= bounds[k]) & (grid_ts < bounds[k + 1])
        sel = np.asarray(sel)
        rp_b = rp_base[sel]
        rp_r = rp_rule[sel]
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        m_year = panel["T"].ge(bounds[k]) & panel["T"].lt(bounds[k + 1])
        m_year = m_year.to_numpy()
        wb = panel["w_base"].to_numpy(float)
        short_m = m_year & (wb < 0)
        short_b = float(np.sum(panel["pnl_base"].to_numpy()[short_m]))
        short_r = float(np.sum(panel["pnl_rule"].to_numpy()[short_m]))
        book_b = float(np.sum(panel["pnl_base"].to_numpy()[m_year]))
        book_r = float(np.sum(panel["pnl_rule"].to_numpy()[m_year]))
        # Long-leg equality check (rule never touches longs).
        long_m = m_year & (wb > 0)
        long_b = float(np.sum(panel["pnl_base"].to_numpy()[long_m]))
        long_r = float(np.sum(panel["pnl_rule"].to_numpy()[long_m]))
        bear_share = round(float(bear[sel].mean()), 6) if sel.size else 0.0
        zb = zbar[sel]
        wb_bar = w_base[sel]
        short_bar = wb_bar < 0
        n_short = int(short_bar.sum())
        up = int(((zb[:, None] < Z_LO) & short_bar & np.isfinite(zb[:, None])).sum())
        down = int(((zb[:, None] > Z_HI) & short_bar & np.isfinite(zb[:, None])).sum())
        cov = round(float(np.isfinite(zb).mean()), 6)
        row = {
            "year": str(a0.date()),
            "bear_share": bear_share,
            "coverage": cov,
            "n_bars": int(sel.sum()),
            "n_short_cells": n_short,
            "share_short_up": round(up / n_short, 6) if n_short else 0.0,
            "share_short_down": round(down / n_short, 6) if n_short else 0.0,
            "share_short_tilted": round((up + down) / n_short, 6) if n_short else 0.0,
            "short_pnl_base": round(short_b, 6),
            "short_pnl_rule": round(short_r, 6),
            "book_pnl_base": round(book_b, 6),
            "book_pnl_rule": round(book_r, 6),
            "long_pnl_base": round(long_b, 6),
            "long_pnl_rule": round(long_r, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "pnl_not_lower": bool(book_r >= book_b),
            "dd_not_worse": bool(dd_r <= dd_b + 1e-12),
        }
        years.append(row)
        pnl_wins += int(row["pnl_not_lower"])
        dd_wins += int(row["dd_not_worse"])

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    tot_b = float(np.sum(pnl_base))
    tot_r = float(np.sum(pnl_rule))
    d_pnl = round(tot_r - tot_b, 6)
    d_dd = round(full_dd_r - full_dd_b, 6)

    # --- placebo: 500 full-series block-shuffles by run (oc_premexpo shape) ---
    vals, lens = runs_of(mult_bar)
    n_runs = int(len(vals))
    print(f"rule runs: {n_runs} bars={len(mult_bar)}", flush=True)
    plac_dpnl = np.empty(N_PLACEBO)
    plac_ddd = np.empty(N_PLACEBO)
    short_m_all = w_base < 0
    for i in range(N_PLACEBO):
        pm = shuffle_runs(mult_bar, FULL_SEED_BASE + i)
        w_p = np.where(short_m_all, w_base * pm[:, None], w_base)
        c_p = turnover_cost(w_p)
        p_p = w_p * r1 - c_p
        plac_dpnl[i] = float(np.sum(p_p) - np.sum(pnl_base))
        plac_ddd[i] = float(max_dd(equity_path(p_p.sum(axis=1)))
                           - max_dd(equity_path(rp_base)))
        if (i + 1) % 100 == 0:
            print(f"placebo {i + 1}/{N_PLACEBO}", flush=True)
    plac_dpnl_r = np.round(plac_dpnl, 6)
    plac_ddd_r = np.round(plac_ddd, 6)
    gate_pnl_p95 = float(np.quantile(plac_dpnl_r, 0.95))
    gate_dd_p05 = float(np.quantile(plac_ddd_r, 0.05))
    pct_pnl = float(100.0 * np.mean(plac_dpnl_r <= d_pnl))
    pct_dd = float(100.0 * np.mean(plac_ddd_r <= d_dd))
    pass_pnl = bool(d_pnl >= gate_pnl_p95)
    pass_dd = bool(d_dd <= gate_dd_p05)

    promising = bool(pnl_wins >= 4 and dd_wins >= 4 and pass_pnl and pass_dd)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_usdtprem)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter FIRST (longs x0.5 when BTC 4h open < 1200-bar mean)",
            "usdt": "coinbase USDT-USD hourly (data/raw/coinbase_usdt_20261006); prem=close-1; mean24 rolling(24,min20); z90 rolling(2160,min1728) shift(1); as-of last row end<T (end<=T-1s)",
            "rule": "BASE shorts x1.15 when z<-1, x0.85 when z>1, else x1.0 (all coins); longs/flats/NaN-z unchanged",
            "costs": "0.0005 per unit turnover (|w - w_prev| per sym, first prev=0; each path own chain)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "placebo": "500 full-series block-shuffles by run: permute (value,length) run pairs of the rule bar-mult series (seeds 9100+i, same as oc_premexpo 5y draws); row counts per mult level exact; deltas vs same base; gates/pcts on 6dp-rounded deltas (oc_placebo convention)",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(pd.to_datetime(grid_ts.min())),
            "grid_end": str(pd.to_datetime(grid_ts.max())),
            "n_panel": int(len(panel)),
            "n_runs_rule": n_runs,
            "n_placebo": N_PLACEBO,
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_rule": round(full_dd_r, 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_rule": round(tot_r, 6),
            "dPnl_5y": d_pnl,
            "dDD_full": d_dd,
        },
        "placebo": {
            "gate_pnl_p95": round(gate_pnl_p95, 6),
            "gate_dd_p05": round(gate_dd_p05, 6),
            "real_dPnl_percentile": round(pct_pnl, 2),
            "real_dDD_percentile": round(pct_dd, 2),
            "pass_pnl_tail": pass_pnl,
            "pass_dd_tail": pass_dd,
            "dPnl_5y": [round(float(v), 6) for v in plac_dpnl],
            "dDD_full": [round(float(v), 6) for v in plac_ddd],
        },
        "decision": {
            "pnl_not_lower_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "pnl_tail": f"{d_pnl} vs p95 {round(gate_pnl_p95, 6)} -> {'PASS' if pass_pnl else 'FAIL'}",
            "dd_tail": f"{d_dd} vs p05 {round(gate_dd_p05, 6)} -> {'PASS' if pass_dd else 'FAIL'}",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)
    print(json.dumps(res["full_path"], indent=1))
    print(json.dumps({k: v for k, v in res["placebo"].items() if not k.startswith("d")}, indent=1))


if __name__ == "__main__":
    main()
