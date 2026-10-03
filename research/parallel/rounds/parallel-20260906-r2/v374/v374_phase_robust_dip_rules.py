"""v374: phase-robust selection of the dip-limit rule (registry v374).

Why: the dev-only diagnostic research/diagnostics/phase_offset_dips (2026-10-04) showed the dip sleeve's results swing with the 4h grid phase
(dev totals +452 / +34 / +126 / +104 % for grids shifted 0 / 1 / 2 / 3 h; the order flips on 2020-06..2021-09). Every dip rule so far was tuned on
the standard 00 UTC grid only. v374 re-selects the human-placeable dip rule on the MEAN OVER FOUR PHASES, and validates on the pre-research period
2020-10-01 .. 2021-09-23, which no dip rule was ever designed on (disclosure: the phase diagnostic ran the reference rule once on that period, at
a different scale; no variant was ever run there).
Model: dip-only sleeve (zero books), engine_user.simulate on 4h grids shifted by 0, 1, 2, 3 h (research/diagnostics/phase_offset_dips/
phase_offset_dips.py::prep_grid, identical to engine_user.prepare at shift 0), bids live minutes 16..238 of the bar, maker on a strict trade-through,
TP limit (maker), exchange-native touch stop (taker, stop-first), timeout at the next bar open (taker), risk budget 0.26 counted at the stop,
size_mult 4.375, rung scale fixed 1.0 (rung_scale_fixed; zero books would otherwise put the vol-target scale at its cap), governor on the sleeve's
own equity, no agents, funding ignored for the dip-only sleeve (identical across rows). Nothing is fitted.
Rows (fixed before running, 18): rungs {(3.0, 4.0) = reference M3/M5 form, (3.0,) = M2 form, (2.5, 3.5, 4.5)} x TP {0.75, 1.0, 1.5} sigma_4h
x touch stop {8, 6} sigma_4h. Reference = (3.0, 4.0) / TP 1.0 / stop 8.
Fitness on a set of dev years: F = mean over the 4 phases of [monthly geometric return over the years - 0.2 x max(0, max yearly 1m DD - 20)].
PROTOCOL: folds k = 2, 3 choose argmax F on years [:k] and compare with the reference on year k (single-year F); TRANSFER if a non-reference row
is chosen and wins in both folds. Final = argmax F on the four dev years. Validation (report only, never used to choose): final vs reference on
2020-10-01 .. 2021-09-23, mean over phases. The most recent year is NOT simulated (no deployment decision here; a transfer would be plugged into
the M-series in a new version).

  python research/parallel/rounds/parallel-20260906-r2/v374/v374_phase_robust_dip_rules.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]  # POST-REGISTRATION FIX (disclosed): was parents[2]; the first run crashed at import, before any simulation
DIAG = ROOT / "research/diagnostics/phase_offset_dips"
RUNGS = {"D34": (3.0, 4.0), "D3": (3.0,), "D2545": (2.5, 3.5, 4.5)}
TPS = (0.75, 1.0, 1.5)
STOPS = (8.0, 6.0)
ROWS = [f"{r}_tp{t}_sl{s:g}" for r, t, s in itertools.product(RUNGS, TPS, STOPS)]
REF = "D34_tp1.0_sl8"
PERIODS = {"dev": ("2021-09-24", "2025-09-24"), "pre": ("2020-10-01", "2021-09-24")}  # pre starts after SOLUSDT perp listing + warm-up
DEV_YEARS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse(row):
    r, t, s = row.split("_")
    return RUNGS[r], float(t[2:]), float(s[2:])


def yearly(eq, eq_min, idx, starts):
    out = []
    for a in starts:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = np.asarray((idx >= a0) & (idx < a0 + pd.Timedelta(days=365)))
        if not mk.any():
            continue
        first = int(np.argmax(mk))
        base = eq[first - 1] if first > 0 else 1.0
        e, em = eq[mk] / base, eq_min[mk] / base
        peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
        out.append(dict(start=a, net=float(e[-1] - 1), dd=float(np.max(1 - np.minimum(e, em) / peak)), n=int(mk.sum())))
    return out


def phase_worker(shift):
    sys.path.insert(0, str(DIAG))
    P = _load(f"pod_{shift}", DIAG / "phase_offset_dips.py")
    eu = _load(f"eu374_{shift}", RD / "engine_user/engine_user.py")
    M = P.minutes()
    res = {}
    for per, (a, b) in PERIODS.items():
        P.DEV0, P.DEV1 = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        idx, opens, prep = P.prep_grid(M, shift, eu)
        books = pd.DataFrame(0.0, index=idx, columns=P.SYMS)
        sh = pd.Timedelta(hours=shift)
        eu.v110.START, eu.v110.END = P.DEV0 + sh, P.DEV1 + sh
        starts = DEV_YEARS if per == "dev" else ("2020-10-01",)
        cap = {}
        eu.summarize = lambda idx_, net, eq, eq_min, g, stats, eq_max=None: cap.update(eq=eq.copy(), eq_min=eq_min.copy(), stats=stats) or {}
        for row in ROWS:
            rungs, tp, sl = parse(row)
            eu.simulate(books, opens, prep, sleeve=True, rungs=rungs, sleeve_stop_mode="touch", m_sleeve_sl=sl, sleeve_risk_budget=0.26,
                        size_mult=4.375, m_sleeve_tp=tp, sleeve_start=16, win_start=5, rung_scale_fixed=1.0)
            ys = yearly(cap["eq"], cap["eq_min"], idx + sh, starts) if per == "dev" else None
            if per == "pre":  # one block over the whole pre period (~15.7 months)
                live = np.asarray((idx + sh >= P.DEV0) & (idx + sh < P.DEV1))
                first = int(np.argmax(live))
                base = cap["eq"][first - 1] if first > 0 else 1.0
                e, em = cap["eq"][live] / base, cap["eq_min"][live] / base
                peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
                months = live.sum() / 6 / 30.44
                ys = [dict(start=a, net=float(e[-1] - 1), dd=float(np.max(1 - np.minimum(e, em) / peak)), months=float(months))]
            res[(per, row)] = dict(years=ys, rungs=int(cap["stats"]["rungs"]), tps=int(cap["stats"]["rung_tps"]), sls=int(cap["stats"]["rung_stops"]))
            print(shift, per, row, [round(100 * y["net"], 1) for y in ys], flush=True)
    return shift, res


def monthly(ys):
    g = np.prod([1 + y["net"] for y in ys])
    months = sum(y.get("months", 12.0) for y in ys)
    return 100 * (g ** (1 / months) - 1)


def F(allres, row, years, per="dev"):
    vals = []
    for sh in range(4):
        ys = [allres[sh][(per, row)]["years"][y] for y in years] if per == "dev" else allres[sh][(per, row)]["years"]
        dd = 100 * max(y["dd"] for y in ys)
        vals.append(monthly(ys) - 0.2 * max(0.0, dd - 20.0))
    return float(np.mean(vals))


def summary(allres, row, years, per="dev"):
    out = []
    for sh in range(4):
        ys = [allres[sh][(per, row)]["years"][y] for y in years] if per == "dev" else allres[sh][(per, row)]["years"]
        out.append(dict(shift=sh, R=round(monthly(ys), 3), DD=round(100 * max(y["dd"] for y in ys), 2)))
    return dict(phases=out, R_mean=round(float(np.mean([o["R"] for o in out])), 3), DD_mean=round(float(np.mean([o["DD"] for o in out])), 2),
                F=round(F(allres, row, years, per), 4))


def main():
    with Pool(4) as pool:
        allres = dict(pool.map(phase_worker, range(4)))
    out = {"version": "v374", "rows": {r: summary(allres, r, [0, 1, 2, 3]) for r in ROWS}, "folds": {}}
    for r, v in sorted(out["rows"].items(), key=lambda kv: -kv[1]["F"]):
        print(r, v["R_mean"], v["DD_mean"], v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ch = max(ROWS, key=lambda r: F(allres, r, list(range(k))))
        fc, f0 = F(allres, ch, [k]), F(allres, REF, [k])
        out["folds"][k] = dict(choice=ch, test_F=round(fc, 4), ref_F=round(f0, 4))
        gains.append(ch != REF and fc > f0)
        print("FOLD", k, ch, round(fc, 4), "vs ref", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    ch = max(ROWS, key=lambda r: F(allres, r, [0, 1, 2, 3]))
    out["final"] = dict(choice=ch, dev4=out["rows"][ch], validation_pre=summary(allres, ch, None, "pre"),
                        reference_pre=summary(allres, REF, None, "pre"), reference_dev4=out["rows"][REF])
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v374_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
