"""audit_amihud 4-phase engine: G2 (re-run) + A1 Amihud tilt (blind, PLAN.md only).

Mechanism copied from research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py:
multiplier on STANDARD book rows after the bear filter, before shifted-clock ffill.
Rows before 2021-09-24 not tilted. Harness/costs/fills/reset/full-path exactly as v426/v421.
Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h at 00/08/16 UTC, shorts 0;
limit trade-through fills, win_start=5 (no fill first 5 min), stop-first same-bar.

Usage (one phase per process, via heavy_slot):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag audit_amihud --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/audit_amihud/compute_a1_engine.py --shift S
  ... for S in 0 1 2 3, then:
  .venv/Scripts/python.exe research/tournament/audit_amihud/compute_a1_engine.py --combine
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
TMP = HERE / "tmp"
STRAT_G2 = "R2B1D17BFG2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_shift(shift: int):
    sys.path.insert(0, str(ROOT / "research" / "diagnostics" / "phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podA_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histA_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221A_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwA_{shift}", ROOT / "scripts/forward_v205.py")
    sys.path.insert(0, str(HERE))
    import amihud_signal as sig
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    v388 = _load("v388A", RD / "v388" / "v388_bot_stop_distance.py")
    Y1 = v388.Y1
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
    # A1 tilt on STANDARD rows (sb.index), then ffill to minute grid
    frames, raws, zf = sig.tilt_frames(sb.index, list(sb.columns))
    mult = frames["A1"].reindex(sb.index).fillna(1.0)
    sb_a1 = sb.where(sb == 0.0, sb * mult)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    books_a1 = sb_a1.reindex(idx, method="ffill").fillna(0.0)
    nz = int((sb != 0.0).to_numpy().sum())
    tilted = int(((sb != 0.0) & (mult != 1.0)).to_numpy().sum())
    print(f"shift {shift}: nonzero std cells {nz}, tilted {tilted}, "
          f"mean mult {float(mult.to_numpy()[sb.to_numpy() != 0].mean()) if nz else 1.0:.4f}", flush=True)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    out = {}
    for name, bk in (("G2", books_bear), ("A1", books_a1)):
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule, kd = kw["sleeve_fill_size"], "inv", 1.7
        ev, stops, ptr = [], {}, [0]
        cool = False
        COOL = pd.Timedelta(hours=24)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult_ = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult_ * kd * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e, k=1.0: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
        kw["sleeve_gross_cap"] = 2.0
        eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    TMP.mkdir(exist_ok=True)
    (TMP / f"a1_shift_{shift}.pkl").write_bytes(pickle.dumps({shift: out}))
    print(f"shift {shift} saved", flush=True)


def combine():
    v388 = _load("v388C", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("resetC", ROOT / "research" / "diagnostics" / "r2_decompose5" / "reset_metric.py")
    runs = {}
    for s in range(4):
        p = TMP / f"a1_shift_{s}.pkl"
        if not p.exists():
            raise SystemExit(f"missing {p}; run --shift {s} first")
        runs.update(pickle.loads(p.read_bytes()))
    (HERE / "engine_runs.pkl").write_bytes(pickle.dumps(runs))
    # G2 reproduction check from cache (must match to the digit)
    cache = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    exp_years_R, exp_years_DD = [], []
    for y in range(5):
        yy = rm.year_reset(cache, STRAT_G2, y)
        exp_years_R.append(yy["R"])
        exp_years_DD.append(yy["DD"])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(cache, STRAT_G2, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    exp_full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2 years:", list(zip(exp_years_R, exp_years_DD)), "full", exp_full, flush=True)
    assert exp_years_R == [2.588, 3.282, 6.045, 10.677, 4.648], exp_years_R
    assert exp_years_DD == [10.86, 16.91, 15.81, 8.27, 12.9], exp_years_DD
    assert exp_full == 16.82, exp_full
    # engine rows
    rows = {}
    for name in ("G2", "A1"):
        yy = [rm.year_reset(runs, name, y) for y in range(5)]
        geo5 = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / 5) - 1)
        geo4 = 100 * (np.prod([1 + y["R"] / 100 for y in yy[:4]]) ** (1 / 4) - 1)
        e2, mn2 = v388.mix(runs, name, g1)
        seg2 = e2.index > pd.Timestamp("2021-09-24", tz="UTC")
        es2, ms2 = e2[seg2].to_numpy(), mn2[seg2].to_numpy()
        full = round(100 * float(np.max(1 - ms2 / np.maximum.accumulate(es2))), 2)
        rows[name] = dict(years=yy, R5=round(float(geo5), 3),
                          W5=min(y["R"] for y in yy), DD5=max(y["DD"] for y in yy),
                          dev4_mean=round(float(geo4), 3),
                          dev4_worst=min(y["R"] for y in yy[:4]),
                          dev4_maxDD=max(y["DD"] for y in yy[:4]),
                          full_path_dd=full)
        print(name, rows[name], flush=True)
    # engine G2 must reproduce cached triple to the digit
    assert rows["G2"]["years"] == [{"R": r, "DD": d} for r, d in zip(exp_years_R, exp_years_DD)], \
        (rows["G2"]["years"], exp_years_R, exp_years_DD)
    assert rows["G2"]["R5"] == 5.41, rows["G2"]
    assert rows["G2"]["DD5"] == 16.91, rows["G2"]
    assert rows["G2"]["full_path_dd"] == 16.82, rows["G2"]
    (HERE / "engine_results.json").write_text(json.dumps(rows, indent=1))
    a1 = rows["A1"]
    g2 = rows["G2"]
    rep = {
        "meta": {
            "note": "blind replication of Amihud A1 from oc_lit_xs PLAN.md only; "
                    "daily source data/raw/xs_universe_20260924/*_1d.parquet quote_volume; "
                    "day rule D*(T)=date(T)-1day (D usable iff D+1 00:00<=T); "
                    "XS z ddof=1 same-T only; mult clip(1+0.25z,[0.5,1.5]) both legs; "
                    "v426 mechanism after bear filter before ffill; rows<2021-09-24 not tilted; "
                    "gate costs maker 0.0002 taker 0.00055 longs 0.0001/8h shorts 0; "
                    "win_start=5 trade-through stop-first; written BEFORE opening oc_lit_xs code/REPORT/results",
            "g2_reproduction": {
                "years_R": exp_years_R, "years_DD": exp_years_DD,
                "R5": 5.41, "W5": 2.588, "DD5": 16.91, "full_path_dd": 16.82,
                "engine_reran": True,
            },
        },
        "A1_per_year": a1["years"],
        "A1_dev4_mean": a1["dev4_mean"],
        "A1_dev4_worst": a1["dev4_worst"],
        "A1_dev4_maxDD": a1["dev4_maxDD"],
        "A1_5y_R": a1["R5"],
        "A1_5y_W": a1["W5"],
        "A1_5y_maxDD": a1["DD5"],
        "A1_full_path_dd": a1["full_path_dd"],
        "G2_engine_per_year": g2["years"],
    }
    (HERE / "replication.json").write_text(json.dumps(rep, indent=1))
    print("wrote replication.json", json.dumps(rep, indent=1), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shift", type=int, default=None)
    ap.add_argument("--combine", action="store_true")
    a = ap.parse_args()
    if a.combine:
        combine()
    elif a.shift is not None:
        run_shift(a.shift)
    else:
        raise SystemExit("pass --shift S or --combine")


if __name__ == "__main__":
    main()
