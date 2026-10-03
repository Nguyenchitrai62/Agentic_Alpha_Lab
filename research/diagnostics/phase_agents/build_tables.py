"""Dev-only diagnostic (not a registered version): the R2 dip-agent decision table (size S1 + take-profit X4, fit "U", rungs 2.5/3.0/3.5/4.0/5.0)
rebuilt on 4h grids shifted by s = 0..3 h, so the phase-offset replay can keep the agents ON off-phase.

Same construction as v306_gene_tables.py (fit "U" only) + r2_cache.py:
  - training: pooled fills of the 5 majors + 30 U2020 alts on the STANDARD grid (v293.fills_of, rungs 2.0..5.0), per anchor
    (2021..2025-09-24) only fills that exited before anchor - 7 days; HGB v296.hgb(10 jj + h [+ 3 c]) cross-fitted on j % 2 halves
    (identical data, order and seeds -> identical models; nothing is refitted differently per phase);
  - state at the open of every SHIFTED holding bar T (= START + s h + 4h j): sp30 / btc sp30 / dd24 at the close of minute 0 (kk = 240 j),
    volreg / trend / sigma_4h from the shifted grid's own 4h opens (sigma shifted one bar, as v293), hour = T.hour; model = anchor <= T;
  - rules (R2 genome): size 1.5 if both halves > 2 mu, 0.5 if both < 0 (and not up), else 1; TP 0.5 / 1.5 sigma if both halves pick the same
    non-base action with gain > 0.001, else 1.0.
Minute data is loaded only up to 2025-09-25 (fills exiting after 2025-09-17 are never used by any model; bars are built only up to the last
holding bar the dev replay touches).
Check: s = 0 reproduces the raw U predictions of v306_gene_tables.parquet and the deployed v321_r2_table_m0.parquet.
Output: tables/r2_table_s{s}.parquet (T, sym, rung, size, tp), fills_U.parquet (cache), build_check.json
  python research/diagnostics/phase_agents/build_tables.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE = Path(__file__).parent
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
END = pd.Timestamp("2025-09-25", tz="UTC")
TMAX = pd.Timestamp("2025-09-24 08:00", tz="UTC")  # last holding bar of the dev engine index (std idx <= DEV1 + 4h) is DEV1 + 8h (+ s)
QC = ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def rules(df):
    """v306._tables with the R2 genome (up_th 2, up_mult 1.5, dn_th 0, dn_mult 0.5, tp_margin 0.001)."""
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


def main():
    v294 = L("v294_pa", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_pa", RD / "v296/v296_joint_dip_agent.py")
    eu = L("v221_pa", RD / "v221/v221_grid_hysteresis.py").eu
    v293.RUNGS = U
    v293.END = END
    START0 = v293.START
    fp = HERE / "fills_U.parquet"
    if fp.exists():
        allf = pd.read_parquet(fp)
    else:
        btc = v293.Asset("BTCUSDT")
        parts = []
        for s in v293.MAJORS + v294.universe():
            A = btc if s == "BTCUSDT" else v293.Asset(s)
            d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
            if len(d):
                parts.append(d.assign(sym=s))
            print("fills", s, len(d), flush=True)
            del A
        del btc
        allf = pd.concat(parts, ignore_index=True)
        allf.to_parquet(fp)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    t_exit = pd.to_datetime(allf["t_exit"], utc=True)
    models = []
    for jj, a0 in enumerate(ANCHORS):
        keep = np.asarray(t_exit < a0 - v293.EMBARGO)
        sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(3)] for h in (0, 1)]
        models.append((float(y1[keep].mean()), sm, tm))
        print("fit U anchor", jj, "rows", int(keep.sum()), "mu", round(models[-1][0], 5), flush=True)
    (HERE / "tables").mkdir(exist_ok=True)
    check = {}
    for sft in (0, 1, 2, 3):
        sh = pd.Timedelta(hours=sft)
        v293.START = START0 + sh
        assets = {s: v293.Asset(s) for s in v293.MAJORS}
        btc = assets["BTCUSDT"]
        meta, feats = [], []
        for s, A in assets.items():
            for j, T in enumerate(A.t0):
                if T < ANCHORS[0] or T > TMAX + sh or not np.isfinite(A.sig[j]):
                    continue
                jj = max(q for q, a0 in enumerate(ANCHORS) if T >= a0)
                kk = j * 240
                base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                        np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
                for k in U:
                    meta.append((T, s, k, jj))
                    feats.append(base[:1] + [k] + base[2:])
        del assets, btc
        F = np.array(feats, float)
        J = np.array([m_[3] for m_ in meta])
        res = {c: np.full(len(meta), np.nan) for c in QC}
        for jj, (mu, sm, tm) in enumerate(models):
            sel = J == jj
            if not sel.any():
                continue
            x = F[sel]
            res["pa"][sel], res["pb"][sel] = sm[0].predict(x), sm[1].predict(x)
            res["mu"][sel] = mu
            for c in range(3):
                res[f"qa{c}"][sel] = tm[0][c].predict(x)
                res[f"qb{c}"][sel] = tm[1][c].predict(x)
        raw = pd.DataFrame({"T": [m_[0] for m_ in meta], "sym": [m_[1] for m_ in meta], "k": [m_[2] for m_ in meta], **res})
        raw.to_parquet(HERE / "tables" / f"raw_U_s{sft}.parquet")
        g = raw[raw.k.isin(R2)].copy()
        g["rung"] = g.k.map({k: r for r, k in enumerate(R2)}).astype(int)
        g["size"], g["tp"] = rules(g)
        tab = g[["T", "sym", "rung", "size", "tp"]].reset_index(drop=True)
        tab.to_parquet(HERE / "tables" / f"r2_table_s{sft}.parquet")
        hours = sorted(set(tab["T"].dt.hour))
        st = dict(rows=len(tab), T_min=str(tab["T"].min()), T_max=str(tab["T"].max()), hours=hours,
                  size_counts={str(k): int(v) for k, v in tab["size"].value_counts().items()},
                  tp_counts={str(k): int(v) for k, v in tab["tp"].value_counts().items()},
                  size_by_anchor={str(jj): {str(k): int(v) for k, v in g[J[g.index] == jj]["size"].value_counts().items()} for jj in range(5)})
        if sft == 0:
            ref_raw = pd.read_parquet(eu.er.CACHE / "v306_gene_tables.parquet")
            ref_raw = ref_raw[ref_raw.fit == "U"]
            mg = ref_raw.merge(raw, on=["T", "sym", "k"], suffixes=("_ref", ""))
            st["raw_rows_mine"], st["raw_rows_ref_overlap"] = len(raw), len(mg)
            st["raw_max_abs_diff"] = {c: float(np.nanmax(np.abs(mg[c] - mg[c + "_ref"]))) for c in QC}
            ref = pd.read_parquet(ROOT / "artifacts/research/engine_real/v321_r2_table_m0.parquet")
            ref = ref[ref["T"] <= tab["T"].max()]
            m2 = ref.merge(tab, on=["T", "sym", "rung"], how="left", suffixes=("_ref", ""))
            st["deployed_rows_in_range"] = len(ref)
            st["deployed_rows_missing_in_mine"] = int(m2["size"].isna().sum())
            st["deployed_missing_rows_are_default"] = bool(((m2[m2["size"].isna()][["size_ref", "tp_ref"]] == 1.0).all().all()))
            m2 = m2.dropna(subset=["size"])
            st["size_match"] = float((m2["size"] == m2["size_ref"]).mean())
            st["tp_match"] = float((m2["tp"] == m2["tp_ref"]).mean())
            st["mine_not_in_deployed"] = int(len(tab.merge(ref, on=["T", "sym", "rung"], how="left", indicator=True).query("_merge == 'left_only'")))
        check[f"s{sft}"] = st
        print("shift", sft, json.dumps(st), flush=True)
    (HERE / "build_check.json").write_text(json.dumps(check, indent=1))


if __name__ == "__main__":
    main()
