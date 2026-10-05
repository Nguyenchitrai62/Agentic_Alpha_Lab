"""v395: the user gate for the frozen finalist R2CS6_4P - most recent year scored ONCE (registry v395).

Finalist: R2CS6_4P from v394 = the BOT R2 on four 4h clocks (1/4 capital each, never rebalanced) with dip-rung sizes from the market-context
size model (research/tournament/context, V2 hgb_mono, deployed 1.5 / 1.0 / 0.5 rule) and the dip close-stop at 6 sigma (backstop 8 sigma).
Selection disclosure: among the v391-v394 dev rows it is the only one with dev DD <= 20, no losing year and dev4 >= 5 %/month (AGENTS robust
criterion, the standing selection rule for directions from v204 on); the registered BOT-fitness folds of v394 preferred R2K (DD 25.2), and the
robust-criterion fold check was computed after seeing the dev rows (fold 2 -> R2C, fold 3 -> R2CS6). The most recent year has been used many
times in this program (only prospective paper evidence is clean); it is scored here ONCE and nothing is selected on it.
Inputs: size tables research/tournament/context/tables/ctx_v2_s{s}.parquet (dev) + ctx_v2_hidden_s{s}.parquet (anchor 2025-09-24 fold model,
trained on fills with t_exit < 2025-09-17; T from 2025-09-24); the hidden-year table rows replace the dev table rows for T >= 2025-09-24.
TP = deployed agent's per-phase tables (v376/tables_hidden, which hold the anchor-2025 rows). Engine and mix exactly as v388 / v376_final_hidden.
Gate (user, AGENTS.md): (a) 5-year walk-forward geometric mean >= 5 %/month (2021-09-24 .. 2026-09-23, mix path), (b) most recent year alone
>= 5 %/month, (c) no losing year, and DD <= 20 % over the full path (conservative 1m-marked mix DD). Reported next to R2_4P's known most recent
year (v376_final_hidden: 3.90 %/month, DD 18.8). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v395/v395_r2cs6_final_gate.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
TABLES = RD / "v376" / "tables_hidden"
CTX = ROOT / "research/tournament/context/tables"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_395", RD / "v388" / "v388_bot_stop_distance.py")
ANCH, Y1 = v388.ANCH, v388.Y1
A5 = pd.Timestamp(ANCH[4], tz="UTC")


def look_table(shift):
    dev = pd.read_parquet(CTX / f"ctx_v2_s{shift}.parquet")
    hid = pd.read_parquet(CTX / f"ctx_v2_hidden_s{shift}.parquet")
    t = pd.concat([dev[pd.to_datetime(dev["T"], utc=True) < A5], hid], ignore_index=True)
    return {(pd.Timestamp(T), s, int(r)): float(z) for T, s, r, z in zip(t["T"], t["sym"], t["rung"], t["size"])}


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod395_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist395_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_395_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw395_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    look = look_table(shift)
    kw["sleeve_fill_size"] = lambda i, a, r, f: look.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)
    kw["m_sleeve_sl"] = 6.0
    events = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    out = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(), eq_min=(cap["eq_min"][lv] / base).tolist())
    print(shift, "final equity", round(out["eq"][-1], 3), flush=True)
    return shift, {"R2CS6": out}


def main():
    with Pool(2) as pool:
        runs = dict(pool.map(worker, range(4)))
    g1 = Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, "R2CS6", g1)
    years = [v388.year_stats(e, mn, [y]) for y in range(5)]
    five = v388.year_stats(e, mn, [0, 1, 2, 3, 4])
    dev4 = v388.year_stats(e, mn, [0, 1, 2, 3])
    seg = (e.index > pd.Timestamp(ANCH[0], tz="UTC")) & (e.index <= g1)
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full_dd = 100 * float(np.max(1 - ms / np.maximum.accumulate(es)))
    last = years[4]
    gate = dict(a_5y_ge5=five["R"] >= 5, b_last_ge5=last["R"] >= 5, c_no_losing_year=five["losing"] == 0, dd_full_le20=full_dd <= 20)
    out = {"version": "v395", "finalist": "R2CS6_4P", "years": years, "dev4": dev4, "five_year": five, "most_recent_year_once": last,
           "full_path_dd_conservative": round(full_dd, 2), "gate": gate, "gate_pass": all(gate.values()),
           "reference_R2_4P_most_recent_year": json.loads((RD / "v376" / "v376_final_hidden.json").read_text())["mix_R2_4P"]}
    print(json.dumps(out, indent=1, default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v395_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
