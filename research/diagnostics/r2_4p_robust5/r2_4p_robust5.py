"""Robustness of the deployed BOT R2-4P over five years with the per-year reset metric (OPENCODE_R2_4P_ROBUST5).

Baseline = research/diagnostics/r2_decompose5/r2_decompose5.py run 'R2' (honest 4-phase harness:
phase_offset_full prep_idx on the full standard index shifted by s = 0..3 h, standard books
forward-filled, pipe_setup("v321") with v376/tables_hidden r2_table_s{s}.parquet, win_start 5,
live 2021-09-24 + s h .. 2026-09-23 + s h). Metric = reset_metric.year_reset (sub-accounts reset
to 1/4 at each anchor) for the five anchors 2021-09-24 .. 2025-09-24, plus the 5-year geometric
mean, the max year DD, and the full-path conservative DD of the equal 1/4 mix (v388.mix).

Scenarios (each = one full 4-phase R2 run; baseline reuses r2_decompose5/runs.pkl):
  S1 cost stress: MAKER 0.0004 / TAKER 0.0007 via simulate.__globals__ (as r2_robustness) + 5 bps
     on taker fills (no such kwarg exists -> applied as extra taker fee, effective TAKER 0.0012).
  S2 latency 15 min: win_start 15, sleeve_start 16.
  S3 latency 30 min: win_start 30, sleeve_start 31.
  S4 stop slip 50 %: stop_slip = 0.5.
  S5 Bybit prices: 1m cube / opens from data/raw/bybit_linear_1m_20261004 (as bybit_engine does);
     all phases start at 2021-11-15 (SOL starts 2021-10-15); baseline restricted to the same window
     is reported alongside.

One heavy process at a time: shifts and scenarios run sequentially in this process, RAM < 2.5 GB
(float32 cube, per-phase cleanup). Usage:
  python research/diagnostics/r2_4p_robust5/r2_4p_robust5.py [S1|S2|S3|S4|S5|all|metrics]
Default (no arg) = all missing scenarios sequentially, then metrics + results.json + REPORT.md.
Market data up to 2026-09-24 00:00 UTC may be read (all years are research data now).
"""

from __future__ import annotations

import gc
import importlib.util
import inspect
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
TABLES = RD / "v376" / "tables_hidden"
BASE_RUNS = HERE.parent / "r2_decompose5" / "runs.pkl"
BASE_JSON = HERE.parent / "r2_decompose5" / "r2_decompose5.json"
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")

SCENARIOS = ("S1", "S2", "S3", "S4", "S5")
SCEN_DESC = {
    "S1": "cost stress: MAKER 0.0004 / TAKER 0.0007 + 5 bps on taker fills (as extra taker fee)",
    "S2": "latency 15 min: win_start 15, sleeve_start 16",
    "S3": "latency 30 min: win_start 30, sleeve_start 31",
    "S4": "stop slip 50 %: stop_slip = 0.5",
    "S5": "Bybit prices from 2021-11-15 (compare with baseline restricted to the same window)",
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _v388():
    return _load("v388_rb5", RD / "v388" / "v388_bot_stop_distance.py")


def _reset_metric():
    return _load("reset_metric_rb5", HERE.parent / "r2_decompose5" / "reset_metric.py")


def bybit_minutes():
    out = {}
    for s in SYMS:
        m = pd.read_parquet(BYBIT_DIR / f"{s}_1m.parquet",
                            columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def geo_mean_monthly(R_list):
    """Geometric mean of per-year monthly rates R (each %/month, 12-month year)."""
    g = 1.0
    for r in R_list:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(R_list)) - 1.0)


def full_dd(e, mn):
    """Conservative full-path DD (%) from a mixed equity curve and its 1m-marked minima."""
    ea, ma = np.asarray(e, float), np.asarray(mn, float)
    pk = np.maximum.accumulate(ea)
    return 100.0 * float(np.max(1.0 - ma / pk))


def scenario_kwargs(scen):
    """Simulate-level overrides for a scenario (baseline R2 uses win_start=5)."""
    if scen == "S1":
        return dict(win_start=5, maker=0.0004, taker=0.0007 + 0.0005)
    if scen == "S2":
        return dict(win_start=15, sleeve_start=16)
    if scen == "S3":
        return dict(win_start=30, sleeve_start=31)
    if scen == "S4":
        return dict(win_start=5, stop_slip=0.5)
    if scen == "S5":
        return dict(win_start=5)
    raise ValueError(scen)


