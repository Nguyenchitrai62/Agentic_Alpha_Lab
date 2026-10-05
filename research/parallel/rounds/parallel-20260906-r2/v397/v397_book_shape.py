"""v397: book signal shape in R2-4P - smoothed book weights and a long-only book (registry v397).

Why: the book is R2-4P's steady engine (r2_decompose5: book-only 2.65-3.91 %/month 2022-2025 at DD 9-15) but lost in 2021 (-0.32); the G2 /
CB drawdown anatomy (research/diagnostics/g2_dd, cb_dd) found book whipsaws (2022) and that the book's profit comes from longs held > 4 days
while shorts earn ~0. Hypotheses: (S) smoothing the book weights (EMA, half-life 3 bars of 4h, causal) removes whipsaw churn; (L) zeroing
the book's shorts removes a ~0-edge leg (dips are long-only anyway).
Rows (fixed before running): R2 (reference = research/diagnostics/r2_decompose5 runs), R2S (books = causal EMA of the standard book rows,
alpha = 1 - 0.5 ** (1 / 3), applied on the standard grid BEFORE forward-filling to the shifted clocks), R2L (books clipped at 0, long-only),
R2SL (both). Everything else = R2 (agents, dips, C4 rules). Harness, per-year reset metric, selection rule and folds exactly as v396.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v397/v397_book_shape.py
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
RUNS = {"R2": {}, "R2S": dict(smooth=True), "R2L": dict(long_only=True), "R2SL": dict(smooth=True, long_only=True)}
REF = "R2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_397", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_397", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod397_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist397_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_397_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw397_{shift}", ROOT / "scripts/forward_v205.py")
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
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name == "R2":
            continue  # reference = research/diagnostics/r2_decompose5 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        b = std_books
        if cfg.get("smooth"):
            b = b.ewm(alpha=1 - 0.5 ** (1 / 3), adjust=False).mean()  # causal: uses rows <= t only
        if cfg.get("long_only"):
            b = b.clip(lower=0.0)
        books = b.reindex(idx, method="ffill").fillna(0.0)
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
    cache = HERE / "v397_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((ROOT / "research/diagnostics/r2_decompose5/runs.pkl").read_bytes())
        for s in range(4):
            runs[s]["R2"] = ref[s]["R2"]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v397", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
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
    (HERE / "v397_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
