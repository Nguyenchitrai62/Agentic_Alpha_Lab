"""oc_phaserebal: phase-sub-account rebalancing diagnostic for R2B1D17BF (v411).

Implements PLAN.md exactly. LIGHT: one process, no 1m data.
Reads ONLY research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl
(row R2B1D17BF). Helpers v388 / reset_metric are imported read-only.

  python research/tournament/oc_phaserebal/compute_rebalance.py
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
STRAT = "R2B1D17BF"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_ocph", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_ocph", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")

Y1 = v388.Y1
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = Y1 + pd.Timedelta(hours=12)
ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]


def monthly_calendar():
    return pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="UTC")


def weekly_calendar():
    # Mondays 00:00 UTC from 2021-09-27 to 2026-09-21 inclusive.
    return pd.date_range("2021-09-27", "2026-09-21", freq="7D", tz="UTC")


def rebalanced_path(E, M, idx, cal):
    """Equal-weight rebalanced close/min paths. E, M: (N,4) float64, idx: DTI."""
    cal_in = [t for t in cal if t > idx[0] and t < idx[-1]]
    pos = idx.searchsorted(list(cal_in), side="right") - 1  # last grid <= T
    pos = np.array(sorted({int(p) for p in pos if 0 < int(p) < len(idx) - 1}), dtype=np.int64)
    ends = np.concatenate([[0], pos, [len(idx) - 1]])
    Ep = np.empty(len(idx))
    Mp = np.empty(len(idx))
    Ep[0] = 1.0
    Mp[0] = float(np.mean(M[0] / E[0]))  # == min ratio at start (==1.0 normally)
    P = 1.0
    for k in range(1, len(ends)):
        a, b = int(ends[k - 1]), int(ends[k])
        base = E[a]
        seg_E = E[a + 1:b + 1] / base if b > a else np.empty((0, 4))
        seg_M = M[a + 1:b + 1] / base if b > a else np.empty((0, 4))
        if len(seg_E):
            Ep[a + 1:b + 1] = P * seg_E.mean(axis=1)
            Mp[a + 1:b + 1] = P * seg_M.mean(axis=1)
            P = float(Ep[b])
    return pd.Series(Ep, index=idx), pd.Series(Mp, index=idx), [str(t) for t in cal_in]


def year_slice_stats(Ep, Mp, y):
    a0 = ANCH[y]
    seg = (Ep.index > a0) & (Ep.index <= a0 + pd.Timedelta(days=365))
    hit = Ep[Ep.index <= a0]
    b = float(hit.iloc[-1]) if len(hit) else 1.0
    es = Ep[seg] / b
    ms = Mp[seg] / b
    pk = np.maximum.accumulate(es.to_numpy())
    R = 100 * float(es.iloc[-1] ** (1 / 12) - 1)
    DD = 100 * float(np.max(1 - ms.to_numpy() / pk))
    return R, DD, float(es.iloc[-1])


def full_dd(Ep, Mp):
    seg = Ep.index > pd.Timestamp("2021-09-24", tz="UTC")
    es = Ep[seg].to_numpy()
    ms = Mp[seg].to_numpy()
    pk = np.maximum.accumulate(es)
    dd_4h = 100 * float(np.max(1 - es / pk))
    dd_1m = 100 * float(np.max(1 - ms / pk))
    return dd_4h, dd_1m, max(dd_4h, dd_1m)


def main():
    runs = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
    assert set(runs.keys()) == {0, 1, 2, 3}
    for s in range(4):
        assert set(runs[s][STRAT].keys()) == {"t", "eq", "eq_min"}

    # (a) reset metric, reproduced exactly via imported year_reset.
    a_years = [rm.year_reset(runs, STRAT, y) for y in range(5)]
    v411 = json.loads((RD / "v411" / "v411_result.json").read_text())
    ref_years = v411["rows"][STRAT]["years"]
    match = all(
        abs(a["R"] - r[0]) < 1e-9 and abs(a["DD"] - r[1]) < 1e-9
        for a, r in zip(a_years, ref_years)
    )
    R5_a = 100 * (float(np.prod([1 + y["R"] / 100 for y in a_years])) ** (1 / 5) - 1)
    DDmax_a = max(y["DD"] for y in a_years)
    e_mix, mn_mix = v388.mix(runs, STRAT, G1)
    a_4h, a_1m, a_gate = full_dd(e_mix, mn_mix)
    # cross-check vs v411 full_path_dd (1m-marked gate convention there)
    assert abs(a_gate - v411["rows"][STRAT]["full_path_dd"]) < 0.05, (a_gate, v411["rows"][STRAT]["full_path_dd"])

    # Per-phase hourly series for rebalancing.
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], G0, G1)
        Es.append(e1)
        Ms.append(m1)
    idx = Es[0].index
    assert all(e.index.equals(idx) for e in Es) and all(m.index.equals(idx) for m in Ms)
    E = np.column_stack([e.to_numpy(float) for e in Es])
    M = np.column_stack([m.to_numpy(float) for m in Ms])

    out_arms = {
        "a_no_rebal": {
            "R": [y["R"] for y in a_years],
            "DD": [y["DD"] for y in a_years],
            "R5": round(R5_a, 3),
            "DDmax": DDmax_a,
            "full_4h": round(a_4h, 2),
            "full_1m": round(a_1m, 2),
            "full_gate": round(a_gate, 2),
            "reset_match_v411": bool(match),
        }
    }
    cals = {"b_monthly": monthly_calendar(), "c_weekly": weekly_calendar()}
    for arm, cal in cals.items():
        Ep, Mp, used = rebalanced_path(E, M, idx, cal)
        per = [year_slice_stats(Ep, Mp, y) for y in range(5)]
        Rs = [round(p[0], 3) for p in per]
        DDs = [round(p[1], 2) for p in per]
        R5 = 100 * (float(np.prod([1 + r / 100 for r in Rs])) ** (1 / 5) - 1)
        f4, f1, fg = full_dd(Ep, Mp)
        out_arms[arm] = {
            "R": Rs,
            "DD": DDs,
            "R5": round(float(R5), 3),
            "DDmax": max(DDs),
            "full_4h": round(float(f4), 2),
            "full_1m": round(float(f1), 2),
            "full_gate": round(float(fg), 2),
            "n_rebalances": len(used),
            "first_rebal": used[0] if used else None,
            "last_rebal": used[-1] if used else None,
        }

    def decide(cand):
        A = out_arms["a_no_rebal"]
        C = out_arms[cand]
        d = [a - c for a, c in zip(A["DD"], C["DD"])]
        g = [c - a for a, c in zip(A["R"], C["R"])]
        n_dd = sum(x >= -0.005 for x in d)
        loyo_dd = [float(np.mean([x for j, x in enumerate(d) if j != k])) for k in range(5)]
        n_loyo = sum(x >= -0.005 for x in loyo_dd)
        loyo_g = [float(np.mean([x for j, x in enumerate(g) if j != k])) for k in range(5)]
        spec = (n_dd >= 4) and (C["R5"] >= A["R5"] - 0.0005)
        default = (n_dd >= 4) and (n_loyo >= 4)
        return {
            "d_DD": [round(float(x), 3) for x in d],
            "g_R": [round(float(x), 4) for x in g],
            "n_dd_not_worse": int(n_dd),
            "R5_gap": round(float(C["R5"] - A["R5"]), 4),
            "loyo_dd_mean": [round(float(x), 3) for x in loyo_dd],
            "n_loyo_hold": int(n_loyo),
            "loyo_R_gap_mean": [round(float(x), 4) for x in loyo_g],
            "specific_pass": bool(spec),
            "default_pass": bool(default),
            "promising": bool(spec and default),
        }

    res = {
        "version": "oc_phaserebal",
        "strat": STRAT,
        "anchors": [str(a) for a in ANCH],
        "g0": str(G0),
        "g1": str(G1),
        "n_grid": len(idx),
        "arms": out_arms,
        "decisions": {c: decide(c) for c in ("b_monthly", "c_weekly")},
        "checks": {
            "pkl_keys_ok": True,
            "reset_match_v411": bool(match),
            "v411_full_path_dd": v411["rows"][STRAT]["full_path_dd"],
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for arm, m in out_arms.items():
        print(arm, "R5", m["R5"], "DDmax", m["DDmax"], "full_gate", m["full_gate"], flush=True)
    print(json.dumps(res["decisions"], indent=1))


if __name__ == "__main__":
    main()
