"""Diagnostic (not a registered version; 2026-10-05): where did R2-4P's 2025-26 shortfall come from - book or dip sleeve?

The former hidden year 2025-09-24..2026-09-23 was inspected in v395 and is now research data (AGENTS.md). Runs on the honest 4-phase
harness over the full 5 years (as v395 / v376_final_hidden): R2 (deployed: books + dips + agents), R2_book (sleeve off), R2_dip (books
zeroed, dips + agents only). Each phase runs alone; the 4-phase 1/4-capital mix per year (v388.mix / year_stats). Nothing is selected.

  python research/diagnostics/r2_decompose5/r2_decompose5.py
"""
from __future__ import annotations

import importlib.util
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_dec5", RD / "v388" / "v388_bot_stop_distance.py")
Y1 = v388.Y1
RUNS = ("R2", "R2_book", "R2_dip")


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod_d5_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_d5_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_d5_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_d5_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name in RUNS:
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        b = books
        if name == "R2_book":
            kw["sleeve"] = False
        elif name == "R2_dip":
            b = books * 0.0
        eu.simulate(b, opens, prep, trade=trade, win_start=5, events=[], **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(), eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def main():
    cache = HERE / "runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    g1 = Y1 + pd.Timedelta(hours=12)
    res = {}
    for name in RUNS:
        e, mn = v388.mix(runs, name, g1)
        res[name] = [v388.year_stats(e, mn, [y]) for y in range(5)]
        print(name, [(y["R"], y["DD"]) for y in res[name]], flush=True)
    (HERE / "r2_decompose5.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
