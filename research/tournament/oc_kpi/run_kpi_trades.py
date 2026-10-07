"""oc_kpi trades replica: exact v411 R2B1D17BF worker for one shift with events/bars.

Setup is bit-for-bit the v411 worker (v411_d17bf.py) and oc_ddanat17's replica:
dips x1.7 inv-rule, budget 0.26*1.7, bear-book filter, R2 agents, v216 grid
trade policy, win_start=5. ONE process per invocation; run shifts 0..3
sequentially. Checks rerun 4h-close equity == v411_runs.pkl to 1e-9 relative.

Usage: .venv/Scripts/python.exe research/tournament/oc_kpi/run_kpi_trades.py --shift N
Writes events_sN.parquet, barsum_sN.parquet, check_sN.json in this folder.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shift", type=int, required=True, choices=(0, 1, 2, 3))
    shift = ap.parse_args().shift

    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof

    v388 = _load(f"v388_kpit_{shift}", RD / "v388" / "v388_bot_stop_distance.py")
    Y1 = v388.Y1
    pod = pof._load(f"pod_kpi_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_kpi_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_kpi_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_kpi_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216

    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy(), stats=dict(stats)) or {}

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
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size, rule, kd = kw["sleeve_fill_size"], "inv", 1.7

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
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd

    events, attrib, path_out, bars = [], [], {}, []
    eu.simulate(books_bear, opens, prep, trade=trade, win_start=5,
                events=events, attrib=attrib, path_out=path_out, bars=bars, **kw)
    print(f"shift {shift}: simulate done", flush=True)
    st = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}
    print(f"shift {shift}: stats", st, flush=True)

    # --- equity check vs v411_runs.pkl (4h-close, live window, same base) ---
    pidx = path_out["t"]
    eq = np.asarray(path_out["eq"], float)
    lv = np.asarray((pidx >= live0) & (pidx < live1))
    first = int(np.argmax(lv))
    base = float(eq[first - 1]) if first > 0 else 1.0
    li = np.where(lv)[0]
    e_live = eq[li] / base
    t_live = pidx[li] + pd.Timedelta(hours=8)
    runs = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
    ref = runs[shift]["R2B1D17BF"]
    rt = pd.to_datetime(ref["t"], utc=True)
    re_ = np.asarray(ref["eq"], float)
    common = pd.Index(t_live).intersection(rt)
    a = pd.Series(e_live, index=t_live).reindex(common).to_numpy(float)
    b = pd.Series(re_, index=rt).reindex(common).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        reldiff = np.abs(a / b - 1)
    maxrel = float(np.nanmax(reldiff))
    ok = bool(maxrel <= 1e-9 and len(common) == len(ref["t"]))
    print(f"shift {shift}: overlap {len(common)}/{len(ref['t'])} maxrel {maxrel:.3e} {'OK' if ok else 'MISMATCH'}",
          flush=True)

    # --- per-bar book summary from bars[] ---
    rows = []
    for bb in bars:
        t = pd.Timestamp(bb["t"])
        if not (live0 <= t - pd.Timedelta(hours=4) < live1):
            continue
        qty = np.asarray(bb["qty"], float)
        opn = np.asarray(bb["open"], float)
        eqb = float(bb["equity"])
        nopen = int((np.abs(qty) > 0).sum())
        gross = float(np.abs(qty * np.where(np.isfinite(opn), opn, 0.0)).sum() / eqb) if eqb else 0.0
        rows.append(dict(t=str(t), n_book=nopen, gross_book=round(gross, 6), equity=eqb))
    bsum = pd.DataFrame(rows)

    ev = pd.DataFrame(events)
    ev.to_parquet(HERE / f"events_s{shift}.parquet")
    bsum.to_parquet(HERE / f"barsum_s{shift}.parquet")
    check = dict(shift=shift, live=[str(live0), str(live1)], overlap=int(len(common)),
                 ref_bars=int(len(ref["t"])), max_rel_diff=maxrel, match_1e9=ok,
                 eq_end_rerun=float(e_live[-1]), eq_end_ref=float(re_[-1]),
                 stats=st, n_events=int(len(ev)), n_bars=int(len(bsum)),
                 n_attrib=int(len(attrib)))
    (HERE / f"check_s{shift}.json").write_text(json.dumps(check, indent=1))
    print(f"shift {shift}: wrote events/barsum/check match={ok}", flush=True)
    if not ok:
        raise SystemExit(f"shift {shift}: equity mismatch (maxrel {maxrel:.3e})")


if __name__ == "__main__":
    main()
