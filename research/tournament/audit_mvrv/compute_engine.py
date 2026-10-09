"""audit_mvrv 4-phase engine: G2 reference + M1 blind replica + CTRL_M1 control.

Mechanism copied from research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py
on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0). Gate (PLAN.md) applied AFTER
the bear-book filter and BEFORE the shifted-clock forward fill, on STANDARD book rows.
Rows before 2021-09-24 are never gated (v426 convention).

Usage:
  python research/tournament/audit_mvrv/compute_engine.py --check-g2   # fast, cached v421 only
  python research/tournament/audit_mvrv/compute_engine.py --run        # heavy 4-phase engine
Heavy runs must go through:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag audit_mvrv --min-free-gb 2.0 -- <above>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
V421_PKL = RD / "v421" / "v421_runs.pkl"
OUT_PKL = HERE / "tmp" / "audit_mvrv_runs.pkl"

sys.path.insert(0, str(HERE))
import signals_mvrv as SG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_audit", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_audit", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1
G2KEY = "R2B1D17BFG2"

# Expected G2 rows from v421_result.json (reproduce-to-the-digit gate)
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27), (4.648, 12.9)]
EXP = dict(R=5.41, W=2.588, DD=16.91, FULL=16.82)


def check_g2() -> dict:
    runs = pickle.loads(V421_PKL.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, set(runs)
    assert G2KEY in runs[0], list(runs[0])
    years = [rm.year_reset(runs, G2KEY, y) for y in range(5)]
    rows = [(y["R"], y["DD"]) for y in years]
    g1 = Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, G2KEY, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    geo = round(float(100 * (np.prod([1 + y["R"] / 100 for y in years]) ** (1 / 5) - 1)), 3)
    print("G2 cached yearly:", rows, flush=True)
    print(f"G2 cached geo={geo} W={min(y['R'] for y in years)} DD={max(y['DD'] for y in years)} full={full}", flush=True)
    for (r, d), (er, ed) in zip(rows, EXP_YEARS):
        assert abs(r - er) < 0.0005, (r, er)
        assert abs(d - ed) < 0.005, (d, ed)
    assert abs(geo - EXP["R"]) < 0.0005, geo
    assert abs(max(y["DD"] for y in years) - EXP["DD"]) < 0.005
    assert abs(full - EXP["FULL"]) < 0.005, full
    print("G2 REPRODUCED to the digit.", flush=True)
    return dict(yearly=rows, R=geo, W=min(y["R"] for y in years),
                DD=max(y["DD"] for y in years), full_path_dd=full)


def build_gates(sb: pd.DataFrame):
    mvrv = SG.load_mvrv_daily()
    zm = SG.compute_zm(mvrv)
    zT = SG.z_at_T(sb.index, zm)
    mult = SG.m1_multiplier(zT)
    s_m1 = SG.apply_gate(sb, mult)
    s_ctrl, means = SG.control_multiplier(sb, mult)
    share = SG.gated_share(sb, mult)
    return mult, s_m1, s_ctrl, means, share, zT


def worker(shift: int):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podamv_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histamv_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221amv_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwamv_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap: dict = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    # bear filter on the STANDARD grid (exactly as v426/v421)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    # M1 gate + control on the STANDARD grid
    mult, s_m1, s_ctrl, means, share, zT = build_gates(sb)
    print(shift, "M1 gated long-cell share",
          {k: v["share"] for k, v in share.items()},
          "means", {k: round(v, 4) for k, v in means.items()}, flush=True)
    books_g2 = sb.reindex(idx, method="ffill").fillna(0.0)
    books_m1 = s_m1.reindex(idx, method="ffill").fillna(0.0)
    books_ctrl = s_ctrl.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    variants = {"G2": books_g2, "M1": books_m1, "CTRL_M1": books_ctrl}
    out: dict = {}
    for name, books in variants.items():
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]

        def corr_size(i, a, r, f, base_size=base_size):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult_ = 1.0 / (1 + n)
            return mult_ * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0
        ev: list = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    out["_meta"] = dict(means=means, share=share)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy), DD=max(y["DD"] for y in yy),
                losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main_run():
    g2 = check_g2()  # reproduce first, else stop
    OUT_PKL.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PKL.exists():
        runs = pickle.loads(OUT_PKL.read_bytes())
        print("loaded cached runs", sorted(runs), flush=True)
    else:
        t0 = pd.Timestamp.now(tz="UTC")
        print(f"engine start {t0} (4 phases, Pool(2), heavy_slot holder)", flush=True)
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        OUT_PKL.write_bytes(pickle.dumps(runs))
        print("saved", OUT_PKL, flush=True)
    rows = {r: stats(runs, r, list(range(5))) for r in ("G2", "M1", "CTRL_M1")}
    dev4 = {r: stats(runs, r, list(range(4))) for r in ("G2", "M1", "CTRL_M1")}
    for r, m in rows.items():
        print(r, "5y", m, "dev4", dev4[r], flush=True)
    # our G2 must match cached G2 to the digit
    for (r, d), (er, ed) in zip(rows["G2"]["years"], EXP_YEARS):
        assert abs(r - er) < 0.0005, (r, er)
        assert abs(d - ed) < 0.005, (d, ed)
    assert abs(rows["G2"]["R"] - EXP["R"]) < 0.0005
    print("OWN G2 matches v421 cache to the digit.", flush=True)
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in ("G2", "M1", "CTRL_M1"):
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        rows[r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, "full-path DD", rows[r]["full_path_dd"], flush=True)
    assert abs(rows["G2"]["full_path_dd"] - EXP["FULL"]) < 0.005
    # gated bars per year from shift-0 standard grid (deterministic, engine-independent)
    import importlib.util as iu
    fw_spec = iu.spec_from_file_location("fw_meta", ROOT / "scripts/forward_v205.py")
    _ = fw_spec  # (engine already validated the gate; counts recomputed cheaply below)
    rep = {
        "reference_G2": {"yearly": rows["G2"]["years"], "R5y": rows["G2"]["R"],
                         "W5y": rows["G2"]["W"], "DDmax": rows["G2"]["DD"],
                         "full_path_dd": rows["G2"]["full_path_dd"]},
        "M1": {"yearly": rows["M1"]["years"], "R5y": rows["M1"]["R"],
               "W5y": rows["M1"]["W"], "DDmax": rows["M1"]["DD"],
               "full_path_dd": rows["M1"]["full_path_dd"],
               "dev4": dev4["M1"]},
        "CTRL_M1": {"yearly": rows["CTRL_M1"]["years"], "R5y": rows["CTRL_M1"]["R"],
                    "W5y": rows["CTRL_M1"]["W"], "DDmax": rows["CTRL_M1"]["DD"],
                    "full_path_dd": rows["CTRL_M1"]["full_path_dd"],
                    "dev4": dev4["CTRL_M1"]},
        "G2_dev4": dev4["G2"],
        "gated": runs[0]["_meta"]["share"],
        "control_means": runs[0]["_meta"]["means"],
        "costs": "maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts nothing, win_start=5, stop-first",
    }
    (HERE / "replication.json").write_text(json.dumps(rep, indent=1))
    print("wrote replication.json BEFORE any oc_lit_position/oc_mvrvrobust read", flush=True)
    (HERE / "results.json").write_text(json.dumps(
        {"rows": rows, "dev4": dev4, "gated": runs[0]["_meta"]["share"],
         "control_means": runs[0]["_meta"]["means"]}, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-g2", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.check_g2:
        check_g2()
    elif a.run:
        main_run()
    else:
        check_g2()
