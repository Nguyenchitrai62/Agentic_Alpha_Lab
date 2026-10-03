"""v376: MULTI-PHASE BOT - one strategy run as four sub-books on 4h clocks shifted by 0 / 1 / 2 / 3 h, each with 1/4 of the capital (registry v376).

Why: v375 + research/diagnostics/phase_agents (2026-10-04): on the honest 4-phase evaluation (agents on, rebuilt for each phase) M5 earns 4.09 and
R2 4.68 %/month on average with a single-phase 1m DD of 26 / 33 %, while an equal split over the four phases (daily rebalanced) earned 4.18 / 4.77
with daily DD 15.3 / 20.9 and no losing dev year. Phases are only 0.57-0.63 correlated, so splitting the clock diversifies. A bot can run four
order cycles per 4h. Rows (fixed before running):
  R2_1P      reference: R2 as deployed on ONE clock, honest expectation = the mean over the four single-phase runs (metrics averaged)
  R2_4P      R2 on four clocks, 1/4 capital each
  M5_4P      M5 rules (bot-executed) on four clocks, 1/4 capital each
  M5_4P_k12  M5_4P with every sub-book's risk x1.2 (engine risk_mult = 1.2 on the governor: book targets and dip sizes; dip risk budget unchanged)
Setup = research/diagnostics/phase_agents/replay_agents.py (phase_offset_full prep_idx / pipe_setup; standard books forward-filled to the shifted
decision times, no look-ahead; adverse long funding on the bar containing a settlement; dip agents ON with the per-phase rebuilt R2 tables, same
per-anchor models; s = 0 reproduces history_tm). Dev years only (2021-09-24 .. 2025-09-23 + s h).
Mix accounting (4P rows): four sub-accounts, each starts with 1/4 of the capital at its own first bar and is never rebalanced; the mix equity is the
sum on an hourly grid (each sub-book's last bar-end equity carried forward). Conservative intrabar DD: each sub-book's 1m-marked bar minimum is
assigned to every hour of its bar, summed, against the running peak of the hourly mix equity.
Metrics on a set of dev years (anchor years of the standard clock): R = geometric monthly, W = worst-year monthly, DD = max conservative intrabar DD
inside those years, win_all = pooled book + dip-rung win rate. BOT fitness = v306 formula (8 %/month, W / 5, DD 15, win 0.65; any losing year ->
-1 + R / 100). R2_1P: R / W / DD = means over the four single phases.
PROTOCOL: folds k = 2, 3 choose argmax fitness on years [:k]; TRANSFER if a non-reference row is chosen and beats R2_1P on year k in both folds.
Final = dev4 argmax. The most recent year is NOT simulated here (the per-phase agent tables stop at the dev end); a transferring final gets its most
recent year once in a follow-up step, and a paper pipeline if it holds.

  python research/parallel/rounds/parallel-20260906-r2/v376/v376_multiphase_bot.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
PA = ROOT / "research/diagnostics/phase_agents"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
RUNS = {"R2": ("v321", 1.0), "M5": ("v367", 1.0), "M5k12": ("v367", 1.2)}
ROWS = ("R2_1P", "R2_4P", "M5_4P", "M5_4P_k12")
REF = "R2_1P"


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod376_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist376_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_376_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw376_{shift}", ROOT / "scripts/forward_v205.py")
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
    hist.R2_TABLE = PA / "tables" / f"r2_table_s{shift}.parquet"
    out = {}
    for name, (pipe, k) in RUNS.items():
        kw, trade = pof.pipe_setup(pipe, hist, v221, v216, idx, cols, True)
        if k != 1.0:
            kw["risk_mult"] = lambda i, e, k=k: k
        events = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        live = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        t_end = cap["idx"][live] + pd.Timedelta(hours=8)
        first = int(np.argmax(live))  # POST-RUN FIX (disclosed): the first run took eq[-1] as the base when the first live bar is row 0
        base = cap["eq"][first - 1] if first > 0 else 1.0
        rr = [float(e["ret"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
        bw = pof.book_win(v221, events, live0, live1)
        out[name] = dict(t=[str(x) for x in t_end], eq=(cap["eq"][live] / base).tolist(), eq_min=(cap["eq_min"][live] / base).tolist(),
                         nb=bw["book_trades"], wb=round((bw["book_win"] or 0) * bw["book_trades"]), nr=len(rr), wr=int(sum(r > 0 for r in rr)),
                         ev_t=[str(e["t"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")])
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def hourly(run):
    t = pd.to_datetime(run["t"], utc=True)
    eq = pd.Series(run["eq"], index=t)
    lo = pd.Series(run["eq_min"], index=t - pd.Timedelta(hours=4))  # the bar's minimum, held from its start
    grid = pd.date_range(pd.Timestamp("2021-09-24 04:00", tz="UTC"), pd.Timestamp("2025-09-24 12:00", tz="UTC"), freq="1h")
    e = eq.reindex(grid, method="ffill").fillna(1.0)
    m = lo.reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(m, e)


def year_stats(e, mn, ys):
    """Geometric monthly over the anchor years ys, worst-year monthly and the max conservative DD inside them (hourly mix series)."""
    nets, dds = [], []
    for y in ys:
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        seg = (e.index > a0) & (e.index <= a0 + pd.Timedelta(days=365))
        b = float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
        es, ms = e[seg] / b, mn[seg] / b
        pk = np.maximum.accumulate(np.concatenate([[1.0], es.to_numpy()]))[1:]
        nets.append(float(es.iloc[-1] - 1))
        dds.append(100 * float(np.max(1 - ms.to_numpy() / pk)))
    R = 100 * (np.prod([1 + x for x in nets]) ** (1 / (12 * len(ys))) - 1)
    W = min(100 * ((1 + x) ** (1 / 12) - 1) for x in nets)
    return R, W, max(dds), nets


def metrics(allres, row, ys):
    strat = {"R2_1P": "R2", "R2_4P": "R2", "M5_4P": "M5", "M5_4P_k12": "M5k12"}[row]
    runs = [allres[s][strat] for s in range(4)]
    nb = sum(r["nb"] for r in runs); wb = sum(r["wb"] for r in runs); nr = sum(r["nr"] for r in runs); wr = sum(r["wr"] for r in runs)
    hs = [hourly(r) for r in runs]
    if row.endswith("_1P"):
        st = [year_stats(e, mn, ys) for e, mn in hs]
        R, W, DD = (float(np.mean([x[j] for x in st])) for j in range(3))
        losing = float(np.mean([sum(n < 0 for n in x[3]) for x in st]))
    else:
        e = sum(h[0] for h in hs) / 4
        mn = sum(h[1] for h in hs) / 4
        R, W, DD, nets = year_stats(e, mn, ys)
        losing = sum(n < 0 for n in nets)
    return dict(R=round(R, 3), W=round(W, 3), DD=round(DD, 2), win_all=round((wb + wr) / max(nb + nr, 1), 4), losing=losing)


def fitness(m):
    if m["losing"] or m["W"] < 0:
        return -1 + m["R"] / 100
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6), m["win_all"] / 0.65], 1.2)
    return float(0.5 * g.min() + 0.5 * g.mean())


def main():
    import pickle
    cache = HERE / "v376_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(4) as pool:
            allres = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v376", "rows": {}, "folds": {}}
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
    (HERE / "v376_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
