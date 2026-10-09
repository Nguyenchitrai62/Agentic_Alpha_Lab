"""audit_cboost analyze: score REF/B7 runs -> replication.json (Part A, blind).

REF reproduction gate first (must match v421 R2B1D17BFG2 to the digit, else STOP).
Metrics: per-year reset %/mo + DD via reset_metric.year_reset; dev4/5y geo means;
full-path DD via v388.mix from 2021-09-24 (max of marked/close).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rm = _load("reset_for_cb", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
v388 = _load("v388_for_cb", RD / "v388/v388_bot_stop_distance.py")

DEV_RUNS = HERE / "tmp" / "runs_dev.pkl"
LAST_RUNS = HERE / "tmp" / "runs_last.pkl"
V421_RES = RD / "v421" / "v421_result.json"
TRIG = HERE / "tmp" / "trigger_counts.json"
OUT = HERE / "replication.json"


def metric_runs(allres):
    return {s: {v: allres[s][v]["run"] for v in allres[s]} for s in allres}


def geo(rs):
    return round(float(100 * (np.prod([1 + r / 100 for r in rs]) ** (1 / len(rs)) - 1)), 3)


def main():
    assert LAST_RUNS.exists(), f"missing {LAST_RUNS} (run last stage first)"
    last = pickle.loads(LAST_RUNS.read_bytes())
    dev = pickle.loads(DEV_RUNS.read_bytes()) if DEV_RUNS.exists() else None
    print(f"[audit_cboost] loaded last shifts={sorted(last)} variants={sorted(last[0])}", flush=True)
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    mr = metric_runs(last)
    # REF gate on all 5 years
    got_ref = [rm.year_reset(mr, "REF", y) for y in range(5)]
    print("[audit_cboost] REF years:", got_ref, flush=True)
    print("[audit_cboost] EXP years:", exp["years"], flush=True)
    for y in range(5):
        assert abs(got_ref[y]["R"] - exp["years"][y][0]) < 1e-9, (y, got_ref[y], exp["years"][y])
        assert abs(got_ref[y]["DD"] - exp["years"][y][1]) < 1e-9, (y, got_ref[y], exp["years"][y])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    for strat in ("REF", "B7"):
        assert strat in mr[0], strat
    e, mn = v388.mix(mr, "REF", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
    assert max(dd_m, dd_c) == exp["full_path_dd"], (dd_m, dd_c, exp["full_path_dd"])
    print(f"[audit_cboost] REF reproduction OK: 5y {exp['R']}/{exp['DD']} full {exp['full_path_dd']}", flush=True)
    if dev is not None:
        mrd = metric_runs(dev)
        gotd = [rm.year_reset(mrd, "REF", y) for y in range(4)]
        for y in range(4):
            assert abs(gotd[y]["R"] - exp["years"][y][0]) < 1e-9, ("dev", y)
            assert abs(gotd[y]["DD"] - exp["years"][y][1]) < 1e-9, ("dev", y)
        print("[audit_cboost] DEV REF gate OK", flush=True)

    rows = {}
    for strat in ("REF", "B7"):
        yy = [rm.year_reset(mr, strat, y) for y in range(5)]
        dev4 = [y["R"] for y in yy[:4]]
        all5 = [y["R"] for y in yy]
        e, mn = v388.mix(mr, strat, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        pk = np.maximum.accumulate(es)
        dd_m = round(100 * float(np.max(1 - ms / pk)), 2)
        dd_c = round(100 * float(np.max(1 - es / pk)), 2)
        # worst marked episode
        dd = 1 - ms / pk
        i_tr = int(np.argmax(dd))
        peak = float(np.max(es[:i_tr + 1])) if i_tr else float(es[0])
        rows[strat] = dict(
            years=[dict(R=y["R"], DD=y["DD"]) for y in yy],
            dev4=dict(R=geo(dev4), W=min(dev4), DD=max(y["DD"] for y in yy[:4]),
                      losing=int(sum(r < 0 for r in dev4))),
            y4=dict(R=yy[4]["R"], DD=yy[4]["DD"]),
            y5=dict(R=geo(all5), W=min(all5), DD=max(y["DD"] for y in yy),
                    losing=int(sum(r < 0 for r in all5))),
            full_path_dd=max(dd_m, dd_c), full_marked_dd=dd_m, full_close_dd=dd_c,
            worst_episode=dict(depth=round(float(dd[i_tr]), 6),
                               trough=str(e.index[seg][i_tr]),
                               peak_value=peak),
        )
        # pooled wins from per-shift wins (last runs)
        nb = wb = nr = wr = 0
        ms_sum, mc, bs = 0.0, 0, 0
        miss = 0
        for s in sorted(last):
            w = last[s][strat]["wins"]
            for y in range(5):
                nb += w[y]["nb"]; wb += w[y]["wb"]; nr += w[y]["nr"]; wr += w[y]["wr"]
            for y in range(5):
                m = last[s][strat]["mult"][str(y)]
                if m["n_sized"]:
                    ms_sum += m["sized_mean"] * m["n_sized"]; mc += m["n_sized"]
                    bs += m["n_boosted"]; miss += m["n_miss"]
        rows[strat]["pooled"] = dict(
            book_trades=nb, book_wins=wb, book_win=round(wb / nb, 4) if nb else None,
            rung_trades=nr, rung_wins=wr, rung_win=round(wr / nr, 4) if nr else None,
            all_trades=nb + nr, all_wins=wb + wr,
            all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
            sized_mean=round(ms_sum / mc, 6) if mc else None,
            n_sized=mc, n_boosted_sized=bs,
            boosted_sizing_share=round(bs / mc, 6) if mc else None,
            n_miss=miss,
        )
    trig = json.loads(TRIG.read_text())
    pq_bytes = (HERE / "boost_mult_4shift.parquet").read_bytes()
    rep = dict(
        meta=dict(
            blind=True,
            contamination=("B7 idea formed after oc_cascadedelay replica covered all five years "
                           "incl. post-release year; every 2025-09-24..2026-09-23 number is a LABELLED "
                           "DIAGNOSTIC, selection on dev4 only"),
            engine=("v421 pipe v321, corr-aware inv kd=1.7, bear books, risk budget 0.26*1*1.7, "
                    "sleeve_gross_cap=2.0, win_start=5, gate costs maker 0.0002/taker 0.00055, "
                    "longs 0.0001/8h shorts 0, trade-through only, nothing first 5 min, stop-first"),
            boost="market-wide per (shift,T): 1.5 iff exists trigger (any major, same shift) with 0<T-tc<=7d else 1.0",
            ref_src="research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl row R2B1D17BFG2",
            b7_src="research/tournament/audit_cboost/tmp/runs_last.pkl (4-phase, win_start=5, gate costs)",
            boost_parquet_sha256=hashlib.sha256(pq_bytes).hexdigest(),
            y4_label="SCORED-ONCE DIAGNOSTIC (contaminated)",
        ),
        triggers=trig,
        years_ref=rows["REF"]["years"],
        years_b7=rows["B7"]["years"],
        dev4_ref=rows["REF"]["dev4"],
        dev4_b7=rows["B7"]["dev4"],
        y4_ref=rows["REF"]["y4"],
        y4_b7=rows["B7"]["y4"],
        y5_ref=rows["REF"]["y5"],
        y5_b7=rows["B7"]["y5"],
        full_path_dd_ref=rows["REF"]["full_path_dd"],
        full_path_dd_b7=rows["B7"]["full_path_dd"],
        full_detail={k: {j: rows[k][j] for j in ("full_marked_dd", "full_close_dd", "worst_episode", "pooled")} for k in ("REF", "B7")},
        cap_check=dict(
            param='kw["sleeve_gross_cap"] = 2.0 for both REF and B7 (asserted in run_engine.py source)',
            note=("Direct per-fill cap-bind counter is not exposed by the engine; reported proxy: "
                  "boosted share of (shift,T) time-bars (from trigger_counts.json) + boosted share of "
                  "sleeve sizings and sized mean multiplier (from pooled). Larger boosted rungs can only "
                  "hit the 2.0 cap at least as often as REF by construction; method disclosed in REPORT."),
        ),
        rows=rows,
    )
    OUT.write_text(json.dumps(rep, indent=1))
    print("[audit_cboost] REF:", rows["REF"]["dev4"], rows["REF"]["y4"], rows["REF"]["y5"], rows["REF"]["full_path_dd"], flush=True)
    print("[audit_cboost] B7 :", rows["B7"]["dev4"], rows["B7"]["y4"], rows["B7"]["y5"], rows["B7"]["full_path_dd"], flush=True)
    print(f"[audit_cboost] wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
