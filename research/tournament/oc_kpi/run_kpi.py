"""oc_kpi: equity/monthly/DD of R2B1D17BF from v411_runs.pkl (fast part, no simulation).

Uses research/diagnostics/r2_decompose5/reset_metric.py (year_reset) and
v388.hourly/mix exactly. Writes monthly table + yearly + full-path DD into
results_equity.json for compute_kpi.py to merge.
Usage: .venv/Scripts/python.exe research/tournament/oc_kpi/run_kpi.py
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v388 = _load("v388_kpi", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("rm_kpi", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
    strat = "R2B1D17BF"
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in runs:
        assert set(runs[s][strat]) == {"t", "eq", "eq_min"}, runs[s][strat].keys()
    g1 = v388.Y1 + pd.Timedelta(hours=12)

    # per-year reset rows + 4h/1m split
    years = []
    for y in range(5):
        r = rm.year_reset(runs, strat, y)
        a0 = pd.Timestamp(v388.ANCH[y], tz="UTC")
        E, MN, ES = [], [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s][strat], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1)
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            es, ms = e1[seg] / b, m1[seg] / b
            E.append(es)
            MN.append(ms)
        es = sum(E) / 4
        ms = sum(MN) / 4
        pk = np.maximum.accumulate(es.to_numpy())
        dd4 = float(np.max(1 - es.to_numpy() / pk))
        dd1 = float(np.max(1 - np.minimum(es.to_numpy(), ms.to_numpy()) / pk))
        years.append(dict(year=y, anchor=v388.ANCH[y], R=r["R"], DD_reset=r["DD"],
                          DD_4h=round(100 * dd4, 2), DD_1m=round(100 * dd1, 2)))
    # continuous mix + calendar months
    e, mn = v388.mix(runs, strat, g1)
    m = e.resample("ME").last()
    m = m[(m.index >= "2021-09-01") & (m.index <= "2026-09-30")]
    prev = pd.Series([float(e.iloc[0])], index=[pd.Timestamp("2021-08-31", tz="UTC")])
    mm = pd.concat([prev, m])
    r = mm.pct_change().iloc[1:]
    monthly = [(ts.strftime("%Y-%m"), round(100 * float(v), 2)) for ts, v in r.items()]
    arr = r.to_numpy(float)
    full = np.array([v for _, v in monthly], float)
    share5 = float((arr >= 0.05).mean())
    share0 = float((arr >= 0).mean())
    full_idx = [i for i, (k, _) in enumerate(monthly) if k not in ("2021-09", "2026-09")]
    arr_f = arr[full_idx]
    best = cur = 0
    for v in arr:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    pk = np.maximum.accumulate(es)
    pk1 = np.maximum.accumulate(np.maximum(es, es))  # 4h path peak (eq only)
    dd4 = float(np.max(1 - es / pk1))
    dd1 = float(np.max(1 - np.minimum(es, ms) / pk))
    out = dict(
        variant=strat, g1=str(g1),
        monthly=[[k, v] for k, v in monthly],
        share_ge5_all=round(share5, 4), share_ge0_all=round(share0, 4),
        share_ge5_full59=round(float((arr_f >= 0.05).mean()), 4),
        share_ge0_full59=round(float((arr_f >= 0).mean()), 4),
        longest_losing_streak_months=int(best),
        n_months=len(monthly),
        years=years,
        full_path=dict(DD_4h=round(100 * dd4, 2), DD_1m=round(100 * dd1, 2),
                       DD_gate=round(100 * max(dd4, dd1), 2),
                       net_pct=round(100 * float(e.iloc[-1] - 1), 2),
                       eq_end=round(float(e.iloc[-1]), 4)),
        checks=dict(prod_minus_net=float(np.prod(1 + arr) - 1 - (float(e.iloc[-1]) - 1)),
                    mix_end=str(e.index[-1]), mix_start=str(e.index[0])),
    )
    (HERE / "results_equity.json").write_text(json.dumps(out, indent=1))
    print("months", len(monthly), "share>=5", round(share5, 4), "share>=0", round(share0, 4),
          "losing streak", best, flush=True)
    print("years", [(y["anchor"][:4], y["R"], y["DD_4h"], y["DD_1m"]) for y in years], flush=True)
    print("full path", out["full_path"], flush=True)


if __name__ == "__main__":
    main()
