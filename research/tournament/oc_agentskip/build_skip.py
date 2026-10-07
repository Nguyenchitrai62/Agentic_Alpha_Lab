"""oc_agentskip: base (V0 S1 path) + SKIP-gated R2 tables, phase s=0 only.

V0 code path copied from research/tournament/oc_rlbear/build_v0_v2.py
(originals never edited/imported for writing): same U/R2/anchors/seeds/
clip/mu/embargo/rules; training fills from research/tournament/ext/
fills_U_ext.parquet. SKIP (idea #57, ONE fixed variant): size 0 when BOTH
halves predict y1.0 < -0.002, else S1 unchanged; TP rule unchanged.

MEDIUM slot: single process, one majors 1m coin at a time.
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

U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
R2_IDX = {k: r for r, k in enumerate(R2)}
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
T_MIN = ANCHORS[0]
T_MAX = pd.Timestamp("2026-09-23 12:00", tz="UTC")  # = v376 hidden s0 max T
END = pd.Timestamp("2026-09-24", tz="UTC")
QC = ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")
SKIP_TH = -0.002  # fixed upfront (~round-trip cost scale)


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


def apply_skip(pa, pb, size_base, thresh=SKIP_TH):
    """SKIP gate: size 0 when BOTH halves predict y1.0 < thresh, else base.

    Uses ONLY the bar-open predictions pa/pb (no future / fill-minute data).
    """
    pa = np.asarray(pa, dtype=float)
    pb = np.asarray(pb, dtype=float)
    base = np.asarray(size_base, dtype=float)
    skip = (pa < thresh) & (pb < thresh) & np.isfinite(pa) & np.isfinite(pb)
    out = base.copy()
    out[skip] = 0.0
    return out


def main():
    t0 = time.time()
    v294 = L("v294_agentskip", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    v293.RUNGS = U
    v293.END = END
    assert str(v293.START) == "2020-08-01 00:00:00+00:00", v293.START
    print("START", v293.START, "END", v293.END, flush=True)

    # ---- training fills (full universe, as R2) ----
    fills = pd.read_parquet(EXT / "fills_U_ext.parquet")
    t_exit = pd.to_datetime(fills["t_exit"], utc=True)
    X7 = fills[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(fills[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (fills["j"] % 2).to_numpy()
    print("fills", fills.shape, "t_fill", fills["t_fill"].min(), fills["t_fill"].max(), flush=True)

    # ---- fits per anchor (V0 path: 7 feats) ----
    models = []
    for jj, a0 in enumerate(ANCHORS):
        keep = np.asarray(t_exit < a0 - v293.EMBARGO)
        mu = float(y1[keep].mean())
        sm = [hgb(10 * jj + h).fit(X7[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[hgb(10 * jj + h + 3 * c).fit(X7[keep & (half == h)], Y[keep & (half == h), c])
               for c in range(3)] for h in (0, 1)]
        models.append((mu, sm, tm))
        print(f"anchor {jj} {a0.date()} rows {int(keep.sum())} mu {mu:.5f} {time.time()-t0:.0f}s",
              flush=True)
    del X7, Y, y1

    # ---- s=0 tables, one coin at a time ----
    base_parts, skip_parts = [], []
    btc = v293.Asset("BTCUSDT")
    for sym in v293.MAJORS:
        A = btc if sym == "BTCUSDT" else v293.Asset(sym)
        meta, F7 = [], []
        for j, T in enumerate(A.t0):
            if T < T_MIN or T > T_MAX or not np.isfinite(A.sig[j]):
                continue
            jj = max(q for q, a0 in enumerate(ANCHORS) if T >= a0)
            kk = j * 240
            dd = np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan
            row7 = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk), dd, float(T.hour)]
            for k in U:
                meta.append((T, sym, k, jj))
                F7.append(row7[:1] + [k] + row7[2:])
        F7 = np.array(F7, float)
        J = np.array([m[3] for m in meta])
        res = {c: np.full(len(meta), np.nan) for c in QC}
        for jj2, (mu, sm, tm) in enumerate(models):
            sel = J == jj2
            if not sel.any():
                continue
            x = F7[sel]
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
        size_base, tp = rules(g)
        size_skip = apply_skip(g["pa"].to_numpy(), g["pb"].to_numpy(), size_base)
        g["tp"] = tp
        g["size_base"] = size_base
        g["size"] = size_skip
        base_parts.append(g[["T", "sym", "rung", "size_base", "tp"]].rename(
            columns={"size_base": "size"}).reset_index(drop=True))
        skip_parts.append(g[["T", "sym", "rung", "size", "tp"]].reset_index(drop=True))
        print(f"table {sym} rows {len(g)} skip_frac {float(np.mean(size_skip == 0.0)):.4f} "
              f"{time.time()-t0:.0f}s", flush=True)
        del F7, meta, J
        if sym != "BTCUSDT":
            del A
    base = pd.concat(base_parts, ignore_index=True).sort_values(["T", "sym", "rung"]).reset_index(drop=True)
    skip = pd.concat(skip_parts, ignore_index=True).sort_values(["T", "sym", "rung"]).reset_index(drop=True)
    base.to_parquet(HERE / "base_table_s0.parquet")
    skip.to_parquet(HERE / "skip_table_s0.parquet")
    print("saved", base.shape, skip.shape, flush=True)

    # ---- V0 reproduction check vs v376 hidden s0 ----
    ref = pd.read_parquet(REF_S0)
    ref["T"] = pd.to_datetime(ref["T"], utc=True)
    base["T"] = pd.to_datetime(base["T"], utc=True)
    skip["T"] = pd.to_datetime(skip["T"], utc=True)
    mg = ref.merge(base, on=["T", "sym", "rung"], how="inner", suffixes=("_ref", ""))
    size_match = float((mg["size"] == mg["size_ref"]).mean()) if len(mg) else float("nan")
    tp_match = float((mg["tp"] == mg["tp_ref"]).mean()) if len(mg) else float("nan")
    info = dict(
        fills_rows=int(len(fills)), ref_rows=int(len(ref)),
        base_rows=int(len(base)), skip_rows=int(len(skip)),
        overlap_rows=int(len(mg)),
        ref_only=int(len(ref.merge(base, on=["T", "sym", "rung"], how="left",
                                   indicator=True).query("_merge=='left_only'"))),
        base_only=int(len(base.merge(ref, on=["T", "sym", "rung"], how="left",
                                     indicator=True).query("_merge=='left_only'"))),
        size_match=size_match, tp_match=tp_match,
        skip_thresh=SKIP_TH,
        base_size_counts={str(k): int(v) for k, v in base["size"].value_counts().items()},
        base_tp_counts={str(k): int(v) for k, v in base["tp"].value_counts().items()},
        skip_size_counts={str(k): int(v) for k, v in skip["size"].value_counts().items()},
        skip_tp_counts={str(k): int(v) for k, v in skip["tp"].value_counts().items()},
        skip_frac=float((skip["size"] == 0.0).mean()),
        mus=[m[0] for m in models],
        runtime_s=round(time.time() - t0),
    )
    (HERE / "build_info.json").write_text(json.dumps(info, indent=1, default=str))
    print(json.dumps(info, indent=1, default=str))
    if not (size_match >= 0.999 and tp_match >= 0.999):
        print("V0 REPRODUCTION FAILED: stopping before screening", flush=True)
    else:
        print("V0 reproduction OK", flush=True)


if __name__ == "__main__":
    main()
