"""oc_lit_xs engine: Amihud (A1/A2/A3) + MAX (X1/X2/X3) XS tilts on G2 (4-phase).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py:
multiplier on STANDARD book rows AFTER the bear-book filter and BEFORE the
shifted-clock forward fill. Rows before 2021-09-24 are not tilted (v426).
Both-legs variants scale every non-zero weight; longs-only (A2/X2) scale only
w>0. Mults clipped [0.5,1.5], NaN->1. Controls are per-year constants equal to
the variant's realised mean multiplier on the affected side (no timing).

Rows (13): G2, A1, A2, A3, X1, X2, X3, C_A1, C_A2, C_A3, C_X1, C_X2, C_X3.
Base = G2 (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
Step 1 validates cached G2 (v421_runs.pkl -> 5.41 / 16.91 / 16.82); else stops.
HEAVY: run through heavy_slot (Pool(2), same as v426).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_lit_xs_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_lit_xs/compute_xs_engine.py
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
from xs_signal import tilt_frames

VARIANTS = ["A1", "A2", "A3", "X1", "X2", "X3"]
LONGS_ONLY = {"A2", "X2"}
CONTROLS = [f"C_{v}" for v in VARIANTS]
RUNS = {"G2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0)}
for v in VARIANTS:
    RUNS[v] = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate=v)
for v in VARIANTS:
    RUNS[f"C_{v}"] = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0,
                           gate=f"C_{v}", base=v)
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
EXP_R, EXP_DD, EXP_FULL = 5.41, 16.91, 16.82
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81),
             (10.677, 8.27), (4.648, 12.9)]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_xs", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_xs", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def gate_books(sb: pd.DataFrame):
    """Tilted books on the STANDARD index. Returns (books dict, info)."""
    cols = list(sb.columns)
    T = sb.index
    frames, _ = tilt_frames(T, cols)
    for v in VARIANTS:
        frames[v].loc[T < CUTOFF] = 1.0
    sbv = sb.to_numpy(float)
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    Tts = pd.to_datetime(T, utc=True)
    books: dict[str, pd.DataFrame] = {}
    per_year: dict[str, list] = {}
    ctrl_const: dict[str, list] = {}
    for v in VARIANTS:
        m = frames[v].to_numpy(float)
        longs_only = v in LONGS_ONLY
        aff = (sbv > 0) if longs_only else (sbv != 0)
        g = sb.copy()
        g[:] = np.where(aff, sbv * m, sbv)
        books[v] = g
        # exposure-matched control constants per year
        cs = []
        rows = []
        for k in range(5):
            sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
            denom = aff[sel].sum()
            if denom:
                mu = float(m[sel][aff[sel]].mean())
            else:
                mu = 1.0
            cs.append(round(mu, 6))
            affcells = int(aff[sel].sum())
            tiltcells = int(((m[sel] != 1.0) & aff[sel]).sum())
            rows.append(dict(
                year=str(ANCH[k].date()),
                affected_cells=affcells,
                tilted_cells=tiltcells,
                share_tilted=round(tiltcells / max(affcells, 1), 6),
                mean_mult=round(float(m[sel][aff[sel]].mean()) if denom else 1.0, 6),
                ctrl_mult=round(mu, 6)))
        ctrl_const[v] = cs
        per_year[v] = rows
        c = sb.copy()
        cb = c.to_numpy(float).copy()
        for k in range(5):
            sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
            cb[sel] = np.where(aff[sel], sbv[sel] * cs[k], sbv[sel])
        c[:] = cb
        books[f"C_{v}"] = c
    info = dict(ctrl_const=ctrl_const, per_year=per_year)
    return books, info


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podxs_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histxs_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_xs_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwxs_{shift}", ROOT / "scripts/forward_v205.py")
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
    tilted, _ginfo = gate_books(sb)
    fwd = {"G2": books_bear_std}
    for name in VARIANTS + CONTROLS:
        fwd[name] = tilted[name].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)

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
        eu.simulate(fwd[name], opens, prep, trade=trade, win_start=5, events=[], **kw)
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
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "oc_lit_xs_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in RUNS},
           "dev4": {r: stats(runs, r, list(range(4))) for r in RUNS}}
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    # Standard-index gate accounting (shift-independent).
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    v221_0 = pof0._load("v221_xs_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwxs_info", ROOT / "scripts/forward_v205.py")
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
