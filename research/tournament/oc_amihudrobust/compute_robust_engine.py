"""oc_amihudrobust engine: frozen A1 robustness (frictions, jitters, static).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py via
oc_lit_xs/compute_xs_engine.py: multiplier on STANDARD book rows AFTER the
bear-book filter and BEFORE the shifted-clock forward fill. Rows before
2021-09-24 are not tilted. Base = G2 (R2B1D17BFG2: rule inv, k 1.0, kd 1.7,
bear True, G 2.0). Step 1 validates cached G2; else stops.

Engine rows (17): G2, A1, J_K015, J_K035, J_W20, J_W45, C_STATIC,
  G2_S1..S5, A1_S1..S5 (frictions exactly as v421_audit/robust_v421.py).
Friction defs: S1 MAKER 0.0004/TAKER 0.0012 (globals patched); S2
win_start=15/sleeve_start=16; S3 win_start=30/sleeve_start=31; S4
win_start=5/stop_slip=0.5; S5 Bybit 1m prices from 2021-11-15 (short 2021).
HEAVY: run through heavy_slot (Pool(2), same as v426/oc_lit_xs).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_amihudrobust_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_amihudrobust/compute_robust_engine.py
"""
from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import pickle
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from amihud_signal import SYMS as XS_SYMS, a1_mult

BASE_BOOK_ROWS = ["G2", "A1", "J_K015", "J_K035", "J_W20", "J_W45", "C_STATIC"]
FRIC_SUFFIX = ["S1", "S2", "S3", "S4", "S5"]
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
EXP_R, EXP_DD, EXP_FULL = 5.41, 16.91, 16.82
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81),
             (10.677, 8.27), (4.648, 12.9)]
JITTER_DEFS = {
    "J_K015": dict(K=0.15, W=30, minp=20),
    "J_K035": dict(K=0.35, W=30, minp=20),
    "J_W20": dict(K=0.25, W=20, minp=13),
    "J_W45": dict(K=0.25, W=45, minp=30),
}
A1_DEF = dict(K=0.25, W=30, minp=20)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_amihudrobust", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_amihudrobust", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def build_tilt_frames_std(sb: pd.DataFrame):
    """Tilt frames on the STANDARD index. Returns (frames dict, info)."""
    cols = list(sb.columns)
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    frames: dict[str, pd.DataFrame] = {}
    # A1 base
    f_a1, _ = a1_mult(T, cols=cols, **A1_DEF)
    f_a1.loc[Tts < CUTOFF] = 1.0
    frames["A1"] = f_a1
    # jitters
    for name, kw in JITTER_DEFS.items():
        f, _ = a1_mult(T, cols=cols, **kw)
        f.loc[Tts < CUTOFF] = 1.0
        frames[name] = f
    # static control: per (year, coin) constant = mean A1 mult over TRAIN=[Y-365d, Y-7d)
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    static = pd.DataFrame(1.0, index=T, columns=cols)
    train_means: dict[str, list] = {}
    a1v = f_a1.to_numpy(float)
    colix = {c: i for i, c in enumerate(cols)}
    for ci, c in enumerate(cols):
        ms = []
        for k in range(5):
            tr0, tr1 = bounds[k] - pd.Timedelta(days=365), bounds[k] - pd.Timedelta(days=7)
            sel = np.asarray((Tts >= tr0) & (Tts < tr1))
            mu = float(a1v[sel, ci].mean()) if sel.sum() else 1.0
            ms.append(round(mu, 6))
        train_means[c] = ms
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        for ci, c in enumerate(cols):
            static.to_numpy()[sel, ci] = train_means[c][k]
    static.loc[Tts < CUTOFF] = 1.0
    frames["C_STATIC"] = static
    info = dict(train_means=train_means,
                jitter={k: dict(v) for k, v in JITTER_DEFS.items()})
    return frames, info


