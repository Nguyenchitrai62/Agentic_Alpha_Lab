"""oc_netting engine rows (PLAN-frozen): G2REF + N1, v421 harness verbatim + N1 gate.

Stage 1 dev (selection): live = DEV0+sh .. DEV1+sh, rows G2REF/N1.
Stage 2 full (recent year ONCE): live = DEV0+sh .. Y1+sh, only the pick (--rows).

G2REF = v421 R2B1D17BFG2 config verbatim (agents ON, corr inv kd=1.7,
budget 0.26*1.7, gross cap 2.0, trade mode, win_start=5, default gov).
N1 = G2REF + sleeve_filter gate: skip ALL dip rungs of (i,a) when the
close-known book target books_bear[i,a] < 0 strictly (book SHORT vs dip LONG).
Survivor = book (untouched SL/TP); freed budget never re-used.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_netting --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_netting/compute_engine.py --stage dev
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_netting --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_netting/compute_engine.py --stage full --rows N1

Sequential shifts (ONE engine job at a time); float32 cube via prep_idx;
progress prints every shift/row (~10-min rule: each shift prints start/end).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]
TABLES = RD / "v376" / "tables_hidden"
STORED = RD / "v421/v421_runs.pkl"
STRAT = "R2B1D17BFG2"

ROWS = ("G2REF", "N1")
KD = 1.7
BUDGET = 0.26 * KD
GCAP = 2.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def run_shift(shift, rows, last_year):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podnet_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histnet_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_net_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwnet_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    v388 = _load(f"v388net_{shift}", RD / "v388/v388_bot_stop_distance.py")
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), stats=dict(stats)) or {}
    sh = pd.Timedelta(hours=shift)
    live0 = pof.DEV0 + sh
    live1 = (v388.Y1 if last_year else pof.DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    print(f"[{now()}] shift {shift}: loading 1m minutes ...", flush=True)
    t0 = time.time()
    M = pod.minutes()
    print(f"[{now()}] shift {shift}: minutes in {time.time() - t0:.0f}s", flush=True)
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

    # N1 gate mask (close-known target sign, one coin-bar at a time logic,
    # vectorized mask; no 1m data): SHORT strictly -> skip all dip rungs.
    short_mask = (books_bear.to_numpy() < 0.0)
    n_short_bars = int(short_mask.any(axis=1).sum())
    print(f"[{now()}] shift {shift}: N1 gate SHORT bars {n_short_bars}/{len(idx)} "
          f"({100 * short_mask.mean():.2f}% coin-bars)", flush=True)

    out, evs, rowstats = {}, {}, {}
    for name in rows:
        assert name in ROWS, name
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
        kw["risk_mult"] = lambda i, e: 1.0
        if name == "N1":
            kw["sleeve_filter"] = lambda i, a, r, sm=short_mask: 0.0 if sm[i, a] else 1.0
        t1 = time.time()
        ev = []
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        evs[name] = ev
        st = cap["stats"]
        rowstats[name] = {k: (round(float(v), 6) if isinstance(v, float) else v)
                          for k, v in st.items()}
        print(f"[{now()}] shift {shift} {name}: eq_end {out[name]['eq'][-1]:.3f} "
              f"fills={st.get('fills')} rungs={st.get('rungs')} "
              f"fees={st.get('fees', 0):.4f} funding={st.get('funding', 0):.4f} "
              f"in {time.time() - t1:.0f}s", flush=True)
    return shift, out, evs, rowstats


def stats_of(runs, row, ys):
    rm = _load("reset_for_neteng", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
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
    ap.add_argument("--rows", default=None)
    args = ap.parse_args()
    last_year = args.stage == "full"
    rows = args.rows.split(",") if args.rows else (["G2REF", "N1"] if not last_year else ["N1"])
    for r in rows:
        assert r in ROWS, r
    print(f"[{now()}] oc_netting engine stage={args.stage} rows={rows} last_year={last_year}", flush=True)
    t_start = time.time()
    runs, allevents, allstats = {}, {}, {}
    for s in range(4):  # SEQUENTIAL: one engine job at a time
        print(f"[{now()}] --- shift {s} start ---", flush=True)
        sh, out, evs, rowstats = run_shift(s, rows, last_year)
        runs[sh] = out
        allevents[sh] = evs
        allstats[sh] = rowstats
        print(f"[{now()}] --- shift {s} done ---", flush=True)
    el = time.time() - t_start
    print(f"[{now()}] all shifts done in {el / 60:.1f} min", flush=True)
    cache = HERE / "tmp" / f"engine_{args.stage}.pkl"
    if cache.exists():
        try:
            prev = pickle.loads(cache.read_bytes())
            same = True
            for s in runs:
                for r in runs[s]:
                    if r not in prev.get(s, {}):
                        same = False
                        continue
                    same = (same and np.array_equal(np.asarray(runs[s][r]["eq"], float),
                                                   np.asarray(prev[s][r]["eq"], float)))
            print(f"[{now()}] equity bit-identical to previous {args.stage} cache: {same}", flush=True)
        except Exception as ex:
            print(f"[{now()}] bit-identity check skipped: {ex}", flush=True)
    cache.write_bytes(pickle.dumps(runs))
    (HERE / "tmp" / f"engine_{args.stage}_events.pkl").write_bytes(pickle.dumps(allevents))
    (HERE / "tmp" / f"engine_{args.stage}_rowstats.json").write_text(json.dumps(allstats, indent=1, default=str))
    out = {}
    ys = [4] if last_year else [0, 1, 2, 3]
    for r in rows:
        m = stats_of(runs, r, [4] if last_year else [0, 1, 2, 3])
        out[r] = m
        print(r, m, flush=True)
    if not last_year and "G2REF" in rows:
        stored = pickle.loads(STORED.read_bytes())
        ok = True
        for s in range(4):
            a = np.asarray(runs[s]["G2REF"]["eq"], float)
            st = pd.to_datetime(stored[s][STRAT]["t"], utc=True)
            cut = pd.Timestamp("2025-09-24", tz="UTC") + pd.Timedelta(hours=s)
            ndev = int((st <= cut).sum())
            b = np.asarray(stored[s][STRAT]["eq"], float)
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
    print(f"[{now()}] wrote tmp/engine_{args.stage}.pkl + events + stats.json", flush=True)


if __name__ == "__main__":
    main()
