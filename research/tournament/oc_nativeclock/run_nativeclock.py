"""oc_nativeclock heavy engine run: G2 REF (forward-filled) + NATIVE books, 4 phases.

Exact v421_gross_cap.py:worker replica for the G2 row (R2B1D17BFG2: rule inv,
k=1.0, kd=1.7, bear True, G=2.0), plus the NATIVE book frames from the same
construction as build_native_books.py (bit-identical to REF given the member
audit: all 6 members forward-filled). Runs BOTH book sets through eu.simulate
per shift and asserts NATIVE equity == REF equity bit-exact (phase 0 trivially
identical). Captures events for per-year book/dip trade stats + engine stats
(fills, fees/funding as reported by the engine).

Read-only inputs; writes tmp/native_runs.pkl + tmp/native_engine_years.json.
Heavy: run ONLY via:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_nativeclock --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_nativeclock/run_nativeclock.py
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_shift(shift, M, books154, std_books, opens_std):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podnc_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histnc_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221nc_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), stats=dict(stats)) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, pof.DEV1 + pd.Timedelta(days=365) + sh
    Y1 = pd.Timestamp("2026-09-23", tz="UTC")
    live1 = Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    sh_idx = books154.index + sh
    opens, prep = pof.prep_idx(M, sh_idx, shift, list(books154.columns))
    idx, cols = prep["idx"], list(prep["cols"])
    std = std_books.reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_ref = sb.reindex(idx, method="ffill").fillna(0.0)
    # NATIVE: all members forward-filled per audit -> identical frame
    books_nat = sb.reindex(idx, method="ffill").fillna(0.0)
    assert float(np.max(np.abs(books_nat.to_numpy() - books_ref.to_numpy()))) == 0.0
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    results = {}
    for tag, books in (("REF", books_ref), ("NATIVE", books_nat)):
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule, kd = kw["sleeve_fill_size"], "inv", 1.7

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
        kw["risk_mult"] = lambda i, e, k=1.0: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
        kw["sleeve_gross_cap"] = 2.0
        ev = []
        t0 = time.time()
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        bw = pof.book_win(v221, ev, live0, live1)
        results[tag] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                            eq=(cap["eq"][lv] / base).tolist(),
                            eq_min=(cap["eq_min"][lv] / base).tolist(),
                            stats=cap["stats"], book_win=bw,
                            n_events=len(ev), secs=round(time.time() - t0))
        print(f"shift {shift} {tag}: eq_end {round(results[tag]['eq'][-1], 4)} "
              f"book_trades {bw['book_trades']} win {bw['book_win']} rungs {bw['rungs']} "
              f"in {results[tag]['secs']}s", flush=True)
    # NATIVE must equal REF bit-exact (same books fed)
    assert results["NATIVE"]["eq"] == results["REF"]["eq"], "NATIVE != REF equity"
    assert results["NATIVE"]["eq_min"] == results["REF"]["eq_min"], "NATIVE != REF eq_min"
    return shift, results


def main():
    t_start = time.time()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    pod0 = pof0._load("podnc_main", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    eu0 = _load("eu0nc", RD / "engine_user/engine_user.py")
    fw0 = _load("fw0nc", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)[list(books154.columns)]
    print("loading 1m minutes (full OHLC, heavy) ...", flush=True)
    M = pod0.minutes()
    print(f"minutes loaded in {time.time()-t_start:.0f}s", flush=True)
    out = {}
    for shift in range(4):
        print(f"--- shift {shift} ---", flush=True)
        s, res = run_shift(shift, M, books154, std_books, opens_std)
        out[s] = res
        print(f"shift {s} done in {time.time()-t_start:.0f}s total", flush=True)
    (HERE / "tmp" / "native_runs.pkl").write_bytes(pickle.dumps(out))
    # per-year reset metrics for REF (= NATIVE) with reset_metric
    rm = _load("rm_nc", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    ref_runs = {s: {"REF": out[s]["REF"]} for s in range(4)}
    years = [rm.year_reset(ref_runs, "REF", y) for y in range(5)]
    for y, m in enumerate(years):
        print(f"year {y}: {m}", flush=True)
    # compare against v421 pickle (tolerance: bit-exact expected, allow 1e-9)
    v421 = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    maxd = 0.0
    for s in range(4):
        a = np.asarray(out[s]["REF"]["eq"], float)
        b = np.asarray(v421[s]["R2B1D17BFG2"]["eq"], float)
        n = min(len(a), len(b))
        maxd = max(maxd, float(np.max(np.abs(a[:n] - b[:n]))))
    print(f"max |eq_replica - eq_v421| over 4 phases: {maxd:.3e}", flush=True)
    (HERE / "tmp" / "native_engine_years.json").write_text(json.dumps(
        {"years": years, "max_abs_diff_vs_v421": maxd}, indent=1, default=str))
    print(f"done in {time.time()-t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
