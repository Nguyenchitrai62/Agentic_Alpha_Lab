"""v390: ex-ante (covariance) risk sizing of the BOOK in the multi-phase BOT R2-4P (registry v390).

Why: the book's portfolio scale s = target / trailing 60-day realized vol of the book's OWN past PnL (engine_user, v92 lineage) does not
see the CURRENT positions' risk. The G2 / R2 drawdown anatomy (research/diagnostics/g2_dd) found half of the DD is the book's one-way
concentration (all-long into a -11 % BTC move, net-short into a +16 % squeeze) across five assets with ~0.8 correlation. An ex-ante estimate
sigma_ex(i) = sqrt(365 * 6 * w_i' Sigma_i w_i) with w_i = W_BOOKS * book row i and Sigma_i the covariance of 4h open-to-open returns over the
trailing 360 bars (min 120; opens up to the decision row, the same information as the engine's own scale) is large when the book is one-way
and small when it is mixed. s_ex = min(target / sigma_ex, cap) with the engine's target 0.25 and cap 2.0.
Implementation without engine changes: the audited trade-mode hook book_size(i, a, sgn) multiplies the target of a NEW book entry (for the
life of that position, adds aim at the scaled target) by m_i = s_ex(i) / s_hist(i) (s_hist = the engine's own formula, recomputed here):
  R2_4P     reference (deployed BOT, cached R2 runs of v388 = identical settings; not re-run)
  R2X1_4P   de-risk only: m = min(1, s_ex / s_hist)
  R2X2_4P   two-sided: m = clip(s_ex / s_hist, 0.5, 1.5)
Dip rungs unchanged (their size still uses s_hist). Evaluation, metrics, BOT fitness, folds and the most-recent-year-once rule exactly as v388
(honest 4-phase harness, agents on with v376/tables_hidden, standard books forward-filled, dev years only for selection).
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v390/v390_exante_book_risk.py
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
RUNS = {"R2X1": "derisk", "R2X2": "twosided"}
ROWS = {"R2_4P": "R2", "R2X1_4P": "R2X1", "R2X2_4P": "R2X2"}
REF = "R2_4P"
PD, TARGET, CAP, LOOK = 6, 0.25, 2.0, 360


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_390", RD / "v388" / "v388_bot_stop_distance.py")
ANCH, Y1 = v388.ANCH, v388.Y1


def risk_ratio(books, opens, idx, cols, w_books):
    """s_ex / s_hist per decision row (causal: opens up to the row, book row i)."""
    o = opens.reindex(idx)[cols]
    r = o / o.shift(1) - 1
    realized = w_books * (books.shift(2) * r).sum(axis=1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s_hist = np.where(np.isnan(vol), 1.0, np.minimum(TARGET / np.where(np.isnan(vol), 1.0, vol), CAP))
    R = r.to_numpy()
    W = w_books * books.to_numpy()
    n = len(idx)
    s_ex = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - LOOK + 1)
        x = R[lo:i + 1]
        x = x[np.all(np.isfinite(x), axis=1)]
        if len(x) < 120 or not np.any(W[i]):
            continue
        sig = float(np.sqrt(max(W[i] @ np.cov(x, rowvar=False) @ W[i], 0.0) * PD * 365))
        if sig > 0:
            s_ex[i] = min(TARGET / sig, CAP)
    ratio = np.where(np.isfinite(s_ex), s_ex / s_hist, 1.0)
    return ratio


def worker(args):
    shift, names, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod390_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist390_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_390_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw390_{shift}", ROOT / "scripts/forward_v205.py")
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
    ratio = risk_ratio(books, opens, idx, cols, eu.v99.W_BOOKS)
    live = np.asarray((idx >= live0) & (idx < live1))
    print(shift, "ratio live mean", round(float(np.mean(ratio[live])), 3), "p10/p50/p90", np.round(np.percentile(ratio[live], [10, 50, 90]), 3), flush=True)
    out = {}
    for name in names:
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        if RUNS.get(name) == "derisk":
            kw["book_size"] = lambda i, a, sgn: float(min(1.0, ratio[i]))
        elif RUNS.get(name) == "twosided":
            kw["book_size"] = lambda i, a, sgn: float(np.clip(ratio[i], 0.5, 1.5))
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
        print(shift, name, "last" if last_year else "dev", round(out[name]["eq"][-1], 3), flush=True)
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
    cache = HERE / "v390_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            allres = dict(pool.map(worker, [(s, list(RUNS), False) for s in range(4)]))
        ref = pickle.loads((RD / "v388" / "v388_runs.pkl").read_bytes())
        for s in range(4):
            allres[s]["R2"] = ref[s]["R2"]
        cache.write_bytes(pickle.dumps(allres))
    out = {"version": "v390", "rows": {}, "folds": {}}
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
        for s in range(4):
            e1, m1 = v388.hourly(last[s][ROWS[ch]], pd.Timestamp("2021-09-24 04:00", tz="UTC"), Y1 + pd.Timedelta(hours=12))
            b = float(e1[e1.index <= a0].iloc[-1])
            E.append(e1[e1.index > a0] / b); MN.append(m1[m1.index > a0] / b)
        es, ms = sum(E) / 4, sum(MN) / 4
        pk = np.maximum.accumulate(es.to_numpy())
        out["final"]["most_recent_year_once"] = dict(monthly=round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3),
                                                     dd_conservative=round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2))
    print("TRANSFER", out["transfer"], "FINAL", json.dumps(out["final"]), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v390_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
