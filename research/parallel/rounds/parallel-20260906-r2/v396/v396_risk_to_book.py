"""v396: move risk from the dip sleeve to the book in R2-4P - five walk-forward years, per-year reset metric (registry v396).

Why (research/diagnostics/r2_decompose5, 2026-10-05, the former hidden year is now research data): with the four sub-accounts reset to 1/4
of the capital at each anchor (what a user starting that year gets; the v376-v395 continuous mix let the lucky phase-0 sub-account dominate
later years - METRIC CORRECTION from this version on), R2-4P earns 1.96 / 3.77 / 4.01 / 10.63 / 3.95 %/month (2021..2025 anchors), DD up
to 25.1. Book-only (sleeve off): -0.32 / 2.65 / 2.96 / 3.91 / 3.65 with DD 9-15; dip-only: 0.59 / 0.43 / 1.30 / 3.16 / 0.34 - the book is
the steadier engine since 2022, the dip sleeve is erratic and carried the crash DDs. Hypothesis: shifting risk toward the book raises the
weak years and lowers DD.
Rows (fixed before running): R2 (reference, deployed), R2B125 (book_mult 1.25, dip risk budget 0.20 instead of 0.26), R2B150 (book_mult 1.5,
dip budget 0.13), R2B150X (book_mult 1.5, sleeve off). Same 4-phase harness as v395 (full 2021-09-24 .. 2026-09-23, agents' TP / size tables
v376/tables_hidden), per-year metric = reset mix (research/diagnostics/r2_decompose5/reset_metric.py).
SELECTION (fixed): AGENTS robust criterion on the years seen: among rows with every-year DD <= 20 and no losing year prefer geometric mean
>= 5 %/month, then the highest worst-year return; if no row has DD <= 20, rank by the BOT fitness of v388 (8 %/m, W/5, 15/DD, win). Folds
k = 2, 3, 4: choose on years [:k], compare with R2 on year k (TRANSFER = a non-reference row chosen in >= 2 of 3 folds and beating R2's year-k
return without a higher year-k DD in those folds). The final (choice on all 5 years) is validated only prospectively (paper), since every year
has now been seen. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v396/v396_risk_to_book.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
TABLES = RD / "v376" / "tables_hidden"
RUNS = {"R2": {}, "R2B125": dict(book_mult=1.25, budget=0.20), "R2B150": dict(book_mult=1.5, budget=0.13),
        "R2B150X": dict(book_mult=1.5, sleeve=False)}
REF = "R2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_396", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_396", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod396_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist396_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_396_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw396_{shift}", ROOT / "scripts/forward_v205.py")
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
    for name, cfg in RUNS.items():
        if name == "R2":
            continue  # reference = research/diagnostics/r2_decompose5 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        trade["book_mult"] = cfg["book_mult"]
        if "budget" in cfg:
            kw["sleeve_risk_budget"] = cfg["budget"]
        if cfg.get("sleeve") is False:
            kw["sleeve"] = False
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=[], **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(), eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy), DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def rank_key(m):
    ok = m["DD"] <= 20 and m["losing"] == 0
    if ok:
        return (2, int(m["R"] >= 5), m["W"], m["R"])
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6)], 1.2)
    return (1 if m["losing"] == 0 else 0, 0, float(0.5 * g.min() + 0.5 * g.mean()), m["R"])


def main():
    cache = HERE / "v396_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((ROOT / "research/diagnostics/r2_decompose5/runs.pkl").read_bytes())
        for s in range(4):
            runs[s]["R2"] = ref[s]["R2"]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v396", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
    for r, m in out["rows"].items():
        print(r, m, flush=True)
    wins = 0
    for k in (2, 3, 4):
        ch = max(RUNS, key=lambda r: rank_key(stats(runs, r, list(range(k)))))
        t, t0 = rm.year_reset(runs, ch, k), rm.year_reset(runs, REF, k)
        good = ch != REF and t["R"] > t0["R"] and t["DD"] <= t0["DD"]
        wins += good
        out["folds"][k] = dict(choice=ch, test=t, ref=t0, good=good)
        print("FOLD", k, ch, t, "vs", t0, good, flush=True)
    out["transfer"] = wins >= 2
    out["final"] = max(RUNS, key=lambda r: rank_key(out["rows"][r]))
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v396_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
