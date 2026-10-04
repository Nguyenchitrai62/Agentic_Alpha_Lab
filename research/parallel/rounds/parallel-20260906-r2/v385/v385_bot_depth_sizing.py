"""v385: order-book-depth dip sizing for the multi-phase BOT R2-4P - a ONE-SHOT test on the most recent year (registry v385).

Why: NEW DATA (research/diagnostics/newdata_bookdepth, dev-only study 2026-10-04): Binance USD-M order-book depth within +-1 % of mid, relative to
its trailing 7-day median, predicts the outcome of dip-limit fills with the same sign in 2023, 2024 and 2025 and for all five majors (IC -0.16 /
-0.16 / -0.24; thin book -> better reversion; partial t -11.5 after the existing state features). The depth archive starts 2023-01-01, so the usual
two-fold dev protocol is impossible (no depth before the 2023 anchor) and the dev years 2023-2025 were used for the screening. The CLEAN test is
the most recent year (2025-09-24 .. 2026-09-23), which no depth study has touched: one pre-registered rule, thresholds fixed from pre-anchor data,
scored once.
Rule (fixed): a bot keeps every resting dip-rung bid's size updated each minute; at a fill in minute f the size multiplier is
  1.5 if D <= q30,  0.5 if D >= q70,  1.0 otherwise (also when D is missing),
D = (bid + ask notional within 1 %) of the last depth snapshot strictly before the fill minute / median of the same per-minute totals over the
trailing 7 days (min 1000 minutes) = research/diagnostics/newdata_bookdepth/features.py bd_depth_rel_7d on a per-minute grid. q30 / q70 = the
30th / 70th percentiles of D at the fill minutes of the five majors' standard-grid dip fills (research/diagnostics/phase_agents/fills_U.parquet)
with t_fill in 2023-01-01 .. 2025-09-16 (before the anchor-2025 cutoff). The multiplier multiplies the R2 agent's size (engine sleeve_fill_size at
the fill minute uses data up to the previous minute only).
Rows (fixed): R2_4P (reference = v376 final: per-phase agent tables v376/tables_hidden), R2depth_4P (same + the depth multiplier).
Evaluation: the v376 most-recent-year procedure (v376_final_hidden.py): each phase's whole path 2021-09-24 .. 2026-09-23 (+ s h) on the audited
phase harness, the most recent year's mix of four sub-accounts started with 1/4 each at the year start, conservative intrabar DD. Decision rule
(pre-registered): R2depth_4P replaces R2_4P as the BOT paper candidate iff its most-recent-year monthly >= reference + 0.20 and its conservative
DD <= reference + 1.0 (check: the reference must reproduce v376_final_hidden: 3.902 %/month). Also reported, LABELLED as screening-contaminated: the dev year 2024-25 (both rows).

  python research/parallel/rounds/parallel-20260906-r2/v385/v385_bot_depth_sizing.py
"""
from __future__ import annotations

import hashlib
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
TABLES = RD / "v376" / "tables_hidden"
DEPTH = ROOT / "data/raw/bookdepth_20261004"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
Y0, Y1 = pd.Timestamp("2025-09-24", tz="UTC"), pd.Timestamp("2026-09-23", tz="UTC")
D24 = pd.Timestamp("2024-09-24", tz="UTC")


def depth_rel():
    """Per coin: Series indexed by minute m -> D for a decision at m + 1 minute (snapshot of minute m, ts < m + 1 min)."""
    out = {}
    for s in SYMS:
        d = pd.read_parquet(DEPTH / f"{s}_bookdepth_1m.parquet").sort_values("minute")
        tot = pd.Series((d["bid_n1"] + d["ask_n1"]).to_numpy(float), index=pd.to_datetime(d["minute"], utc=True))
        tot = tot[~tot.index.duplicated(keep="last")]
        med = tot.rolling("7D", min_periods=1000).median()
        out[s] = (tot / med).dropna()
    return out


def thresholds(D):
    fl = pd.read_parquet(ROOT / "research/diagnostics/phase_agents/fills_U.parquet")
    fl = fl[fl.sym.isin(SYMS) & (fl.t_fill >= pd.Timestamp("2023-01-01", tz="UTC")) & (fl.t_fill < pd.Timestamp("2025-09-16", tz="UTC"))]
    vals = []
    for s, g in fl.groupby("sym"):
        ser = D[s]
        pos = ser.index.searchsorted(g["t_fill"] - pd.Timedelta(minutes=1), side="right") - 1
        ok = pos >= 0
        v = np.full(len(g), np.nan)
        v[ok] = ser.to_numpy()[pos[ok]]
        lag_ok = np.zeros(len(g), bool)
        lag_ok[ok] = (g["t_fill"].to_numpy()[ok] - ser.index.to_numpy()[pos[ok]]) <= np.timedelta64(5, "m")
        vals.append(v[lag_ok])
    v = np.concatenate(vals)
    v = v[np.isfinite(v)]
    return float(np.quantile(v, 0.3)), float(np.quantile(v, 0.7)), int(len(v))


