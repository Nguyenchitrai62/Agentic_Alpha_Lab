"""v167 blind audit Part A replication.

Blind rule: does NOT read research/.../v167/*, nor v167_result.json,
nor artifacts/kaggle/v167/kernel/*, nor output log_*.json/summary.json.
Only inputs: artifacts/kaggle/v167/output/v167_out/pred_<anchor>.parquet
plus the audited leader modules (imported, not copied):
  v144/v144_deploy_v3.py (books_v142, simulate, v129, v125, ext=v115.v114.v113)
  v151/v151_info_ensemble.py (books_with_options)
  v154/v154_ensemble_coinbase.py (books_coinbase)

Steps (from OPENCODE_V167_AUDIT.md):
A1: file checks; A2: p_k = gru_p_k + IC vs v103 panel; A3: vol forecast;
A4: member E; A5: primary (A+B+D+E)/4 + secondary E, simulate rows.
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[5]
OUT = HERE / "replication.json"
PRED_DIR = ROOT / "artifacts/kaggle/v167/output/v167_out"


def _load(name, rel):
    base = ROOT / "research/parallel/rounds/parallel-20260906-r2"
    spec = importlib.util.spec_from_file_location(name, base / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def spearman(a, b):
    m = pd.DataFrame({"a": np.asarray(a, dtype=float), "b": np.asarray(b, dtype=float)}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def main():
    # ---- A1: file checks ----
    anchors = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    pred_parts = []
    checks = []
    for a in anchors:
        f = PRED_DIR / f"pred_{a}.parquet"
        assert f.exists(), f"missing {f}"
        df = pd.read_parquet(f)
        df["t"] = pd.to_datetime(df["t"], utc=True)
        a0 = pd.Timestamp(a, tz="UTC")
        e0 = a0 + pd.Timedelta(days=365)
        n_dup = int(df.duplicated(["t", "sym"]).sum())
        n_nan = int(df.isna().sum().sum())
        in_range = bool(((df["t"] >= a0) & (df["t"] < e0)).all())
        exp = 2190 * 5
        checks.append(dict(anchor=a, rows=int(len(df)), expect=int(exp),
                           n_t=int(df["t"].nunique()), n_sym=int(df["sym"].nunique()),
                           syms=sorted(df["sym"].unique().tolist()),
                           t_min=str(df["t"].min()), t_max=str(df["t"].max()),
                           in_range=in_range, dup=int(n_dup), nan=int(n_nan)))
        assert len(df) == exp, (a, len(df))
        assert n_dup == 0, (a, n_dup)
        assert n_nan == 0, (a, n_nan)
        assert in_range, a
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert set(df.columns) >= {"t", "sym", "gru_p6", "gru_p18", "gru_p42", "gru_p84"}, df.columns.tolist()
        pred_parts.append(df)
    pred_all = pd.concat(pred_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    for k in ("p6", "p18", "p42", "p84"):
        pred_all[k] = pred_all[f"gru_{k}"].astype(float)
    print("A1 checks passed", [(c["anchor"], c["rows"]) for c in checks], flush=True)

    # ---- leader modules ----
    v144 = _load("v144_audit167", "v144/v144_deploy_v3.py")
    v151 = _load("v151_audit167", "v151/v151_info_ensemble.py")
    v154m = _load("v154_audit167", "v154/v154_ensemble_coinbase.py")
    ext = v144.v115.v114.v113
    v129, v125 = v144.v129, v144.v125
    ANCHORS = tuple(ext.v92.ANCHORS)
    EMBARGO_BARS = int(ext.v92.EMBARGO_BARS)
    assert list(ANCHORS) == anchors, ANCHORS

    # ---- A/B/D books (each trains internally; heavy) ----
    p103, A = v144.books_v142()
    print(f"A done {A.shape} {A.index.min()} -> {A.index.max()}", flush=True)
    _, B = v151.books_with_options()
    print(f"B done {B.shape}", flush=True)
    _, D = v154m.books_coinbase()
    print(f"D done {D.shape}", flush=True)
    p103["t"] = pd.to_datetime(p103["t"], utc=True)
    assert "y6" in p103.columns and "y" in p103.columns, list(p103.columns[:50])

    # ---- A2: IC vs v103 panel ----
    merged = p103[["t", "sym", "y6", "y"]].merge(
        pred_all[["t", "sym", "gru_p6", "gru_p18", "gru_p42", "gru_p84",
                  "p6", "p18", "p42", "p84"]],
        on=["t", "sym"], how="inner")
    ic_table = []
    for a in anchors:
        a0 = pd.Timestamp(a, tz="UTC")
        e0 = a0 + pd.Timedelta(days=365)
        g = merged[(merged["t"] >= a0) & (merged["t"] < e0)]
        row = dict(anchor=a, n=int(len(g)))
        row["ic_gru_p6_vs_y6"] = round(spearman(g["gru_p6"], g["y6"]), 4)
        row["ic_gru_p42_vs_y"] = round(spearman(g["gru_p42"], g["y"]), 4)
        row["ic_p6_vs_y6"] = round(spearman(g["p6"], g["y6"]), 4)
        row["ic_p42_vs_y"] = round(spearman(g["p42"], g["y"]), 4)
        ic_table.append(row)
        print(a, {k: v for k, v in row.items() if k.startswith("ic_")}, flush=True)

    # ---- A3: vol forecast ----
    f103 = [c for c in p103.columns if c not in ("t", "open", "sym", "bar") and not c.startswith("y")]
    pv, vol_q = v129.vol_predict(p103, f103, ANCHORS, EMBARGO_BARS)
    pv["t"] = pd.to_datetime(pv["t"], utc=True)
    print("vol quality", vol_q, flush=True)
    p103v = p103.merge(pv[["t", "sym", "pvol"]], on=["t", "sym"], how="left")
    n_replaced = int(p103v["pvol"].notna().sum())
    p103v["vol42"] = p103v["pvol"].fillna(p103v["vol42"])
    base = p103v[["t", "sym", "rib", "vol42"]].merge(
        pred_all[["t", "sym", "p6", "p18", "p42", "p84"]], on=["t", "sym"], how="inner")
    assert len(base) == len(pred_all), (len(base), len(pred_all))

    # ---- A4: member E ----
    def frame(pred_series):
        fr = base[["t", "sym", "rib", "vol42"]].copy()
        fr["pred"] = np.asarray(pred_series, dtype=float)
        return fr.dropna(subset=["pred"])

    f_lo = frame(base["p42"])
    f_94 = frame((base["p18"] + base["p42"] + base["p84"]) / 3.0)
    f_103 = frame((base["p6"] + base["p18"]) / 2.0)
    W_lo = v125.phased(v125.raw_lo(f_lo), range(6))
    W_94 = v125.phased(v125.raw_ls(f_94), range(6))
    W_103 = v125.phased(v125.raw_ls(f_103), range(6))
    idxE = W_lo.index.union(W_94.index).union(W_103.index).sort_values()
    s_lo = ext.v92.vol_target_scale(p103, W_lo).reindex(idxE).fillna(1.0)
    s_94 = ext.v94.vol_target_scale(p103, W_94).reindex(idxE).fillna(1.0)
    s_103 = ext.v94.vol_target_scale(p103, W_103).reindex(idxE).fillna(1.0)
    E = (0.25 * W_lo.reindex(idxE).fillna(0.0).mul(s_lo, axis=0)
         + 0.25 * W_94.reindex(idxE).fillna(0.0).mul(s_94, axis=0)
         + 0.5 * W_103.reindex(idxE).fillna(0.0).mul(s_103, axis=0))
    E = E.reindex(sorted(E.columns), axis=1)
    print(f"E done {E.shape} {E.index.min()} -> {E.index.max()}", flush=True)

    # ---- A5: primary + secondary, simulate ----
    idxU = A.index.union(B.index).union(D.index).union(E.index).sort_values()
    primary = (A.reindex(idxU).fillna(0.0) + B.reindex(idxU).fillna(0.0)
               + D.reindex(idxU).fillna(0.0) + E.reindex(idxU).fillna(0.0)) / 4.0
    secondary = E.reindex(sorted(E.columns), axis=1)
    print(f"union {len(idxU)} A={len(A)} B={len(B)} D={len(D)} E={len(E)}", flush=True)
    sim_primary = v144.simulate(p103, primary)
    sim_secondary = v144.simulate(p103, secondary)

    def slim(sim):
        out = {}
        for k, r in sim.items():
            out[k] = dict(monthly_pct=r["monthly_pct"], full_path_dd=r["full_path_dd"],
                          yearly=[dict(anchor=y["anchor"], net_pct=y["net_pct"],
                                       max_drawdown_percent=y["max_drawdown_percent"]) for y in r["yearly"]])
        return out

    result = {
        "version": "v167_audit_replication_partA",
        "blind": "did_not_open_research_v167_until_this_file_saved",
        "anchors": anchors,
        "file_checks": checks,
        "ic_table": ic_table,
        "merge_rows": int(len(merged)),
        "vol": {"features_n": len(f103), "embargo_bars": EMBARGO_BARS,
                "n_pvol_replaced": n_replaced, "quality": vol_q},
        "member_E": {"shape": list(E.shape), "index_min": str(E.index.min()),
                     "index_max": str(E.index.max()), "columns": list(E.columns)},
        "union_bars": int(len(idxU)),
        "primary": slim(sim_primary),
        "secondary_E": slim(sim_secondary),
        "meta": {
            "p_k": "gru_p_k single architecture for k in p6/p18/p42/p84",
            "vol": "v129.vol_predict(p103, f103 minus y*, ANCHORS, EMBARGO_BARS); vol42=pvol where available",
            "E": "0.25*LO(p42)+0.25*LS94(mean p18/p42/p84)+0.5*LS103(mean p6/p18); raw_lo/raw_ls+phased(range6); scales ext.v92 (LO) / ext.v94 (LS) on p103 panel, NaN->1",
            "books": "primary=(A+B+D+E)/4 union missing->0; secondary=E; simulate=v144 rows 0.15 ungoverned / 0.20 / 0.25 governed",
            "A": "v144.books_v142", "B": "v151.books_with_options", "D": "v154.books_coinbase",
            "costs": "v144 engine: fee 0.0002/fill, 10bps limit on 1m, gov 0.20/0.10, carry+funding as v104, capital indexed 100",
        },
    }
    OUT.write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({"primary": {k: v["monthly_pct"] for k, v in slim(sim_primary).items()},
                      "secondary": {k: v["monthly_pct"] for k, v in slim(sim_secondary).items()}}, indent=1))


if __name__ == "__main__":
    main()
