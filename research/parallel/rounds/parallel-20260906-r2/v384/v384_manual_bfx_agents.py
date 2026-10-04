"""v384: Bitfinex-feature dip agents for the MANUAL M5, judged on the honest single-clock 4-phase evaluation (registry v384).

Why: as v383 (BOT): Bitfinex margin positioning predicts dip-limit outcomes with the same sign every dev year; M5's two bracket dip limits take
their size / TP from the R2 agent table (rung map 3.0 / 4.0 sigma). Same DISCLOSURE: features screened on the dev years before registration.
Rows (fixed before running): M5 (reference, v376 agent tables), M5bfx (agent tables research/diagnostics/phase_agents_bfx/tables_bfx).
Evaluation, metrics, v310 goal-1 fitness on phase means, folds k = 2, 3 and the most-recent-year-once rule exactly as v377 (a MANUAL pipeline runs
on one clock, so the metrics are means over single-phase runs).

  python research/parallel/rounds/parallel-20260906-r2/v384/v384_manual_bfx_agents.py
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
ROWS = {"M5": {}, "M5bfx": dict(tables=ROOT / "research/diagnostics/phase_agents_bfx/tables_bfx")}
REF = "M5"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def run_phase(args):
    shift, rows, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod384_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist384_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_384_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw384_{shift}", ROOT / "scripts/forward_v205.py")
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
    out = {}
    for name in rows:
        cfg = ROWS[name]
        hist.R2_TABLE = cfg.get("tables", TABLES) / f"r2_table_s{shift}.parquet"
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        if "budget" in cfg:
            kw["sleeve_risk_budget"] = cfg["budget"]
        if "book_mult" in cfg:
            trade["book_mult"] = cfg["book_mult"]
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
    cache = HERE / "v384_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(4) as pool:
            allres = dict(pool.map(run_phase, [(s, list(ROWS), False) for s in range(4)]))
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v384", "rows": {}, "folds": {}}
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
    if out["transfer"]:
        with Pool(4) as pool:
            last = dict(pool.map(run_phase, [(s, [ch, REF], True) for s in range(4)]))
        out["final"]["most_recent_year_once"] = {r: metrics(last, r, [4]) for r in (ch, REF)}
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v384_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