def gate_books(sb: pd.DataFrame):
    """Apply tilt frames to bear-filtered standard books. Returns (books, info)."""
    cols = list(sb.columns)
    frames, info = build_tilt_frames_std(sb)
    sbv = sb.to_numpy(float)
    Tts = pd.to_datetime(sb.index, utc=True)
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    books: dict[str, pd.DataFrame] = {}
    per_year: dict[str, list] = {}
    for name in ["A1", *JITTER_DEFS, "C_STATIC"]:
        m = frames[name].to_numpy(float)
        aff = sbv != 0
        g = sb.copy()
        g[:] = np.where(aff, sbv * m, sbv)
        books[name] = g
        rows = []
        for k in range(5):
            sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
            denom = int(aff[sel].sum())
            tilt = int(((m[sel] != 1.0) & aff[sel]).sum())
            mu = float(m[sel][aff[sel]].mean()) if denom else 1.0
            rows.append(dict(year=str(ANCH[k].date()), affected_cells=denom,
                             tilted_cells=tilt,
                             share_tilted=round(tilt / max(denom, 1), 6),
                             mean_mult=round(mu, 6)))
        per_year[name] = rows
    info["per_year"] = per_year
    return books, info


def bybit_minutes():
    out = {}
    for s in XS_SYMS:
        # files are <SYM>_1m.parquet with ms open_time (same as robust_v421)
        m = pd.read_parquet(BYBIT_DIR / (f"{s}_1m.parquet"),
                            columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def run_books_on_grid(books_fwd: dict[str, pd.DataFrame], opens, prep, idx, cols,
                      live0, live1, fric: str, cap: dict,
                      pof, hist, v221, v216, eu):
    """Run G2-style simulates for the given books under friction `fric`.

    fric in base/S1/S2/S3/S4 (S5 handled by caller with its own grid).
    Reuses the worker's hist/v221 modules (same R2_TABLE/shift) so the
    dip-agent lookups match oc_lit_xs/v426 exactly.
    Returns dict name -> run dict.
    """
    out = {}
    extra: dict = {}
    if fric == "base":
        extra = dict(win_start=5)
    elif fric == "S1":
        extra = dict(win_start=5)
    elif fric == "S2":
        extra = dict(win_start=15, sleeve_start=16)
    elif fric == "S3":
        extra = dict(win_start=30, sleeve_start=31)
    elif fric == "S4":
        extra = dict(win_start=5, stop_slip=0.5)
    else:
        raise ValueError(fric)
    for name, fwd in books_fwd.items():
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
            return (1.0 / (1 + n)) * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0
        eu.summarize = (lambda idx_, net, eq, eq_min, g, stats, eq_max=None:
                        cap.update(idx=idx_, eq=eq.copy(), eq_min=eq_min.copy()) or {})
        old_maker, old_taker = None, None
        try:
            if fric == "S1":
                old_maker = eu.simulate.__globals__["MAKER"]
                old_taker = eu.simulate.__globals__["TAKER"]
                eu.simulate.__globals__["MAKER"] = 0.0004
                eu.simulate.__globals__["TAKER"] = 0.0007 + 0.0005
            t0 = time.time()
            eu.simulate(fwd, opens, prep, trade=trade, events=[], **kw, **extra)
            lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
            first = int(np.argmax(lv))
            base = cap["eq"][first - 1] if first > 0 else 1.0
            out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                             eq=(cap["eq"][lv] / base).tolist(),
                             eq_min=(cap["eq_min"][lv] / base).tolist())
            print(f"  fric={fric} row={name} eq_end={out[name]['eq'][-1]:.3f} ({time.time()-t0:.0f}s)",
                  flush=True)
        finally:
            if fric == "S1" and old_maker is not None:
                eu.simulate.__globals__["MAKER"] = old_maker
                eu.simulate.__globals__["TAKER"] = old_taker
    return out


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podamr0_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histamr0_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_amr0_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwamr0_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap: dict = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    t_prep0 = time.time()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    gc.collect()
    print(f"shift {shift}: prep done ({time.time()-t_prep0:.0f}s)", flush=True)
    idx, cols = prep["idx"], list(prep["cols"])
    assert cols == XS_SYMS or set(cols) == set(XS_SYMS), cols
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear_std = sb.reindex(idx, method="ffill").fillna(0.0)
    tilted, _ginfo = gate_books(sb)
    # forward-fill tilted to shifted clock
    fwd_base: dict[str, pd.DataFrame] = {"G2": books_bear_std}
    for name in ["A1", *JITTER_DEFS, "C_STATIC"]:
        fwd_base[name] = tilted[name].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    out: dict[str, dict] = {}
    # base + S1..S4 share this grid
    for fric in ["base", "S1", "S2", "S3", "S4"]:
        if fric == "base":
            names = ["G2", "A1", *JITTER_DEFS, "C_STATIC"]
            sub = {n: fwd_base[n] for n in names}
            label = {n: n for n in names}
        else:
            sub = {"G2": fwd_base["G2"], "A1": fwd_base["A1"]}
            label = {"G2": f"G2_{fric}", "A1": f"A1_{fric}"}
        got = run_books_on_grid(sub, opens, prep, idx, cols, live0, live1, fric, cap,
                                  pof, hist, v221, v216, eu)
        for n, run in got.items():
            out[label[n]] = run
        gc.collect()
    del opens, prep
    gc.collect()
    # S5: Bybit grid
    try:
        Mb = bybit_minutes()
        eu.v110.START, eu.v110.END = S5_START + sh, live1
        std_idx = books154.index[books154.index >= S5_START] + sh
        opens5, prep5 = pof.prep_idx(Mb, std_idx, shift, list(books154.columns))
        del Mb
        gc.collect()
        idx5, cols5 = prep5["idx"], list(prep5["cols"])
        books5 = sb.reindex(idx5, method="ffill").fillna(0.0)
        f5a1 = tilted["A1"].reindex(idx5, method="ffill").fillna(0.0)
        hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
        got5 = run_books_on_grid({"G2": books5, "A1": f5a1}, opens5, prep5, idx5, cols5,
                                 S5_START + sh, live1, "base", cap,
                                 pof, hist, v221, v216, eu)
        out["G2_S5"] = got5["G2"]
        out["A1_S5"] = got5["A1"]
        del opens5, prep5
        gc.collect()
    except Exception as e:
        print(f"shift {shift}: S5 FAILED ({type(e).__name__}: {e})", flush=True)
        out["G2_S5"] = {"error": f"{type(e).__name__}: {e}"}
        out["A1_S5"] = {"error": f"{type(e).__name__}: {e}"}
    print(f"shift {shift}: done rows {sorted(out)}", flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main():
    runs_cached = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = stats(runs_cached, "R2B1D17BFG2", list(range(5)))
    e, mn = v388.mix(runs_cached, "R2B1D17BFG2", Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2:", got, "full", full, flush=True)
    assert got["R"] == EXP_R and got["DD"] == EXP_DD and full == EXP_FULL, (got, full, exp)
    assert [tuple(y) for y in got["years"]] == [tuple(y) for y in EXP_YEARS], got
    print("G2 reproduction OK (5.41 / 16.91 / 16.82)", flush=True)

    cache = HERE / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        # resume-safe: check all shifts and rows present
        need = {"G2", "A1", *JITTER_DEFS, "C_STATIC",
                *[f"G2_{s}" for s in FRIC_SUFFIX], *[f"A1_{s}" for s in FRIC_SUFFIX]}
        ok = all(set(runs.get(s, {})) >= need or set(runs.get(s, {})).issuperset(need - set()) for s in range(4))
        if not (set(runs) == {0, 1, 2, 3} and ok):
            print("cache incomplete, resuming missing shifts...", flush=True)
            with Pool(2) as pool:
                fresh = dict(pool.map(worker, [s for s in range(4) if s not in runs or set(runs[s]) < need]))
            runs.update(fresh)
            cache.write_bytes(pickle.dumps(runs))
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    rows = (["G2", "A1", *JITTER_DEFS, "C_STATIC"]
            + [f"G2_{s}" for s in FRIC_SUFFIX] + [f"A1_{s}" for s in FRIC_SUFFIX])
    out = {"version": "oc_amihudrobust_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in rows if "error" not in runs.get(0, {}).get(r, {})},
           "dev4": {r: stats(runs, r, list(range(4))) for r in rows if "error" not in runs.get(0, {}).get(r, {})}}
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in list(out["rows"]):
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    # standard-index gate accounting (shift-independent)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    v221_0 = pof0._load("v221_amr_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwamr_info", ROOT / "scripts/forward_v205.py")
    eu0 = v221_0.eu
    eu0.v110.START, eu0.v110.END = pof0.DEV0, Y1
    books154, _o = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)
    btc = _o["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    _, ginfo = gate_books(sb)
    out["gate_info"] = ginfo
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
