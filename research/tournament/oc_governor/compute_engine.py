"""oc_governor engine rows (PLAN-frozen): G2REF + GV1/GV2/GV3, v421 harness verbatim.

Stage 1 (dev, selection): live = DEV0+sh .. 2025-09-24+sh, rows G2REF/GV1/GV2/GV3.
Stage 2 (recent year, ONCE): full live .. Y1+sh, only qualifier rows (args).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_governor --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_governor/compute_engine.py --stage dev
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_governor --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_governor/compute_engine.py --stage full --rows GVx

GV1 gov=(0.25,0.10); GV2 gov=(0.30,0.15); GV3 pooled two-pass approximation
(pass1 from stored G2 paths; pass2 gov=(1.0,1e-9) x risk_mult=pooled g).
Gate costs / win_start=5 / stop-first = engine defaults (unchanged).
"""
from __future__ import annotations

import argparse
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
TABLES = RD / "v376" / "tables_hidden"
STORED = RD / "v421/v421_runs.pkl"
STRAT = "R2B1D17BFG2"

ROW_CFGS = {
    "G2REF": dict(gov=None),
    "GV1": dict(gov=(0.25, 0.10)),
    "GV2": dict(gov=(0.30, 0.15)),
    "GV3": dict(gov=(1.0, 1e-9), pooled=True),
}
KD = 1.7
BUDGET = 0.26 * KD
GCAP = 2.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pooled_g_from_stored() -> dict:
    """Pass 1: combined hourly equity from STORED G2 paths -> per-shift pooled g."""
    v388 = _load("v388_for_govpool", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(STORED.read_bytes())
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    grid = pd.date_range(g0, g1, freq="1h")
    Es = []
    for s in range(4):
        e1, _ = v388.hourly(runs[s][STRAT], g0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(float))
    E = np.mean(np.stack(Es), axis=0)
    peak = np.maximum.accumulate(E)
    dd = 1 - E / peak
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    out = {}
    for s in range(4):
        t = pd.to_datetime(runs[s][STRAT]["t"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        g = np.ones(len(t))
        for i in range(2, len(t)):
            lag = t[i - 2]
            pos = int(np.searchsorted(gn, lag, side="right")) - 1
            d = float(dd[max(pos, 0)])
            g[i] = float(np.clip((0.20 - d) / 0.10, 0.0, 1.0))
        out[s] = g
    (HERE / "tmp" / "pooled_pass1.json").write_text(json.dumps(dict(
        note="GV3 pass-1 pooled g from STORED G2 combined hourly equity; g_s[i]=clip((0.20-dd_comb(t[i-2]))/0.10)",
        mean_g={str(s): round(float(out[s].mean()), 4) for s in out},
        frac_lt1={str(s): round(float((out[s] < 1 - 1e-12).mean()), 4) for s in out},
    ), indent=1))
    return out


def worker(args):
    shift, rows, last_year = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podgov_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histgov_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_gov_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwgov_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    v388 = _load(f"v388gov_{shift}", RD / "v388/v388_bot_stop_distance.py")
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0 = pof.DEV0 + sh
    live1 = (v388.Y1 if last_year else pof.DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    print(f"shift {shift}: loading 1m minutes ...", flush=True)
    t0 = time.time()
    M = pod.minutes()
    print(f"shift {shift}: minutes in {time.time() - t0:.0f}s", flush=True)
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    pooled = pooled_g_from_stored() if any(ROW_CFGS[r].get("pooled") for r in rows) else {}
    out = {}
    for name in rows:
        cfg = ROW_CFGS[name]
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
            return (1.0 / (1 + n)) * KD * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["sleeve_risk_budget"] = BUDGET
        kw["sleeve_gross_cap"] = GCAP
        if cfg.get("pooled"):
            garr = pooled[shift]
            kw["risk_mult"] = lambda i, e, garr=garr: float(garr[i]) if i < len(garr) else 1.0
        else:
            kw["risk_mult"] = lambda i, e: 1.0
        sim_kw = dict(kw)
        if cfg["gov"] is not None:
            sim_kw["gov"] = cfg["gov"]
        t1 = time.time()
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=[], **sim_kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(f"shift {shift} {name}: eq_end {out[name]['eq'][-1]:.3f} in {time.time() - t1:.0f}s", flush=True)
    return shift, out


def stats_of(runs, row, ys):
    rm = _load("reset_for_goveng", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs_slim = {s: {row: {"t": runs[s][row]["t"], "eq": runs[s][row]["eq"],
                            "eq_min": runs[s][row]["eq_min"]}} for s in runs}
    yy = [rm.year_reset(runs_slim, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "full"], required=True)
    ap.add_argument("--rows", default=None, help="comma list subset of G2REF,GV1,GV2,GV3")
    args = ap.parse_args()
    last_year = args.stage == "full"
    rows = args.rows.split(",") if args.rows else (["G2REF", "GV1", "GV2", "GV3"] if not last_year else ["GV1", "GV2", "GV3"])
    for r in rows:
        assert r in ROW_CFGS, r
    print(f"oc_governor engine stage={args.stage} rows={rows} last_year={last_year}", flush=True)
    t_start = time.time()
    with Pool(2) as pool:
        runs = dict(pool.map(worker, [(s, rows, last_year) for s in range(4)]))
    el = time.time() - t_start
    print(f"all shifts done in {el / 60:.1f} min", flush=True)
    cache = HERE / "tmp" / (f"engine_{args.stage}.pkl")
    cache.write_bytes(pickle.dumps(runs))
    out = {}
    ys = [4] if last_year else [0, 1, 2, 3]
    for r in rows:
        m = stats_of(runs, r, [4] if last_year else [0, 1, 2, 3])
        out[r] = m
        print(r, m, flush=True)
    # bit-exact harness check on dev stage for G2REF vs stored
    if not last_year and "G2REF" in rows:
        stored = pickle.loads(STORED.read_bytes())
        ok = True
        for s in range(4):
            a = np.asarray(runs[s]["G2REF"]["eq"], float)
            # stored full-window eq; dev portion = first N bars where t <= 2025-09-24+sh
            st = pd.to_datetime(stored[s][STRAT]["t"], utc=True)
            cut = pd.Timestamp("2025-09-24", tz="UTC") + pd.Timedelta(hours=s)
            ndev = int((st <= cut).sum())
            # our dev run t: idx[lv]+8h; stored t same grid -> compare first ndev? lengths may differ by warmup offset;
            # compare overlapping tail-anchored II: both rebased to 1.0 at live start, so compare directly when equal length
            b = np.asarray(stored[s][STRAT]["eq"], float)
            # rebase stored dev segment to its own live-start base like worker does
            # worker base = eq[first-1]; stored eq[0]=1.0 at first live bar? check length equality first
            print(f"shift {s}: fresh {len(a)} vs stored-dev {ndev} (stored full {len(b)})", flush=True)
            if len(a) == ndev and np.array_equal(a, b[:ndev]):
                print(f"shift {s} G2REF bit-exact vs stored (dev segment)", flush=True)
            else:
                n = min(len(a), ndev)
                d = float(np.max(np.abs(a[:n] - b[:n]))) if n else float("nan")
                print(f"shift {s} G2REF max-abs-diff vs stored dev: {d:.3e}", flush=True)
                ok = ok and d < 1e-12
        out["_harness_bit_exact_dev"] = bool(ok)
    (HERE / "tmp" / f"engine_{args.stage}_stats.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote tmp/engine_{args.stage}.pkl + tmp/engine_{args.stage}_stats.json", flush=True)


if __name__ == "__main__":
    main()
