"""oc_idea2_dipstop: FIXED per-coin dip stops in the 4-phase engine (IDEAS 2026-10-07 section 2).

Pre-registered (REPORT.md section 0, written before any run): only 2 variants.
  P1: G2 + XRP 5.5sg / rest 4.0sg
  P2: G2 + XRP 5.5sg / rest 4.5sg
TP 1.0sg agent lookup unchanged. Gate costs (maker 0.02%%, taker 0.055%%,
longs pay 0.01%%/8h) are the engine defaults. Book idea judged in the 4-phase
engine only (v421 harness verbatim); never a vectorised screen.

Stages:
  python run_dipstop.py --check    # baseline reproduction from cache (light)
  python run_dipstop.py --run      # 4-phase engine for P1/P2 (HEAVY, serial, resumable)
  python run_dipstop.py --slip     # S4 stop_slip=0.5 row for the dev winner (HEAVY)
  python run_dipstop.py --report   # select on dev4, score 2025 once for winner, write results.json

Heavy stages run under scripts/heavy_slot.py (never --leader).
Scratch cache: research/tournament/oc_idea2_dipstop/tmp/ (repo keeps only the
script, REPORT.md and results.json).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
TMP = HERE / "tmp"
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
V421_RUNS = RD / "v421" / "v421_runs.pkl"
V421_RES = RD / "v421" / "v421_result.json"
CC_RES = ROOT / "research/tournament/oc_carrycompound/results.json"

REF = "R2B1D17BFG2"  # G2, from the v421 cache (bit-exact, never rerun)
RUNS = {
    "G2_P1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, xrp=5.5, rest=4.0),
    "G2_P2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, xrp=5.5, rest=4.5),
}
SLIP_ROW_SUFFIX = "_S4slip05"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_dipstop", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_dipstop", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift, names, stop_slip=0.0):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podds_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histds_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_ds_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwds_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name in names:
        cfg = RUNS[name.removesuffix(SLIP_ROW_SUFFIX)]
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult * kd * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        kw["sleeve_gross_cap"] = cfg["G"]
        # fixed per-coin close-stop: XRP cfg["xrp"], rest cfg["rest"]; replaces
        # m_sleeve_sl for the rung stop AND its risk-budget cost (TP untouched)
        kw["m_sleeve_sl"] = cfg["rest"]
        base_sl = cfg["rest"]
        xa = cols.index("XRPUSDT")
        x = cfg["xrp"]
        kw["sleeve_sl_coin"] = lambda i, a, xa=xa, x=x, b=base_sl: x if a == xa else b

        eu.simulate(books_bear if cfg.get("bear") else books, opens, prep,
                    trade=trade, win_start=5, events=[], stop_slip=stop_slip, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, "slip=%s" % stop_slip, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def rank_key(m):
    ok = m["DD"] <= 20 and m["losing"] == 0
    if ok:
        return (2, int(m["R"] >= 5), m["W"], m["R"])
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6)], 1.2)
    return (1 if m["losing"] == 0 else 0, 0, float(0.5 * g.min() + 0.5 * g.mean()), m["R"])


def full_dd(allres, row):
    g1 = Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(allres, row, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    return round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)


def do_check():
    runs = pickle.loads(V421_RUNS.read_bytes())
    exp = json.loads(V421_RES.read_text())["rows"][REF]
    got = stats(runs, REF, list(range(5)))
    assert [r for r, _ in got["years"]] == [r for r, _ in exp["years"]], (got, exp)
    assert [d for _, d in got["years"]] == [d for _, d in exp["years"]], (got, exp)
    assert (got["R"], got["W"], got["DD"]) == (exp["R"], exp["W"], exp["DD"]), (got, exp)
    assert full_dd(runs, REF) == exp["full_path_dd"], (full_dd(runs, REF), exp)
    print("G2 baseline OK: R=%s W=%s DD=%s full=%s" % (got["R"], got["W"], got["DD"], exp["full_path_dd"]), flush=True)
    cc = json.loads(CC_RES.read_text())["rows"]["G2_f0.25"]
    assert (cc["R"], cc["W"], cc["DD"]) == (5.634, 2.778, 16.75), cc
    assert cc["full_path_dd"]["full"] == 16.66, cc
    print("G2+carry baseline OK: R=5.634 W=2.778 DD=16.75 full=16.66", flush=True)


def do_run(shifts, stop_slip=0.0, suffix=""):
    TMP.mkdir(parents=True, exist_ok=True)
    cache = TMP / "runs_dipstop.pkl"
    allres = pickle.loads(cache.read_bytes()) if cache.exists() else {}
    names = [r + suffix for r in RUNS]
    for s in shifts:
        todo = [n for n in names if not (s in allres and n in allres[s])]
        if not todo:
            print("shift %d cached, skip" % s, flush=True)
            continue
        t0 = time.time()
        sh, out = worker(s, todo, stop_slip=stop_slip)
        allres.setdefault(sh, {}).update(out)
        cache.write_bytes(pickle.dumps(allres))
        print("shift %d done in %.1fs" % (s, time.time() - t0), flush=True)
    return allres


def do_report():
    cache = TMP / "runs_dipstop.pkl"
    assert cache.exists(), "no engine runs yet"
    new = pickle.loads(cache.read_bytes())
    ref_runs = pickle.loads(V421_RUNS.read_bytes())
    allres = {}
    for s in range(4):
        allres[s] = dict(ref_runs[s])
        if s in new:
            allres[s].update({k: v for k, v in new[s].items() if not k.endswith(SLIP_ROW_SUFFIX)})
    dev = {r: stats(allres, r, [0, 1, 2, 3]) for r in [REF, *RUNS]}
    for r, m in dev.items():
        print(r, m, flush=True)
    winner = max(RUNS, key=lambda r: rank_key(dev[r]))
    print("dev4 winner:", winner, rank_key(dev[winner]), flush=True)
    # most recent year scored ONCE, for the winner only (+ REF from published cache)
    y4 = {r: rm.year_reset(allres, r, 4) for r in (REF, winner)}
    print("2025 POST-HOC:", y4, flush=True)
    fdd = {REF: full_dd(ref_runs, REF), winner: full_dd(allres, winner)}
    print("full-path DD:", fdd, flush=True)
    folds = {}
    for k in (2, 3, 4):
        ch = max([REF, *RUNS], key=lambda r: rank_key(stats(allres, r, list(range(k)))))
        t, t0 = rm.year_reset(allres, ch, k), rm.year_reset(allres, REF, k)
        good = ch != REF and t["R"] > t0["R"] and t["DD"] <= t0["DD"]
        folds[k] = dict(choice=ch, test=t, ref=t0, good=good)
        print("FOLD", k, ch, t, "vs", t0, good, flush=True)
    slip_runs = {}
    for s in range(4):
        key = winner + SLIP_ROW_SUFFIX
        if s in new and key in new[s]:
            slip_runs[s] = {key: new[s][key]}
    slip_dev = stats(slip_runs, winner + SLIP_ROW_SUFFIX, [0, 1, 2, 3]) if len(slip_runs) == 4 else None
    print("S4 slip dev4:", slip_dev, flush=True)
    out = {
        "meta": {
            "idea": "IDEAS_20261007 section 2: fixed per-coin dip stops (XRP 5.5sg / rest 4.0 or 4.5sg), TP 1.0sg unchanged",
            "prereg": ["G2_P1: XRP5.5/rest4.0", "G2_P2: XRP5.5/rest4.5"],
            "base": "G2=R2B1D17BFG2 v421 cache (inv, k=1.0, kd=1.7, bear, G=2.0); harness = v421 worker verbatim (v321, agents on, win_start=5)",
            "costs": "maker 0.0002, taker 0.00055, longs pay 0.0001/8h (engine defaults); S4 row stop_slip=0.5",
            "metric": "reset_metric.year_reset per anchor year + v421 full-path DD; selection on dev4 only (robust criterion); 2025 scored once for winner, POST-HOC",
            "label": "POST-HOC INFORMED: per-coin choice from oc_idea2 screen that saw all five years",
        },
        "baseline": {
            "G2": {"R": 5.41, "W": 2.588, "DD": 16.91, "full_path_dd": 16.82},
            "G2_carry_f025": {"R": 5.634, "W": 2.778, "DD": 16.75, "full_path_dd": 16.66},
        },
        "dev4": dev,
        "winner": winner,
        "y2025_posthoc": {r: dict(v) for r, v in y4.items()},
        "full_path_dd": fdd,
        "folds": folds,
        "slip_S4_dev4": slip_dev,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("sha256", hashlib.sha256(json.dumps(out, indent=1, default=str).encode()).hexdigest())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--slip", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--shifts", default="0,1,2,3")
    a = ap.parse_args()
    shifts = [int(x) for x in a.shifts.split(",") if x != ""]
    if a.check:
        do_check()
    if a.run:
        do_run(shifts)
    if a.slip:
        new = pickle.loads((TMP / "runs_dipstop.pkl").read_bytes())
        allres = {}
        ref_runs = pickle.loads(V421_RUNS.read_bytes())
        for s in range(4):
            allres[s] = dict(ref_runs[s])
            allres[s].update({k: v for k, v in new.get(s, {}).items() if not k.endswith(SLIP_ROW_SUFFIX)})
        w = max(RUNS, key=lambda r: rank_key(stats(allres, r, [0, 1, 2, 3])))
        print("slip row for winner:", w, flush=True)
        TMP.mkdir(parents=True, exist_ok=True)
        cache = TMP / "runs_dipstop.pkl"
        allres = pickle.loads(cache.read_bytes()) if cache.exists() else {}
        for s in shifts:
            key = w + SLIP_ROW_SUFFIX
            if s in allres and key in allres[s]:
                print("shift %d slip cached, skip" % s, flush=True)
                continue
            t0 = time.time()
            sh, out = worker(s, [key], stop_slip=0.5)
            allres.setdefault(sh, {}).update(out)
            cache.write_bytes(pickle.dumps(allres))
            print("shift %d slip done in %.1fs" % (s, time.time() - t0), flush=True)
    if a.report:
        do_report()


if __name__ == "__main__":
    main()
