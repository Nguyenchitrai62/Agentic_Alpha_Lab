"""oc_stablegate Leg 1: stablecoin-impulse book gate on G2 (4-phase engine).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py:
STANDARD book rows (sb index) with bear-filtered weight > 0 get x0.75,
applied AFTER the bear-book filter and BEFORE the shifted-clock forward fill.
Shorts/flats/NaN-z unchanged. Rows before 2021-09-24 are not gated (v426 convention).

  G2   = R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True, G 2.0), no gate
  G1   = G2 + long x0.75 when z(T) < -1.0
  G2S  = G2 + long x0.75 when z(T) < -1.5
  CTRL = G2 + per-year constant long multiplier = G1 realised mean mult over
         long rows in that anchor year (exposure-matched, no timing)

Step 1 validates the cached G2 (v421_runs.pkl -> 5.41 / 16.91 / 16.82); else stops.
HEAVY: run through heavy_slot (Pool(2), same as v426).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_stablegate_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_stablegate/compute_stablegate_engine.py
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
sys.path.insert(0, str(HERE))
from stablegate_signal import asof_z, load_daily

RUNS = {
    "G2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0),
    "G1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="G1"),
    "G2S": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="G2S"),
    "CTRL": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="CTRL"),
}
THRESH = {"G1": -1.0, "G2S": -1.5}
GATE_MULT = 0.75
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
EXP_R, EXP_DD, EXP_FULL = 5.41, 16.91, 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_sg", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_sg", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1

_DAILY = None


def daily():
    global _DAILY
    if _DAILY is None:
        _DAILY = load_daily()
    return _DAILY


def gate_frames(sb: pd.DataFrame):
    """Per-row gated books on the STANDARD index. Returns dict name->DataFrame + info."""
    d = daily()
    T = sb.index
    z = asof_z(d, T)
    gated_ok = np.asarray(T >= CUTOFF)
    m1 = np.ones(len(T))
    m1[np.isfinite(z) & (z < THRESH["G1"]) & gated_ok] = GATE_MULT
    m2 = np.ones(len(T))
    m2[np.isfinite(z) & (z < THRESH["G2S"]) & gated_ok] = GATE_MULT
    # CTRL: per-year mean of G1 mult over long rows.
    sbv = sb.to_numpy(float)
    is_long = sbv > 0
    ctrl_mult = np.ones(len(T))
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(T, utc=True)
    mean_per_year = []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        seln = sel
        denom = int((is_long[seln]).sum())
        if denom:
            m1sel = m1[seln]
            full = np.broadcast_to(m1sel[:, None], is_long[seln].shape)
            mu = float(full[is_long[seln]].mean())
        else:
            mu = 1.0
        mean_per_year.append(round(mu, 6))
        ctrl_mult[seln] = mu
    out = {}
    for name, mult in (("G1", m1), ("G2S", m2), ("CTRL", ctrl_mult)):
        g = sb.copy()
        adj = (sbv > 0) & (mult[:, None] < 1.0)
        g[:] = np.where(adj, sbv * mult[:, None], sbv)
        out[name] = g
    info = dict(
        z=z.tolist(),
        mult_G1=m1.tolist(),
        mult_G2S=m2.tolist(),
        ctrl_per_year=mean_per_year,
        share_G1=round(float((m1 < 1.0)[is_long.any(axis=1)] .mean()) if len(T) else 0.0, 6),
    )
    # share of book LONG ROWS gated (per-cell, the reported metric is computed per year below)
    long_cells = int(is_long.sum())
    info["gated_cells_G1"] = int(((m1[:, None] < 1.0) & is_long).sum())
    info["gated_cells_G2S"] = int(((m2[:, None] < 1.0) & is_long).sum())
    info["long_cells"] = long_cells
    return out, info


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podsg_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histsg_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_sg_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwsg_{shift}", ROOT / "scripts/forward_v205.py")
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
    books_bear_std = sb.reindex(idx, method="ffill").fillna(0.0)
    gated, ginfo = gate_frames(sb)
    fwd = {"G2": books_bear_std}
    for name in ("G1", "G2S", "CTRL"):
        fwd[name] = gated[name].reindex(idx, method="ffill").fillna(0.0)
    print(shift, "gated long cells G1", ginfo["gated_cells_G1"], "G2S",
          ginfo["gated_cells_G2S"], "of", ginfo["long_cells"], flush=True)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)
        ev, stops, ptr = [], {}, [0]
        COOL = pd.Timedelta(hours=24)

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
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        eu.simulate(fwd[name], opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
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

    cache = HERE / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "oc_stablegate_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in RUNS},
           "dev4": {r: stats(runs, r, list(range(4))) for r in RUNS}}
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    # Per-year gated shares + mean mults (standard-index accounting, same for all phases).
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    hist0 = pof0._load("histsg_info", ROOT / "backend/history_tm.py")
    v221_0 = pof0._load("v221_sg_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwsg_info", ROOT / "scripts/forward_v205.py")
    eu0 = v221_0.eu
    eu0.v110.START, eu0.v110.END = pof0.DEV0, Y1
    books154, _o = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)
    btc = _o["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    gated, ginfo = gate_frames(sb)
    out["gate_info"] = {k: v for k, v in ginfo.items() if k != "z"}
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(sb.index, utc=True)
    per_year = []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        sbv = sb.to_numpy(float)[sel]
        long_m = sbv > 0
        zsel = np.array(ginfo["z"])[sel]
        per_year.append({
            "year": str(ANCH[k].date()),
            "long_cells": int(long_m.sum()),
            "share_gated_G1": round(float((((np.array(ginfo["mult_G1"])[sel])[:, None] < 1.0) & long_m).sum() / max(long_m.sum(), 1)), 6),
            "share_gated_G2S": round(float((((np.array(ginfo["mult_G2S"])[sel])[:, None] < 1.0) & long_m).sum() / max(long_m.sum(), 1)), 6),
            "mean_mult_G1": round(float(np.array(ginfo["mult_G1"])[sel].mean()), 6),
            "ctrl_mult": ginfo["ctrl_per_year"][k],
        })
    out["per_year_gate"] = per_year
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
