"""oc_manualbf: MANUAL M4/M5 on five years with the v410 bear-regime book filter (honest human schedule).

PLAN.md fixes the rows before running. Harness = manual_human.py (human
schedule) + r2_decompose5.py (full 5y index books154.index + shift,
v376/tables_hidden r2 tables) + v410 bear transform (standard book LONG x0.5
where BTC 4h open < its 1200-bar mean, before the shifted-clock forward fill)
+ v377 win pooling. ONE heavy process (Pool(1)).

  python research/diagnostics/oc_manualbf/oc_manualbf.py
"""
from __future__ import annotations

import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
PIPES = {"M4": "v362", "M5": "v367"}
VARIANTS = ("base", "human", "humanBF")
ROWS = [f"{p}_{v}" for p in ("M4", "M5") for v in VARIANTS]
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")


def bear_books(std_books: pd.DataFrame, btc_open: pd.Series) -> pd.DataFrame:
    """v410 transform on STANDARD book rows: LONG targets x0.5 on bear rows.

    bear[t] = open[t] < mean(open[t-1199..t]) (rolling 1200, min_periods 600);
    row t uses opens <= t only. Shorts (<= 0) unchanged.
    """
    b = btc_open.reindex(std_books.index)
    bear = (b < b.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy()
    sb = std_books.copy()
    idx = std_books.index[bear]
    blk = sb.loc[idx]
    sb.loc[idx] = blk.where(blk <= 0, blk * 0.5)
    return sb


def run_phase(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod_mbf_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_mbf_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_mbf_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_mbf_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    idx = prep["idx"]
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    sb = bear_books(std_books, opens_std["BTCUSDT"])
    books_plain = std_books.reindex(idx, method="ffill").fillna(0.0)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    hours = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    night = (20 + shift) % 24
    out = {}
    for pname, pipe in PIPES.items():
        for variant in VARIANTS:
            kw, trade = pof.pipe_setup(pipe, hist, v221, v216, idx, cols, True)
            lat = 5 if variant == "base" else 15
            if variant in ("human", "humanBF"):
                pol = trade["policy"]
                trade["policy"] = lambda i, a, st, pol=pol: ("wait" if st["pos"] == 0 else "hold") if hours[i] == night else pol(i, a, st)
                kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
                kw["sleeve_start"] = 16
            bk = books_bear if variant == "humanBF" else books_plain
            events: list = []
            eu.simulate(bk, opens, prep, trade=trade, win_start=lat, events=events, **kw)
            m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], ANCH5, live0, live1, sh)
            years = []
            for y, a in enumerate(ANCH5):
                a0 = pd.Timestamp(a, tz="UTC") + sh
                a1 = min(a0 + pd.Timedelta(days=365), live1)
                ev = [e for e in events if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
                ts = v216.v213.trade_stats(ev)
                nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
                wb = sum(round((ts.get(k) or {}).get("win_rate", 0) * (ts.get(k) or {}).get("trades", 0)) for k in ("dev", "_hidden"))
                rr = [float(e["ret"]) for e in ev if e["kind"] in RUNG_KINDS and "ret" in e]
                yy = m["yearly"][y]
                years.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"], nb=int(nb), wb=int(wb),
                                  nr=len(rr), wr=int(sum(r > 0 for r in rr))))
            out[f"{pname}_{variant}"] = years
            print(shift, pname, variant, [round(100 * v["net"], 1) for v in years],
                  [v["dd"] for v in years], flush=True)
    return shift, out


def _monthly(net):
    return 100 * ((1 + net) ** (1 / 12) - 1)


def summary(allres, row, ys):
    per_year, r_ph, dd_ph, w_ph = [], [], [], []
    nb = wb = nr = wr = 0
    for s in range(4):
        yy = [allres[s][row][y] for y in ys]
        per_year.append([_monthly(v["net"]) for v in yy])
        r_ph.append(100 * (np.prod([1 + v["net"] for v in yy]) ** (1 / (12 * len(yy))) - 1))
        dd_ph.append(max(v["dd"] for v in yy))
        w_ph.append(min(_monthly(v["net"]) for v in yy))
        nb += sum(v["nb"] for v in yy)
        wb += sum(v["wb"] for v in yy)
        nr += sum(v["nr"] for v in yy)
        wr += sum(v["wr"] for v in yy)
    n = len(ys)
    return dict(
        years_monthly=[round(float(np.mean([per_year[s][i] for s in range(4)])), 3) for i in range(n)],
        years_monthly_phases=[[round(float(v), 2) for v in row_y] for row_y in zip(*per_year)],
        R=round(float(np.mean(r_ph)), 3),
        R_phases=[round(float(v), 2) for v in r_ph],
        DD=round(float(np.mean(dd_ph)), 2),
        DD_phases=[round(float(v), 1) for v in dd_ph],
        DD_max=round(float(max(dd_ph)), 1),
        W=round(float(np.mean(w_ph)), 3),
        book_trades=int(nb),
        book_win=round(wb / nb, 4) if nb else None,
        rung_trades=int(nr),
        rung_win=round(wr / nr, 4) if nr else None,
        win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
    )


def main():
    cache = HERE / "oc_manualbf_runs.pkl"
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
    else:
        with Pool(1) as pool:
            allres = dict(pool.map(run_phase, range(4)))
        cache.write_bytes(pickle.dumps(allres))
    table = {}
    for row in ROWS:
        table[row] = dict(y5=summary(allres, row, [0, 1, 2, 3, 4]),
                          dev4=summary(allres, row, [0, 1, 2, 3]),
                          last=summary(allres, row, [4]))
        v = table[row]["y5"]
        print(row, "R5", v["R"], "DD", v["DD"], f"({v['DD_max']})", "book_win", v["book_win"], "win_all", v["win_all"], flush=True)
    meta = dict(dev0=str(DEV0), live1=str(Y1), anchors=list(ANCH5),
                note="M4=v362 M5=v367; human=15min+night skip; humanBF=human+bear LONG x0.5 (v410); single-clock mean over 4 phases")
    (HERE / "results.json").write_text(json.dumps(dict(meta=meta, rows=table), indent=1))


if __name__ == "__main__":
    main()
