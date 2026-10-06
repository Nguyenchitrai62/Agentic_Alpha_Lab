"""C1 PRE-REGISTRATION (oc_bookmodel_impl C1 — pooled 77-coin training, fixed architecture, TV + order-flow, multi-horizon).

Direction: walk-forward refresh of the BOT/MANUAL book leg (dip sleeve, agents, execution held fixed).
Variant C1 (of max 2; direction closes after C1/C2): pooled 77-coin estimation with capacity fixed.

Data windows: symbols = 5 majors (BTC/ETH/SOL/BNB/XRP USD-M perps, 4h-bar decisions) + the 72
survivorship-free Dec-2020 perp markets (data/raw/alts2020_intraday_20260930, delisted included;
alt rows only where the coin was listed before the bar; universe fixed Dec-2020 so no survivorship
pick-up; 2017 spot prefix for majors as in the deployed builder). Training rows: earliest available
-> anchor - 7 days. Test/predict: [anchor, anchor + 365 days).
Features per (t, sym), all causal at the bar close, NO new formulas: base v142 xs
(v92 features + v103 kline-flow + cross-sectional xs/xr) + TV(17) (v231 tv_indicators, standard
defaults, pivots confirmed after 3 right-hand bars) + v236 order-level whale flow(6) on rebuilt taker
orders (data/raw/aggflow_20260928_orders; consecutive same-timestamp/side aggTrades = one order;
alt rows carry NaN flow). HGB depth-4 hyper-parameters unchanged (max_depth 4, lr 0.03, max_iter 400,
min_samples_leaf 300, l2 1.0, seed 0) — v299 overfit came from a larger HGB; C1 tests data scale, not capacity.
Targets: v92 7d vol-norm panel (H=42) + v103-style 12h (h=3 bars) and 3d (h=18 bars) short-horizon
panel; y_h = clip(log(open[t+1+h]/open[t+1])/(vol42*sqrt(h)), +-4); one HGB per horizon, mean prediction.
Embargo: 7 days (t_exit and label-realisation < anchor - 7 d; >= all horizons used; plus the +1-bar margin).
Walk-forward folds: anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 for SELECTION;
2025-09-24 scored ONCE for the frozen finalist only (never used to pick between variants).
Members: annual A/B + quarterly Aq/Bq refit per anchor/quarter (quarterly cutoff = quarter start - 7 d);
A-members = full feature set (xs + TV + flow), B-members = xs + TV only; BOTH trained on pooled rows
(majors + alts, asset id 5 for every alt); predictions for the majors only.
Member blend: books = 0.8 x pooled-O1 + 0.2 x D with D byte-identical to deployed
(members_v154 key D + members_quarterly_D)/2; O1 = 0.5x(A+B)/2 + 0.5x(Aq+Bq)/2, v94.weights_ls(shorts=True).
Evaluation: the 4-phase reset-metric harness (v376 + research/diagnostics/r2_decompose5/reset_metric.py:
four clock-shifted 0/1/2/3 h sub-books, 1/4 capital each, never rebalanced, reset at each anchor;
per-year R, worst year, max-yearly DD and full-path DD as max(4h-close, 1m-marked incl. open positions);
gate costs maker 0.02%% / taker 0.055%%, adverse funding longs 0.01%%/8h shorts zero; report book-only AND
full-pipeline rows with the R2 dip sleeve + agents fixed; plus cost-stress and latency-15 robustness rows,
not selection) with the deployed R2B1D17BF sleeve fixed. Selection ONLY on 2021-2024 per the user rule,
v204+ robust criterion (DD <= 20 and no losing year in 2021-2024; prefer mean >= 5%%/mo if any; among them
highest worst-year monthly; ties -> higher mean). If C1/C2 fail dev DD/worst-year filters, close the
book-refresh direction without touching the last year again. No statistic from 2025-09-24+ feeds any choice.

Usage:
  python research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py --smoke
  python research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py --full --out <dir>
  python research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py --build-kpack <dir>
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
import common_impl as C

HERE = Path(__file__).parent
CAND = "C1-pooled-tvflow"


def build_panel_full(log=print, max_alts=None):
    stack = C.load_stack()
    v92, v94, v103, v142, tvm, flo, flo_o = stack
    ext_load = v92.load_asset
    try:
        v144 = C._load("ocbm_v144x", C.RD / "v144/v144_deploy_v3.py")
        ext = v144.v115.v114.v113
        ext.cb_bars = v144.v115.v114.cb_bars_ext
        ext.v92.load_asset = ext.load_asset_ext
        ext_load = ext.load_asset_ext
    except Exception as e:
        log(f"C1: extended loader unavailable, majors-only bars ({e})")
    panel = C.build_majors_panel(stack, with_flow_kline=True)
    panel = C.add_tv_and_flow(stack, panel, ext_load, order_flow=True)
    uni = C.alt_universe()
    panel = C.add_alt_rows(stack, panel, ext_load, uni, max_alts=max_alts, log=log)
    panel = C.add_targets_multi(panel, C.H_C1)
    panel = C.add_xs(stack, panel)
    return panel, stack


def fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=None, seed=0, quarterly=False):
    _, v94, _, _, _, _, _ = stack
    is_major = panel.sym.isin(("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"))
    segs = []
    if quarterly:
        starts = C.quarter_starts(anchor)
        ends = starts[1:] + [C.quarter_end(anchor)]
    else:
        a0 = pd.Timestamp(anchor, tz="UTC")
        starts, ends = [a0], [a0 + pd.Timedelta(days=365)]
    out_A, out_B = [], []
    for q0, q1 in zip(starts, ends):
        cutoff = q0 - pd.Timedelta(days=C.EMBARGO_DAYS)
        trm = C.train_mask(panel, cutoff, C.H_C1)
        te = panel[is_major & (panel["t"] >= q0) & (panel["t"] < q1)].copy()
        if not len(te):
            continue
        for feats, store in ((feats_A, out_A), (feats_B, out_B)):
            tr = panel[trm]
            if max_rows and len(tr) > max_rows:
                tr = tr.sample(n=max_rows, random_state=seed)
            preds = []
            for h in C.H_C1:
                m = HistGradientBoostingRegressor(**C.HGB)
                m.fit(tr[feats].to_numpy(float), tr[f"y{h}"].to_numpy(float))
                preds.append(m.predict(te[feats].to_numpy(float)))
            te2 = te.copy()
            te2["pred"] = np.mean(preds, axis=0)
            store.append(te2)
    oos_A = pd.concat(out_A, ignore_index=True) if out_A else panel.iloc[0:0]
    oos_B = pd.concat(out_B, ignore_index=True) if out_B else panel.iloc[0:0]
    return oos_A, oos_B


def run(smoke=False, out=None, max_alts=None, max_rows=None):
    t0 = time.time()
    log = print
    if smoke:
        panel, stack = build_panel_full(log=log, max_alts=2)
        anchor = C.DEV_ANCHORS[0]
        feats = C.feature_list(panel)
        feats_A, feats_B = feats, C.feature_list(panel, exclude_flow_for_B=True)
        oos_A, oos_B = fit_anchor(panel, stack, anchor, feats_A, feats_B,
                                  max_rows=3000 if max_rows is None else max_rows,
                                  quarterly=False)
        _, v94, _, _, _, _, _ = stack
        WA = C.format_member(C.weights_frame(oos_A, v94, True)) if len(oos_A) else None
        WB = C.format_member(C.weights_frame(oos_B, v94, True)) if len(oos_B) else None
        dt = time.time() - t0
        log(f"C1 smoke anchor={anchor} panel={panel.shape} feats={len(feats)} "
            f"A_oos={len(oos_A)} B_oos={len(oos_B)} {dt:.1f}s")
        if out:
            out = Path(out)
            out.mkdir(parents=True, exist_ok=True)
            if WA is not None:
                WA.to_parquet(out / "member_C1_A_smoke.parquet")
            if WB is not None:
                WB.to_parquet(out / "member_C1_B_smoke.parquet")
        return {"panel_shape": panel.shape, "feats": len(feats),
                "A_oos": len(oos_A), "B_oos": len(oos_B), "seconds": round(dt, 1)}
    panel, stack = build_panel_full(log=log, max_alts=max_alts)
    feats = C.feature_list(panel)
    feats_A, feats_B = feats, C.feature_list(panel, exclude_flow_for_B=True)
    _, v94, _, _, _, _, _ = stack
    out = Path(out) if out else (HERE / "kaggle_out_C1")
    out.mkdir(parents=True, exist_ok=True)
    for anchor in list(C.DEV_ANCHORS) + [C.FINAL_ANCHOR]:
        pass  # full loop below writes per-anchor caches; final anchor only for frozen finalist
    for anchor in C.DEV_ANCHORS:
        oos_A, oos_B = fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=max_rows)
        C.format_member(C.weights_frame(oos_A, v94, True)).to_parquet(out / f"member_C1_A_{anchor[:4]}.parquet")
        C.format_member(C.weights_frame(oos_B, v94, True)).to_parquet(out / f"member_C1_B_{anchor[:4]}.parquet")
        oos_Aq, oos_Bq = fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=max_rows, quarterly=True)
        C.format_member(C.weights_frame(oos_Aq, v94, True)).to_parquet(out / f"member_C1_Aq_{anchor[:4]}.parquet")
        C.format_member(C.weights_frame(oos_Bq, v94, True)).to_parquet(out / f"member_C1_Bq_{anchor[:4]}.parquet")
        log(f"C1 anchor {anchor} done {time.time()-t0:.0f}s")
    log(f"C1 dev folds written to {out} in {time.time()-t0:.0f}s "
        f"(2025-09-24 scored once for the frozen finalist only)")
    return {"out": str(out)}


def build_kpack(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = ["data/raw/xs_universe_20260924", "data/raw/spot_majors_20260925",
              "data/raw/alts2020_intraday_20260930", "data/raw/um_universe_20260930",
              "data/raw/aggflow_20260928_orders",
              "artifacts/research/engine_real/members_v154.parquet",
              "artifacts/research/engine_real/members_quarterly_D.parquet"]
    (out_dir / "kernel_run.py").write_text(
        "import subprocess,sys\n"
        "subprocess.check_call([sys.executable, 'c1_pooled_tvflow.py', '--full', '--out', 'out_C1'])\n")
    for f in ("c1_pooled_tvflow.py", "common_impl.py"):
        src = (HERE / f).read_bytes()
        (out_dir / f).write_bytes(src)
    C.write_kpack_template(out_dir, CAND, "oc-c1-pooled-tvflow", inputs,
                           "C1 full: pooled ~1M rows; 4 dev anchors x (A:3 + B:3 HGB fits) + 16 quarterly x 6 fits "
                           "(~120 depth-4 HGB fits); expect ~3-6 h on Kaggle CPU; GPU not needed (HGB CPU-bound).")
    print(f"C1 kpack template written to {out_dir} (private; leader uploads)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--build-kpack", default=None)
    ap.add_argument("--max-alts", type=int, default=None)
    ap.add_argument("--max-rows", type=int, default=None)
    a = ap.parse_args()
    if a.build_kpack:
        build_kpack(a.build_kpack)
    elif a.smoke:
        run(smoke=True, out=a.out)
    elif a.full:
        run(smoke=False, out=a.out, max_alts=a.max_alts, max_rows=a.max_rows)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
