"""oc_placebo: placebo / false-positive rate of the vectorised BOT book screen.

Covers research/tournament/oc_expirybook (idea #62, PROMISING 4/5 DD + 4/5
retention>=98%) and research/tournament/oc_cmegap (idea #69, PROMISING 4/5
P&L + 5/5 DD), both NO in the full 4-phase engine (oc_expiry4p, oc_cmegap4p).

Method (per assignment OPENCODE_W_oc_placebo.md): 1,000 seeded random rules
of each shape, windows drawn with an RNG without looking at returns, run
through the SAME vectorised screen (v410 bear filter FIRST, 0.05% per unit
turnover, open-to-open 4h returns, per-year reset equity, peak-to-trough
maxDD) and judged by the SAME PROMISING criteria as each original report.

Shapes (fixed before running; literal geometry wins over the "~%" hints):
  (a) expiry-like: halve book targets (both sides) on one contiguous 12-bar
      window per calendar month, start uniform inside the month (window kept
      fully inside the month, so no cross-month overlap). 61 months x 12 =
      732 bars (~6.7% of the 10955-bar grid; the assignment's "~4%" hint
      understates 12/180 per month -- the realised share matches the real
      expiry share 6.5% by construction).
  (b) CME-like: per anchor year 10 windows, length uniform in {12,18,24} bars
      (2/3/4 days), start uniform inside the year, non-overlapping
      (rejection sampling), random sign per window (longs x0.75 or x1.25,
      shorts/flats unchanged). ~180 bars/year (~8.2%/year, ~8.2% total;
      above the "~1.5%" hint but close to the real CME total 6.8% and the
      real max-18-bar window shape).

Real-rule reference deltas are recomputed under this SAME 0.0005 screen
(expiry windows via the same last-Friday-08:00 calendar; CME windows via
oc_cmegap/panel.parquet affected/gap mapped onto the rebuilt base) so the
percentile ranks are apples-to-apples. (Original expiry costs were 0.0002;
original CME costs were already 0.0005.)

LIGHT: vectorised 4h only, no engine runs, single process, streaming per
rule (no per-rule panels stored). Peak is the (10955,5) float64 working
arrays (~1 MB) plus the books/opens frames.

  python research/tournament/oc_placebo/compute_placebo.py
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
OC_EXP = ROOT / "research/tournament/oc_expirybook"
OC_CME = ROOT / "research/tournament/oc_cmegap"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
BOUNDS = ANCHORS + [LAST_BOUND]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0005  # assignment screen: 0.05% per unit turnover
SEED = 20261006
N_EXP = 1000
N_CME = 1000
EXP_WIN = 12
CME_LENS = (12, 18, 24)
CME_PER_YEAR = 10


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2."""
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


def expiry(y: int, m: int) -> pd.Timestamp:
    """Last Friday of month m, 08:00 UTC (same as compute_expirybook)."""
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


def real_expiry_mask(grid: pd.DatetimeIndex) -> np.ndarray:
    ti = grid.astype("int64").to_numpy()
    H = np.int64(3_600_000_000_000)
    flag = np.zeros(len(grid), bool)
    for y in range(2021, 2027):
        for mm in range(1, 13):
            e = expiry(y, mm)
            if e >= CUTOFF + pd.Timedelta(days=1):
                continue
            ev = np.int64(e.value)
            flag |= (ti >= ev - np.int64(48) * H) & (ti < ev)
    return flag


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def turnover_cost(w: np.ndarray) -> np.ndarray:
    """MAKER * |w - w_prev| per sym, first prev = 0. w: (n, 5) time-ordered."""
    prev = np.vstack([np.zeros((1, w.shape[1])), w[:-1, :]])
    return MAKER * np.abs(w - prev)


