"""oc_ablation analysis: G2 reproduction check + per-year reset metrics + DDs.

Light job (no 1m). Reads tmp/runs_s{shift}.pkl, validates G2 against
v421_result.json to the digit (same code path as v421 + oc_carrycompound),
then writes tmp/ablation_years.json. Gap test is separate (compute_gap.py).
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
ROWS = ["G2", "NO_GOV", "NO_BEAR", "NO_CAP", "NO_B1", "TOUCH", "NO_VT"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v388 = _load("v388_an", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("rm_an", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs = {}
    for s in range(4):
        p = HERE / "tmp" / f"runs_s{s}.pkl"
        assert p.exists(), f"missing {p} (run run_shift.py for shift {s} first)"
        d = pickle.loads(p.read_bytes())
        runs[s] = {r: {"t": d[r]["t"], "eq": d[r]["eq"], "eq_min": d[r]["eq_min"]} for r in ROWS}
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    # G2 reproduction to the digit (same assertions as oc_carrycompound f=0)
    got_years = [rm.year_reset(runs, "G2", y) for y in range(5)]
    assert [y["R"] for y in got_years] == [r for r, _ in exp["years"]], got_years
    assert [y["DD"] for y in got_years] == [d for _, d in exp["years"]], got_years
    e, mn = v388.mix(runs, "G2", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], full
    geo5 = round(float(np.prod([1 + y["R"] / 100 for y in got_years]) ** (1 / 5) - 1) * 100, 3)
    assert geo5 == exp["R"], (geo5, exp["R"])
    print(f"G2 reproduction OK: R {geo5} full {full} years {[(y['R'], y['DD']) for y in got_years]}")

    table = {}
    for r in ROWS:
        ys = [rm.year_reset(runs, r, y) for y in range(5)]
        dev4 = [y["R"] for y in ys[:4]]
        geo_dev4 = round(float(np.prod([1 + x / 100 for x in dev4]) ** (1 / 4) - 1) * 100, 3)
        geo5 = round(float(np.prod([1 + y["R"] / 100 for y in ys]) ** (1 / 5) - 1) * 100, 3)
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
        # worst single-phase DD over the full 5y window per shift
        worst_phase, phase_dds = 0.0, []
        for s in range(4):
            t = pd.to_datetime(runs[s][r]["t"], utc=True)
            eq = np.array(runs[s][r]["eq"], float)
            em = np.array(runs[s][r]["eq_min"], float)
            pk = np.maximum.accumulate(eq)
            pk1 = np.maximum.accumulate(np.maximum(eq, em))
            dd = round(100 * float(max(np.max(1 - eq / pk), np.max(1 - np.minimum(eq, em) / pk1))), 2)
            phase_dds.append(dd)
            worst_phase = max(worst_phase, dd)
        table[r] = {"years": ys, "dev4_R": geo_dev4, "R5": geo5,
                    "W_dev4": min(dev4), "W5": min(y["R"] for y in ys),
                    "losing5": sum(y["R"] < 0 for y in ys),
                    "max_yearly_DD": max(y["DD"] for y in ys),
                    "full_path_dd": {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)},
                    "worst_phase_DD": worst_phase, "phase_DDs": phase_dds}
        print(r, table[r])
    (HERE / "tmp" / "ablation_years.json").write_text(json.dumps(table, indent=1, default=str))
    print("wrote tmp/ablation_years.json")


if __name__ == "__main__":
    main()
