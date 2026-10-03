"""L2 MANUAL robustness report (diagnostic only - nothing is selected on it).

Candidate: v342 L2 = MANUAL book M2 x0.75 (books (2A + 2PT + D)/5, pullback entry 0.75 sigma_4h valid 3 bars, v216 grid in position, SL 4 / TP 8,
target 0.25, cap 2) + TWO human-placeable dip limits per coin at 3.0 and 4.0 sigma_4h below the 4h open, each with an exchange-native touch stop at
8 sigma and a take-profit limit (R2 agents' size / TP at the bar open, size_mult 4.375 per rung, align (1.5, 0.5), budget 0.26 counted at 8 sigma).
Rows: base | cost_stress (maker 0.0004, taker 0.0012) | human latency 15 / 30 / 60 min (book orders fill from minute L, dip limits from L + 1) |
CB books (2A + 2B + D)/5 instead of M2 = the books that are live today (deployment-form check) | stationary block bootstrap of the base
(first four years daily returns, 30-day blocks, 2000 draws, seed 0).

  python research/diagnostics/l2_robustness/l2_robustness.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
C = ROOT / "artifacts/research/engine_real"
OUT = Path(__file__).parent / "l2_robustness.json"
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
AG = dict(fit="U", up_th=2.0, up_mult=1.5, dn_th=0.0, dn_mult=0.5, tp_margin=0.001)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bootstrap(idx, eq):
    s = pd.Series(eq, index=idx)
    dev = s[(s.index >= pd.Timestamp("2021-09-24", tz="UTC")) & (s.index < pd.Timestamp("2025-09-24", tz="UTC"))]
    daily = dev.resample("1D").last().pct_change().dropna().to_numpy()
    rng = np.random.default_rng(0)
    months, dds = [], []
    for _ in range(2000):
        path = []
        while len(path) < 365:
            st = rng.integers(0, len(daily) - 30)
            path.extend(daily[st:st + 30])
        e = np.cumprod(1 + np.array(path[:365]))
        months.append(100 * (e[-1] ** (1 / 12) - 1))
        dds.append(100 * float(np.max(1 - e / np.maximum.accumulate(e))))
    m, d = np.array(months), np.array(dds)
    return dict(monthly_p5=round(float(np.percentile(m, 5)), 2), monthly_p50=round(float(np.percentile(m, 50)), 2),
                monthly_p95=round(float(np.percentile(m, 95)), 2), p_monthly_ge5=round(float(np.mean(m >= 5)), 3),
                p_loss_year=round(float(np.mean(m < 0)), 3), dd_p50=round(float(np.percentile(d, 50)), 2),
                dd_p95=round(float(np.percentile(d, 95)), 2), p_dd_gt20=round(float(np.mean(d > 20)), 3))


def main():
    v306 = _load("v306_l2r", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    size, tp = v306._tables(AG)
    v310 = _load("v310_l2r", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_l2r", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols, eu = W0["idx"], W0["cols"], W0["eu"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    A, B, D = W0["grp"]["wA"].copy(), W0["grp"]["wB"].copy(), W0["grp"]["wD"].copy()
    books = {"M2": (2 * A + 2 * PT + D) / 5, "CB": (2 * A + 2 * B + D) / 5}
    sim0, base_p9 = eu.simulate, v310._policy9
    m0, t0 = eu.MAKER, eu.TAKER
    kus = [U.index(k) for k in (3.0, 4.0)]

    def run(bk="M2", maker=m0, taker=t0, lat=5, cap=None):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = books[bk]
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        RUNG = {}

        def sim(*a, **kw):
            kw.update(sleeve=True, rungs=(3.0, 4.0), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26, size_mult=4.375,
                      align=(1.5, 0.5), sleeve_start=max(16, lat + 1), win_start=lat,
                      sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, kus[r]]), sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, kus[r]]))
            kw["trade"] = dict(kw["trade"], book_mult=0.75)
            po = {}
            kw["path_out"] = po
            out = sim0(*a, **kw)
            if cap is not None:
                cap.update(po)
            rows = v306._trade_rows(kw["events"])
            for y in range(5):
                a0 = W0["anchors"][y]
                rg = [x[2] for x in rows if x[0] == "rung" and a0 <= x[1] < a0 + pd.Timedelta(days=365)]
                RUNG[y] = (len(rg), int(sum(v > 0 for v in rg)))
            return out
        eu.simulate = sim
        eu.MAKER, eu.TAKER = maker, taker
        v306.W["eu"].MAKER, v306.W["eu"].TAKER = maker, taker
        try:
            res = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), True)
        finally:
            eu.simulate, v310._policy9 = sim0, base_p9
            eu.MAKER, eu.TAKER = m0, t0
            v306.W["eu"].MAKER, v306.W["eu"].TAKER = m0, t0
        for y, yy in enumerate(res["years"]):
            yy["n_rung"], yy["w_rung"] = RUNG[y]
        return dict(dev4=v310.metrics(res, [0, 1, 2, 3]), last_year=v310.metrics(res, [4]), five_years=v310.metrics(res, [0, 1, 2, 3, 4]),
                    years=[(round(y["monthly"], 3), round(y["dd"], 2)) for y in res["years"]],
                    **{q: res[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})

    cap = {}
    rows = {"base": run(cap=cap)}
    assert abs(rows["base"]["dev4"]["R"] - 5.779) < 0.003, rows["base"]["dev4"]
    for name, kw in (("cost_stress", dict(maker=0.0004, taker=0.0012)), ("latency_15", dict(lat=15)), ("latency_30", dict(lat=30)),
                     ("latency_60", dict(lat=60)), ("CB_books", dict(bk="CB")), ("CB_books_latency_30", dict(bk="CB", lat=30))):
        rows[name] = run(**kw)
        r = rows[name]
        print(name, r["dev4"], "| 5y", r["monthly_5y"], "last", r["monthly_last_year"], "DD", r["gate_dd"], "lose", r["losing_years"], flush=True)
    boot = bootstrap(pd.DatetimeIndex(cap["t"]), np.asarray(cap["eq"]))
    print("bootstrap", boot, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap": boot}, indent=1, default=str))


if __name__ == "__main__":
    main()