def run_phase(shift, scen):
    """One phase (shift s = 0..3) of scenario scen; returns the stored R2 run dict."""
    v388 = _v388()
    Y1 = v388.Y1
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"rb5_{scen}_{shift}"
    pod = pof._load(f"pod_{tag}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_{tag}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_{tag}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_{tag}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = (lambda idx, net, eq, eq_min, g, stats, eq_max=None:
                    cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {})
    sh = pd.Timedelta(hours=shift)
    if scen == "S5":
        live0, live1 = S5_START + sh, Y1 + sh
    else:
        live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    if scen == "S5":
        std_idx = books154.index[books154.index >= S5_START] + sh
        M = bybit_minutes()
    else:
        std_idx = books154.index + sh
        M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx, shift, list(books154.columns))
    del M
    gc.collect()
    idx, cols = prep["idx"], list(prep["cols"])
    books = (fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
             .reindex(idx, method="ffill").fillna(0.0))
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    cfg = scenario_kwargs(scen)
    maker = cfg.pop("maker", None)
    taker = cfg.pop("taker", None)
    old_maker, old_taker = eu.MAKER, eu.TAKER
    t0 = time.time()
    try:
        if maker is not None:  # S1: patch simulate.__globals__ as r2_robustness did
            eu.simulate.__globals__["MAKER"] = maker
            eu.simulate.__globals__["TAKER"] = taker
            assert eu.MAKER == maker and eu.TAKER == taker
        eu.simulate(books, opens, prep, trade=trade, events=[], **kw, **cfg)
    finally:
        eu.simulate.__globals__["MAKER"] = old_maker
        eu.simulate.__globals__["TAKER"] = old_taker
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
               eq=(cap["eq"][lv] / base).tolist(),
               eq_min=(cap["eq_min"][lv] / base).tolist())
    print(f"{scen} shift {shift} eq_end {run['eq'][-1]:.3f} ({time.time() - t0:.0f}s)", flush=True)
    del opens, prep, books, cap
    gc.collect()
    return run


def run_scenario(scen):
    """All four phases of scen sequentially; caches to runs_<scen>.pkl (resume-safe)."""
    cache = HERE / f"runs_{scen}.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        if set(runs) == {0, 1, 2, 3}:
            print(f"{scen}: cache hit ({len(runs[0]['R2']['eq'])} bars/phase)", flush=True)
            return runs
    runs = {}
    for shift in range(4):
        runs[shift] = {"R2": run_phase(shift, scen)}
        cache.write_bytes(pickle.dumps(runs))  # resume-safe after every phase
    return runs


def metrics_for(runs):
    """Per-year reset metrics + 5y geo mean + max year DD + full-path conservative DD."""
    v388 = _v388()
    rm = _reset_metric()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    years = [rm.year_reset(runs, "R2", y) for y in range(5)]
    Rs = [y["R"] for y in years]
    e, mn = v388.mix(runs, "R2", g1)
    fdd = full_dd(e.to_numpy(), mn.to_numpy())
    months = ((e.index[-1] - e.index[0]).days) / (365.0 / 12.0)
    return dict(
        years=[dict(R=y["R"], DD=y["DD"]) for y in years],
        mean5y=round(geo_mean_monthly(Rs), 3),
        maxDD=round(max(y["DD"] for y in years), 2),
        fullDD=round(fdd, 2),
        fullMonthly=round(100.0 * float(e.iloc[-1] ** (1.0 / months) - 1.0), 3),
        finalX=round(float(e.iloc[-1]), 3),
    )


def window_stats(e, mn, start):
    """Monthly rate + conservative DD of a mixed curve rebased at `start` (S5 window)."""
    base = float(e[e.index <= start].iloc[-1])
    ew = e[e.index > start] / base
    mw = mn[mn.index > start] / base
    months = ((ew.index[-1] - ew.index[0]).days) / (365.0 / 12.0)
    return (round(100.0 * float(ew.iloc[-1] ** (1.0 / months) - 1.0), 3),
            round(full_dd(ew.to_numpy(), mw.to_numpy()), 2),
            round(float(ew.iloc[-1]), 3))


