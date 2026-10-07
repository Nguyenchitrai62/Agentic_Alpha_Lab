"""engine_kelly: 4-phase G2-identical engine with Kelly dip sizes (heavy; run via heavy_slot).

Rest identical G2 (v421 R2B1D17BFG2): R2 rungs, kd=1.7-equivalent budget via C0,
bear-book halving, risk budget 0.26*1.7, gross cap G=2.0, D17 stops/backstop,
deployed TP. Only sleeve_fill_size changes to the pre-registered Kelly rule.

Kelly size (per fill, bot-executable like B1):
  n = #{other majors with C(f-1) <= O(0)*(1-2.5*sg)} (v421-exact, 0..4)
  B1 = 1/(1+n);  y = anchor year containing Tb=idx[i]+4h
  size = B1 * Base[y][k] * f_frac * C0[y]
Base/C0 from tmp/fit_tables.json (train t_exit<anchor-7d only).
K1 f=0.25, K2 f=0.50. No 2025 data used in DEV runs; LAST run winner-only.
"""
from __future__ import annotations

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
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
FRAC = {"K1": 0.25, "K2": 0.50}
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def anchor_idx(tb):
    y = 0
    for i, a in enumerate(ANCH):
        if tb >= pd.Timestamp(a, tz="UTC"):
            y = i
    return y


def run_one(shift, variants, last_year, tables):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podK_{shift}_{int(last_year)}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histK_{shift}_{int(last_year)}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_K_{shift}_{int(last_year)}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwK_{shift}_{int(last_year)}", ROOT / "scripts/forward_v205.py")
    v388 = _load(f"v388K_{shift}_{int(last_year)}", RD / "v388/v388_bot_stop_distance.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    Y1 = v388.Y1
    live0, live1 = pof.DEV0 + sh, (Y1 if last_year else pof.DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = std_books["BTCUSDT"].reindex(books154.index) if "BTCUSDT" in std_books else None
    _o = _load(f"euK_{shift}", RD / "v221/v221_grid_hysteresis.py")
    # bear books exactly as v421 (BTC < 1200b mean -> halve positive books)
    import pandas as _pd
    btc_s = books154["BTCUSDT"] if "BTCUSDT" in books154 else std_books["BTCUSDT"]
    bear = (btc_s < btc_s.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    out = {}
    for name in variants:
        f_frac = FRAC[name]
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        base_size = kw["sleeve_fill_size"]

        def kelly_size(i, a, r, f, f_frac=f_frac):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b])
                                  and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            b1 = 1.0 / (1 + n)
            tb = idx[i] + pd.Timedelta(hours=4)
            y = anchor_idx(tb)
            t = tables[ANCH[min(y, 4)]]
            k = R2[r] if 0 <= r < len(R2) else 2.5
            base = float(t["base"].get(str(k), 1.0))
            return b1 * base * f_frac * float(t["C0"])

        kw["sleeve_fill_size"] = kelly_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0
        ev = []
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        rr = [float(e["ret"]) for e in ev if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")
              and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
        bw = pof.book_win(v221, ev, live0, live1)
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist(),
                         nb=int(bw.get("book_trades", 0) or 0),
                         wb=int(round((bw.get("book_win") or 0) * (bw.get("book_trades") or 0))),
                         nr=int(len(rr)), wr=int(sum(r > 0 for r in rr)))
        print(shift, name, "last" if last_year else "dev",
              round(out[name]["eq"][-1], 3), "rungs", len(rr), flush=True)
        del ev
    del opens, prep, idx, cols, books, books_bear, std_books
    return shift, out


def run_engine_dev(shifts=(0, 1, 2, 3), variants=("K1", "K2")):
    tables = json.loads((HERE / "tmp" / "fit_tables.json").read_text())
    # DEV anchors only inside the engine (Tb<2025-09-24 -> y<=3); drop the 2025 table
    # from lookup is automatic via anchor_idx; keep all for safety.
    runs = {}
    for s in shifts:
        _, out = run_one(s, list(variants), False, tables)
        for v, d in out.items():
            runs.setdefault(s, {})[v] = {k: d[k] for k in ("t", "eq", "eq_min", "nb", "wb", "nr", "wr")}
    p = HERE / "tmp" / "engine_dev.pkl"
    p.write_bytes(pickle.dumps(runs))
    print("wrote", p, {s: list(runs[s]) for s in runs}, flush=True)


def run_engine_last(winner=None, shifts=(0, 1, 2, 3)):
    tables = json.loads((HERE / "tmp" / "fit_tables.json").read_text())
    if winner is None:
        dev = json.loads((HERE / "tmp" / "engine_dev_choice.json").read_text())
        winner = dev["winner"]
    assert winner in FRAC, winner
    runs = {}
    for s in shifts:
        _, out = run_one(s, [winner], True, tables)
        runs.setdefault(s, {})[winner] = out[winner]
    p = HERE / "tmp" / "engine_last.pkl"
    p.write_bytes(pickle.dumps(runs))
    print("wrote", p, "winner", winner, flush=True)
