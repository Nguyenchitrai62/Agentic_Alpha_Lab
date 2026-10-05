"""v405: tighter governor + more risk on correlation-aware R2-4P (registry v405).

Why: v404 - the governor (0.18, 0.10) on R2B1_130 cut the full-path DD 20.5 -> 18.7 (yearly max 16.5) at 4.78 vs 5.17 %/month: a DD-for-return
dial that acts on the 2022 grind. Hypothesis: with that governor the risk multiplier can be raised so the return is back above 5 %/month
while the full-path DD stays <= 20.
Rows (fixed before running): R2B1_130 (reference, v400 cache), R2B1G18_140 (gov (0.18, 0.10), k 1.4, dip budget 0.26 x 1.4), R2B1G18_150
(gov (0.18, 0.10), k 1.5). Everything else as v400 R2B1_130. Harness, reset metric, full-path DD, selection and folds exactly as v401.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v405/v405_gov_risk.py
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
RUNS = {"R2B1_130": dict(rule="inv", k=1.3), "R2B1G18_140": dict(rule="inv", k=1.4, gov=(0.18, 0.10)), "R2B1G18_150": dict(rule="inv", k=1.5, gov=(0.18, 0.10))}
REF = "R2B1_130"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_405", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_405", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod405_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist405_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_405_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw405_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name == REF:
            continue  # reference = v400 cached R2B1_130 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]

        def corr_size(i, a, r, f, base_size=base_size, rule=rule):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k
        if "gov" in cfg:
            kw["gov"] = cfg["gov"]
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=[], **kw)
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
    cache = HERE / "v405_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((RD / "v400" / "v400_runs.pkl").read_bytes())
        for s in range(4):
            runs[s][REF] = ref[s][REF]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v405", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
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
    (HERE / "v405_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
