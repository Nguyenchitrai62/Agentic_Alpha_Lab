"""audit_d1 engine: REF (cache) + D1 tilt on G2 (v421 rule inv k1.0 kd1.7 bear G2.0).

Blind independent implementation. Mechanism copied from
research/tournament/audit_c2/run_engine.py (itself a copy of
oc_chronos/run_engine.py = v414 pipe v321, corr-aware inv sizes kd=1.7,
bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
gate costs inside the engine). Fits from fit_d1.py (shift-0 only,
risk=risk_D1). Heavy: run via scripts/heavy_slot.py.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
FEATS = HERE / "downshare_D1_4shift.parquet"

ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
STRAT_REF = "R2B1D17BFG2"
STRAT_D1 = "R2B1D17BFG2D1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_d1", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_d1", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def load_fits():
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    d = harness.load()
    f = pd.read_parquet(FEATS, columns=["sym", "shift", "T", "risk_D1"])
    f0 = f[f["shift"] == 0][["sym", "T", "risk_D1"]].copy()
    f0["T"] = pd.to_datetime(f0["T"], utc=True)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    fits = {}
    for a in ANCH:
        cut = a - EMBARGO
        tr = d[d.sym.isin(harness.MAJORS) & (d.t_exit < cut)]
        m = tr.merge(f0, on=["sym", "T"], how="inner")
        m = m[m["risk_D1"].notna()]
        rho = float(m["risk_D1"].corr(m["y_dep"], method="spearman")) if len(m) else float("nan")
        direction = int(1 if rho > 0 else (-1 if rho < 0 else 0))
        q20 = float(m["risk_D1"].quantile(0.20)) if len(m) else float("nan")
        q80 = float(m["risk_D1"].quantile(0.80)) if len(m) else float("nan")
        fits[str(a.date())] = dict(direction=direction, q20=q20, q80=q80,
                                   rho=rho, n_train=int(len(tr)), n_joined=int(len(m)))
    return fits


def load_feat_maps():
    f = pd.read_parquet(FEATS)
    f["T"] = pd.to_datetime(f["T"], utc=True)
    maps = {}
    for s in range(4):
        d = f[f["shift"] == s][["sym", "T", "risk_D1"]]
        maps[s] = dict(zip(zip(d["sym"], d["T"]), d["risk_D1"].astype(float)))
    return maps


FITS = None
FMAPS = None


def anchor_for(H):
    # latest anchor <= H; warmup before first anchor uses first fit
    H = pd.Timestamp(H)
    if H.tzinfo is None:
        H = H.tz_localize("UTC")
    else:
        H = H.tz_convert("UTC")
    for k in range(len(ANCH) - 1, -1, -1):
        if H >= ANCH[k]:
            return str(ANCH[k].date())
    return str(ANCH[0].date())


def assign_mult(risk, direction, q20, q80, hi=1.25, lo=0.75):
    if direction == 0 or not np.isfinite(q20) or not np.isfinite(q80):
        return 1.0
    if not np.isfinite(risk):
        return 1.0
    if direction == 1:
        if risk >= q80:
            return hi
        if risk <= q20:
            return lo
        return 1.0
    else:
        if risk <= q20:
            return hi
        if risk >= q80:
            return lo
        return 1.0


def d1_mult(sym, H, shift):
    global FITS, FMAPS
    key = anchor_for(H)
    fit = FITS[key]
    Hn = pd.Timestamp(H)
    Hn = Hn.tz_localize("UTC") if Hn.tzinfo is None else Hn.tz_convert("UTC")
    v = FMAPS[shift].get((sym, Hn), np.nan)
    if not np.isfinite(v):
        return 1.0
    risk = float(v)
    return assign_mult(risk, fit["direction"], fit["q20"], fit["q80"])


def worker(shift):
    global FITS, FMAPS
    if FITS is None:
        FITS = load_fits()
    if FMAPS is None:
        FMAPS = load_feat_maps()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podad1_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histad1_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_ad1_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwad1_{shift}", ROOT / "scripts/forward_v205.py")
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
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    # D1 only (REF comes from v421 cache bit-exact)
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size = kw["sleeve_fill_size"]
    kd = 1.7

    def corr_size(i, a, r, f, base_size=base_size, kd=kd):
        m = f - 1
        n = 0
        for b in range(len(cols)):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
        mult = 1.0 / (1 + n)
        H = idx[i] + pd.Timedelta(hours=4)
        tilt = d1_mult(cols[a], H, shift)
        return mult * kd * tilt * base_size(i, a, r, f)

    kw["sleeve_fill_size"] = corr_size
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
    kw["sleeve_gross_cap"] = 2.0
    ev = []
    eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    out[STRAT_D1] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
    print(shift, STRAT_D1, round(out[STRAT_D1]["eq"][-1], 3), flush=True)
    return shift, out


def main():
    global FITS, FMAPS
    FITS = load_fits()
    FMAPS = load_feat_maps()
    print("FITS", json.dumps(FITS, indent=1), flush=True)
    cache = HERE / "audit_d1_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(1) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    # score with reset metric (REF from v421 cache, D1 from this run)
    ref = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    for s in range(4):
        runs[s][STRAT_REF] = ref[s][STRAT_REF]
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    for strat in (STRAT_REF, STRAT_D1):
        yy = [rm.year_reset(runs, strat, y) for y in range(5)]
        print(strat, yy, flush=True)
    g1 = Y1 + pd.Timedelta(hours=12)
    for strat in (STRAT_REF, STRAT_D1):
        e, mn = v388.mix(runs, strat, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        print(strat, "full-path DD",
              round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2), flush=True)


if __name__ == "__main__":
    main()
