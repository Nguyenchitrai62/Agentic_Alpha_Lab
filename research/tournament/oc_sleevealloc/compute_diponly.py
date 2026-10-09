"""oc_sleevealloc dip-only engine gap-fill: G2 with books zeroed, dip sleeve ON.

Exact mirror of oc_bookattrib/run_bookonly.py except books x 0.0 with sleeve
kept ON (dip-only standalone net tradable). PLAN.md pre-registered this as data
construction (NOT a variant). Read-only inputs; writes tmp/diponly_runs.pkl +
tmp/diponly_years.json. Heavy: run via
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_sleevealloc_dip
--min-free-gb 2.0 -- .venv/Scripts/python.exe
research/tournament/oc_sleevealloc/compute_diponly.py`
"""
from __future__ import annotations

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


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_shift(shift, M, books154, std_books, opens_std):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"poddi_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histdi_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221di_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwdi_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0 = pof.DEV0 + sh
    Y1 = pd.Timestamp("2026-09-23", tz="UTC")
    live1 = Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    sh_idx = books154.index + sh
    opens, prep = pof.prep_idx(M, sh_idx, shift, list(books154.columns))
    idx, cols = prep["idx"], list(prep["cols"])
    std = std_books.reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    books_zero = books_bear * 0.0  # DIP ONLY: no book exposure
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    base_size = kw["sleeve_fill_size"]
    kd = 1.7
    kw["sleeve_fill_size"] = base_size
    kw["risk_mult"] = lambda i, e, k=1.0: k
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
    kw["sleeve_gross_cap"] = 2.0
    # sleeve stays ON (dip-only); do NOT set kw["sleeve"] = False
    ev = []
    t0 = time.time()
    print(f"[diponly] shift {shift}: simulate start {time.strftime('%H:%M:%S')}", flush=True)
    eu.simulate(books_zero, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    print(f"[diponly] shift {shift}: simulate done in {time.time()-t0:.0f}s, bars {len(cap['idx'])}", flush=True)
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    return dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                eq=(cap["eq"][lv] / base).tolist(),
                eq_min=(cap["eq_min"][lv] / base).tolist())


def main():
    t_start = time.time()
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof0
    pod0 = pof0._load("poddi_main", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    eu0 = _load("eu0di", RD / "engine_user/engine_user.py")
    fw0 = _load("fw0di", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu0.er.v154_books()
    std_books = fw0.research_books_d2(eu0).reindex(books154.index).fillna(0.0)[list(books154.columns)]
    print("[diponly] loading 1m minutes (full OHLC, heavy) ...", flush=True)
    M = pod0.minutes()
    print(f"[diponly] minutes loaded in {time.time()-t_start:.0f}s", flush=True)
    out = {}
    for shift in range(4):
        out[shift] = {"DIPONLY": run_shift(shift, M, books154, std_books, opens_std)}
        print(f"[diponly] shift {shift} eq_end {round(out[shift]['DIPONLY']['eq'][-1],3)} elapsed {time.time()-t_start:.0f}s", flush=True)
    (HERE / "tmp" / "diponly_runs.pkl").write_bytes(pickle.dumps(out))
    rm = _load("rm_di", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    years = []
    for y in range(5):
        m = rm.year_reset(out, "DIPONLY", y)
        years.append(m)
        print(f"[diponly] year {y}: {m}", flush=True)
    (HERE / "tmp" / "diponly_years.json").write_text(json.dumps(years, indent=1, default=str))
    print(f"[diponly] done in {time.time()-t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
