"""v393: tournament dip-size models in the MANUAL pipeline M5 on the honest 4-phase evaluation (registry v393).

Why: v391 showed the bar-open-trained dip size models (research/tournament) lift every dev year of the BOT (kelly V2) or lift return at equal DD
(context V2). M5's two bracket dip limits (3.0 / 4.0 sigma) get their size from the same deployed R2 agent (rung map 3.0 -> R2 index 1,
4.0 -> 3), set at placement, so a human can follow any bar-open size table. Rows (fixed before running): M5 (reference, deployed; v377 cached M5 runs, identical settings),
M5K (dip size from research/tournament/kelly/tables/kelly_v2_s{s}.parquet), M5C (research/tournament/context/tables/ctx_v2_s{s}.parquet);
lookup key (T = idx + 4 h, sym, R2 rung index), missing -> 1.0; the take-profit stays the deployed agent's. Evaluation, metrics, MANUAL
fitness (v310 goal-1), folds and the most-recent-year rule exactly as v377 (single clock, mean over the four phases, dev years only).
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v393/v393_manual_tournament_sizes.py
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
ROWS = {"M5": {}, "M5K": dict(table="kelly/tables/kelly_v2_s%d.parquet"), "M5C": dict(table="context/tables/ctx_v2_s%d.parquet")}
TOUR = ROOT / "research/tournament"
REF = "M5"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def run_phase(args):
    shift, rows, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod393_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist393_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_393_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw393_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                                                                                 eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    sh = pd.Timedelta(hours=shift)
    end = pd.Timestamp("2026-09-23", tz="UTC") if last_year else pof.DEV1
    live0, live1 = pof.DEV0 + sh, end + sh
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
    for name in rows:
        cfg = ROWS[name]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        if "table" in cfg:
            t = pd.read_parquet(TOUR / (cfg["table"] % shift))
            look = {(pd.Timestamp(T), sy, int(r)): float(z) for T, sy, r, z in zip(t["T"], t["sym"], t["rung"], t["size"])}
            rmap = hist.M3_R2_RUNG
            kw["sleeve_fill_size"] = lambda i, a, r, f, look=look, rmap=rmap: look.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
        events = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        anchors = ANCH if last_year else ANCH[:4]
        m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], anchors, live0, live1, sh)
        years = []
        for y, a in enumerate(anchors):
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            ev = [e for e in events if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v221.v216.v213.trade_stats(ev)
            nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
            wb = sum(round((ts.get(k) or {}).get("win_rate", 0) * (ts.get(k) or {}).get("trades", 0)) for k in ("dev", "_hidden"))
            yy = m["yearly"][y]
            years.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"], nb=nb, wb=wb))
        out[name] = years
        print(shift, name, [round(100 * y["net"], 1) for y in years], [y["dd"] for y in years], flush=True)
    return shift, out


def metrics(allres, name, ys):
    R, DD, W = [], [], []
    nb = wb = 0
    for sh in range(4):
        yy = [allres[sh][name][y] for y in ys]
        R.append(100 * (np.prod([1 + y["net"] for y in yy]) ** (1 / (12 * len(yy))) - 1))
        DD.append(max(y["dd"] for y in yy))
        W.append(min(100 * ((1 + y["net"]) ** (1 / 12) - 1) for y in yy))
        nb += sum(y["nb"] for y in yy); wb += sum(y["wb"] for y in yy)
    return dict(R=round(float(np.mean(R)), 3), DD=round(float(np.mean(DD)), 2), W=round(float(np.mean(W)), 3),
                win_book=round(wb / max(nb, 1), 4), R_phases=[round(r, 3) for r in R], DD_phases=[round(d, 2) for d in DD])


def f_pooled(m):
    g1 = np.minimum([m["R"] / 5, 20 / max(m["DD"], 1e-6), m["win_book"] / 0.55, min(1.0, 1 + m["W"] / 2)], 1.0)
    if g1.min() < 1:
        return float(0.7 * g1.min() + 0.3 * g1.mean())
    g2 = np.minimum([m["R"] / 8, 15 / max(m["DD"], 1e-6), m["win_book"] / 0.60], 1.2)
    return float(1 + 0.25 * g2.min() + 0.75 * g2.mean())


def fitness(allres, name, ys):
    if len(ys) == 1:
        return f_pooled(metrics(allres, name, ys))
    return float(0.5 * min(f_pooled(metrics(allres, name, [y])) for y in ys) + 0.5 * f_pooled(metrics(allres, name, ys)))


def main():
    cache = HERE / "v393_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            allres = dict(pool.map(run_phase, [(s, [r for r in ROWS if r != "M5"], False) for s in range(4)]))
        ref = pickle.loads((RD / "v377" / "v377_runs.pkl").read_bytes())  # M5 reference: identical settings (v377 row M5)
        for s in range(4):
            allres[s]["M5"] = ref[s]["M5"]
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v393", "rows": {}, "folds": {}}
    for name in ROWS:
        out["rows"][name] = dict(dev4=metrics(allres, name, [0, 1, 2, 3]), F=round(fitness(allres, name, [0, 1, 2, 3]), 4),
                                 years=[metrics(allres, name, [y]) for y in range(4)])
        print(name, out["rows"][name]["dev4"], "F", out["rows"][name]["F"], flush=True)
    gains = []
    for k in (2, 3):
        ch = max(ROWS, key=lambda r: fitness(allres, r, list(range(k))))
        fc, f0 = fitness(allres, ch, [k]), fitness(allres, REF, [k])
        out["folds"][k] = dict(choice=ch, test_F=round(fc, 4), ref_F=round(f0, 4), test=metrics(allres, ch, [k]))
        gains.append(ch != REF and fc > f0)
        print("FOLD", k, ch, round(fc, 4), "vs", REF, round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    ch = max(ROWS, key=lambda r: fitness(allres, r, [0, 1, 2, 3]))
    out["final"] = dict(choice=ch, dev4=out["rows"][ch]["dev4"], reference=out["rows"][REF]["dev4"])
    if out["transfer"]:  # the size tables stop at the dev end: the most recent year needs tables built the same way (follow-up step)
        out["final"]["most_recent_year_once"] = "pending: build the hidden-year size tables, then score once"
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v393_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
