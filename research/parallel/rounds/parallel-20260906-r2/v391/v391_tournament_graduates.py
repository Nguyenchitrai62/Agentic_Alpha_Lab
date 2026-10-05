"""v391: idea-tournament graduates in the multi-phase BOT R2-4P on the honest engine harness (registry v391).

Why: research/tournament (2026-10-05) screened new dip-rung decision models on 61.8k exact rung outcomes (35 coins, walk-forward, t_exit <
anchor - 7 d, bar-open features only) against the deployed R2 agent; graduates (gain in >= 3 of 4 dev years, total > 0, tail rule):
  kelly V2 meanvar  (research/tournament/kelly): size = clip(c * max(mu, 0) / V, 0, 2) from bar-open HGB mean + downside-variance models,
                     +4.72 vs deployed (all four years), daily Sharpe higher every year; the deployed agent is trained on FILL-time states but
                     applied with BAR-OPEN states (train / serve skew), the new models are trained on bar-open states;
  context V2 hgb_mono (research/tournament/context): deployed rule on an HGB with 7 bar-open + 17 market-wide features (monotone), +0.70;
  tp: most of the take-profit gain is 'TP 1.5 more often' (always 1.5 graduates, +0.37) -> tested as a control.
The harness ignores the risk budget, concurrency, compounding and the 1m-marked drawdown; this version measures them.
Rows (fixed before running):
  R2_4P      reference (cached R2 runs of v388, identical settings)
  R2K_4P     dip size = kelly V2 per-phase table research/tournament/kelly/tables/kelly_v2_s{s}.parquet (TP = deployed agent)
  R2C_4P     dip size = context V2 per-phase table research/tournament/context/tables/ctx_v2_s{s}.parquet (TP = deployed agent)
  R2T_4P     deployed sizes, every rung's take-profit 1.5 sigma (control)
Size lookup key (T = holding bar start = idx + 4 h, sym, rung index); a missing key -> size 1.0. Evaluation, metrics, BOT fitness, folds and the
most-recent-year-once rule exactly as v388 (honest 4-phase harness, agents' TP tables v376/tables_hidden, dev years only for selection; the
most recent year needs tables for 2025-09-24.. built the same way, only for a transferring final). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v391/v391_tournament_graduates.py
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
TOUR = ROOT / "research/tournament"
RUNS = {"R2K": "kelly", "R2C": "context", "R2T": "tp15"}
ROWS = {"R2_4P": "R2", "R2K_4P": "R2K", "R2C_4P": "R2C", "R2T_4P": "R2T"}
REF = "R2_4P"
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_391", RD / "v388" / "v388_bot_stop_distance.py")
ANCH, Y1 = v388.ANCH, v388.Y1


def size_table(kind, shift):
    p = TOUR / ("kelly/tables/kelly_v2_s%d.parquet" % shift if kind == "kelly" else "context/tables/ctx_v2_s%d.parquet" % shift)
    t = pd.read_parquet(p)
    return {(pd.Timestamp(T), s, int(r)): float(z) for T, s, r, z in zip(t["T"], t["sym"], t["rung"], t["size"])}


def worker(args):
    shift, names, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod391_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist391_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_391_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw391_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, (Y1 if last_year else pof.DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    std_idx = books154.index if last_year else books154.index[books154.index <= pof.DEV1 + pd.Timedelta(hours=4)]
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name in names:
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        kind = RUNS[name]
        if kind in ("kelly", "context"):
            look = size_table(kind, shift)
            kw["sleeve_fill_size"] = lambda i, a, r, f, look=look: look.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)
        elif kind == "tp15":
            kw["sleeve_tp"] = lambda i, a, r, f: 1.5
        events = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        rr = [float(e["ret"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
        bw = pof.book_win(v221, events, live0, live1)
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist(), nb=bw["book_trades"], wb=round((bw["book_win"] or 0) * bw["book_trades"]),
                         nr=len(rr), wr=int(sum(r > 0 for r in rr)))
        print(shift, name, "last" if last_year else "dev", round(out[name]["eq"][-1], 3), "rungs", len(rr), flush=True)
    return shift, out


def metrics(allres, row, ys, g1=pd.Timestamp("2025-09-24 12:00", tz="UTC")):
    strat = ROWS[row]
    e, mn = v388.mix(allres, strat, g1)
    m = v388.year_stats(e, mn, ys)
    runs = [allres[s][strat] for s in range(4)]
    m["win_all"] = round(sum(r["wb"] + r["wr"] for r in runs) / max(sum(r["nb"] + r["nr"] for r in runs), 1), 4)
    return m


fitness = v388.fitness


def main():
    cache = HERE / "v391_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            allres = dict(pool.map(worker, [(s, list(RUNS), False) for s in range(4)]))
        ref = pickle.loads((RD / "v388" / "v388_runs.pkl").read_bytes())
        for s in range(4):
            allres[s]["R2"] = ref[s]["R2"]
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v391", "rows": {}, "folds": {}}
    for row in ROWS:
        m = metrics(allres, row, [0, 1, 2, 3])
        out["rows"][row] = dict(dev4=m, F=round(fitness(m), 4), years=[metrics(allres, row, [y]) for y in range(4)])
        print(row, m, "F", out["rows"][row]["F"], flush=True)
    gains = []
    for k in (2, 3):
        ch = max(ROWS, key=lambda r: fitness(metrics(allres, r, list(range(k)))))
        fc, f0 = fitness(metrics(allres, ch, [k])), fitness(metrics(allres, REF, [k]))
        out["folds"][k] = dict(choice=ch, test_F=round(fc, 4), ref_F=round(f0, 4), test=metrics(allres, ch, [k]))
        gains.append(ch != REF and fc > f0)
        print("FOLD", k, ch, round(fc, 4), "vs", REF, round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    ch = max(ROWS, key=lambda r: fitness(metrics(allres, r, [0, 1, 2, 3])))
    out["final"] = dict(choice=ch, dev4=out["rows"][ch]["dev4"], reference=out["rows"][REF]["dev4"])
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v391_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
