"""Blind v168 audit replication (Part A).

Does NOT open research/.../v168/* until this file + replication.json are saved.
Base (per OPENCODE_V168_AUDIT.md): v154 replication (members A = v144 books,
B = + v150 options features, D = + v111 Coinbase premium features;
import the leader modules, do not copy logic).

A: in all three members replace ONLY the v103 model (v103.train_predict),
per anchor, keeping the audited v103 cutoff (anchor - 4h*v103.EMBARGO),
per-horizon row filter (t + 4h*(h+1) < cutoff, y{h} not NaN) and h in v103.HS:
for each h and q in (0.25, 0.5, 0.75) fit
HistGradientBoostingRegressor(loss="quantile", quantile=q, max_depth=4,
learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
random_state=0) on the training rows. Test rows = [anchor, anchor+365d).
m = mean over h of q=0.5 test predictions; s = mean over h of
max(q75-q25, 1e-3). On training rows common to both horizons:
c_tr = |mean_h median| / mean_h spread (same floor), c_ref = median(c_tr).
k = clip((|m|/s)/c_ref, 0.5, 1.5); pred = m*k. v92/v94 books unchanged.
Books = (A+B+D)/3, v144 simulate rows (0.15 ungoverned, 0.20/0.25 governed).
ALSO report (diagnostic, not in v168) the same with k=1 (median only),
plus Spearman IC per anchor of m vs y6 and of the audited v103 regressor
prediction vs y6.

Blind choices (frozen before running):
- c_ref from training rows ONLY (common rows: t<cutoff, y6+y18 not NaN,
  t+4h*(maxH+1)<cutoff; predictions on those rows from the fitted quantile
  models; median over rows). No test row enters c_ref.
- Common-row definition = intersection of the two per-horizon training
  filters (strictest time filter maxH+1).
- ICs on test rows with y6 not NaN (spearman).
- Median-only diagnostic reuses the same quantile fits (no refit): second
  books_v142 pass per member returns cached median OOS; v92/v94 OOS also
  cached so the diagnostic costs only the vol refit inside books_v142.
- Ensemble union index missing->0, p103 grid from the A leg, v144.simulate.
"""
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[5]
os.chdir(ROOT)

OUT = HERE / "replication.json"
QS = (0.25, 0.5, 0.75)
QPARAMS = dict(loss="quantile", max_depth=4, learning_rate=0.03, max_iter=400,
               min_samples_leaf=300, l2_regularization=1.0, random_state=0)
ROWS_WANT = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")

MODE = {"v103": "quant"}  # "quant" or "median"
CACHE = {}  # (tag, anchor) -> dict with te_quant/te_median/te_base/info
CACHE92 = {}
CACHE94 = {}


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
    try:
        return float(spearmanr(m["a"], m["b"]).statistic)
    except Exception:
        return float("nan")


