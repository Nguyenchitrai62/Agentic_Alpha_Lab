"""oc_amihudbybit engine: venue-consistent Amihud tilt AB1 (POST-HOC, labelled).

PLAN-fixed (see PLAN.md). Mechanism copied from v426 via oc_lit_xs /
oc_amihudrobust: multiplier on STANDARD book rows AFTER the bear-book filter
and BEFORE the shifted-clock forward fill. Rows before 2021-09-24 untilted.
Base = G2 (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0).

Engine rows (8): base grid G2, A1, AB1, CTRL_AB1; S5 grid G2_S5, A1_S5,
AB1_S5, CTRL_AB1_S5. S5 def exactly as v421_audit/robust_v421.py and
oc_amihudrobust/compute_robust_engine.py: Bybit 1m prices from 2021-11-15
(short 2021 window, labelled), standard index filtered to >= 2021-11-15
before shift, win_start=5. AB1 = Bybit-Amihud both-legs 1+0.25z clip
[0.5,1.5]; A1 = Binance-Amihud repro; CTRL_AB1 = per-year constant equal to
AB1's realised mean multiplier over non-zero cells that year (both legs).

Reproduction gate: cached G2 5.41/W 2.588/DD 16.91/full 16.82 AND engine
re-run G2 dev4 5.601, A1 dev4 5.844, G2_S5 dev4 4.994/5y 4.883,
A1_S5 dev4 4.989/5y 4.884 (oc_amihudrobust numbers) to the digit; else STOP.

HEAVY: run through heavy_slot (Pool(2), same as v426/oc_lit_xs).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_amihudbybit_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_amihudbybit/compute_bybit_engine.py
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
from bybit_signal import SYMS as XS_SYMS, a1_mult, ab1_mult

BASE_ROWS = ["G2", "A1", "AB1", "CTRL_AB1"]
S5_ROWS = ["G2_S5", "A1_S5", "AB1_S5", "CTRL_AB1_S5"]
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
EXP_R, EXP_DD, EXP_FULL = 5.41, 16.91, 16.82
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81),
             (10.677, 8.27), (4.648, 12.9)]
# oc_amihudrobust engine_results.json values (repro must match to the digit)
EXP_G2_S5_DEV4, EXP_G2_S5_5Y = 4.994, 4.883
EXP_A1_S5_DEV4, EXP_A1_S5_5Y = 4.989, 4.884
EXP_G2_DEV4, EXP_A1_DEV4 = 5.601, 5.844


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_amihudbybit", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_amihudbybit", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def build_tilt_frames_std(sb: pd.DataFrame):
    """Tilt frames on the STANDARD index. Returns (frames dict, info)."""
    cols = list(sb.columns)
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    f_a1, _ = a1_mult(T, cols=cols)
    f_a1.loc[Tts < CUTOFF] = 1.0
    f_ab1, i_ab1 = ab1_mult(T, cols=cols)
    f_ab1.loc[Tts < CUTOFF] = 1.0
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    # CTRL_AB1: per-year constant = AB1 realised mean over non-zero sb cells
    sbv = sb.to_numpy(float)
    ab1v = f_ab1.to_numpy(float)
    aff = sbv != 0
    ctrl_const = []
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        denom = int(aff[sel].sum())
        mu = float(ab1v[sel][aff[sel]].mean()) if denom else 1.0
        ctrl_const.append(round(mu, 6))
    ctrl = pd.DataFrame(1.0, index=T, columns=cols)
    cv = ctrl.to_numpy()
    for k in range(5):
        sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
        cv[sel] = np.where(aff[sel], ctrl_const[k], 1.0)
    ctrl.loc[Tts < CUTOFF] = 1.0
    frames = {"A1": f_a1, "AB1": f_ab1, "CTRL_AB1": ctrl}
    info = dict(ctrl_const=ctrl_const, cov_bybit=i_ab1["cov"])
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
    for name in ["A1", "AB1", "CTRL_AB1"]:
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
        m = pd.read_parquet(BYBIT_DIR / (f"{s}_1m.parquet"),
                            columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def run_books_on_grid(books_fwd: dict[str, pd.DataFrame], opens, prep, idx, cols,
                      live0, live1, cap: dict, pof, hist, v221, v216, eu):
    """Run G2-style simulates (win_start=5, stop-first ties in harness).

    Fill timing: limit fills only on a 1m trade-through, no fill in the first
    5 minutes after a 4h close (win_start=5); stop-first in the same 1m bar
    (engine convention, same as v426/oc_lit_xs/oc_amihudrobust).
    """
    out = {}
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
        t0 = time.time()
        eu.simulate(fwd, opens, prep, trade=trade, events=[],
                    win_start=5, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(f"  row={name} eq_end={out[name]['eq'][-1]:.3f} ({time.time()-t0:.0f}s)",
              flush=True)
    return out


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podabb_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histabb_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_abb_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwabb_{shift}", ROOT / "scripts/forward_v205.py")
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
    print(f"shift {shift}: base prep done ({time.time()-t_prep0:.0f}s)", flush=True)
    idx, cols = prep["idx"], list(prep["cols"])
    assert set(cols) == set(XS_SYMS), cols
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear_std = sb.reindex(idx, method="ffill").fillna(0.0)
    tilted, _ginfo = gate_books(sb)
    fwd_base: dict[str, pd.DataFrame] = {"G2": books_bear_std}
    for name in ["A1", "AB1", "CTRL_AB1"]:
        fwd_base[name] = tilted[name].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    out: dict[str, dict] = {}
    got = run_books_on_grid(fwd_base, opens, prep, idx, cols, live0, live1, cap,
                            pof, hist, v221, v216, eu)
    out.update(got)
    del opens, prep
    gc.collect()
    # S5: Bybit grid (exactly as oc_amihudrobust: index >= S5_START, win_start=5)
    try:
        Mb = bybit_minutes()
        eu.v110.START, eu.v110.END = S5_START + sh, live1
        std_idx = books154.index[books154.index >= S5_START] + sh
        opens5, prep5 = pof.prep_idx(Mb, std_idx, shift, list(books154.columns))
        del Mb
        gc.collect()
        idx5, cols5 = prep5["idx"], list(prep5["cols"])
        fwd5 = {"G2_S5": sb.reindex(idx5, method="ffill").fillna(0.0),
                "A1_S5": tilted["A1"].reindex(idx5, method="ffill").fillna(0.0),
                "AB1_S5": tilted["AB1"].reindex(idx5, method="ffill").fillna(0.0),
                "CTRL_AB1_S5": tilted["CTRL_AB1"].reindex(idx5, method="ffill").fillna(0.0)}
        hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
        got5 = run_books_on_grid(fwd5, opens5, prep5, idx5, cols5,
                                 S5_START + sh, live1, cap,
                                 pof, hist, v221, v216, eu)
        out.update(got5)
        del opens5, prep5
        gc.collect()
    except Exception as e:
        print(f"shift {shift}: S5 FAILED ({type(e).__name__}: {e})", flush=True)
        raise
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
        need = set(BASE_ROWS + S5_ROWS)
        ok = (set(runs) == {0, 1, 2, 3}
              and all(set(runs.get(s, {})) >= need for s in range(4)))
        if not ok:
            print("cache incomplete, resuming missing shifts...", flush=True)
            missing = [s for s in range(4)
                       if set(runs.get(s, {})) < need]
            with Pool(2) as pool:
                fresh = dict(pool.map(worker, missing))
            runs.update(fresh)
            cache.write_bytes(pickle.dumps(runs))
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    rows = BASE_ROWS + S5_ROWS
    out = {"version": "oc_amihudbybit_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in rows},
           "dev4": {r: stats(runs, r, list(range(4))) for r in rows}}
    # harness proof: G2_S5 / A1_S5 must match oc_amihudrobust to the digit
    assert out["dev4"]["G2_S5"]["R"] == EXP_G2_S5_DEV4, out["dev4"]["G2_S5"]
    assert out["rows"]["G2_S5"]["R"] == EXP_G2_S5_5Y, out["rows"]["G2_S5"]
    assert out["dev4"]["A1_S5"]["R"] == EXP_A1_S5_DEV4, out["dev4"]["A1_S5"]
    assert out["rows"]["A1_S5"]["R"] == EXP_A1_S5_5Y, out["rows"]["A1_S5"]
    assert out["dev4"]["G2"]["R"] == EXP_G2_DEV4, out["dev4"]["G2"]
    assert out["dev4"]["A1"]["R"] == EXP_A1_DEV4, out["dev4"]["A1"]
    print("harness proof OK: G2/A1/G2_S5/A1_S5 match oc_amihudrobust", flush=True)
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in rows:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    v221_0 = pof0._load("v221_abb_info", pof0.RD / "v221/v221_grid_hysteresis.py")
    fw0 = pof0._load("fwabb_info", ROOT / "scripts/forward_v205.py")
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