def gen_expiry_mask(grid: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """One contiguous 12-bar window per calendar month, fully inside month.

    Uses ONLY grid timestamps + RNG (never returns/weights).
    """
    mask = np.zeros(len(grid), dtype=bool)
    months = pd.Series(grid).dt.tz_localize(None).dt.to_period("M").to_numpy()
    for key in pd.unique(months):
        loc = np.where(months == key)[0]
        if len(loc) < EXP_WIN:
            continue
        s = int(rng.integers(0, len(loc) - EXP_WIN + 1))
        mask[loc[s:s + EXP_WIN]] = True
    return mask


def gen_cme_masks(
    year_pos: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """10 non-overlapping windows in one year + per-bar sign multipliers.

    year_pos: global grid positions of this year's bars (sorted).
    Returns (mask_global_bool, mult_global_float with 1.0 off-window).
    Uses ONLY positions + RNG (never returns/weights).
    """
    n = len(year_pos)
    taken = np.zeros(n, dtype=bool)
    mult_local = np.ones(n, dtype=float)
    placed = 0
    tries = 0
    while placed < CME_PER_YEAR and tries < 500:
        tries += 1
        L = int(CME_LENS[int(rng.integers(0, len(CME_LENS)))])
        if n < L:
            break
        s = int(rng.integers(0, n - L + 1))
        if taken[s:s + L].any():
            continue
        taken[s:s + L] = True
        mult_local[s:s + L] = float(rng.choice((0.75, 1.25)))
        placed += 1
    # Return year-local taken mask + multipliers; caller maps to global grid.
    return taken, mult_local


def evaluate_rule(
    w_rule: np.ndarray,
    bar_base: np.ndarray,
    base_year_tot: list[float],
    base_year_dd: list[float],
    r1: np.ndarray,
    year_m: list[np.ndarray],
) -> dict:
    """Score one rule weight matrix vs precomputed base (same MAKER screen)."""
    cost_r = turnover_cost(w_rule)
    pnl_r = w_rule * r1 - cost_r
    bar_r = pnl_r.sum(axis=1)
    dd_w = 0
    pnl_w = 0
    ret_w = 0
    tot_r = float(bar_r.sum())
    for k in range(5):
        sel = year_m[k]
        rp_r = bar_r[sel]
        eq_r = equity_path(rp_r)
        dd_r = max_dd(eq_r)
        tot_r_k = float(rp_r.sum())
        if dd_r <= base_year_dd[k]:
            dd_w += 1
        if tot_r_k >= base_year_tot[k]:
            pnl_w += 1
        b = base_year_tot[k]
        ok = (tot_r_k >= 0.98 * b) if b > 0 else (tot_r_k >= b)
        ret_w += int(bool(ok))
    full_dd_r = max_dd(equity_path(bar_r))
    return {
        "bar": bar_r,
        "dd_wins": int(dd_w),
        "pnl_wins": int(pnl_w),
        "ret_wins": int(ret_w),
        "total": tot_r,
        "full_dd": float(full_dd_r),
    }


def qstats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    return {
        "mean": round(float(np.mean(x)), 6),
        "sd": round(float(np.std(x, ddof=1)) if len(x) > 1 else 0.0, 6),
        "min": round(float(np.min(x)), 6),
        "p5": round(float(np.quantile(x, 0.05)), 6),
        "p25": round(float(np.quantile(x, 0.25)), 6),
        "p50": round(float(np.quantile(x, 0.50)), 6),
        "p75": round(float(np.quantile(x, 0.75)), 6),
        "p95": round(float(np.quantile(x, 0.95)), 6),
        "max": round(float(np.max(x)), 6),
    }


def main() -> None:
    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid)
    o = opens.reindex(grid)[SYMS]
    fwd1 = o.shift(-1) / o - 1.0
    exit1_ok = np.asarray(grid.shift(-1) <= CUTOFF)
    books_raw, fwd1 = books_raw[exit1_ok], fwd1[exit1_ok]
    valid1 = fwd1.notna().all(axis=1)
    books_raw, fwd1 = books_raw[valid1], fwd1[valid1]
    grid = books_raw.index
    assert len(grid) == 10955, f"grid {len(grid)} != 10955"
    print(f"grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    bear = bear_flags(opens_full, grid)
    w0 = books_raw[SYMS].to_numpy(float)
    base = w0.copy()
    pos = w0 > 0
    base[bear[:, None] & pos] = 0.5 * w0[bear[:, None] & pos]
    r1 = fwd1[SYMS].to_numpy(float)
    cost_b = turnover_cost(base)
    pnl_b = base * r1 - cost_b
    bar_b = pnl_b.sum(axis=1)
    year_m = [np.asarray((grid >= BOUNDS[k]) & (grid < BOUNDS[k + 1])) for k in range(5)]
    base_year_tot, base_year_dd = [], []
    for k in range(5):
        rp = bar_b[year_m[k]]
        base_year_tot.append(float(rp.sum()))
        base_year_dd.append(max_dd(equity_path(rp)))
    base_full_dd = max_dd(equity_path(bar_b))
    base_full_tot = float(bar_b.sum())
    print(f"base totals: {[round(t, 6) for t in base_year_tot]}", flush=True)
    print(f"base DDs: {[round(d, 6) for d in base_year_dd]} full {base_full_dd:.6f}", flush=True)

    # --- real rules under the SAME 0.0005 screen ---
    inexp = real_expiry_mask(grid)
    w_exp = base.copy()
    w_exp[inexp, :] = 0.5 * base[inexp, :]
    ev_exp = evaluate_rule(w_exp, bar_b, base_year_tot, base_year_dd, r1, year_m)

    cme_panel = pd.read_parquet(OC_CME / "panel.parquet")
    cme_panel["T"] = pd.to_datetime(cme_panel["T"], utc=True)
    first = cme_panel.groupby("T", sort=True)[["affected", "gap"]].first().reindex(grid)
    assert first["affected"].notna().all(), "CME panel grid mismatch"
    assert (first.index == grid).all(), "CME panel grid order mismatch"
    aff = first["affected"].to_numpy(bool)
    gapv = first["gap"].to_numpy(float)
    w_cme = base.copy()
    up = aff & np.isfinite(gapv) & (gapv > 0.02)
    dn = aff & np.isfinite(gapv) & (gapv < -0.02)
    longs_up = up[:, None] & (base > 0)
    longs_dn = dn[:, None] & (base > 0)
    w_cme[longs_up] = 0.75 * base[longs_up]
    w_cme[longs_dn] = 1.25 * base[longs_dn]
    ev_cme = evaluate_rule(w_cme, bar_b, base_year_tot, base_year_dd, r1, year_m)
    d_exp = float(ev_exp["total"] - base_full_tot)
    dd_exp = float(ev_exp["full_dd"] - base_full_dd)
    d_cme = float(ev_cme["total"] - base_full_tot)
    dd_cme = float(ev_cme["full_dd"] - base_full_dd)

    # --- placebo loop (streaming, one rule at a time) ---
    rng = np.random.default_rng(SEED)
    exp_dp, exp_dd, exp_pass, exp_ddw, exp_retw, exp_cov = [], [], [], [], [], []
    for i in range(N_EXP):
        m = gen_expiry_mask(grid, rng)
        w = base.copy()
        w[m, :] = 0.5 * base[m, :]
        ev = evaluate_rule(w, bar_b, base_year_tot, base_year_dd, r1, year_m)
        exp_dp.append(float(ev["total"] - base_full_tot))
        exp_dd.append(float(ev["full_dd"] - base_full_dd))
        exp_ddw.append(ev["dd_wins"])
        exp_retw.append(ev["ret_wins"])
        exp_pass.append(bool(ev["dd_wins"] >= 4 and ev["ret_wins"] >= 4))
        exp_cov.append(float(m.mean()))
        if (i + 1) % 250 == 0:
            print(f"exp {i + 1}/{N_EXP}", flush=True)
    exp_dp = np.array(exp_dp)
    exp_dd = np.array(exp_dd)

    cme_dp, cme_dd, cme_pass_s, cme_pass_l, cme_ddw, cme_pnlw, cme_cov = (
        [], [], [], [], [], [], [])
    year_pos = [np.where(year_m[k])[0] for k in range(5)]
    for i in range(N_CME):
        mult_g = np.ones(len(grid), dtype=float)
        m_g = np.zeros(len(grid), dtype=bool)
        for k in range(5):
            taken, mult_local = gen_cme_masks(year_pos[k], rng)
            loc = year_pos[k][taken]
            m_g[loc] = True
            mult_g[loc] = mult_local[taken]
        mg5 = np.broadcast_to(m_g[:, None], base.shape)
        longs = mg5 & (base > 0)
        factor = np.ones_like(base)
        factor[longs] = np.broadcast_to(mult_g[:, None], base.shape)[longs]
        w = base * factor
        ev = evaluate_rule(w, bar_b, base_year_tot, base_year_dd, r1, year_m)
        cme_dp.append(float(ev["total"] - base_full_tot))
        cme_dd.append(float(ev["full_dd"] - base_full_dd))
        cme_ddw.append(ev["dd_wins"])
        cme_pnlw.append(ev["pnl_wins"])
        cme_pass_s.append(bool(ev["pnl_wins"] >= 4 and ev["dd_wins"] == 5))
        cme_pass_l.append(bool(ev["pnl_wins"] >= 4 and ev["dd_wins"] >= 4))
        cme_cov.append(float(m_g.mean()))
        if (i + 1) % 250 == 0:
            print(f"cme {i + 1}/{N_CME}", flush=True)
    cme_dp = np.array(cme_dp)
    cme_dd = np.array(cme_dd)

    def pct_le(x: np.ndarray, v: float) -> float:
        return round(float(np.mean(x <= v)) * 100.0, 2)

    # Percentiles use the ROUNDED deltas stored in results.json (ties at 0.0
    # carry mass, so full- vs 6dp-precision would disagree by ~4pp on CME DD).
    d_exp_r, dd_exp_r = round(d_exp, 6), round(dd_exp, 6)
    d_cme_r, dd_cme_r = round(d_cme, 6), round(dd_cme, 6)
    exp_dp_r = np.round(exp_dp, 6)
    exp_dd_r = np.round(exp_dd, 6)
    cme_dp_r = np.round(cme_dp, 6)
    cme_dd_r = np.round(cme_dd, 6)

    fpr_exp = round(float(np.mean(exp_pass)), 4)
    fpr_cme_s = round(float(np.mean(cme_pass_s)), 4)
    fpr_cme_l = round(float(np.mean(cme_pass_l)), 4)

    # Stricter screen: require the joint PROMISING legs PLUS a placebo-tail
    # effect-size gate. Calibrate gates at the placebo 95th percentiles so the
    # joint FPR <= 5% by construction; report realised joint FPRs.
    g_exp_pnl = float(np.quantile(exp_dp_r, 0.95))
    g_exp_dd = float(np.quantile(exp_dd_r, 0.05))  # DD delta: more negative = better
    g_cme_pnl = float(np.quantile(cme_dp_r, 0.95))
    g_cme_dd = float(np.quantile(cme_dd_r, 0.05))
    strict_exp = (np.array(exp_pass) & (exp_dp_r >= g_exp_pnl)
                  & (exp_dd_r <= g_exp_dd))
    strict_cme = (np.array(cme_pass_s) & (cme_dp_r >= g_cme_pnl)
                  & (cme_dd_r <= g_cme_dd))
    # Single-gate sensitivities (legs + one tail gate).
    s_exp_p = np.array(exp_pass) & (exp_dp_r >= g_exp_pnl)
    s_exp_d = np.array(exp_pass) & (exp_dd_r <= g_exp_dd)
    s_cme_p = np.array(cme_pass_s) & (cme_dp_r >= g_cme_pnl)
    s_cme_d = np.array(cme_pass_s) & (cme_dd_r <= g_cme_dd)

    res = {
        "meta": {
            "screen": "BASE = raw book + v410 bear-long filter; open-to-open 4h returns; 0.0005/unit turnover (own prev, first prev=0); per-year reset equity; peak-to-trough maxDD",
            "grid": f"{len(grid)} bars {grid.min()}..{grid.max()} x 5 coins",
            "n_bars": int(len(grid)),
            "seed": SEED,
            "n_expiry_like": N_EXP,
            "n_cme_like": N_CME,
            "expiry_like": f"one contiguous {EXP_WIN}-bar window per calendar month, uniform start inside month (fully inside month); halve both sides",
            "cme_like": f"per anchor year {CME_PER_YEAR} windows, length uniform in {list(CME_LENS)} bars, uniform start inside year, non-overlapping; random sign per window (longs x0.75/x1.25)",
            "windows_use_only": "grid timestamps + RNG (never returns/weights/pnl)",
            "criteria_expiry": "DD not worse (rule<=base) in >=4/5 years AND total P&L >=98% of base in >=4/5 years (oc_expirybook REPORT)",
            "criteria_cme_strict": "total P&L >= base in >=4/5 years AND DD not worse in 5/5 years (oc_cmegap REPORT text)",
            "criteria_cme_loose": "total P&L >= base in >=4/5 years AND DD not worse in >=4/5 years (oc_cmegap compute code)",
            "real_ref": "both real rules rescored under this same 0.0005 screen (expiry calendar rebuilt; CME windows from oc_cmegap/panel.parquet mapped onto rebuilt base)",
            "engine_context": "oc_expiry4p VERDICT NO; oc_cmegap4p VERDICT NO (full 4-phase engine, post-hoc checks)",
            "resources": "vectorised 4h only, single process, no engine runs",
        },
        "base": {
            "year_totals": [round(t, 6) for t in base_year_tot],
            "year_maxDD": [round(d, 6) for d in base_year_dd],
            "full_total": round(base_full_tot, 6),
            "full_maxDD": round(base_full_dd, 6),
        },
        "real": {
            "expiry": {
                "dd_wins": ev_exp["dd_wins"],
                "pnl_ge_wins": ev_exp["pnl_wins"],
                "ret98_wins": ev_exp["ret_wins"],
                "passes_expiry_criterion": bool(ev_exp["dd_wins"] >= 4 and ev_exp["ret_wins"] >= 4),
                "dPnl_5y": round(d_exp, 6),
                "dDD_full": round(dd_exp, 6),
                "note": "same 48h pre-expiry halving as oc_expirybook, rescored at 0.0005 (orig costs 0.0002: 5y dPnl +0.015914, dDD -0.009987)",
            },
            "cme": {
                "dd_wins": ev_cme["dd_wins"],
                "pnl_ge_wins": ev_cme["pnl_wins"],
                "passes_cme_strict": bool(ev_cme["pnl_wins"] >= 4 and ev_cme["dd_wins"] == 5),
                "passes_cme_loose": bool(ev_cme["pnl_wins"] >= 4 and ev_cme["dd_wins"] >= 4),
                "dPnl_5y": round(d_cme, 6),
                "dDD_full": round(dd_cme, 6),
                "note": "same CME tilt as oc_cmegap, rescored at 0.0005 (orig costs already 0.0005: 5y dPnl +0.005655, dDD 0.0)",
            },
        },
        "placebo_expiry": {
            "n": N_EXP,
            "mean_coverage": round(float(np.mean(exp_cov)), 6),
            "fpr_expiry_criterion": fpr_exp,
            "dd_ge4_rate": round(float(np.mean(np.array(exp_ddw) >= 4)), 4),
            "ret_ge4_rate": round(float(np.mean(np.array(exp_retw) >= 4)), 4),
            "dPnl_5y_stats": qstats(exp_dp_r),
            "dDD_full_stats": qstats(exp_dd_r),
            "real_dPnl_percentile": pct_le(exp_dp_r, d_exp_r),
            "real_dDD_percentile": pct_le(exp_dd_r, dd_exp_r),
        },
        "placebo_cme": {
            "n": N_CME,
            "mean_coverage": round(float(np.mean(cme_cov)), 6),
            "fpr_cme_strict_4pnl_5dd": fpr_cme_s,
            "fpr_cme_loose_4pnl_4dd": fpr_cme_l,
            "pnl_ge4_rate": round(float(np.mean(np.array(cme_pnlw) >= 4)), 4),
            "dd_eq5_rate": round(float(np.mean(np.array(cme_ddw) == 5)), 4),
            "dd_ge4_rate": round(float(np.mean(np.array(cme_ddw) >= 4)), 4),
            "dPnl_5y_stats": qstats(cme_dp_r),
            "dDD_full_stats": qstats(cme_dd_r),
            "real_dPnl_percentile": pct_le(cme_dp_r, d_cme_r),
            "real_dDD_percentile": pct_le(cme_dd_r, dd_cme_r),
        },
        "stricter": {
            "gate_exp_pnl_p95": round(g_exp_pnl, 6),
            "gate_exp_dd_p05": round(g_exp_dd, 6),
            "gate_cme_pnl_p95": round(g_cme_pnl, 6),
            "gate_cme_dd_p05": round(g_cme_dd, 6),
            "exp_legs_plus_both_tails_fpr": round(float(np.mean(strict_exp)), 4),
            "cme_strict_plus_both_tails_fpr": round(float(np.mean(strict_cme)), 4),
            "exp_legs_plus_pnl_tail_fpr": round(float(np.mean(s_exp_p)), 4),
            "exp_legs_plus_dd_tail_fpr": round(float(np.mean(s_exp_d)), 4),
            "cme_strict_plus_pnl_tail_fpr": round(float(np.mean(s_cme_p)), 4),
            "cme_strict_plus_dd_tail_fpr": round(float(np.mean(s_cme_d)), 4),
            "real_exp_passes_legs_plus_both": bool(
                (ev_exp["dd_wins"] >= 4 and ev_exp["ret_wins"] >= 4)
                and (d_exp_r >= g_exp_pnl) and (dd_exp_r <= g_exp_dd)),
            "real_cme_passes_strict_plus_both": bool(
                (ev_cme["pnl_wins"] >= 4 and ev_cme["dd_wins"] == 5)
                and (d_cme_r >= g_cme_pnl) and (dd_cme_r <= g_cme_dd)),
            "recommendation": "require the original legs PLUS 5y dPnl >= placebo p95 AND full-path dDD <= placebo p05 (joint tails); realised joint FPRs are reported above and must be <= 0.05 for the screen to be usable",
        },
    }
    # Store compact per-draw deltas for audit (1000 floats each; small).
    res["placebo_expiry"]["dPnl_5y"] = [round(float(v), 6) for v in exp_dp]
    res["placebo_expiry"]["dDD_full"] = [round(float(v), 6) for v in exp_dd]
    res["placebo_expiry"]["pass"] = [bool(v) for v in exp_pass]
    res["placebo_cme"]["dPnl_5y"] = [round(float(v), 6) for v in cme_dp]
    res["placebo_cme"]["dDD_full"] = [round(float(v), 6) for v in cme_dd]
    res["placebo_cme"]["pass_strict"] = [bool(v) for v in cme_pass_s]
    res["placebo_cme"]["pass_loose"] = [bool(v) for v in cme_pass_l]

    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({
        "fpr_expiry": fpr_exp,
        "fpr_cme_strict": fpr_cme_s,
        "fpr_cme_loose": fpr_cme_l,
        "real_exp_pct_pnl/dd": [pct_le(exp_dp_r, d_exp_r),
                                pct_le(exp_dd_r, dd_exp_r)],
        "real_cme_pct_pnl/dd": [pct_le(cme_dp_r, d_cme_r),
                                pct_le(cme_dd_r, dd_cme_r)],
        "strict_exp_fpr": round(float(np.mean(strict_exp)), 4),
        "strict_cme_fpr": round(float(np.mean(strict_cme)), 4),
    }, indent=1))


if __name__ == "__main__":
    main()
