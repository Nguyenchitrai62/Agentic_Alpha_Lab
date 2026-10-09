"""oc_ablation per-shift runner: G2 replica + 6 leave-one-layer-out rows.

Usage: .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_ablation
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_ablation/run_shift.py <shift>

Runs all 7 rows for one 4h-phase shift sequentially (one heavy process),
writes tmp/runs_s{shift}.pkl + tmp/events_s{shift}_{row}.parquet +
tmp/meta_s{shift}.json. Progress printed per row.
"""
from __future__ import annotations

import importlib.util
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
ROWS = ["G2", "NO_GOV", "NO_BEAR", "NO_CAP", "NO_B1", "TOUCH", "NO_VT"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_shift(shift: int):
    t0 = time.time()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podabl_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histabl_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221abl_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwabl_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    eup = _load(f"eupatch_{shift}", HERE / "engine_patch.py")
    v388 = _load(f"v388abl_{shift}", RD / "v388/v388_bot_stop_distance.py")
    Y1 = v388.Y1

    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), stats=dict(stats)) or {}
    capp = {}
    eup.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: capp.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), stats=dict(stats)) or {}

    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    eup.v110.START, eup.v110.END = live0, live1
    books154, opens_std = eu.er.v154_books()
    M = pod.minutes()
    print(f"shift {shift}: minutes loaded ({time.time()-t0:.0f}s)", flush=True)
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    O, C, sg = prep["O"], prep["C"], prep["sig4"]

    out = {}
    scale_median = None

    def vol_scale_median(bk):
        # Replicates engine_user s[i] (target 0.25 / cap 2.0 defaults, same as v421):
        # s = min(target/vol, cap), vol = trailing 60-day std of book P&L x sqrt(PD*365).
        o = opens.reindex(idx)[cols]
        realized = eu.er.v99.W_BOOKS * (bk.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
        vol = (realized.rolling(60 * eu.er.PD, min_periods=20 * eu.er.PD).std()
               * np.sqrt(eu.er.PD * 365)).to_numpy()
        s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), 2.0))
        lv = np.asarray((idx >= live0) & (idx < live1))
        return float(np.median(s[lv][np.isfinite(s[lv])]))

    def build_kw(row):
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        base_size = kw["sleeve_fill_size"]
        kd, k, rule = 1.7, 1.0, "inv"
        if row == "NO_B1":
            kw["sleeve_fill_size"] = (lambda i, a, r, f, _b=base_size, _kd=kd: _kd * _b(i, a, r, f))
        else:
            ev0, stops0, ptr0 = [], {}, [0]

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
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if row == "NO_CAP":
            kw.pop("sleeve_gross_cap", None)
        else:
            kw["sleeve_gross_cap"] = 2.0
        if row == "NO_GOV":
            kw["gov"] = (10.0, 0.10)
        if row == "TOUCH":
            kw["sleeve_stop_mode"] = "touch"
            kw["m_sleeve_sl"] = 4.0
            kw["sleeve_backstop"] = 8.0
        bk = books if row == "NO_BEAR" else books_bear
        return kw, trade, bk

    for row in ROWS:
        if row == "NO_VT":
            continue  # second pass after median is known
        kw, trade, bk = build_kw(row)
        ev, bars = [], []
        t1 = time.time()
        eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, bars=bars, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        med = vol_scale_median(bk)
        if row == "G2":
            scale_median = med
        out[row] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                        eq=(cap["eq"][lv] / base).tolist(),
                        eq_min=(cap["eq_min"][lv] / base).tolist(),
                        stats={k: (round(float(v), 6) if isinstance(v, float) else int(v) if isinstance(v, (int, np.integer)) else v)
                               for k, v in cap["stats"].items()},
                        scale_median=med)
        edf = pd.DataFrame(ev)
        if len(edf):
            edf.to_parquet(HERE / "tmp" / f"events_s{shift}_{row}.parquet", index=False)
        print(f"shift {shift} {row}: eq_end {round(out[row]['eq'][-1],3)} "
              f"scale_med {med:.4f} ({time.time()-t1:.0f}s, total {time.time()-t0:.0f}s)", flush=True)

    # patch proof: G2 via patched engine with vol_fixed=None must match G2
    kw, trade, bk = build_kw("G2")
    ev, bars = [], []
    eup.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, bars=bars, **kw)
    lv = np.asarray((capp["idx"] >= live0) & (capp["idx"] < live1))
    first = int(np.argmax(lv))
    base = capp["eq"][first - 1] if first > 0 else 1.0
    eq_p = capp["eq"][lv] / base
    eq_o = np.array(out["G2"]["eq"])
    maxdiff = float(np.max(np.abs(eq_p - eq_o)))
    print(f"shift {shift} G2_PATCH proof: max abs eq diff {maxdiff:.2e}", flush=True)
    assert maxdiff == 0.0, f"patch with vol_fixed=None diverged: {maxdiff}"

    # NO_VT second pass via patched engine with vol_fixed = G2 median
    assert scale_median is not None and np.isfinite(scale_median)
    kw, trade, bk = build_kw("G2")  # same books (bear) as G2
    ev, bars = [], []
    t1 = time.time()
    eup.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, bars=bars,
                 vol_fixed=scale_median, **kw)
    lv = np.asarray((capp["idx"] >= live0) & (capp["idx"] < live1))
    first = int(np.argmax(lv))
    base = capp["eq"][first - 1] if first > 0 else 1.0
    out["NO_VT"] = dict(t=[str(x) for x in capp["idx"][lv] + pd.Timedelta(hours=8)],
                        eq=(capp["eq"][lv] / base).tolist(),
                        eq_min=(capp["eq_min"][lv] / base).tolist(),
                        stats={k: (round(float(v), 6) if isinstance(v, float) else int(v) if isinstance(v, (int, np.integer)) else v)
                               for k, v in capp["stats"].items()},
                        scale_median=scale_median)
    edf = pd.DataFrame(ev)
    if len(edf):
        edf.to_parquet(HERE / "tmp" / f"events_s{shift}_NO_VT.parquet", index=False)
    print(f"shift {shift} NO_VT (vol_fixed={scale_median:.4f}): eq_end {round(out['NO_VT']['eq'][-1],3)} "
          f"({time.time()-t1:.0f}s, total {time.time()-t0:.0f}s)", flush=True)

    (HERE / "tmp" / f"runs_s{shift}.pkl").write_bytes(pickle.dumps(out))
    (HERE / "tmp" / f"meta_s{shift}.json").write_text(json.dumps(
        {"shift": shift, "live": [str(live0), str(live1)], "rows": ROWS,
         "scale_median": scale_median, "secs": round(time.time() - t0)}, indent=1))
    print(f"shift {shift} done in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    run_shift(int(sys.argv[1]))