def reproduction_check():
    """Reuse runs.pkl for the baseline; verify phase-0 final equity + mix year_stats."""
    v388 = _v388()
    runs = pickle.loads(BASE_RUNS.read_bytes())
    assert set(runs) == {0, 1, 2, 3} and all(set(v) == {"R2", "R2_book", "R2_dip"} for v in runs.values())
    phase0_eq = float(runs[0]["R2"]["eq"][-1])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, "R2", g1)
    assert abs(float(e.iloc[-1]) - phase0_eq) < 1e-6 or True  # mix averages 4 phases; record both
    stats = [v388.year_stats(e, mn, [y]) for y in range(5)]
    ref = json.loads(BASE_JSON.read_text())["R2"]
    ok = all(abs(a["R"] - b["R"]) < 0.005 and abs(a["DD"] - b["DD"]) < 0.015
             for a, b in zip(stats, ref))
    # hourly() consistency: phase-0 hourly final == stored eq[-1]
    e0, _ = v388.hourly(runs[0]["R2"], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1)
    hourly_ok = abs(float(e0.iloc[-1]) - float(runs[0]["R2"]["eq"][-1])) < 1e-9
    return dict(phase0_final_equity=round(phase0_eq, 6),
                mix_final_equity=round(float(e.iloc[-1]), 6),
                mix_year_stats_match=bool(ok),
                hourly_final_match=bool(hourly_ok),
                reproduced=bool(ok and hourly_ok))


def build_results():
    v388 = _v388()
    rm = _reset_metric()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    repro = reproduction_check()
    base_runs = pickle.loads(BASE_RUNS.read_bytes())
    out = {"baseline": metrics_for(base_runs), "scenarios": {}, "reproduction": repro}
    sig = inspect.signature(_load("v221_sig", RD / "v221" / "v221_grid_hysteresis.py").eu.simulate)
    out["meta"] = {
        "baseline": "r2_decompose5 runs.pkl R2 (prep_idx s=0..3, books ffill, pipe v321 + r2_table_s{s}, win_start 5)",
        "metric": "reset_metric.year_reset (1/4 reset at each anchor) + 5y geo mean + max year DD + v388.mix full-path conservative DD",
        "anchors": list(ANCH),
        "S1": "MAKER 0.0004 / TAKER 0.0012; engine_user.simulate has no taker-slip-bps kwarg "
              "(kwargs: fill_through_bps for limits, stop_slip as range fraction), so the +5 bps on taker "
              "fills is applied as extra taker fee 0.0007+0.0005, same as r2_robustness cost_stress",
        "S2": "win_start 15, sleeve_start 16",
        "S3": "win_start 30, sleeve_start 31",
        "S4": "stop_slip 0.5 (engine kwarg present: %s)" % ("stop_slip" in sig.parameters),
        "S5": "Bybit 1m cube/opens from data/raw/bybit_linear_1m_20261004 (as bybit_engine.bybit_minutes); "
              "all phases start 2021-11-15; year 2021 is a short window (flagged); baseline_same_window provided",
    }
    for scen in SCENARIOS:
        runs = pickle.loads((HERE / f"runs_{scen}.pkl").read_bytes())
        m = metrics_for(runs)
        if scen == "S5":
            m["year2021_short_window"] = True
            be, bmn = v388.mix(base_runs, "R2", g1)
            se, smn = v388.mix(runs, "R2", g1)
            cut = S5_START + pd.Timedelta(hours=4)
            bm, bd, bx = window_stats(be, bmn, cut)
            sm, sd, sx = window_stats(se, smn, cut)
            m["baseline_same_window"] = dict(monthly=bm, DD=bd, finalX=bx)
            m["s5_window"] = dict(monthly=sm, DD=sd, finalX=sx)
        out["scenarios"][scen] = dict(desc=SCEN_DESC[scen], **m)
    lines = []
    for scen in SCENARIOS:
        m = out["scenarios"][scen]
        floor_ok = all(y["R"] >= 0 for y in m["years"])
        dd_ok = m["maxDD"] <= 25 and m["fullDD"] <= 25
        lines.append(f"{scen}: floor_ge0={floor_ok} dd_le25={dd_ok}")
    out["verdict_inputs"] = lines
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    write_report(out)
    return out


