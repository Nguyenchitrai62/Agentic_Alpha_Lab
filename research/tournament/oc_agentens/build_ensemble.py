"""oc_agentens: seed-ensemble R2 dip tables, phase s=0 only.

Copied logic from research/tournament/oc_rlbear/build_v0_v2.py V0 (itself a
verbatim copy of phase_agents/build_tables.py + v296 HGB hyperparams +
v293.EMBARGO + R2 rules): same U/R2/anchors/clip/mu/embargo/rules; training
fills from research/tournament/ext/fills_U_ext.parquet; NO extra feature.

Seed scheme (frozen in PLAN.md, v303 convention): S in {0,101,202,303,404}.
S=0 is the deployed seed (random_state = 10*jj+h size, +3*c TP). For S>0:
random_state = 1000*S + 10*jj+h (+3*c TP). Ensemble = per-(T,sym,rung)
majority vote over the 5 tables, separately for size and tp; ties -> 1.0.

MEDIUM slot: single process, one majors 1m coin at a time (BTC kept for
btc.sp30 while each other major is loaded, featurised, predicted, released
— exactly like build_v0_v2.py); seeds built sequentially (models released
per seed) to stay < 3 GB.
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
EXT = ROOT / "research/tournament/ext"
REF_S0 = RD / "v376/tables_hidden/r2_table_s0.parquet"
V0_CHECK = ROOT / "research/tournament/oc_rlbear/v0_table_s0.parquet"

U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
R2_IDX = {k: r for r, k in enumerate(R2)}
SEEDS = (0, 101, 202, 303, 404)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
T_MIN = ANCHORS[0]
T_MAX = pd.Timestamp("2026-09-23 12:00", tz="UTC")  # = v376 hidden s0 max T
END = pd.Timestamp("2026-09-24", tz="UTC")
QC = ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")
VALS = (0.5, 1.0, 1.5)


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def hgb(seed):
    # verbatim v296 hyperparameters
    return HistGradientBoostingRegressor(
        max_depth=3, learning_rate=0.05, max_iter=200,
        min_samples_leaf=200, l2_regularization=1.0, random_state=seed)


def rules(df):
    """Verbatim copy of phase_agents/build_tables.py::rules (R2 genome)."""
    pa, pb, mu = df.pa.to_numpy(), df.pb.to_numpy(), df.mu.to_numpy()
    up = (pa > 2.0 * mu) & (pb > 2.0 * mu)
    dn = (pa < 0.0 * mu) & (pb < 0.0 * mu)
    size = np.ones(len(df))
    size[up] = 1.5
    size[dn & ~up] = 0.5
    size[~np.isfinite(pa)] = 1.0
    qa, qb = df[["qa0", "qa1", "qa2"]].to_numpy(), df[["qb0", "qb1", "qb2"]].to_numpy()
    ba, bb = np.nanargmax(np.nan_to_num(qa, nan=-9), -1), np.nanargmax(np.nan_to_num(qb, nan=-9), -1)
    n = np.arange(len(df))
    ga, gb = qa[n, ba] - qa[:, 1], qb[n, bb] - qb[:, 1]
    ok = (ba == bb) & (ba != 1) & (ga > 0.001) & (gb > 0.001) & np.isfinite(ga) & np.isfinite(gb)
    tp = np.where(ok, np.array((0.5, 1.0, 1.5))[ba], 1.0)
    return size, tp


def majority_vote(col_stack):
    """Per-row majority vote over 5 columns with values in {0.5,1.0,1.5}.

    Ties for the top count -> 1.0 (deployed default, frozen in PLAN.md).
    """
    V = np.asarray(col_stack, float)  # (n, 5)
    out = np.full(V.shape[0], 1.0)
    for v in VALS:
        cnt_v = (V == v).sum(axis=1)
        cnt_max = np.maximum.reduce([(V == u).sum(axis=1) for u in VALS])
        # unique mode v: count is max and strictly greater than every other
        others = [u for u in VALS if u != v]
        uniq = cnt_v == cnt_max
        for u in others:
            uniq &= cnt_v > (V == u).sum(axis=1)
        out[uniq] = v
    # rows where no unique mode keep 1.0
    return out


def build_seed_table(S, v293, btc_holder, fills_cache):
    """Fit 40 HGB models for seed S and build its s=0 table. One coin at a time."""
    X7, Y, y1, half, t_exit = fills_cache
    models = []
    for jj in range(len(ANCHORS)):
        a0 = ANCHORS[jj]
        keep = np.asarray(t_exit < a0 - v293.EMBARGO)
        mu = float(y1[keep].mean())
        base = 1000 * S + 10 * jj
        sm = [hgb(base + h).fit(X7[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[hgb(base + h + 3 * c).fit(X7[keep & (half == h)], Y[keep & (half == h), c])
               for c in range(3)] for h in (0, 1)]
        models.append((mu, sm, tm))
    parts = []
    btc = btc_holder
    for sym in v293.MAJORS:
        A = btc if sym == "BTCUSDT" else v293.Asset(sym)
        meta, F = [], []
        for j, T in enumerate(A.t0):
            if T < T_MIN or T > T_MAX or not np.isfinite(A.sig[j]):
                continue
            jj = max(q for q, a0 in enumerate(ANCHORS) if T >= a0)
            kk = j * 240
            dd = np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan
            row = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk), dd, float(T.hour)]
            for k in U:
                meta.append((T, sym, k, jj))
                F.append(row[:1] + [k] + row[2:])
        F = np.array(F, float)
        J = np.array([m[3] for m in meta])
        res = {c: np.full(len(meta), np.nan) for c in QC}
        for jj2, (mu, sm, tm) in enumerate(models):
            sel = J == jj2
            if not sel.any():
                continue
            x = F[sel]
            res["pa"][sel], res["pb"][sel] = sm[0].predict(x), sm[1].predict(x)
            res["mu"][sel] = mu
            for c in range(3):
                res[f"qa{c}"][sel] = tm[0][c].predict(x)
                res[f"qb{c}"][sel] = tm[1][c].predict(x)
        raw = pd.DataFrame(
            {"T": [m[0] for m in meta], "sym": [m[1] for m in meta],
             "k": [m[2] for m in meta], **res})
        g = raw[raw.k.isin(R2)].copy()
        g["rung"] = g.k.map(R2_IDX).astype(int)
        g["size"], g["tp"] = rules(g)
        tab = g[["T", "sym", "rung", "size", "tp"]].reset_index(drop=True)
        parts.append(tab)
        del F, meta, J
        if sym != "BTCUSDT":
            del A
    tab = pd.concat(parts, ignore_index=True).sort_values(["T", "sym", "rung"]).reset_index(drop=True)
    del models
    return tab


def main():
    t0 = time.time()
    v294 = L("v294_agentens", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    v293.RUNGS = U
    v293.END = END
    assert str(v293.START) == "2020-08-01 00:00:00+00:00", v293.START
    print("START", v293.START, "END", v293.END, flush=True)

    fills = pd.read_parquet(EXT / "fills_U_ext.parquet")
    t_exit = pd.to_datetime(fills["t_exit"], utc=True)
    X7 = fills[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(fills[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (fills["j"] % 2).to_numpy()
    print("fills", fills.shape, flush=True)
    cache = (X7, Y, y1, half, t_exit)

    btc = v293.Asset("BTCUSDT")
    seed_tabs = {}
    for S in SEEDS:
        tab = build_seed_table(S, v293, btc, cache)
        tab.to_parquet(HERE / f"seed_table_s{S}_s0.parquet")
        seed_tabs[S] = tab
        print(f"seed {S} rows {len(tab)} size_counts {dict(tab['size'].value_counts())} "
              f"tp_counts {dict(tab['tp'].value_counts())} {time.time()-t0:.0f}s", flush=True)
    del btc
    del X7, Y, y1

    # S=0 reproduction gate vs oc_rlbear V0 (hence v376 hidden ref)
    v0 = pd.read_parquet(V0_CHECK)
    v0["T"] = pd.to_datetime(v0["T"], utc=True)
    s0 = seed_tabs[0].copy()
    s0["T"] = pd.to_datetime(s0["T"], utc=True)
    mg = v0.merge(s0, on=["T", "sym", "rung"], how="inner", suffixes=("_v0", ""))
    size_match = float((mg["size"] == mg["size_v0"]).mean()) if len(mg) else float("nan")
    tp_match = float((mg["tp"] == mg["tp_v0"]).mean()) if len(mg) else float("nan")
    print(f"S0 vs V0 overlap {len(mg)} size_match {size_match} tp_match {tp_match}", flush=True)

    # key alignment across seeds, then positional majority vote
    keys = [t[["T", "sym", "rung"]] for t in seed_tabs.values()]
    base_keys = keys[0].reset_index(drop=True)
    aligned = all(k.reset_index(drop=True).equals(base_keys) for k in keys)
    print("keys aligned across seeds:", aligned, flush=True)
    if aligned:
        size_stack = np.column_stack([seed_tabs[S]["size"].to_numpy() for S in SEEDS])
        tp_stack = np.column_stack([seed_tabs[S]["tp"].to_numpy() for S in SEEDS])
        ens = base_keys.copy()
        ens["size"] = majority_vote(size_stack)
        ens["tp"] = majority_vote(tp_stack)
    else:  # fallback: outer merge on keys (should not happen)
        ens = base_keys.copy()
        msz = base_keys.copy()
        mtp = base_keys.copy()
        for S in SEEDS:
            t = seed_tabs[S]
            msz = msz.merge(t[["T", "sym", "rung", "size"]].rename(columns={"size": f"sz{S}"}),
                            on=["T", "sym", "rung"], how="outer")
            mtp = mtp.merge(t[["T", "sym", "rung", "tp"]].rename(columns={"tp": f"tp{S}"}),
                            on=["T", "sym", "rung"], how="outer")
        ens["size"] = majority_vote(msz[[f"sz{S}" for S in SEEDS]].to_numpy())
        ens["tp"] = majority_vote(mtp[[f"tp{S}" for S in SEEDS]].to_numpy())
    ens = ens.sort_values(["T", "sym", "rung"]).reset_index(drop=True)
    ens.to_parquet(HERE / "ens_table_s0.parquet")
    print("saved ens", ens.shape, dict(ens["size"].value_counts()),
          dict(ens["tp"].value_counts()), flush=True)

    # agreement of each seed vs S0
    agree = {}
    for S in SEEDS[1:]:
        agree[str(S)] = dict(
            size_agree=round(float((seed_tabs[S]["size"].to_numpy() == seed_tabs[0]["size"].to_numpy()).mean()), 4),
            tp_agree=round(float((seed_tabs[S]["tp"].to_numpy() == seed_tabs[0]["tp"].to_numpy()).mean()), 4))
    agree["ENS"] = dict(
        size_agree=round(float((ens["size"].to_numpy() == seed_tabs[0]["size"].to_numpy()).mean()), 4),
        tp_agree=round(float((ens["tp"].to_numpy() == seed_tabs[0]["tp"].to_numpy()).mean()), 4))
    info = dict(
        fills_rows=int(len(fills)), seeds=list(SEEDS),
        seed_rows={str(S): int(len(seed_tabs[S])) for S in SEEDS},
        ens_rows=int(len(ens)), keys_aligned=bool(aligned),
        s0_vs_v0=dict(overlap_rows=int(len(mg)), size_match=size_match, tp_match=tp_match),
        agreement_vs_s0=agree,
        seed_size_counts={str(S): {str(k): int(v) for k, v in seed_tabs[S]["size"].value_counts().items()} for S in SEEDS},
        seed_tp_counts={str(S): {str(k): int(v) for k, v in seed_tabs[S]["tp"].value_counts().items()} for S in SEEDS},
        ens_size_counts={str(k): int(v) for k, v in ens["size"].value_counts().items()},
        ens_tp_counts={str(k): int(v) for k, v in ens["tp"].value_counts().items()},
        runtime_s=round(time.time() - t0),
    )
    (HERE / "build_info.json").write_text(json.dumps(info, indent=1, default=str))
    print(json.dumps(info, indent=1, default=str))
    if not (size_match >= 0.999 and tp_match >= 0.999):
        print("S0 REPRODUCTION FAILED: stopping before screening", flush=True)
    else:
        print("S0 reproduction OK", flush=True)


if __name__ == "__main__":
    main()
