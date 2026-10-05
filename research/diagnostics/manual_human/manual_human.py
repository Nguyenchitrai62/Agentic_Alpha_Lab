"""Dev-only diagnostic (not a registered version): honest MANUAL expectation for a human who sleeps and reacts late.

The MANUAL replays assume an action 5 minutes after EVERY 4h close (6 per day, including 03:00 Vietnam time). A real person skips the night
decision and reacts ~15 minutes late. Rows (fixed before running), each on the four 4h-grid phases s = 0..3 (phase_offset_full harness, agents
ON with the per-phase tables v376/tables_hidden, standard books forward-filled, dev years 2021-09-24..2025-09-23 only):
  <P>_base   deployed rules, minute-5 reaction, every bar (P = M2 v340, M3 v342, M4 v362, M5 v367)
  <P>_human  15-minute reaction (book orders from minute 15, dip limits from minute 16) and the night bar skipped: on the holding bar that
             starts at (20 + s) UTC (= 03:00 + s local time) no new book order (flat -> wait, in position -> hold; resting orders, SL and TP
             stay on the exchange) and no new dip limit.
Metrics as v377: R = mean over phases of the dev4 geometric monthly return, DD = mean over phases of the max yearly 1m DD, W = mean over phases
of the worst-year monthly, plus each phase's R and DD. Nothing is selected here: the table is the honest MANUAL expectation for the report.

  python research/diagnostics/manual_human/manual_human.py
"""
from __future__ import annotations

import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
PIPES = {"M2": "v340", "M3": "v342", "M4": "v362", "M5": "v367"}
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")


def run_phase(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod_mh_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_mh_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_mh_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_mh_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                                                                                 eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, pof.DEV1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    std_idx = books154.index[books154.index <= pof.DEV1 + pd.Timedelta(hours=4)]
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    hours = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    night = (20 + shift) % 24
    out = {}
    for name, pipe in PIPES.items():
        for mode in ("base", "human"):
            kw, trade = pof.pipe_setup(pipe, hist, v221, v216, idx, cols, True)
            lat = 5
            if mode == "human":
                lat = 15
                pol = trade["policy"]
                trade["policy"] = lambda i, a, st, pol=pol: ("wait" if st["pos"] == 0 else "hold") if hours[i] == night else pol(i, a, st)
                kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
                kw["sleeve_start"] = max(16, lat + 1)
            eu.simulate(books, opens, prep, trade=trade, win_start=lat, events=[], **kw)
            m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], ANCH, live0, live1, sh)
            out[f"{name}_{mode}"] = [dict(net=y["net_pct"] / 100, dd=y["dd_1m_pct"]) for y in m["yearly"]]
            print(shift, name, mode, [y["net_pct"] for y in m["yearly"]], [y["dd_1m_pct"] for y in m["yearly"]], flush=True)
    return shift, out


def summary(allres, row):
    R, DD, W = [], [], []
    for s in range(4):
        yy = allres[s][row]
        R.append(100 * (np.prod([1 + y["net"] for y in yy]) ** (1 / 48) - 1))
        DD.append(max(y["dd"] for y in yy))
        W.append(min(100 * ((1 + y["net"]) ** (1 / 12) - 1) for y in yy))
    return dict(R=round(float(np.mean(R)), 3), DD=round(float(np.mean(DD)), 2), W=round(float(np.mean(W)), 3),
                R_phases=[round(r, 2) for r in R], DD_phases=[round(d, 1) for d in DD], DD_max=round(float(max(DD)), 1))


def main():
    cache = HERE / "manual_human_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            allres = dict(pool.map(run_phase, range(4)))
        cache.write_bytes(pickle.dumps(allres))
    table = {row: summary(allres, row) for row in allres[0]}
    for row, v in table.items():
        print(row, v, flush=True)
    (HERE / "manual_human.json").write_text(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
