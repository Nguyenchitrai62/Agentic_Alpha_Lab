"""v379: the bear-regime dip filter on the multi-phase BOT R2-4P (registry v379).

Why: v378 (MANUAL) showed that halving the dip limits while BTC is below its 200-day mean improves every honest dev4 metric of M5 (phase mean R
4.35 vs 4.09, single-phase DD 21.3 vs 24.4, worst year 1.25 vs 0.28) but missed the strict two-fold transfer by 0.011 in the 2024-25 bull year.
The mechanism (dip ladders bleed in bear grinds) is not product specific; v379 tests it on the BOT form chosen in v376 (R2 as four clock-shifted
sub-books, 1/4 capital each, never rebalanced).
Rows (fixed before running): R2_4P (reference = v376 final), R2BH_4P (R2 dip-ladder rung sizes x0.5 while the BTC open of the holding bar is below
the mean of the last 1200 4h opens on that phase's grid, built from the full 1m history, min 600 - exactly v378's flag).
Evaluation exactly as v376: research/diagnostics/phase_offset_full prep_idx / pipe_setup on the standard index shifted by s = 0..3 h, standard books
forward-filled, adverse long funding per settlement bar, agents ON with the per-phase tables (v376/tables_hidden), four never-rebalanced
sub-accounts summed hourly, conservative intrabar DD, BOT fitness (v306 formula) on the mix. Dev years; folds k = 2, 3; TRANSFER if R2BH_4P is chosen
and beats R2_4P on the unseen year in both folds; final = dev4 argmax; if it transfers, the most recent year is computed ONCE for the final (mix
started at the year's beginning, as v376_final_hidden).

  python research/parallel/rounds/parallel-20260906-r2/v379/v379_bot_bear_filter.py
"""
from __future__ import annotations

import hashlib
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
RUNS = {"R2": None, "R2BH": 0.5}
ROWS = {"R2_4P": "R2", "R2BH_4P": "R2BH"}
REF = "R2_4P"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")


def worker(args):
    shift, names, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod379_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist379_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_379_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw379_{shift}", ROOT / "scripts/forward_v205.py")
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
    b1 = M["BTCUSDT"]["open"]
    b4 = b1[((b1.index - sh).floor("4h") + sh) == b1.index]
    bear_at = b4 < b4.rolling(1200, min_periods=600).mean()
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    bear = bear_at.reindex(idx + pd.Timedelta(hours=4)).fillna(False).to_numpy(bool)
    out = {}
    for name in names:
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        if RUNS[name] is not None:
            kw["sleeve_filter"] = lambda i, a, r, f=RUNS[name]: f if bear[i] else 1.0
        events = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        live = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(live))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        rr = [float(e["ret"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
        bw = pof.book_win(v221, events, live0, live1)
        out[name] = dict(t=[str(x) for x in cap["idx"][live] + pd.Timedelta(hours=8)], eq=(cap["eq"][live] / base).tolist(),
                         eq_min=(cap["eq_min"][live] / base).tolist(), nb=bw["book_trades"], wb=round((bw["book_win"] or 0) * bw["book_trades"]),
                         nr=len(rr), wr=int(sum(r > 0 for r in rr)))
        print(shift, name, "last" if last_year else "dev", round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def hourly(run, g0, g1):
    t = pd.to_datetime(run["t"], utc=True)
    grid = pd.date_range(g0, g1, freq="1h")
    e = pd.Series(run["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
    lo = pd.Series(run["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(lo, e)


def mix(allres, strat, g1):
    hs = [hourly(allres[s][strat], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1) for s in range(4)]
    return sum(h[0] for h in hs) / 4, sum(h[1] for h in hs) / 4


def year_stats(e, mn, ys):
    nets, dds = [], []
    for y in ys:
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        seg = (e.index > a0) & (e.index <= a0 + pd.Timedelta(days=365))
        b = float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
        es, ms = e[seg] / b, mn[seg] / b
        pk = np.maximum.accumulate(np.concatenate([[1.0], es.to_numpy()]))[1:]
        nets.append(float(es.iloc[-1] - 1))
        dds.append(100 * float(np.max(1 - ms.to_numpy() / pk)))
    return dict(R=round(100 * (np.prod([1 + x for x in nets]) ** (1 / (12 * len(ys))) - 1), 3),
                W=round(min(100 * ((1 + x) ** (1 / 12) - 1) for x in nets), 3), DD=round(max(dds), 2), losing=sum(x < 0 for x in nets))


def metrics(allres, row, ys, g1=pd.Timestamp("2025-09-24 12:00", tz="UTC")):
    strat = ROWS[row]
    e, mn = mix(allres, strat, g1)
    m = year_stats(e, mn, ys)
    runs = [allres[s][strat] for s in range(4)]
    m["win_all"] = round(sum(r["wb"] + r["wr"] for r in runs) / max(sum(r["nb"] + r["nr"] for r in runs), 1), 4)
    return m


def fitness(m):
    if m["losing"] or m["W"] < 0:
        return -1 + m["R"] / 100
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6), m["win_all"] / 0.65], 1.2)
    return float(0.5 * g.min() + 0.5 * g.mean())


def main():
    cache = HERE / "v379_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            allres = dict(pool.map(worker, [(s, list(RUNS), False) for s in range(4)]))
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v379", "rows": {}, "folds": {}}
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
    if out["transfer"]:
        with Pool(2) as pool:
            last = dict(pool.map(worker, [(s, [ROWS[ch]], True) for s in range(4)]))
        a0 = pd.Timestamp(ANCH[4], tz="UTC")
        E, MN = [], []
        for s in range(4):  # as v376_final_hidden: each sub-account starts the year with 1/4 of the capital
            e1, m1 = hourly(last[s][ROWS[ch]], pd.Timestamp("2021-09-24 04:00", tz="UTC"), Y1 + pd.Timedelta(hours=12))
            b = float(e1[e1.index <= a0].iloc[-1])
            E.append(e1[e1.index > a0] / b); MN.append(m1[m1.index > a0] / b)
        es, ms = sum(E) / 4, sum(MN) / 4
        pk = np.maximum.accumulate(es.to_numpy())
        out["final"]["most_recent_year_once"] = dict(monthly=round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3),
                                                     dd_conservative=round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2))
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v379_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