def worker(args):
    shift, name, q = args
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod385_{shift}_{name}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist385_{shift}_{name}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_385_{shift}_{name}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw385_{shift}_{name}", ROOT / "scripts/forward_v205.py")
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
    if name == "R2depth":
        D = depth_rel()
        base = kw["sleeve_fill_size"]
        lo, hi = q
        arr = {cols.index(s): (D[s].index.tz_convert(None).to_numpy(), D[s].to_numpy()) for s in SYMS}  # POST-REGISTRATION FIX (disclosed): naive UTC datetime64 (the first run crashed on a tz comparison before any result)

        def mult(i, a, f):
            t = (idx[i] + pd.Timedelta(hours=4) + pd.Timedelta(minutes=int(f))).to_datetime64()
            ts, vs = arr[a]
            p = np.searchsorted(ts, t - np.timedelta64(1, "m"), side="right") - 1  # snapshot minute <= f - 1
            if p < 0 or t - ts[p] > np.timedelta64(5, "m") or not np.isfinite(vs[p]):
                return 1.0
            return 1.5 if vs[p] <= lo else (0.5 if vs[p] >= hi else 1.0)
        kw["sleeve_fill_size"] = lambda i, a, r, f: base(i, a, r, f) * mult(i, a, f)
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=[], **kw)
    live = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    t = cap["idx"][live] + pd.Timedelta(hours=8)
    print(shift, name, "done", flush=True)
    return (shift, name), dict(t=[str(x) for x in t], eq=cap["eq"][live].tolist(), eq_min=cap["eq_min"][live].tolist())


def year_mix(runs, name, a0, a1):
    grid = pd.date_range(a0 + pd.Timedelta(hours=4), a1 + pd.Timedelta(hours=12), freq="1h")
    E, MN = [], []
    for s in range(4):
        r = runs[(s, name)]
        t = pd.to_datetime(r["t"], utc=True)
        e = pd.Series(r["eq"], index=t)
        lo = pd.Series(r["eq_min"], index=t - pd.Timedelta(hours=4))
        b = float(e[e.index <= a0 + pd.Timedelta(hours=4 + s)].iloc[-1])  # equity at the end of the last bar before the year (as v376_final_hidden)
        ee = e.reindex(grid, method="ffill") / b
        mm = lo.reindex(grid, method="ffill") / b
        E.append(ee.fillna(1.0)); MN.append(np.minimum(mm.fillna(1.0), ee.fillna(1.0)))
    e, mn = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(e.to_numpy())
    return dict(monthly=round(100 * float(e.iloc[-1] ** (1 / 12) - 1), 3), net_pct=round(100 * float(e.iloc[-1] - 1), 2),
                dd_conservative=round(100 * float(np.max(1 - mn.to_numpy() / pk)), 2))


def main():
    D = depth_rel()
    q30, q70, n = thresholds(D)
    print("thresholds q30 / q70", round(q30, 4), round(q70, 4), "from", n, "pre-anchor major fills", flush=True)
    cache = HERE / "v385_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, [(s, nm, (q30, q70)) for nm in ("R2", "R2depth") for s in range(4)]))
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v385", "thresholds": dict(q30=q30, q70=q70, n=n), "most_recent_year": {}, "dev_2024_25_contaminated": {}}
    for nm in ("R2", "R2depth"):
        out["most_recent_year"][nm] = year_mix(runs, nm, Y0, Y1)
        out["dev_2024_25_contaminated"][nm] = year_mix(runs, nm, D24, Y0 - pd.Timedelta(days=1))
        print(nm, "MRY", out["most_recent_year"][nm], "dev 2024-25 (contaminated)", out["dev_2024_25_contaminated"][nm], flush=True)
    ref, new = out["most_recent_year"]["R2"], out["most_recent_year"]["R2depth"]
    out["adopt"] = bool(new["monthly"] >= ref["monthly"] + 0.20 and new["dd_conservative"] <= ref["dd_conservative"] + 1.0)
    print("ADOPT", out["adopt"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v385_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