def quantile_core(panel, anchor, feats, HS, EMBARGO, orig_fn):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * int(EMBARGO))
    HS = tuple(int(h) for h in HS)
    maxH = max(HS)
    tr_sets = {}
    models = {}
    train_rows = {}
    for h in HS:
        yh = f"y{h}"
        tr = panel[(panel["t"] < cutoff) & panel[yh].notna()]
        tr = tr[tr["t"] + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        tr_sets[h] = tr
        train_rows[h] = int(len(tr))
        for q in QS:
            m = HistGradientBoostingRegressor(quantile=q, **QPARAMS)
            m.fit(tr[feats], tr[yh])
            models[(h, q)] = m
    te = panel[(panel["t"] >= a) & (panel["t"] < end)].copy()
    meds, spreads = [], []
    for h in HS:
        p25 = models[(h, 0.25)].predict(te[feats])
        p50 = models[(h, 0.5)].predict(te[feats])
        p75 = models[(h, 0.75)].predict(te[feats])
        meds.append(np.asarray(p50, dtype=float))
        spreads.append(np.maximum(np.asarray(p75, dtype=float) - np.asarray(p25, dtype=float), 1e-3))
    m_test = np.mean(np.column_stack(meds), axis=1)
    s_test = np.mean(np.column_stack(spreads), axis=1)
    # common training rows (intersection, strictest time filter)
    ycols = [f"y{h}" for h in HS]
    mask = (panel["t"] < cutoff)
    for yc in ycols:
        mask = mask & panel[yc].notna()
    mask = mask & (panel["t"] + pd.Timedelta(hours=4 * (maxH + 1)) < cutoff)
    common = panel[mask].copy()
    meds_tr, spreads_tr = [], []
    for h in HS:
        p25 = models[(h, 0.25)].predict(common[feats])
        p50 = models[(h, 0.5)].predict(common[feats])
        p75 = models[(h, 0.75)].predict(common[feats])
        meds_tr.append(np.asarray(p50, dtype=float))
        spreads_tr.append(np.maximum(np.asarray(p75, dtype=float) - np.asarray(p25, dtype=float), 1e-3))
    m_tr = np.mean(np.column_stack(meds_tr), axis=1)
    s_tr = np.mean(np.column_stack(spreads_tr), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        c_tr = np.abs(m_tr) / s_tr
    c_tr = c_tr[np.isfinite(c_tr)]
    if len(c_tr) == 0:
        c_ref = 1.0
    else:
        c_ref = float(np.median(c_tr))
        if not np.isfinite(c_ref) or c_ref <= 1e-12:
            c_ref = 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (np.abs(m_test) / s_test) / c_ref
    k_test = np.clip(ratio, 0.5, 1.5)
    k_test = np.where(np.isfinite(k_test), k_test, 1.0)
    pred_q = m_test * k_test
    te_q = te.copy()
    te_q["pred"] = pred_q
    te_q["m"] = m_test
    te_q["s"] = s_test
    te_q["k"] = k_test
    te_m = te.copy()
    te_m["pred"] = m_test
    te_m["m"] = m_test
    te_m["s"] = s_test
    te_m["k"] = np.ones_like(k_test)
    # audited baseline for IC diagnostic
    te_b, rows_b = orig_fn(panel, anchor, feats)
    ic_m = spearman(te_m["m"], te_m["y6"])
    ic_b = spearman(te_b["pred"], te_b["y6"])
    info = dict(train_rows={str(h): train_rows[h] for h in HS},
                n_test=int(len(te)), n_common=int(len(common)),
                c_ref=float(c_ref),
                mean_k=float(np.mean(k_test)) if len(k_test) else float("nan"),
                share_k_low=float(np.mean(k_test <= 0.5001)) if len(k_test) else float("nan"),
                share_k_high=float(np.mean(k_test >= 1.4999)) if len(k_test) else float("nan"),
                ic_m_vs_y6=round(float(ic_m), 4) if np.isfinite(ic_m) else None,
                ic_base_vs_y6=round(float(ic_b), 4) if np.isfinite(ic_b) else None,
                n_test_with_y6=int(te["y6"].notna().sum()),
                baseline_train_rows=rows_b)
    return te_q, te_m, te_b, info


def make_v103_wrapper(orig_fn, tag, HS, EMBARGO):
    def wrapper(panel, anchor, feats):
        key = (tag, str(anchor))
        if MODE["v103"] == "median" and key in CACHE:
            c = CACHE[key]
            return c["te_m"].copy(), c["rows"]
        te_q, te_m, te_b, info = quantile_core(panel, anchor, list(feats), HS, EMBARGO, orig_fn)
        rows = {int(h): info["train_rows"][str(h)] for h in info["train_rows"]}
        CACHE[key] = {"te_q": te_q, "te_m": te_m, "te_b": te_b, "info": info, "rows": rows}
        print(f"{tag} v103-quant {anchor} rows={rows} c_ref={info['c_ref']:.4f} "
              f"ic_m={info['ic_m_vs_y6']} ic_base={info['ic_base_vs_y6']}", flush=True)
        if MODE["v103"] == "median":
            return te_m.copy(), rows
        return te_q.copy(), rows
    return wrapper


def make_v92_wrapper(orig_fn, tag):
    def wrapper(panel, anchor):
        key = (tag, "v92", str(anchor))
        if MODE["v103"] == "median" and key in CACHE92:
            te, ntr = CACHE92[key]
            return te.copy(), ntr
        te, ntr = orig_fn(panel, anchor)
        CACHE92[key] = (te.copy(), int(ntr))
        return te, ntr
    return wrapper


def make_v94_wrapper(orig_fn, tag):
    def wrapper(panel, anchor, feats):
        key = (tag, "v94", str(anchor))
        if MODE["v103"] == "median" and key in CACHE94:
            te, ntrs = CACHE94[key]
            return te.copy(), list(ntrs)
        te, ntrs = orig_fn(panel, anchor, feats)
        CACHE94[key] = (te.copy(), list(ntrs))
        return te, ntrs
    return wrapper


def patch_member(v144_mod, tag):
    v103 = v144_mod.v103
    HS = tuple(v103.HS)
    EMB = int(v103.EMBARGO)
    orig_v103 = v103.train_predict
    v103.train_predict = make_v103_wrapper(orig_v103, tag, HS, EMB)
    ext = v144_mod.v115.v114.v113
    orig92 = ext.v92.train_predict
    orig94 = ext.v94.train_predict
    ext.v92.train_predict = make_v92_wrapper(orig92, tag)
    ext.v94.train_predict = make_v94_wrapper(orig94, tag)
    return dict(HS=[int(h) for h in HS], EMBARGO=EMB)


def books_A(tag="A"):
    v144 = _load(f"v144_{tag}", "v144/v144_deploy_v3.py")
    meta = patch_member(v144, tag)
    MODE["v103"] = "quant"
    p103_q, books_q = v144.books_v142()
    MODE["v103"] = "median"
    _, books_m = v144.books_v142()
    MODE["v103"] = "quant"
    return v144, p103_q, books_q, books_m, meta


def books_B(tag="B"):
    v150 = _load(f"v150_{tag}", "v150/v150_options_flow.py")
    v144 = v150.v144
    OPT = tuple(v150.OPT)
    feats = v150.opt_features()
    meta = patch_member(v144, tag)
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(
        panel, [c for c in fs if c not in OPT], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    MODE["v103"] = "quant"
    p103_q, books_q = v144.books_v142()
    MODE["v103"] = "median"
    _, books_m = v144.books_v142()
    MODE["v103"] = "quant"
    return v144, p103_q, books_q, books_m, dict(OPT=list(OPT), **meta)


def books_D(tag="D"):
    v144 = _load(f"v144_{tag}", "v144/v144_deploy_v3.py")
    v111 = _load(f"v111_{tag}", "v111/v111_coinbase_premium.py")
    CB = tuple(v111.CB)
    cbf = v111.add_cb(v144.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    meta = patch_member(v144, tag)
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(
        panel, [c for c in fs if c not in CB], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(cbf, on="t", how="left")
    v103.build = lambda: b103().merge(cbf, on="t", how="left")
    MODE["v103"] = "quant"
    p103_q, books_q = v144.books_v142()
    MODE["v103"] = "median"
    _, books_m = v144.books_v142()
    MODE["v103"] = "quant"
    return v144, p103_q, books_q, books_m, dict(CB=list(CB), **meta)


def slim(sim):
    out = {}
    for k in ROWS_WANT:
        r = sim[k]
        out[k] = dict(monthly_pct=r["monthly_pct"], full_path_dd=r["full_path_dd"],
                      yearly=[dict(anchor=y["anchor"], net_pct=y["net_pct"],
                                   max_drawdown_percent=y["max_drawdown_percent"],
                                   fills=y.get("fills"), mean_g=y.get("mean_g")) for y in r["yearly"]],
                      mean_g_per_anchor_year=r.get("mean_g_per_anchor_year"),
                      maker_fill_rate=r.get("maker_fill_rate"),
                      orders_live=r.get("orders_live"), fills_live=r.get("fills_live"))
    return out


def main():
    v144a, p103, A_q, A_m, metaA = books_A("A")
    print(f"A done {A_q.shape}", flush=True)
    _, _, B_q, B_m, metaB = books_B("B")
    print(f"B done {B_q.shape}", flush=True)
    _, _, D_q, D_m, metaD = books_D("D")
    print(f"D done {D_q.shape}", flush=True)
    idx = A_q.index.union(B_q.index).union(D_q.index).sort_values()
    books_q = (A_q.reindex(idx).fillna(0.0) + B_q.reindex(idx).fillna(0.0)
               + D_q.reindex(idx).fillna(0.0)) / 3
    books_m = (A_m.reindex(idx).fillna(0.0) + B_m.reindex(idx).fillna(0.0)
               + D_m.reindex(idx).fillna(0.0)) / 3
    sim_q = v144a.simulate(p103, books_q)
    sim_m = v144a.simulate(p103, books_m)
    anchors = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    per_anchor = {}
    for tag in ("A", "B", "D"):
        rows = []
        for a in anchors:
            c = CACHE[(tag, a)]
            rows.append(dict(anchor=a, **c["info"]))
        per_anchor[tag] = rows
    result = {
        "version": "v168_audit_replication",
        "blind": "did_not_open_research_v168_until_this_file_saved",
        "anchors": anchors,
        "v103": {"HS": metaA["HS"], "EMBARGO": metaA["EMBARGO"],
                 "quantile": list(QS), "qparams": QPARAMS,
                 "cutoff": "anchor - 4h*EMBARGO", "row_filter": "t + 4h*(h+1) < cutoff, y{h} not NaN",
                 "c_ref": "median(|mean_h median|/mean_h spread) on training rows common to both horizons",
                 "k": "clip((|m|/s)/c_ref, 0.5, 1.5)", "pred": "m*k"},
        "member_meta": {"A": metaA, "B": metaB, "D": metaD},
        "per_anchor": per_anchor,
        "v168_quant": slim(sim_q),
        "diagnostic_median_only": slim(sim_m),
        "shapes": {"A": list(A_q.shape), "B": list(B_q.shape), "D": list(D_q.shape),
                   "union_bars": int(len(idx))},
        "meta": {
            "A": "v144.books_v142 with v103.train_predict replaced by quantile*mul; v92/v94 unchanged",
            "B": "v150.opt_features merged before xs via v151 glue; v103 quantile; vol excludes OPT",
            "D": "v111.add_cb merged before xs via v154 glue; v103 quantile; vol excludes CB",
            "books": "(A+B+D)/3 union missing->0; simulate=v144 rows 0.15 ungoverned / 0.20 / 0.25 governed",
            "diagnostic": "median-only k=1 reuses same quantile fits (cached); IC m vs y6 and baseline vs y6",
        },
    }
    OUT.write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({"quant": {k: v["monthly_pct"] for k, v in slim(sim_q).items()},
                      "median": {k: v["monthly_pct"] for k, v in slim(sim_m).items()}}, indent=1))


if __name__ == "__main__":
    main()
