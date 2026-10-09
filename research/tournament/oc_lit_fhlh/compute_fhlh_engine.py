"""oc_lit_fhlh engine: BTC FH(00:00-00:30) book gate on G2 (4-phase engine).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py:
multiplier on STANDARD book rows (sb index) AFTER the bear-book filter and
BEFORE the shifted-clock forward fill. Rows before 2021-09-24 are not gated.
Shorts/flats/NaN-FH unchanged unless the variant says so. Dip untouched.

  G2      = R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True, G 2.0), no gate
  M1      = G2 + longs x1.0 if FH>0 else x0.6
  M2      = M1 longs + shorts x1.0 if FH<0 else x0.6
  M3      = M1 with |FH| < med(A) -> x1.0 (per-anchor median, PLAN-fixed)
  CTRL_M1 = per-year constant long mult = M1 realised mean over long cells
  CTRL_M2 = CTRL_M1 longs + per-year constant short mult = M2 short mean
  CTRL_M3 = per-year constant long mult = M3 realised mean over long cells

Step 1 validates the cached G2 (v421_runs.pkl -> 5.41 / 16.91 / 16.82); else stops.
HEAVY: run through heavy_slot (Pool(2), same as v426).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_lit_fhlh_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_lit_fhlh/compute_fhlh_engine.py
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
from fhlh_signal import ANCH, CUTOFF, asof_fh, asof_median, daily as _daily_full, gate_mults, medians

RUNS = {
    "G2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0),
    "M1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="M1"),
    "M2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="M2"),
    "M3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="M3"),
    "CTRL_M1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="CTRL_M1"),
    "CTRL_M2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="CTRL_M2"),
    "CTRL_M3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="CTRL_M3"),
}
GATED = ("M1", "M2", "M3", "CTRL_M1", "CTRL_M2", "CTRL_M3")
EXP_R, EXP_W, EXP_DD, EXP_FULL = 5.41, 2.588, 16.91, 16.82
DAILY_PQ = HERE / "tmp" / "daily_fh.parquet"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_fhlh", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_fhlh", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1

_DAILY = None
_MED = None


def get_daily() -> pd.DataFrame:
    global _DAILY, _MED
    if _DAILY is None:
        if DAILY_PQ.exists():
            _DAILY = pd.read_parquet(DAILY_PQ)
            _DAILY.index = pd.to_datetime(_DAILY.index, utc=True)
        else:
            _DAILY = _daily_full()
            DAILY_PQ.parent.mkdir(parents=True, exist_ok=True)
            _DAILY.to_parquet(DAILY_PQ)
        _MED = medians(_DAILY)
    return _DAILY


def gate_frames(sb: pd.DataFrame):
    """Per-row gated books on the STANDARD index. Returns dict name->DataFrame + info."""
    d = get_daily()
    global _MED
    if _MED is None:
        _MED = medians(d)
    T = sb.index
    fh = asof_fh(d, T)
    med = asof_median(d, T, _MED)
    gated_ok = np.asarray(pd.to_datetime(T, utc=True) >= CUTOFF)
    gm = gate_mults(fh, med)
    m1 = np.where(gated_ok, gm["M1_long"], 1.0)
    s2 = np.where(gated_ok, gm["M2_short"], 1.0)
    m3 = np.where(gated_ok, gm["M3_long"], 1.0)
    sbv = sb.to_numpy(float)
    is_long = sbv > 0
    is_short = sbv < 0
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(T, utc=True)
    c1 = np.ones(len(T))
    c2l = np.ones(len(T))
    c2s = np.ones(len(T))
    c3 = np.ones(len(T))
    mu1, mu2s, mu3 = [], [], []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        if is_long[sel].sum():
            full = np.broadcast_to(m1[sel][:, None], is_long[sel].shape)
            a = float(full[is_long[sel]].mean())
        else:
            a = 1.0
        if is_long[sel].sum():
            full3 = np.broadcast_to(m3[sel][:, None], is_long[sel].shape)
            b = float(full3[is_long[sel]].mean())
        else:
            b = 1.0
        if is_short[sel].sum():
            fulls = np.broadcast_to(s2[sel][:, None], is_short[sel].shape)
            c = float(fulls[is_short[sel]].mean())
        else:
            c = 1.0
        mu1.append(round(a, 6))
        mu3.append(round(b, 6))
        mu2s.append(round(c, 6))
        c1[sel] = a
        c3[sel] = b
        c2l[sel] = a
        c2s[sel] = c
    out = {}
    g = sb.copy()
    g[:] = np.where(is_long & (m1[:, None] < 1.0), sbv * m1[:, None], sbv)
    out["M1"] = g
    g = sb.copy()
    adj = (is_long & (m1[:, None] < 1.0)) | (is_short & (s2[:, None] < 1.0))
    g[:] = np.where(is_long & (m1[:, None] < 1.0), sbv * m1[:, None],
                    np.where(is_short & (s2[:, None] < 1.0), sbv * s2[:, None], sbv))
    out["M2"] = g
    g = sb.copy()
    g[:] = np.where(is_long & (m3[:, None] < 1.0), sbv * m3[:, None], sbv)
    out["M3"] = g
    g = sb.copy()
    g[:] = np.where(is_long, sbv * c1[:, None], sbv)
    out["CTRL_M1"] = g
    g = sb.copy()
    g[:] = np.where(is_long, sbv * c2l[:, None],
                    np.where(is_short, sbv * c2s[:, None], sbv))
    out["CTRL_M2"] = g
    g = sb.copy()
    g[:] = np.where(is_long, sbv * c3[:, None], sbv)
    out["CTRL_M3"] = g
    info = dict(
        fh=fh.tolist(),
        med=med.tolist(),
        mult_M1=m1.tolist(),
        mult_M2_short=s2.tolist(),
        mult_M3=m3.tolist(),
        ctrl_M1_per_year=mu1,
        ctrl_M2_short_per_year=mu2s,
        ctrl_M3_per_year=mu3,
    )
    info["long_cells"] = int(is_long.sum())
    info["short_cells"] = int(is_short.sum())
    info["gated_cells_M1"] = int(((m1[:, None] < 1.0) & is_long).sum())
    info["gated_cells_M2_long"] = int(((m1[:, None] < 1.0) & is_long).sum())
    info["gated_cells_M2_short"] = int(((s2[:, None] < 1.0) & is_short).sum())
    info["gated_cells_M3"] = int(((m3[:, None] < 1.0) & is_long).sum())
    return out, info


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podfhlh_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histfhlh_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_fhlh_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwfhlh_{shift}", ROOT / "scripts/forward_v205.py")
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
    for name in GATED:
        fwd[name] = gated[name].reindex(idx, method="ffill").fillna(0.0)
    print(shift, "gated long M1", ginfo["gated_cells_M1"], "M3", ginfo["gated_cells_M3"],
          "short M2", ginfo["gated_cells_M2_short"], "of", ginfo["long_cells"], ginfo["short_cells"], flush=True)
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
    assert got["R"] == EXP_R and got["W"] == EXP_W and got["DD"] == EXP_DD and full == EXP_FULL, (got, full, exp)
    print("G2 reproduction OK (5.41 / 2.588 / 16.91 / 16.82)", flush=True)

    get_daily()
    print("daily FH rows", len(get_daily()), "medians", _MED, flush=True)

    cache = HERE / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "oc_lit_fhlh_engine",
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
    hist0 = pof0._load("histfhlh_info", ROOT / "backend/history_tm.py")
    v221_0 = pof0._load("v221_fhlh_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwfhlh_info", ROOT / "scripts/forward_v205.py")
    eu0 = v221_0.eu
    eu0.v110.START, eu0.v110.END = pof0.DEV0, Y1
    books154, _o = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)
    btc = _o["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    gated, ginfo = gate_frames(sb)
    out["gate_info"] = {k: v for k, v in ginfo.items() if k not in ("fh", "med")}
    out["medians"] = _MED
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(sb.index, utc=True)
    m1a = np.array(ginfo["mult_M1"])
    m3a = np.array(ginfo["mult_M3"])
    s2a = np.array(ginfo["mult_M2_short"])
    per_year = []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        sbv = sb.to_numpy(float)[sel]
        long_m = sbv > 0
        short_m = sbv < 0
        per_year.append({
            "year": str(ANCH[k].date()),
            "long_cells": int(long_m.sum()),
            "short_cells": int(short_m.sum()),
            "share_gated_M1": round(float((((m1a[sel])[:, None] < 1.0) & long_m).sum() / max(long_m.sum(), 1)), 6),
            "share_gated_M3": round(float((((m3a[sel])[:, None] < 1.0) & long_m).sum() / max(long_m.sum(), 1)), 6),
            "share_gated_M2_short": round(float((((s2a[sel])[:, None] < 1.0) & short_m).sum() / max(short_m.sum(), 1)), 6),
            "mean_mult_M1": round(float(m1a[sel].mean()), 6),
            "mean_mult_M3": round(float(m3a[sel].mean()), 6),
            "ctrl_M1": ginfo["ctrl_M1_per_year"][k],
            "ctrl_M2_short": ginfo["ctrl_M2_short_per_year"][k],
            "ctrl_M3": ginfo["ctrl_M3_per_year"][k],
        })
    out["per_year_gate"] = per_year
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_results.json").write_text(raw)
    (HERE / "results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
