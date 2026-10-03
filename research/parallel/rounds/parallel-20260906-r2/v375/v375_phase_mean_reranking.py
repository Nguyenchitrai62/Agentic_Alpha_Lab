"""v375: honest re-ranking of the deployed paper pipelines on the MEAN OVER FOUR 4h-GRID PHASES (registry v375).

Why: research/diagnostics/phase_offset_full (2026-10-04) showed ~30-37 % of each deployed pipeline's dev return is specific to the standard 00 UTC
grid (phase-mean dev4 without agents: M5 3.51, M4 3.76, M2 3.39, R2 4.21 vs 5.54 / 5.88 / 4.79 / 6.24 on the standard grid; the standard grid ranks
3rd-4th on 2020-21). Every structural choice was made on the standard grid. v375 re-ranks the deployed designs with the phase-mean metrics, using the
same fold protocol, to decide which MANUAL / BOT pipeline should be recommended.
Setup: research/diagnostics/phase_offset_full/phase_offset_full.py (prep_idx, pipe_setup; s = 0 reproduces history_tm's dev4 with agents within
0.003): whole pipeline (book + dips) as backend/history_tm, engine inputs on the standard index shifted by s = 0, 1, 2, 3 h, books = the latest
standard row <= the shifted decision time (no look-ahead), adverse long funding on the bar containing a settlement, dip agents OFF on every phase
(they exist only for standard bars). Dev years only (2021-09-24 .. 2025-09-23); the most recent year is NOT simulated (every row was already scored
on it; this version only re-ranks).
Rows (fixed): MANUAL M2 (v340), M3 (v342), M4 (v362), M5 (v367, reference = recommended today); BOT R2 (v321, reference), G2 (v301), CS (v295).
Metrics for a set of dev years: R = mean over phases of the geometric monthly return; DD = mean over phases of the max yearly 1m DD; W = mean over
phases of the worst-year monthly; win_book / win_all = pooled over phases and years. MANUAL fitness = v310 goal-1 formula (book win; half the worst
single year + half the pooled years); BOT fitness = v306 formula (all-trade win; 8 %/month, DD 15, win 0.65).
PROTOCOL per product: folds k = 2, 3 choose argmax fitness on years [:k], compare with the reference on year k; TRANSFER if a non-reference row is
chosen and wins in both folds. Final = dev4 argmax; it becomes the recommended pipeline of its product only if TRANSFER.

  python research/parallel/rounds/parallel-20260906-r2/v375/v375_phase_mean_reranking.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
POF = ROOT / "research/diagnostics/phase_offset_full/phase_offset_full.py"
MANUAL = {"M2": "v340", "M3": "v342", "M4": "v362", "M5": "v367"}
BOT = {"R2": "v321", "G2": "v301", "CS": "v295"}
REF = {"manual": "M5", "bot": "R2"}
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def worker(shift):
    P = _load(f"pof_{shift}", POF)
    pod = _load(f"pod375_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = _load(f"hist375_{shift}", ROOT / "backend/history_tm.py")
    v221 = _load(f"v221_375_{shift}", RD / "v221/v221_grid_hysteresis.py")
    fw = _load(f"fw375_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                                                                                 eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = P.DEV0 + sh, P.DEV1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    std_idx = books154.index[books154.index <= P.DEV1 + pd.Timedelta(hours=4)]
    M = pod.minutes()
    opens, prep = P.prep_idx(M, std_idx + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    out = {}
    for name, pipe in {**MANUAL, **BOT}.items():
        kw, trade = P.pipe_setup(pipe, hist, v221, v216, idx, cols, False)
        events = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        m = P.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], ANCH, live0, live1, sh)
        years = []
        for y, a in enumerate(ANCH):
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            ev = [e for e in events if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v221.v216.v213.trade_stats(ev)
            nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
            wb = sum(round((ts.get(k) or {}).get("win_rate", 0) * (ts.get(k) or {}).get("trades", 0)) for k in ("dev", "_hidden"))
            rr = [float(e["ret"]) for e in ev if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")]
            yy = m["yearly"][y]
            years.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"], nb=nb, wb=wb, nr=len(rr), wr=int(sum(r > 0 for r in rr))))
        out[name] = years
        print(shift, name, [round(100 * y["net"], 1) for y in years], [y["dd"] for y in years], flush=True)
    return shift, out


def metrics(allres, name, ys):
    R, DD, W = [], [], []
    nb = wb = nr = wr = 0
    for sh in range(4):
        yy = [allres[sh][name][y] for y in ys]
        R.append(100 * (np.prod([1 + y["net"] for y in yy]) ** (1 / (12 * len(yy))) - 1))
        DD.append(max(y["dd"] for y in yy))
        W.append(min(100 * ((1 + y["net"]) ** (1 / 12) - 1) for y in yy))
        nb += sum(y["nb"] for y in yy); wb += sum(y["wb"] for y in yy); nr += sum(y["nr"] for y in yy); wr += sum(y["wr"] for y in yy)
    return dict(R=round(float(np.mean(R)), 3), DD=round(float(np.mean(DD)), 2), W=round(float(np.mean(W)), 3),
                win_book=round(wb / max(nb, 1), 4), win_all=round((wb + wr) / max(nb + nr, 1), 4), R_phases=[round(r, 3) for r in R])


def f_manual_pooled(m):
    g1 = np.minimum([m["R"] / 5, 20 / max(m["DD"], 1e-6), m["win_book"] / 0.55, min(1.0, 1 + m["W"] / 2)], 1.0)
    if g1.min() < 1:
        return float(0.7 * g1.min() + 0.3 * g1.mean())
    g2 = np.minimum([m["R"] / 8, 15 / max(m["DD"], 1e-6), m["win_book"] / 0.60], 1.2)
    return float(1 + 0.25 * g2.min() + 0.75 * g2.mean())


def f_bot(m):
    if m["W"] < 0:
        return -1 + m["R"] / 100
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6), m["win_all"] / 0.65], 1.2)
    return float(0.5 * g.min() + 0.5 * g.mean())


def fitness(allres, name, ys, product):
    if product == "bot":
        return f_bot(metrics(allres, name, ys))
    if len(ys) == 1:
        return f_manual_pooled(metrics(allres, name, ys))
    return float(0.5 * min(f_manual_pooled(metrics(allres, name, [y])) for y in ys) + 0.5 * f_manual_pooled(metrics(allres, name, ys)))


def main():
    with Pool(4) as pool:
        allres = dict(pool.map(worker, range(4)))
    out = {"version": "v375", "rows": {}, "folds": {}, "final": {}, "transfer": {}}
    for product, rows in (("manual", MANUAL), ("bot", BOT)):
        for name in rows:
            out["rows"][name] = dict(dev4=metrics(allres, name, [0, 1, 2, 3]), F=round(fitness(allres, name, [0, 1, 2, 3], product), 4),
                                     years=[metrics(allres, name, [y]) for y in range(4)])
            print(product, name, out["rows"][name]["dev4"], "F", out["rows"][name]["F"], flush=True)
        gains = []
        for k in (2, 3):
            ch = max(rows, key=lambda r: fitness(allres, r, list(range(k)), product))
            fc, f0 = fitness(allres, ch, [k], product), fitness(allres, REF[product], [k], product)
            out["folds"][f"{product}_{k}"] = dict(choice=ch, test_F=round(fc, 4), ref_F=round(f0, 4))
            gains.append(ch != REF[product] and fc > f0)
            print("FOLD", product, k, ch, round(fc, 4), "vs", REF[product], round(f0, 4), flush=True)
        out["transfer"][product] = bool(all(gains))
        ch = max(rows, key=lambda r: fitness(allres, r, [0, 1, 2, 3], product))
        out["final"][product] = dict(choice=ch, dev4=out["rows"][ch]["dev4"], reference=out["rows"][REF[product]]["dev4"],
                                     recommended=ch if out["transfer"][product] else REF[product])
        print("FINAL", product, json.dumps(out["final"][product]), "TRANSFER", out["transfer"][product], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v375_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
