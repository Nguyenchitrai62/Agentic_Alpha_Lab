"""v417: dip stop-cascade controls on the deployment pick R2B1D17BF (registry v417).

Why: two OpenCode screens on the 5 research years passed their pre-registered rules. oc_cooldown (research/tournament/oc_cooldown): a per-coin
24h dip cooldown after a dip stop-out cut the yearly max DD of the rung stream in 4/5 years keeping >= 94% of the sum (mostly the 2022 FTX
cascade). oc_idea2: a wider dip close-stop for XRP only (5.5 sigma, rest 4) beat uniform 4 sigma in 4/5 years (LOO 5/5, worst day 4/5).
Caveat (labelled): both ideas were motivated by oc_ddanat17's drawdown anatomy of the same five years, and XRP was singled out there, so
rows X / CX are POST-HOC INFORMED; a walk-forward per-coin stop choice follows separately. All five years are research data; prospective
paper is the clean test.
Rules (fixed before running):
  C  = cooldown: a dip rung of coin c is not placed (size 0) when a dip rung of c exited by its stop (kind rung_sl, any rung, this sub-book)
       at time s with s < B <= s + 24h, B = the rung's holding bar open (stops are known from earlier bars only; same-bar fills kept).
  X  = per-coin close-stop: XRPUSDT 5.5 sigma, other majors 4 sigma (engine hook sleeve_sl_coin; the risk budget counts the per-coin
       distance; backstop 8 sigma unchanged).
  CX = C + X.
Rows: R2B1D17BF (reference = v411 cache), R2B1D17BFC, R2B1D17BFX, R2B1D17BFCX. Pool(2). Harness, reset metric, full-path DD, robust selection
and folds exactly as v411/v417. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v417/v417_cascade.py
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
RUNS = {"R2B1D17BF": dict(rule="inv", k=1.0, kd=1.7, bear=True), "R2B1D17BFC": dict(rule="inv", k=1.0, kd=1.7, bear=True, cool=True),
        "R2B1D17BFX": dict(rule="inv", k=1.0, kd=1.7, bear=True, xrp=5.5), "R2B1D17BFCX": dict(rule="inv", k=1.0, kd=1.7, bear=True, cool=True, xrp=5.5)}
REF = "R2B1D17BF"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_417", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_417", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod417_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist417_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_417_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw417_{shift}", ROOT / "scripts/forward_v205.py")
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

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, cool=cool):
            if cool and cooled(i, a):
                return 0.0
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
    cache = HERE / "v417_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
        for s in range(4):
            runs[s][REF] = ref[s][REF]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v417", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
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
    (HERE / "v417_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
