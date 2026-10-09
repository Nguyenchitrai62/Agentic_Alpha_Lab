"""oc_hlspread engine (4-phase, HEAVY via heavy_slot, Pool(2)).

PLAN-fixed. Mechanism copied from v426/v426_book_brake.py:
STANDARD book rows (sb index) with bear-filtered weights gated per (T,sym)
AFTER the bear-book filter and BEFORE the shifted-clock forward fill.
  G2   = R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True, G 2.0), cached
  H1   = G2 + z>+1.5 -> long x0.5; z<-1.5 -> short x0.5 (panel.parquet)
  CTRL = per-year exposure-matched constants cL_y/cS_y (H1 realised mean
         mult on long/short cells that year), no timing.
Rows before 2021-09-24 never gated (v426 convention).
Gate costs/fills/funding = gate model in PLAN (engine handles it).
Step 1 reproduces cached G2 5.41/16.91/16.82 to the digit, else stops.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_hlspread --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_hlspread/run_engine.py
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
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]
TABLES = RD / "v376" / "tables_hidden"

RUNS = {"R2B1D17BFG2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0),
        "H1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="H1"),
        "CTRL": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="CTRL")}
CACHED = {"R2B1D17BFG2": ("research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl", "R2B1D17BFG2")}
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF21 = pd.Timestamp("2021-09-24", tz="UTC")
EXP_R, EXP_DD, EXP_FULL = 5.41, 16.91, 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_hlspread", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_hlspread", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1

_PANEL = None


def panel():
    global _PANEL
    if _PANEL is None:
        p = pd.read_parquet(HERE / "panel.parquet", columns=["T", "sym", "z", "gate_long", "gate_short"])
        p["T"] = pd.to_datetime(p["T"], utc=True)
        _PANEL = p
    return _PANEL


def gate_frames(sb: pd.DataFrame):
    """H1 per-(T,sym) gated books + per-year CTRL constants on STANDARD index."""
    p = panel()
    T = sb.index
    tset_L = set(p["T"][p["gate_long"].to_numpy(bool)].astype(str) + "|" + p["sym"])
    # faster: build dict keyed (T_str, sym)
    gl = set(zip(p["T"][p["gate_long"].to_numpy(bool)].astype(str), p["sym"]))
    gs = set(zip(p["T"][p["gate_short"].to_numpy(bool)].astype(str), p["sym"]))
    sbv = sb.to_numpy(float)
    cols = list(sb.columns)
    n, m = sbv.shape
    mult = np.ones((n, m))
    Tstr = T.astype(str)
    gated_ok = np.asarray(pd.to_datetime(T, utc=True) >= CUTOFF21)
    for j, c in enumerate(cols):
        colL = np.array([(t, c) in gl for t in Tstr]) & gated_ok
        colS = np.array([(t, c) in gs for t in Tstr]) & gated_ok
        mult[colL, j] *= 0.5  # longs halved where z>+1.5 (applied below only to longs)
        mult[colS, j] *= 0.5  # shorts halved where z<-1.5 (applied below only to shorts)
    # Apply side-conditionally: long gate only to w>0, short gate only to w<0.
    # Rebuild exactly: need separate masks. Redo per side for correctness:
    h1 = sb.copy()
    h1v = sbv.copy()
    for j, c in enumerate(cols):
        colL = np.array([(t, c) in gl for t in Tstr]) & gated_ok
        colS = np.array([(t, c) in gs for t in Tstr]) & gated_ok
        adjL = colL & (sbv[:, j] > 0)
        adjS = colS & (sbv[:, j] < 0)
        h1v[adjL, j] *= 0.5
        h1v[adjS, j] *= 0.5
    h1[:] = h1v
    # CTRL per-year constants from H1 realised mean mults
    multH1 = np.ones((n, m))
    multH1[h1v != sbv] = 0.5  # every adjusted cell is exactly x0.5 (no overlap: L/S disjoint)
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(T, utc=True)
    cL, cS = {}, {}
    ctrlv = sbv.copy()
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        if sel.sum() == 0:
            cL[k], cS[k] = 1.0, 1.0
            continue
        L = (sbv[sel] > 0)
        S = (sbv[sel] < 0)
        cL[k] = float(multH1[sel][L].mean()) if L.sum() else 1.0
        cS[k] = float(multH1[sel][S].mean()) if S.sum() else 1.0
        ctrlv[sel][L] *= cL[k]
        ctrlv[sel][S] *= cS[k]
    ctrl = sb.copy()
    ctrl[:] = ctrlv
    info = dict(cL={str(ANCH[k].date()): round(cL[k], 6) for k in range(5)},
                cS={str(ANCH[k].date()): round(cS[k], 6) for k in range(5)},
                gated_long_cells=int(((h1v != sbv) & (sbv > 0)).sum()),
                gated_short_cells=int(((h1v != sbv) & (sbv < 0)).sum()),
                long_cells=int((sbv > 0).sum()), short_cells=int((sbv < 0).sum()))
    return {"H1": h1, "CTRL": ctrl}, info


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podhls_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histhls_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_hls_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwhls_{shift}", ROOT / "scripts/forward_v205.py")
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
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    gated, ginfo = gate_frames(sb)
    print(shift, "gated long cells", ginfo["gated_long_cells"], "short", ginfo["gated_short_cells"],
          "of", ginfo["long_cells"], "/", ginfo["short_cells"], flush=True)
    fwd = {"H1": gated["H1"].reindex(idx, method="ffill").fillna(0.0),
           "CTRL": gated["CTRL"].reindex(idx, method="ffill").fillna(0.0)}
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name in CACHED:
            continue
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
            mm = f - 1
            nn = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, mm, b]) and np.isfinite(sg[i][b])):
                    continue
                nn += float(C[i, mm, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + nn) if rule == "inv" else (0.5 if nn >= 2 else 1.0)
            return mult * kd * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        eu.simulate(fwd[cfg["gate"]], opens, prep, trade=trade, win_start=5, events=[], **kw)
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


def main():
    # Step 1: reproduce cached G2 exactly.
    runs_cached = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = stats(runs_cached, "R2B1D17BFG2", list(range(5)))
    e, mn = v388.mix(runs_cached, "R2B1D17BFG2", Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2:", got, "full", full, flush=True)
    assert got["R"] == EXP_R and got["DD"] == EXP_DD and full == EXP_FULL, (got, full, exp)
    print("G2 reproduction OK (5.41 / 16.91 / 16.82)", flush=True)

    cache = HERE / "tmp" / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        for row, (pth, key) in CACHED.items():
            cr = pickle.loads((ROOT / pth).read_bytes())
            for s in range(4):
                runs[s][row] = cr[s][key]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "oc_hlspread_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in RUNS},
           "y2023": {r: rm.year_reset(runs, r, 2) for r in RUNS},
           "y2024": {r: rm.year_reset(runs, r, 3) for r in RUNS},
           "y2025": {r: rm.year_reset(runs, r, 4) for r in RUNS}}
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    assert out["rows"]["R2B1D17BFG2"]["full_path_dd"] == EXP_FULL
    # gate accounting on the standard index (same for all phases)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    hist0 = pof0._load("histhls_info", ROOT / "backend/history_tm.py")
    v221_0 = pof0._load("v221_hls_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwhls_info", ROOT / "scripts/forward_v205.py")
    eu0 = v221_0.eu
    eu0.v110.START, eu0.v110.END = pof0.DEV0, Y1
    books154, _o = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)
    btc = _o["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    gated, ginfo = gate_frames(sb)
    out["gate_info"] = ginfo
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(sb.index, utc=True)
    sbv = sb.to_numpy(float)
    h1v = gated["H1"].to_numpy(float)
    per_year = []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        Lc = int((sbv[sel] > 0).sum())
        Sc = int((sbv[sel] < 0).sum())
        per_year.append({"year": str(ANCH[k].date()), "long_cells": Lc, "short_cells": Sc,
                         "gated_long": int((((h1v[sel] != sbv[sel]) & (sbv[sel] > 0)).sum())),
                         "gated_short": int((((h1v[sel] != sbv[sel]) & (sbv[sel] < 0)).sum())),
                         "cL": ginfo["cL"][str(ANCH[k].date())], "cS": ginfo["cS"][str(ANCH[k].date())]})
    out["per_year_gate"] = per_year
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "tmp" / "engine_results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
