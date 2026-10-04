"""v376 R2-4P: the full walk-forward path of the frozen final as series for the web (evidence table / history page) - nothing is selected here.

Re-runs exactly v376_final_hidden.replay (R2 = v321 on each 4h phase s = 0..3, per-phase agent tables tables_hidden/r2_table_s{s}.parquet = dev
phase_agents tables + the anchor-2025 table, phase_offset_full prep_idx / pipe_setup, standard research books forward-filled, adverse funding on
the bar containing a settlement) over 2021-09-24 .. 2026-09-23 (+ s h) and keeps per phase: the bar-end equity / 1m-marked bar minimum, the engine
events (book trades and dip rungs -> orders, win rates). Checks: the dev part reproduces v376_runs.pkl (R2 runs, same base) and the most recent
year reproduces v376_final_hidden.json per phase (net, 1m DD) and the mix (net 58.31, conservative DD 18.76).
Mix = four sub-accounts, 1/4 capital each from their first bar, never rebalanced (v376 accounting): hourly sum of the sub-books' last bar-end
equity; conservative DD = each sub-book's bar minimum held over its bar, summed, against the running peak of the hourly mix.
Output (local, not in Git): artifacts/research/v376/v376_mix_series.json - read by backend/multiphase.py (summary_tm_v376 / tm_v376).

  python research/parallel/rounds/parallel-20260906-r2/v376/v376_mix_series.py
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
OUT = ROOT / "artifacts/research/v376/v376_mix_series.json"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
DEV0, HID0, END = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC"), pd.Timestamp("2026-09-23", tz="UTC")


def _load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def replay(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod376m_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist376m_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_376m_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw376m_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = DEV0 + sh, END + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = HERE / "tables_hidden" / f"r2_table_s{shift}.parquet"
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    events = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
    live = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(live))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    t_end = cap["idx"][live] + pd.Timedelta(hours=8)
    ts = v221.v216.v213.trade_stats([e for e in events if pd.Timestamp(e["t"]) >= live0])  # book trades split by entry (dev / _hidden)
    wins = {}
    for key, part, a, b in (("dev", "dev", live0, HID0 + sh), ("hidden", "_hidden", HID0 + sh, live1 + pd.Timedelta(hours=8))):
        rr = [float(e["ret"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and a <= pd.Timestamp(e["t"]) < b]
        nb = ts.get(part, {}).get("trades") or 0
        wins[key] = dict(book_trades=nb, book_win=ts.get(part, {}).get("win_rate") if nb else None, rungs=len(rr),
                         rung_win=float(np.mean(np.array(rr) > 0)) if rr else None)
    orders = hist.build_orders([e for e in events if pd.Timestamp(e["t"]) >= live0], open_reason="Hết dữ liệu mô phỏng")
    print("phase", shift, "final eq", round(float(cap["eq"][live][-1] / base), 4), "orders", len(orders), flush=True)
    return shift, dict(t=[str(x) for x in t_end], eq=(cap["eq"][live] / base).tolist(), eq_min=(cap["eq_min"][live] / base).tolist(),
                       wins=wins, orders=orders)


def hourly(run, grid):
    t = pd.to_datetime(run["t"], utc=True)
    e = pd.Series(run["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
    lo = pd.Series(run["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(lo, e)


def main():
    with Pool(4) as pool:
        runs = dict(pool.map(replay, range(4)))
    grid = pd.date_range(DEV0 + pd.Timedelta(hours=4), END + pd.Timedelta(hours=12), freq="1h")
    hs = [hourly(runs[s], grid) for s in range(4)]
    e = sum(h[0] for h in hs) / 4
    mn = sum(h[1] for h in hs) / 4
    pk = np.maximum.accumulate(e.to_numpy())
    dd_full = 100 * float(np.max(1 - mn.to_numpy() / pk))
    yearly, nets = [], []
    for a in ANCH:
        a0 = pd.Timestamp(a, tz="UTC")
        seg = (e.index > a0) & (e.index <= a0 + pd.Timedelta(days=365))
        b = float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
        es, ms = e[seg] / b, mn[seg] / b
        p = np.maximum.accumulate(np.concatenate([[1.0], es.to_numpy()]))[1:]
        nets.append(float(es.iloc[-1] - 1))
        yearly.append((a, round(100 * nets[-1], 2), round(100 * float(np.max(1 - ms.to_numpy() / p)), 2)))
    geo = lambda xs: 100 * (np.prod([1 + x for x in xs]) ** (1 / (12 * len(xs))) - 1)
    # checks against the v376 research outputs
    old = pickle.loads((HERE / "v376_runs.pkl").read_bytes())
    chk = {}
    for s in range(4):
        r_old, r = old[s]["R2"], runs[s]
        n = len(r_old["eq"])
        chk[f"dev_s{s}_max_abs_eq_diff"] = float(np.max(np.abs(np.array(r["eq"][:n]) - np.array(r_old["eq"]))))
        chk[f"dev_s{s}_t_equal"] = r["t"][:n] == r_old["t"]
    hid = json.loads((HERE / "v376_final_hidden.json").read_text())
    for s in range(4):
        t = pd.to_datetime(runs[s]["t"], utc=True)
        y = np.asarray(t > HID0 + pd.Timedelta(hours=s + 4))
        base = runs[s]["eq"][int(np.argmax(y)) - 1]
        chk[f"hidden_s{s}_net"] = [round(100 * (runs[s]["eq"][-1] / base - 1), 2), hid["phases"][str(s)]["net_pct"]]
    # the most recent year as scored once (mix restarted at the year's beginning, v376_final_hidden)
    last = hid["mix_R2_4P"]
    pool_w = lambda key: (sum((runs[s]["wins"][key]["book_trades"] or 0) for s in range(4)),
                          sum(round((runs[s]["wins"][key]["book_win"] or 0) * (runs[s]["wins"][key]["book_trades"] or 0)) for s in range(4)),
                          sum(runs[s]["wins"][key]["rungs"] for s in range(4)),
                          sum(round((runs[s]["wins"][key]["rung_win"] or 0) * runs[s]["wins"][key]["rungs"]) for s in range(4)))
    win = {}
    for key in ("dev", "hidden"):
        nb, wb, nr, wr = pool_w(key)
        win[key] = dict(book_trades=nb, book_win=round(wb / nb, 4) if nb else None, rungs=nr,
                        win_all=round((wb + wr) / (nb + nr), 4) if nb + nr else None)
    # the most recent year as scored once: the four sub-accounts restarted at 1/4 each on 2025-09-24 (v376_final_hidden); the dev years are
    # the continuous mix (v376 rows). The 5-year figure chains those five yearly nets; the never-rebalanced 5-year mix is a side field
    # (its sub-books drift apart, phase 0 dominates by 2025, so its last year is not the scored number).
    cont = dict(monthly_5y_continuous_mix=round(geo(nets), 3), monthly_last_year_continuous_mix=round(geo(nets[4:]), 3),
                last_year_continuous_mix=yearly[4])
    nets[4] = last["net_pct"] / 100
    yearly[4] = (ANCH[4], last["net_pct"], last["dd_conservative"])
    summary = dict(monthly_5y=round(geo(nets), 3), monthly_dev4=round(geo(nets[:4]), 3), monthly_last_year=last["monthly"],
                   gate_dd=round(dd_full, 2), dd_last_year=last["dd_conservative"], dd_conservative_full_path=round(dd_full, 2),
                   dd_1m=round(dd_full, 2), losing_years=int(sum(x < 0 for x in nets)), yearly=yearly, **cont,
                   win_dev=win["dev"]["book_win"], win_hidden=win["hidden"]["book_win"], trades_dev=win["dev"]["book_trades"],
                   trades_hidden=win["hidden"]["book_trades"], win_all_dev=win["dev"]["win_all"], win_all_hidden=win["hidden"]["win_all"],
                   rungs_dev=win["dev"]["rungs"], rungs_hidden=win["hidden"]["rungs"])
    print(json.dumps(summary), json.dumps(chk), flush=True)
    e4 = e[e.index.hour % 4 == 0]  # 4h sampling of the hourly mix for the equity chart
    out = dict(version="v376", row="R2_4P", summary=summary, checks=chk, equity=[(str(t), round(float(v), 6)) for t, v in e4.items()],
               orders={s: runs[s]["orders"] for s in range(4)},
               note="gate_dd = the conservative DD over the whole 5-year path (as every other pipeline); dd_last_year / monthly_last_year = the most recent year scored once (v376_final_hidden: mix started at the year's start); "
                    "dd_conservative_full_path = the same conservative DD over the whole 5-year continuous mix (dev year 2023-24 reaches ~23 %).")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
