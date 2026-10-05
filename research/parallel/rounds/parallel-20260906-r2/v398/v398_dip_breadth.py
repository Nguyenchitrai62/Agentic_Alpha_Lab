"""v398: breadth - the R2-4P dip sleeve on 11 liquid coins (5 majors + ADA, AVAX, DOGE, LINK, LTC, TRX), book unchanged (registry v398).

RESEARCH ONLY: trading coins beyond the five majors needs the user's explicit OK (AGENTS.md); nothing here is deployed.
Why: both layers sit at a local optimum on the majors (v391-v397); the dip edge per coin is erratic year to year (r2_decompose5, oc_regime)
and crash DDs come from a few simultaneous flushes. More coins = more independent dip opportunities under the SAME risk budget (0.26 counted at
the stop), which should smooth the yearly dip P&L; an older 11-asset sleeve test (v186, engine_real) had lower DD at equal return.
Rows (fixed before running): R2 (reference, r2_decompose5 runs), R2X11 (dip ladder also on the 6 alts with the engine's own rules: their
book target is 0, so the R2 alignment gives their rungs the non-long multiplier 0.5; no agent table for alts -> size 1, TP 1), R2X11N (alts'
rungs at neutral size: sleeve_fill_size 2.0 for alts, i.e. 0.5 x 2 = 1). Book = the standard majors book (alts' columns 0). Alt 1m data:
data/raw/alts_intraday_20260926 (same loader convention as v293.load_1m). Harness, per-year reset metric, selection rule and folds exactly as
v396. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v398/v398_dip_breadth.py
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
RUNS = {"R2": {}, "R2X11": dict(alt_size=1.0), "R2X11N": dict(alt_size=2.0)}
ALTS = ["ADAUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "TRXUSDT"]


def alt_minutes():
    out = {}
    for s_ in ALTS:
        files = sorted((ROOT / "data/raw/alts_intraday_20260926").glob(f"{s_}_1m_20*.parquet"))
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        out[s_] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out
REF = "R2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_398", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_398", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod398_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist398_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_398_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw398_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    M.update(alt_minutes())
    syms = list(books154.columns) + ALTS
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, syms)
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[list(books154.columns)]
    books = std.reindex(columns=cols).fillna(0.0).reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name == "R2":
            continue  # reference = research/diagnostics/r2_decompose5 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        maj_size, alt = kw["sleeve_fill_size"], set(range(5, len(cols)))
        kw["sleeve_fill_size"] = lambda i, a, r, f, ms=maj_size, z=cfg["alt_size"]: z if a in alt else ms(i, a, r, f)
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
    cache = HERE / "v398_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((ROOT / "research/diagnostics/r2_decompose5/runs.pkl").read_bytes())
        for s in range(4):
            runs[s]["R2"] = ref[s]["R2"]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v398", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
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
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v398_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