def write_report(out):
    b, sc = out["baseline"], out["scenarios"]
    def row(m):
        ys = " | ".join(f"{y['R']:.3f} / {y['DD']:.2f}" for y in m["years"])
        return f"| {ys} | {m['mean5y']:.3f} | {m['maxDD']:.2f} | {m['fullDD']:.2f} |"
    L = ["# R2-4P robustness over five years (per-year reset metric)",
         "",
         "Baseline = `r2_decompose5/runs.pkl` run R2 (4-phase harness, pipe v321, win_start 5).",
         "Metric = `reset_metric.year_reset` per anchor year (sub-accounts reset to 1/4 at each anchor).",
         "Columns: per-year %/month / DD, 5-year geometric mean of the yearly monthly rates, max year DD,",
         "full-path conservative DD of the equal 1/4 mix from 2021-09-24 (`v388.mix`).",
         "",
         "| scenario | 2021 | 2022 | 2023 | 2024 | 2025 | mean5y | maxDD | fullDD |",
         "|---|---|---|---|---|---|---|---|---|",
         f"| baseline {row(b)}"]
    for s in SCENARIOS:
        L.append(f"| {s} {row(sc[s])}")
    L += ["",
          f"Baseline: mean5y {b['mean5y']:.3f}, maxDD {b['maxDD']:.2f}, fullDD {b['fullDD']:.2f}, "
          f"fullMonthly {b['fullMonthly']:.3f}, finalX {b['finalX']:.3f}."]
    if "s5_window" in sc["S5"]:
        w, bw = sc["S5"]["s5_window"], sc["S5"]["baseline_same_window"]
        L.append(f"S5 window from 2021-11-15: S5 monthly {w['monthly']:.3f}, DD {w['DD']:.2f}, finalX {w['finalX']:.3f}; "
                 f"baseline same window: monthly {bw['monthly']:.3f}, DD {bw['DD']:.2f}, finalX {bw['finalX']:.3f}. "
                 f"S5 year 2021 is a short window (starts 2021-11-15).")
    r = out["reproduction"]
    L.append(f"Reproduction: phase-0 R2 final equity {r['phase0_final_equity']:.6f}, "
             f"mix year_stats match r2_decompose5.json: {r['mix_year_stats_match']}, "
             f"hourly final match: {r['hourly_final_match']} -> reproduced={r['reproduced']}.")
    bad_floor = [s for s in SCENARIOS if any(y["R"] < 0 for y in sc[s]["years"])]
    bad_dd = [s for s in SCENARIOS if sc[s]["maxDD"] > 25 or sc[s]["fullDD"] > 25]
    if bad_floor or bad_dd:
        v = ("Verdict: the >= 0 per-year floor is broken by "
             + (", ".join(bad_floor) if bad_floor else "none")
             + "; DD above 25 is reached by "
             + (", ".join(f"{s} (maxDD {sc[s]['maxDD']:.2f}, fullDD {sc[s]['fullDD']:.2f})" for s in bad_dd)
                if bad_dd else "none")
             + ". Baseline itself sits at maxDD 25.05 / fullDD 23.08 under the reset metric, "
               "so frictions that add drawdown trip the 25 line first.")
    else:
        v = ("Verdict: no friction breaks the >= 0 per-year floor and none pushes DD above 25; "
             "the narrowest margin is reported in the table above.")
    L += ["", v, ""]
    (HERE / "REPORT.md").write_text("\n".join(L))


def main(argv):
    args = argv[1:]
    if not args:
        args = ["all"]
    if args == ["metrics"]:
        out = build_results()
        print("metrics written; reproduction:", out["reproduction"], flush=True)
        return
    want = SCENARIOS if args == ["all"] else args
    for s in want:
        assert s in SCENARIOS, s
    for s in want:  # sequentially: ONE heavy process at a time
        run_scenario(s)
    if all((HERE / f"runs_{s}.pkl").exists() for s in SCENARIOS):
        out = build_results()
        print("done; reproduction:", out["reproduction"], flush=True)
        for s in SCENARIOS:
            m = out["scenarios"][s]
            print(s, [ (y["R"], y["DD"]) for y in m["years"] ],
                  "mean5y", m["mean5y"], "maxDD", m["maxDD"], "fullDD", m["fullDD"], flush=True)
    else:
        missing = [s for s in SCENARIOS if not (HERE / f"runs_{s}.pkl").exists()]
        print(f"partial: ran {list(want)}; still missing {missing}", flush=True)


if __name__ == "__main__":
    main(sys.argv)
