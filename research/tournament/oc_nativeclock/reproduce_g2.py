"""oc_nativeclock: reproduce the deployed G2 baseline before any native test (light).

Loads v421_runs.pkl strat R2B1D17BFG2, recomputes per-year reset metrics with
reset_metric.year_reset, the 5y geometric mean, and the continuous full-path DD
with v388.mix (v421 convention). Asserts the assignment's 5.41 / 16.91 / 16.82
(and the per-year rows from v421_result.json). Writes tmp/g2_repro.json.
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
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
STRAT = "R2B1D17BFG2"
EXP = {"R": 5.41, "W": 2.588, "DD": 16.91, "full": 16.82}
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27), (4.648, 12.90)]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    runs = pickle.loads(V421.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    assert STRAT in runs[0], sorted(runs[0])
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    rm = _load("reset_for_native", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_native", RD / "v388/v388_bot_stop_distance.py")
    years = [rm.year_reset(runs, STRAT, y) for y in range(5)]
    got_years = [(m["R"], m["DD"]) for m in years]
    assert got_years == [(r, d) for r, d in exp["years"]], (got_years, exp["years"])
    assert got_years == EXP_YEARS, got_years
    geo = round(float(np.prod([1 + r / 100 for r, _ in got_years]) ** (1 / 5) - 1) * 100, 3)
    assert geo == exp["R"] == EXP["R"], (geo, exp["R"])
    assert min(r for r, _ in got_years) == exp["W"] == EXP["W"]
    assert max(d for _, d in got_years) == exp["DD"] == EXP["DD"], (got_years, exp["DD"])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, STRAT, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"] == EXP["full"], (full, exp["full_path_dd"])
    # per-phase year table (phase s equity per anchor year, for the per-phase check)
    per_phase = {}
    for s in range(4):
        per_phase[s] = [rm.year_reset({ss: runs[ss] for ss in [s]}, STRAT, y) if False else None for y in range(5)]
    # per-phase via v388.hourly single-phase paths (reset per year against own phase equity)
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1)
        rows = []
        for y in range(5):
            a0 = pd.Timestamp(v388.ANCH[y], tz="UTC")
            segy = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            esy, msy = e1[segy] / b, m1[segy] / b
            pk = np.maximum.accumulate(esy.to_numpy())
            rows.append({"R": round(100 * float(esy.iloc[-1] ** (1 / 12) - 1), 3),
                         "DD": round(100 * float(np.max(1 - msy.to_numpy() / pk)), 2)})
        per_phase[s] = rows
    out = {"strat": STRAT, "years": [{"R": r, "DD": d} for r, d in got_years],
           "R": geo, "W": min(r for r, _ in got_years), "DD": max(d for _, d in got_years),
           "full_path_dd": full, "per_phase": {str(s): per_phase[s] for s in range(4)}}
    (HERE / "tmp" / "g2_repro.json").write_text(json.dumps(out, indent=1))
    print(f"G2 reproduction OK: R={geo} W={out['W']} DD={out['DD']} full={full}", flush=True)
    for s in range(4):
        print(f"phase {s}: " + ", ".join(f"Y{y} {r['R']}/{r['DD']}" for y, r in enumerate(per_phase[s])), flush=True)


if __name__ == "__main__":
    main()
