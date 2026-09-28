"""Robustness report of the best foundation v236 W2 (T3 + whale flow in the A members) (diagnostic only - nothing is selected on it).

Rows (all on the same v205 books, engine_user trade mode, D2 settings unless changed):
  base                    D2 as deployed.
  cost_stress             maker 0.04%, taker 0.07% + 5 bps slippage on taker fills (AGENTS.md stress row).
  latency_15/30/60        a new order may fill only from minute 15 / 30 / 60 after the 4h close (slow trader or bot).
  band_lo / band_hi       grid band max(2%, 30%) / max(4%, 50%) instead of max(3%, 40%).
  cool_3 / cool_12        size-adjustment cooldown 3 / 12 bars instead of 6.
  sleeve_0.13 / 0.17      dip-sleeve stop-risk budget 0.13 / 0.17 instead of 0.15.
  offset_0.15 / 0.40      entry/adjustment limit offset 0.15 / 0.40 sigma_4h instead of 0.25.
Plus a stationary block bootstrap (30-day blocks, 2000 draws, seed 0) of the daily returns of `base` over the first four years: the
distribution of the monthly return and of the max drawdown of a 1-year path.
Reports every walk-forward year (this is a diagnostic of the frozen deployed pipeline, not a selection).

  python research/diagnostics/d2_robustness/d2_robustness.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "w2_robustness.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
eu, v216, v204 = v221.eu, v221.v216, v221.v204


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    C = eu.er.CACHE
    A, B = (pd.read_parquet(C / f).reindex(books154.index).fillna(0.0)[cols] for f in ("member_A_whale.parquet", "member_B_tv.parquet"))

    Aq, Bq = (pd.read_parquet(C / f).reindex(books154.index).fillna(0.0)[cols] for f in ("member_Aq_whale.parquet", "member_Bq_tv.parquet"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    maker0, taker0 = eu.MAKER, eu.TAKER

    def run(band=(0.03, 0.40), cool=6, budget=0.15, k_off=0.25, win_start=5, maker=maker0, taker=taker0, capture=None):
        eu.MAKER, eu.TAKER = maker, taker
        old = v216.COOL
        v216.COOL = cool
        try:
            pol = v216.grid_policy(*band)
            kw = dict(v221.KW, sleeve_risk_budget=budget)
            summ = eu.summarize
            if capture is not None:
                def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
                    capture.update(idx=idx, eq=eq.copy())
                    return summ(idx, net, eq, eq_min, g, stats, eq_max)
                eu.summarize = grab
            r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol, k_off=k_off), win_start=win_start, **kw)
            eu.summarize = summ
        finally:
            eu.MAKER, eu.TAKER, v216.COOL = maker0, taker0, old
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        return {k: r[k] for k in ("monthly_dev4", "worst_dev_month_pct", "monthly_5y", "monthly_last_year", "gate_dd", "losing_years")} | {
            "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"]]}

    cap = {}
    rows = {"base": run(capture=cap)}
    assert abs(rows["base"]["monthly_dev4"] - 5.774) < 0.002
    rows["cost_stress"] = run(maker=0.0004, taker=0.0007 + 0.0005)
    for m in (15, 30, 60):
        rows[f"latency_{m}"] = run(win_start=m)
    rows["band_lo"], rows["band_hi"] = run(band=(0.02, 0.30)), run(band=(0.04, 0.50))
    rows["cool_3"], rows["cool_12"] = run(cool=3), run(cool=12)
    rows["sleeve_0.13"], rows["sleeve_0.17"] = run(budget=0.13), run(budget=0.17)
    rows["offset_0.15"], rows["offset_0.40"] = run(k_off=0.15), run(k_off=0.40)
    for k, r in rows.items():
        print(f"{k:14s} dev4 {r['monthly_dev4']:6.3f} worst {r['worst_dev_month_pct']:6.3f} 5y {r['monthly_5y']:6.3f} "
              f"last {r['monthly_last_year']:6.3f} DD {r['gate_dd']:6.2f} losing {r['losing_years']}", flush=True)
    # block bootstrap on the first four years of the base path
    idx, eq = cap["idx"], cap["eq"]
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
    boot = dict(monthly_p5=round(float(np.percentile(months, 5)), 2), monthly_p50=round(float(np.percentile(months, 50)), 2),
                monthly_p95=round(float(np.percentile(months, 95)), 2), p_monthly_ge5=round(float(np.mean(np.array(months) >= 5)), 3),
                p_loss_year=round(float(np.mean(np.array(months) < 0)), 3), dd_p50=round(float(np.percentile(dds, 50)), 2),
                dd_p95=round(float(np.percentile(dds, 95)), 2), p_dd_gt20=round(float(np.mean(np.array(dds) > 20)), 3))
    print("bootstrap (1-year paths from first-four-year daily returns, 30-day blocks):", boot, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap": boot}, indent=1))


if __name__ == "__main__":
    main()
