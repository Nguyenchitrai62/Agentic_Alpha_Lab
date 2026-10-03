"""v376 follow-up (declared in v376's pre-registration): the most recent year, computed ONCE, for the transferring final R2_4P.

1. Agent decision tables for the most recent year on each 4h phase: the SAME anchor-2025 model as the deployed R2 table (pooled U fills that exited
   before 2025-09-24 - 7 days, research/diagnostics/phase_agents/fills_U.parquet, v296.hgb seeds 40 + h / 40 + h + 3c, j % 2 halves), state at the
   shifted bar open (research/diagnostics/phase_agents/build_tables.py logic, minute data now up to 2026-09-25). Check: at s = 0 the table must equal
   the deployed artifacts/research/engine_real/v321_r2_table_m0.parquet on the most recent year.
2. R2 (v321) replayed on each phase over the whole path 2021-09-24 .. 2026-09-23 (+ s h) with the per-phase tables (dev part = phase_agents tables),
   exactly as v376's worker; only the most recent year is reported: per phase, and the 4-sub-account mix started at the year's beginning (1/4 each,
   never rebalanced; conservative intrabar DD as in v376). The s = 0 single-phase row must reproduce history_tm's v321 most recent year (5.655).
Nothing is selected here.
"""
from __future__ import annotations

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
PA = ROOT / "research/diagnostics/phase_agents"
Y0, Y1 = pd.Timestamp("2025-09-24", tz="UTC"), pd.Timestamp("2026-09-23", tz="UTC")


def _load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def build_tables():
    bt = _load("bt376", PA / "build_tables.py")
    v294 = _load("v294_376", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = _load("v296_376", RD / "v296/v296_joint_dip_agent.py")
    v293.RUNGS = bt.U
    v293.END = pd.Timestamp("2026-09-25", tz="UTC")
    START0 = v293.START
    allf = pd.read_parquet(PA / "fills_U.parquet")
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    keep = np.asarray(pd.to_datetime(allf["t_exit"], utc=True) < bt.ANCHORS[4] - v293.EMBARGO)
    jj = 4
    sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
    tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(3)] for h in (0, 1)]
    mu = float(y1[keep].mean())
    out = {}
    (HERE / "tables_hidden").mkdir(exist_ok=True)
    for sft in range(4):
        sh = pd.Timedelta(hours=sft)
        v293.START = START0 + sh
        assets = {s: v293.Asset(s) for s in v293.MAJORS}
        btc = assets["BTCUSDT"]
        meta, feats = [], []
        for s, A in assets.items():
            for j, T in enumerate(A.t0):
                if T <= bt.TMAX + sh or T > Y1 + pd.Timedelta(hours=12) + sh or not np.isfinite(A.sig[j]):
                    continue
                kk = j * 240
                base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                        np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
                for k in bt.U:
                    meta.append((T, s, k))
                    feats.append(base[:1] + [k] + base[2:])
        del assets, btc
        F = np.array(feats, float)
        res = dict(pa=sm[0].predict(F), pb=sm[1].predict(F), mu=np.full(len(F), mu))
        for c in range(3):
            res[f"qa{c}"], res[f"qb{c}"] = tm[0][c].predict(F), tm[1][c].predict(F)
        raw = pd.DataFrame({"T": [m_[0] for m_ in meta], "sym": [m_[1] for m_ in meta], "k": [m_[2] for m_ in meta], **res})
        g = raw[raw.k.isin(bt.R2)].copy()
        g["rung"] = g.k.map({k: r for r, k in enumerate(bt.R2)}).astype(int)
        g["size"], g["tp"] = bt.rules(g)
        tab = pd.concat([pd.read_parquet(PA / "tables" / f"r2_table_s{sft}.parquet"), g[["T", "sym", "rung", "size", "tp"]]], ignore_index=True)
        tab = tab.drop_duplicates(["T", "sym", "rung"], keep="first")
        tab.to_parquet(HERE / "tables_hidden" / f"r2_table_s{sft}.parquet")
        out[sft] = len(g)
        if sft == 0:
            dep = pd.read_parquet(ROOT / "artifacts/research/engine_real/v321_r2_table_m0.parquet")
            dep = dep[pd.to_datetime(dep["T"], utc=True) > bt.TMAX]
            mg = dep.merge(g[["T", "sym", "rung", "size", "tp"]], on=["T", "sym", "rung"], suffixes=("_dep", "_new"))
            out["check_s0"] = dict(deployed_rows=len(dep), matched=len(mg), size_eq=float((mg.size_dep == mg.size_new).mean()),
                                   tp_eq=float((mg.tp_dep == mg.tp_new).mean()))
            print("CHECK s0", out["check_s0"], flush=True)
    return out


def replay(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod376h_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist376h_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_376h_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw376h_{shift}", ROOT / "scripts/forward_v205.py")
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
    hist.R2_TABLE = HERE / "tables_hidden" / f"r2_table_s{shift}.parquet"
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=[], **kw)
    yr = np.asarray((cap["idx"] >= Y0 + sh) & (cap["idx"] < live1))
    first = int(np.argmax(yr))
    base = cap["eq"][first - 1]
    t = cap["idx"][yr] + pd.Timedelta(hours=8)
    e, mn = cap["eq"][yr] / base, cap["eq_min"][yr] / base
    pk = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
    single = dict(net_pct=round(100 * float(e[-1] - 1), 2), monthly=round(100 * float(e[-1] ** (1 / 12) - 1), 3),
                  dd_1m=round(100 * float(np.max(1 - np.minimum(e, mn) / pk)), 2))
    print("phase", shift, single, flush=True)
    return shift, dict(single=single, t=[str(x) for x in t], eq=e.tolist(), eq_min=mn.tolist())


def main():
    info = build_tables()
    with Pool(4) as pool:
        runs = dict(pool.map(replay, range(4)))
    grid = pd.date_range(Y0 + pd.Timedelta(hours=4), Y1 + pd.Timedelta(hours=12), freq="1h")
    E, MN = [], []
    for s in range(4):
        t = pd.to_datetime(runs[s]["t"], utc=True)
        e = pd.Series(runs[s]["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
        lo = pd.Series(runs[s]["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
        E.append(e); MN.append(np.minimum(lo, e))
    e, mn = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(e.to_numpy())
    mix = dict(net_pct=round(100 * float(e.iloc[-1] - 1), 2), monthly=round(100 * float(e.iloc[-1] ** (1 / 12) - 1), 3),
               dd_conservative=round(100 * float(np.max(1 - mn.to_numpy() / pk)), 2))
    out = dict(version="v376", step="most recent year, once, final R2_4P", tables=info, phases={s: runs[s]["single"] for s in range(4)}, mix_R2_4P=mix)
    print("MIX", mix, flush=True)
    (HERE / "v376_final_hidden.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
