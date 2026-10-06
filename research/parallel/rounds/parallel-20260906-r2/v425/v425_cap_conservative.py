"""v425: dip gross cap on the conservative frontier rows (registry v425) - stretch-DD attempt.

Why: v421 showed the dip gross-notional cap G = 2.0 (engine hook sleeve_gross_cap) lowers R2B1D17BF's max yearly DD 18.33 -> 16.91 at
~no return cost; v425 found the conservative rows R2B1D13BF 4.97 %/month / max yearly DD 14.98 and R2B1D14BFX5 5.07 / 15.34. Applying
the cap to these rows may reach the stretch target (max yearly DD < 15 at >= 5 %/month). LABEL: POST-HOC INFORMED (levers found on the
same five research years); prospective paper (bot d13bf running) is the clean test.
Rows (fixed before running; B1 rule x kd / (1 + n), budget 0.26 x kd, bear-book filter, R2 agents):
  R2B1D17BF       reference (v411 cache).
  D13BFG2         kd 1.3, gross cap 2.0.
  D14BFG2         kd 1.4, gross cap 2.0.
  D14BFX5G2       kd 1.4, 5.0 sigma rung dropped, gross cap 2.0.
  D15BFG2         kd 1.5, gross cap 2.0.
Pool(2). Harness, reset metric, full-path DD, robust selection and folds exactly as v411/v425. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v425/v425_cap_conservative.py
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
RUNS = {"R2B1D17BF": dict(rule="inv", k=1.0, kd=1.7, bear=True), "D13BFG2": dict(rule="inv", k=1.0, kd=1.3, bear=True, G=2.0),
        "D14BFG2": dict(rule="inv", k=1.0, kd=1.4, bear=True, G=2.0), "D14BFX5G2": dict(rule="inv", k=1.0, kd=1.4, bear=True, drop=(5.0,), G=2.0),
        "D15BFG2": dict(rule="inv", k=1.0, kd=1.5, bear=True, G=2.0)}
REF = "R2B1D17BF"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_425", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_425", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod425_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist425_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_425_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw425_{shift}", ROOT / "scripts/forward_v205.py")
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
    for name, cfg in RUNS.items():
        if name == REF:
            continue  # reference = v406 cached R2B1D16 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]

        kd = cfg.get("kd", 1.0)

        ev, stops, ptr = [], {}, [0]
        cool = cfg.get("cool", False)
        COOL = pd.Timedelta(hours=24)

        def cooled(i, a):
            while ptr[0] < len(ev):  # index stop exits recorded so far (rungs of earlier bars and of this bar's earlier fills)
                e = ev[ptr[0]]
                ptr[0] += 1
                if e["kind"] == "rung_sl":
                    stops.setdefault(e["symbol"], []).append(e["t"])
            B = idx[i] + pd.Timedelta(hours=4)
            return any(s_ < B <= s_ + COOL for s_ in stops.get(cols[a], [])[-20:])

        RG = tuple(kw.get("rungs", eu.RUNGS))
        drop = set(cfg.get("drop", ()))
        print(shift, name, "rungs", RG, "drop", sorted(drop), flush=True)

        F = cfg.get("F", 2.5)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, cool=cool, RG=RG, drop=drop, F=F):
            if drop and RG[r] in drop:
                return 0.0
            if cool and cooled(i, a):
                return 0.0
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - F * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult * kd * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        if "xrp" in cfg:
            base_sl = kw.get("m_sleeve_sl", 4.0)
            xa = cols.index("XRPUSDT")
            kw["sleeve_sl_coin"] = lambda i, a, xa=xa, x=cfg["xrp"], b=base_sl: x if a == xa else b
        if "bm" in cfg:
            trade["book_mult"] = cfg["bm"]

        eu.simulate(books_bear if cfg.get("bear") else books, opens, prep, trade=trade, win_start=5, events=ev, **kw)
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
    cache = HERE / "v425_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
        for s in range(4):
            runs[s][REF] = ref[s][REF]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v425", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
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
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, "full-path DD", out["rows"][r]["full_path_dd"], flush=True)
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v425_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
