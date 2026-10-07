"""oc_rolling17: rolling 12-month windows for R2B1D17BF (+R2B1D16), 4-phase 1/4 reset.

LIGHT job: one process, RAM < 1 GB, no 1m data, read-only outside this folder
(except tests/test_oc_rolling17.py). See PLAN.md (pre-registered before outcomes).
Usage: .venv/Scripts/python.exe research/tournament/oc_rolling17/run_rolling17.py
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
V411 = RD / "v411"
V406 = RD / "v406"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def month_starts():
    out = []
    y, m = 2021, 9
    while (y, m) <= (2025, 9):
        out.append(pd.Timestamp(f"{y:04d}-{m:02d}-24", tz="UTC"))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def main():
    v388 = _load("v388_for_r17", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_r17", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")

    runs = pickle.loads((V411 / "v411_runs.pkl").read_bytes())
    ref406 = pickle.loads((V406 / "v406_runs.pkl").read_bytes())
    v411_res = json.loads((V411 / "v411_result.json").read_text())

    strats_v411 = sorted({k for s in runs for k in runs[s]})
    strats_v406 = sorted({k for s in ref406 for k in ref406})
    # Assignment: R2B1D17BF + (R2B1D16 / R2-4P if present in either runs.pkl)
    wanted = ["R2B1D17BF"]
    for cand in ("R2B1D16", "R2-4P", "R2_4P", "R2"):
        if cand in strats_v411 or cand in strats_v406:
            if cand not in wanted:
                wanted.append(cand)
    # Keep only strats we actually score from the v411 cache (consistent grid with v411_result.json).
    # "R2" (r2_decompose5 runs.pkl) is NOT in v411/v406 caches, so it is reported absent, not scored.
    score = [s for s in wanted if s in strats_v411]
    if "R2B1D16" in strats_v411 and "R2B1D16" not in score:
        score.append("R2B1D16")
    score = [s for s in ("R2B1D17BF", "R2B1D16", "R2-4P", "R2_4P", "R2") if s in score]

    # Cache hourly series once per (shift, strat) on the leader grid.
    cache = {}
    for s in range(4):
        for st in score:
            e1, m1 = v388.hourly(runs[s][st], g0, g1)
            cache[(s, st)] = (e1, m1)

    def window_reset(strat, a0):
        E, MN = [], []
        for s in range(4):
            e1, m1 = cache[(s, strat)]
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            E.append(e1[seg] / b)
            MN.append(m1[seg] / b)
        es = sum(E) / 4
        ms = sum(MN) / 4
        pk = np.maximum.accumulate(es.to_numpy())
        R = round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2)
        return dict(R=R, DD=DD, losing=int(R < 0), end_eq=round(float(es.iloc[-1]), 6))

    # Reproduction proof on the five standard anchors vs reset_metric.year_reset + v411_result.json
    repro = []
    max_dR, max_dDD, max_dJ = 0.0, 0.0, 0.0
    for st in score:
        for y in range(5):
            a0 = pd.Timestamp(v388.ANCH[y], tz="UTC")
            got = window_reset(st, a0)
            exp = rm.year_reset(runs, st, y)
            jr, jd = v411_res["rows"][st]["years"][y]
            dR = abs(got["R"] - exp["R"])
            dDD = abs(got["DD"] - exp["DD"])
            dJR = abs(got["R"] - jr)
            dJD = abs(got["DD"] - jd)
            max_dR = max(max_dR, dR)
            max_dDD = max(max_dDD, dDD)
            max_dJ = max(max_dJ, dJR, dJD)
            repro.append(dict(strat=st, y=y, anchor=str(a0.date()),
                              got_R=got["R"], exp_R=exp["R"], json_R=jr,
                              got_DD=got["DD"], exp_DD=exp["DD"], json_DD=jd,
                              dR=dR, dDD=dDD))
    assert max_dR <= 1e-3 and max_dDD <= 1e-3 and max_dJ <= 1e-3, (max_dR, max_dDD, max_dJ)

    starts = month_starts()
    assert len(starts) == 49 and str(starts[0].date()) == "2021-09-24" and str(starts[-1].date()) == "2025-09-24"

    windows = {}
    summary = {}
    for st in score:
        rows = []
        for a0 in starts:
            m = window_reset(st, a0)
            rows.append(dict(start=a0.strftime("%Y-%m-%d"), R=m["R"], DD=m["DD"],
                             losing=m["losing"], end_eq=m["end_eq"]))
        windows[st] = rows
        R = np.array([r["R"] for r in rows])
        D = np.array([r["DD"] for r in rows])

        def dist(x):
            return dict(min=round(float(np.min(x)), 3),
                        p10=round(float(np.percentile(x, 10)), 3),
                        median=round(float(np.percentile(x, 50)), 3),
                        p90=round(float(np.percentile(x, 90)), 3),
                        max=round(float(np.max(x)), 3))

        worst_R = min(rows, key=lambda r: (r["R"], r["start"]))
        worst_DD = max(rows, key=lambda r: (r["DD"], r["start"]))
        # earliest start among ties
        worst_R_dates = sorted(r["start"] for r in rows if r["R"] == worst_R["R"])
        worst_DD_dates = sorted(r["start"] for r in rows if r["DD"] == worst_DD["DD"])
        summary[st] = dict(
            n_windows=len(rows),
            monthly_R=dist(R),
            dd=dist(D),
            share_ge5=round(float(np.mean(R >= 5 - 1e-12)), 4),
            share_dd_lt15=round(float(np.mean(D < 15)), 4),
            share_dd_lt20=round(float(np.mean(D < 20)), 4),
            n_losing=int(sum(r["losing"] for r in rows)),
            worst_R_date=worst_R["start"], worst_R=worst_R["R"],
            worst_R_dates_all=worst_R_dates,
            worst_DD_date=worst_DD["start"], worst_DD=worst_DD["DD"],
            worst_DD_dates_all=worst_DD_dates,
        )

    out = dict(
        task="oc_rolling17",
        note="REPORTING only; no selection; all five years are research data per assignment; needs prospective validation.",
        grid=dict(g0=str(g0), g1=str(g1), window_days=365, n_windows=49,
                  first_start="2021-09-24", last_start="2025-09-24"),
        sources=dict(v411_runs=str(V411 / "v411_runs.pkl").replace(str(ROOT) + "/", ""),
                     v411_result=str(V411 / "v411_result.json").replace(str(ROOT) + "/", ""),
                     v406_runs=str(V406 / "v406_runs.pkl").replace(str(ROOT) + "/", "")),
        strats_in_v411=strats_v411,
        strats_in_v406=strats_v406,
        scored=score,
        r2_4p_present=bool("R2-4P" in strats_v411 or "R2-4P" in strats_v406),
        r2_4p_note="R2-4P key is absent from both v411_runs.pkl and v406_runs.pkl; scored only the present v411 rows.",
        repro_max_abs_diff=dict(vs_year_reset_R=max_dR, vs_year_reset_DD=max_dDD, vs_result_json=max_dJ),
        repro=repro,
        windows=windows,
        summary=summary,
        standard_anchors={st: [dict(start=pd.Timestamp(v388.ANCH[y], tz='UTC').strftime("%Y-%m-%d"),
                                    **{k: v for k, v in window_reset(st, pd.Timestamp(v388.ANCH[y], tz='UTC')).items() if k != 'end_eq'},
                                    end_eq=window_reset(st, pd.Timestamp(v388.ANCH[y], tz='UTC'))["end_eq"])
                               for y in range(5)] for st in score},
    )
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("scored", score, "windows", len(starts))
    print("repro max diff R/DD/json", max_dR, max_dDD, max_dJ)
    for st in score:
        print(st, summary[st])


if __name__ == "__main__":
    main()
