"""oc_mcdd: deployment-risk stationary block bootstrap for R2B1D17BF (and R2B1D16).

See PLAN.md. LIGHT job: one process, only the two runs pkls, numpy+pandas.
Usage: python research/tournament/oc_mcdd/mcdd_bootstrap.py
Writes results.json and REPORT.md in this folder.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
V411 = ROOT / "research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl"
V406 = ROOT / "research/parallel/rounds/parallel-20260906-r2/v406/v406_runs.pkl"
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
D0 = pd.Timestamp("2021-09-24", tz="UTC")
D1 = pd.Timestamp("2026-09-23", tz="UTC")
MEAN_BLOCK = 20.0
N_PATHS = 10000
PATH_LEN = 365
SEED = 0


def phase_daily(run):
    """Daily close E_s and daily marked low M_s on D grid (causal ffill only)."""
    t = pd.to_datetime(run["t"], utc=True)
    eq = pd.Series(np.asarray(run["eq"], dtype=float), index=t).sort_index()
    em = pd.Series(np.asarray(run["eq_min"], dtype=float), index=t).sort_index()
    H = pd.date_range(D0, D1, freq="1h")
    e_h = eq.reindex(H, method="ffill")
    e_h = e_h.fillna(1.0) if float(e_h.iloc[0]) == float(e_h.iloc[0]) else e_h.fillna(1.0)
    lo_h = em.copy()
    lo_h.index = lo_h.index - pd.Timedelta(hours=4)
    lo_h = lo_h.sort_index().reindex(H, method="ffill").fillna(1.0)
    e_h = e_h.fillna(1.0)
    m_h = pd.concat([lo_h, e_h], axis=1).min(axis=1)
    D = pd.date_range(D0, D1, freq="1D")
    E = e_h.reindex(D, method="ffill").fillna(1.0)
    # daily low = min of hourly marked low strictly after prev close up to close
    M = pd.Series(index=D, dtype=float)
    M.iloc[0] = float(E.iloc[0])
    for d in range(1, len(D)):
        seg = m_h[(m_h.index > D[d - 1]) & (m_h.index <= D[d])]
        M.iloc[d] = float(seg.min()) if len(seg) else float(E.iloc[d])
    M = M.fillna(E)
    return D, E.to_numpy(float), M.to_numpy(float)


def chained_mix(runs, strat):
    """Year-reset chained mixed equity (each phase reset to 1/4 at anchors)."""
    D = pd.date_range(D0, D1, freq="1D")
    Es, Ms = [], []
    for s in range(4):
        _, E, M = phase_daily(runs[s][strat])
        Es.append(E)
        Ms.append(M)
    Es = np.column_stack(Es)  # (n,4)
    Ms = np.column_stack(Ms)
    a_idx = [int(np.searchsorted(D, pd.Timestamp(a, tz="UTC"))) for a in ANCH] + [len(D) - 1]
    E_mix = np.zeros(len(D))
    M_mix = np.zeros(len(D))
    C = 1.0
    year_segs = []
    for y in range(5):
        i0, i1 = a_idx[y], a_idx[y + 1]
        base = Es[i0].copy()
        base[~np.isfinite(base) | (base <= 0)] = 1.0
        shares = (C / 4.0) / base
        E_mix[i0 : i1 + 1] = Es[i0 : i1 + 1] @ shares
        M_mix[i0 : i1 + 1] = Ms[i0 : i1 + 1] @ shares
        # rebased segment starting at 1.0 for empirical year stats
        seg_E = E_mix[i0 : i1 + 1] / E_mix[i0]
        seg_M = M_mix[i0 : i1 + 1] / E_mix[i0]
        year_segs.append((seg_E, seg_M))
        C = float(E_mix[i1])
    return D, E_mix, M_mix, year_segs


def year_stats(seg_E, seg_M):
    R = float(seg_E[-1] - 1.0)
    m = float((1.0 + R) ** (1.0 / 12.0) - 1.0)
    pk = np.maximum.accumulate(np.concatenate([[1.0], seg_E]))[1:]
    dd_c = float(np.max(1.0 - seg_E / pk))
    dd_m = float(np.max(1.0 - np.minimum(seg_E, seg_M) / pk))
    return {"R12": R, "m_geo": m, "DD_close": dd_c, "DD_marked": dd_m}


def exact_hourly_year(runs, strat, y):
    """Bit-faithful replica of reset_metric.year_reset (hourly, for the empirical table)."""
    g1 = pd.Timestamp("2026-09-23", tz="UTC") + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    grid = pd.date_range(g0, g1, freq="1h")
    a0 = pd.Timestamp(ANCH[y], tz="UTC")
    E, MN = [], []
    for s in range(4):
        run = runs[s][strat]
        t = pd.to_datetime(run["t"], utc=True)
        e1 = pd.Series(np.asarray(run["eq"], dtype=float), index=t).reindex(grid, method="ffill").fillna(1.0)
        lo = pd.Series(np.asarray(run["eq_min"], dtype=float), index=t - pd.Timedelta(hours=4))
        lo = lo.reindex(grid, method="ffill").fillna(1.0)
        m1 = pd.concat([lo, e1], axis=1).min(axis=1)
        b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
        seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
        E.append(e1[seg] / b)
        MN.append(m1[seg] / b)
    es, ms = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(es.to_numpy())
    R = float(es.iloc[-1] ** (1.0 / 12.0) - 1.0)
    dd = float(np.max(1.0 - ms.to_numpy() / pk))
    Rend = float(es.iloc[-1] - 1.0)
    pkc = np.maximum.accumulate(np.concatenate([[1.0], es.to_numpy()]))[1:]
    dd_c = float(np.max(1.0 - es.to_numpy() / pkc))
    return {"R12": Rend, "m_geo": R, "DD_close": dd_c, "DD_marked": dd}


def stationary_indices(n, length, rng, p):
    out = np.empty(length, dtype=np.int64)
    k = 0
    while k < length:
        start = int(rng.integers(0, n))
        L = int(rng.geometric(p))
        L = min(L, length - k)
        idx = (start + np.arange(L)) % n
        out[k : k + L] = idx
        k += L
    return out


def bootstrap(r, l, n_paths=N_PATHS, length=PATH_LEN, mean_block=MEAN_BLOCK, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(r)
    p = 1.0 / mean_block
    I = np.empty((n_paths, length), dtype=np.int64)
    for b in range(n_paths):
        I[b] = stationary_indices(n, length, rng, p)
    R = r[I]  # (B,T)
    L = l[I]
    P = np.cumprod(1.0 + R, axis=1)
    Pprev = np.concatenate([np.ones((n_paths, 1)), P[:, :-1]], axis=1)
    Mk = np.minimum(P, Pprev * L)
    peak = np.maximum.accumulate(np.concatenate([np.ones((n_paths, 1)), P], axis=1), axis=1)[:, 1:]
    dd_c = np.max(1.0 - P / peak, axis=1)
    dd_m = np.max(1.0 - Mk / peak, axis=1)
    R12 = P[:, -1] - 1.0
    m = (1.0 + np.clip(R12, -0.999999, None)) ** (1.0 / 12.0) - 1.0
    return R12, m, dd_c, dd_m


def summarize(R12, m, dd_c, dd_m):
    def q(x, v):
        return float(np.percentile(x, v))
    return {
        "P_R12_neg": float(np.mean(R12 < 0)),
        "P_m_lt_5pct": float(np.mean(m < 0.05)),
        "m_med": q(m, 50),
        "m_p5": q(m, 5),
        "m_p95": q(m, 95),
        "R12_med": q(R12, 50),
        "R12_p5": q(R12, 5),
        "R12_p95": q(R12, 95),
        "P_DDm_gt15": float(np.mean(dd_m > 0.15)),
        "P_DDm_gt20": float(np.mean(dd_m > 0.20)),
        "P_DDm_gt25": float(np.mean(dd_m > 0.25)),
        "DDm_med": q(dd_m, 50),
        "DDm_p95": q(dd_m, 95),
        "P_DDc_gt15": float(np.mean(dd_c > 0.15)),
        "P_DDc_gt20": float(np.mean(dd_c > 0.20)),
        "P_DDc_gt25": float(np.mean(dd_c > 0.25)),
        "DDc_med": q(dd_c, 50),
    }


def main():
    runs411 = pickle.loads(V411.read_bytes())
    runs406 = pickle.loads(V406.read_bytes())
    # assignment: R2B1D16 from v406 pkl when present; equality check vs v411 copy
    maxdiff = max(
        float(np.max(np.abs(np.array(runs411[s]["R2B1D16"]["eq"]) - np.array(runs406[s]["R2B1D16"]["eq"]))))
        for s in range(4)
    )
    strats = {"R2B1D17BF": runs411, "R2B1D16": runs406}
    out = {
        "meta": {
            "v411": str(V411.relative_to(ROOT)),
            "v406": str(V406.relative_to(ROOT)),
            "anchors": ANCH,
            "window": [str(D0), str(D1)],
            "daily_grid": "1D 00:00 UTC ffill (causal); marked low = hourly ffill min over day",
            "reset": "each phase reset to 1/4 of capital at each anchor, chained",
            "bootstrap": {"kind": "stationary Politis-Romano", "mean_block_days": MEAN_BLOCK,
                          "n_paths": N_PATHS, "path_days": PATH_LEN, "seed": SEED, "circular": True},
            "R2B1D16_v411_eq_v406_maxabsdiff": maxdiff,
        },
        "strategies": {},
    }
    for strat, runs in strats.items():
        D, E_mix, M_mix, segs = chained_mix(runs, strat)
        r = E_mix[1:] / E_mix[:-1] - 1.0
        l = M_mix[1:] / E_mix[:-1]
        years = []
        for y in range(5):
            st = exact_hourly_year(runs, strat, y)
            st["anchor"] = ANCH[y]
            years.append(st)
        R12, m, dd_c, dd_m = bootstrap(r, l)
        out["strategies"][strat] = {
            "n_days": int(len(D)),
            "n_returns": int(len(r)),
            "chained_total_R": float(E_mix[-1] - 1.0),
            "daily_r_mean": float(np.mean(r)),
            "daily_r_std": float(np.std(r)),
            "worst_day": float(np.min(r)),
            "years_empirical": years,
            "bootstrap": summarize(R12, m, dd_c, dd_m),
        }
        b = out["strategies"][strat]["bootstrap"]
        print(strat, "years_m=", [round(y["m_geo"] * 100, 3) for y in years],
              "boot P(m<5%)=", round(b["P_m_lt_5pct"], 4),
              "P(DDm>20)=", round(b["P_DDm_gt20"], 4), flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json")


if __name__ == "__main__":
    main()
