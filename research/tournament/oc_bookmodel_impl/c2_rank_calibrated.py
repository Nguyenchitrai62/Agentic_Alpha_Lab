"""C2 PRE-REGISTRATION (oc_bookmodel_impl C2 — ranking/classification direction target with calibrated sizing, majors only).

Direction: walk-forward refresh of the BOT/MANUAL book leg (dip sleeve, agents, execution held fixed).
Variant C2 (of max 2; direction closes after C1/C2): replace return regression with a calibrated rank
target, isolating the target effect (same features/windows/embargo/folds/blend structure as C1, majors only).

Data windows: 5 majors only (BTC/ETH/SOL/BNB/XRP USD-M perps, 4h-bar decisions; 2017 spot prefix as
training rows, as in the deployed builder). Training rows: earliest available -> anchor - 7 days.
Test/predict: [anchor, anchor + 365 days).
Features per (t, sym), all causal at the bar close, NO new formulas: identical O1 feature set to C1
(base v142 xs + TV(17) + v236 order-level whale flow(6)) but computed on the 5 majors only (isolates
the target effect). HGB same depth-4 budget (max_depth 4, lr 0.03, max_iter 400, min_samples_leaf 300,
l2 1.0; ranker seed 0, calibration seeds fixed).
Targets: pairwise listwise rank of the 5 majors' 7d vol-norm returns per bar: per bar t with all 5
y42 realised, rank r in {0..4} -> mapped to (r/4*2-1) in [-1,1] (cross-sectional rank, NOT a raw sign;
v112 sign classifiers failed as raw signs; v287/v288 path labels are NOT reused). One HGB ranker
regressing the rank (same depth-4 budget). Probability calibration: Platt (logistic) with isotonic
fallback, fit on train folds ONLY (train split by time: last 20%% of pre-cutoff rows = calibration fold;
no test-year data): calibrated rank -> long/short weights via v94.weights_ls(shorts=True) on the
calibrated ranks (pred clipped at +-0.5 as in weights_ls, ribbon gating unchanged), vol_target_scale
unchanged.
Embargo: 7 days (t_exit and label-realisation < anchor - 7 d; >= the 7d horizon; plus the +1-bar margin;
calibration fold also ends before anchor - 7 d).
Walk-forward folds: anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 for SELECTION;
2025-09-24 scored ONCE for the frozen finalist only (never used to pick between variants).
Members: annual A/B + quarterly Aq/Bq refit per anchor/quarter (quarterly cutoff = quarter start - 7 d);
A-members = full feature set, B-members = TV-only (no fl_ flow); predictions for the majors only.
Member blend: books = 0.8 x rank-O1 + 0.2 x D with D byte-identical to deployed
(members_v154 key D + members_quarterly_D)/2; O1 = 0.5x(A+B)/2 + 0.5x(Aq+Bq)/2.
Evaluation: the 4-phase reset-metric harness (v376 + research/diagnostics/r2_decompose5/reset_metric.py:
four clock-shifted 0/1/2/3 h sub-books, 1/4 capital each, never rebalanced, reset at each anchor;
per-year R, worst year, max-yearly DD and full-path DD as max(4h-close, 1m-marked incl. open positions);
gate costs maker 0.02%% / taker 0.055%%, adverse funding longs 0.01%%/8h shorts zero; report book-only AND
full-pipeline rows with the R2 dip sleeve + agents fixed; plus cost-stress and latency-15 robustness rows,
not selection) with the deployed R2B1D17BF sleeve fixed. Selection ONLY on 2021-2024 per the user rule,
v204+ robust criterion (DD <= 20 and no losing year in 2021-2024; prefer mean >= 5%%/mo if any; among them
highest worst-year monthly; ties -> higher mean). If C1/C2 fail dev DD/worst-year filters, close the
book-refresh direction without touching the last year again. No statistic from 2025-09-24+ feeds any choice.
Rationale: book trades are structurally ~50%% winners and all profit comes from longs held > 4 days while
shorts hedge bear years; a calibrated rank->size mapping targets worst-year selection directly.

Usage:
  python research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py --smoke
  python research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py --full --out <dir>
  python research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py --build-kpack <dir>
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).parent))
import common_impl as C

HERE = Path(__file__).parent
CAND = "C2-rank-calibrated"


def rank_target(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank of y42 across the 5 majors per bar, mapped to [-1,1].

    Only bars where all 5 majors have realised y42 get a rank (else NaN -> excluded
    from rank training). Causal: y42(t) uses opens t+1..t+43, so ranks are trained
    only on rows with t+(42+1)*4h < cutoff (see train mask).
    """
    panel = panel.copy()
    wide = panel.pivot_table(index="t", columns="sym", values="y42")
    wide = wide.reindex(columns=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"])
    r = wide.rank(axis=1, pct=False)  # 1..5
    r = (r - 1) / 4 * 2 - 1  # -> [-1,1]
    panel["rank42"] = panel.set_index(["t", "sym"]).index.map(
        lambda k: r.loc[k[0], k[1]] if k[0] in r.index else np.nan)
    return panel


def fit_calibrator(tr_rank_pred: np.ndarray, tr_rank_true: np.ndarray):
    """Platt (logistic) with isotonic fallback; fit on train-calibration fold only."""
    m = tr_rank_pred.reshape(-1, 1)
    try:
        lr = LogisticRegression().fit(m, (tr_rank_true > 0).astype(int))
        return ("platt", lr)
    except Exception:
        ir = IsotonicRegression(out_of_bounds="clip").fit(tr_rank_pred, tr_rank_true)
        return ("isotonic", ir)


def apply_calibrator(cal, pred: np.ndarray) -> np.ndarray:
    kind, m = cal
    if kind == "platt":
        p = m.predict_proba(pred.reshape(-1, 1))[:, 1]
        return p * 2 - 1
    return m.predict(pred)


def build_panel_full(log=print):
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
        log(f"C2: extended loader unavailable ({e})")
    panel = C.build_majors_panel(stack, with_flow_kline=True)
    panel = C.add_tv_and_flow(stack, panel, ext_load, order_flow=True)
    panel = C.add_targets_multi(panel, (42,))
    panel = rank_target(panel)
    panel = C.add_xs(stack, panel)
    return panel, stack


def fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=None, seed=0, quarterly=False):
    _, v94, _, _, _, _, _ = stack
    is_major = panel.sym.isin(("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"))
    if quarterly:
        starts = C.quarter_starts(anchor)
        ends = starts[1:] + [C.quarter_end(anchor)]
    else:
        a0 = pd.Timestamp(anchor, tz="UTC")
        starts, ends = [a0], [a0 + pd.Timedelta(days=365)]
    out_A, out_B = [], []
    for q0, q1 in zip(starts, ends):
        cutoff = q0 - pd.Timedelta(days=C.EMBARGO_DAYS)
        base = (panel["t"] < cutoff) & panel["y42"].notna() & panel["rank42"].notna()
        base &= panel["t"] + pd.Timedelta(hours=4 * (42 + 1)) < cutoff
        te = panel[is_major & (panel["t"] >= q0) & (panel["t"] < q1)].copy()
        if not len(te):
            continue
        for feats, store in ((feats_A, out_A), (feats_B, out_B)):
            tr = panel[base].sort_values("t")
            if max_rows and len(tr) > max_rows:
                tr = tr.sample(n=max_rows, random_state=seed)
            # time-split calibration: last 20% of train = calibration fold (still before cutoff)
            n = len(tr)
            k = max(100, int(0.8 * n))
            tr_fit, tr_cal = tr.iloc[:k], tr.iloc[k:]
            m = HistGradientBoostingRegressor(**C.HGB)
            m.fit(tr_fit[feats].to_numpy(float), tr_fit["rank42"].to_numpy(float))
            cal = fit_calibrator(m.predict(tr_cal[feats].to_numpy(float)),
                                 tr_cal["rank42"].to_numpy(float))
            raw = m.predict(te[feats].to_numpy(float))
            te2 = te.copy()
            te2["pred"] = apply_calibrator(cal, raw)
            store.append(te2)
    oos_A = pd.concat(out_A, ignore_index=True) if out_A else panel.iloc[0:0]
    oos_B = pd.concat(out_B, ignore_index=True) if out_B else panel.iloc[0:0]
    return oos_A, oos_B


def run(smoke=False, out=None, max_rows=None):
    t0 = time.time()
    log = print
    if smoke:
        panel, stack = build_panel_full(log=log)
        anchor = C.DEV_ANCHORS[0]
        feats = C.feature_list(panel)
        feats_A, feats_B = feats, C.feature_list(panel, exclude_flow_for_B=True)
        oos_A, oos_B = fit_anchor(panel, stack, anchor, feats_A, feats_B,
                                  max_rows=3000 if max_rows is None else max_rows)
        _, v94, _, _, _, _, _ = stack
        WA = C.format_member(C.weights_frame(oos_A, v94, True)) if len(oos_A) else None
        WB = C.format_member(C.weights_frame(oos_B, v94, True)) if len(oos_B) else None
        dt = time.time() - t0
        log(f"C2 smoke anchor={anchor} panel={panel.shape} feats={len(feats)} "
            f"rank_cov={float(panel['rank42'].notna().mean()):.3f} "
            f"A_oos={len(oos_A)} B_oos={len(oos_B)} {dt:.1f}s")
        if out:
            out = Path(out)
            out.mkdir(parents=True, exist_ok=True)
            if WA is not None:
                WA.to_parquet(out / "member_C2_A_smoke.parquet")
            if WB is not None:
                WB.to_parquet(out / "member_C2_B_smoke.parquet")
        return {"panel_shape": panel.shape, "feats": len(feats),
                "A_oos": len(oos_A), "B_oos": len(oos_B), "seconds": round(dt, 1)}
    panel, stack = build_panel_full(log=log)
    feats = C.feature_list(panel)
    feats_A, feats_B = feats, C.feature_list(panel, exclude_flow_for_B=True)
    _, v94, _, _, _, _, _ = stack
    out = Path(out) if out else (HERE / "kaggle_out_C2")
    out.mkdir(parents=True, exist_ok=True)
    for anchor in C.DEV_ANCHORS:
        oos_A, oos_B = fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=max_rows)
        C.format_member(C.weights_frame(oos_A, v94, True)).to_parquet(out / f"member_C2_A_{anchor[:4]}.parquet")
        C.format_member(C.weights_frame(oos_B, v94, True)).to_parquet(out / f"member_C2_B_{anchor[:4]}.parquet")
        oos_Aq, oos_Bq = fit_anchor(panel, stack, anchor, feats_A, feats_B, max_rows=max_rows, quarterly=True)
        C.format_member(C.weights_frame(oos_Aq, v94, True)).to_parquet(out / f"member_C2_Aq_{anchor[:4]}.parquet")
        C.format_member(C.weights_frame(oos_Bq, v94, True)).to_parquet(out / f"member_C2_Bq_{anchor[:4]}.parquet")
        log(f"C2 anchor {anchor} done {time.time()-t0:.0f}s")
    log(f"C2 dev folds written to {out} in {time.time()-t0:.0f}s "
        f"(2025-09-24 scored once for the frozen finalist only)")
    return {"out": str(out)}


def build_kpack(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = ["data/raw/xs_universe_20260924", "data/raw/spot_majors_20260925",
              "data/raw/aggflow_20260928_orders",
              "artifacts/research/engine_real/members_v154.parquet",
              "artifacts/research/engine_real/members_quarterly_D.parquet"]
    (out_dir / "kernel_run.py").write_text(
        "import subprocess,sys\n"
        "subprocess.check_call([sys.executable, 'c2_rank_calibrated.py', '--full', '--out', 'out_C2'])\n")
    for f in ("c2_rank_calibrated.py", "common_impl.py"):
        (out_dir / f).write_bytes((HERE / f).read_bytes())
    C.write_kpack_template(out_dir, CAND, "oc-c2-rank-calibrated", inputs,
                           "C2 full: majors-only ~90k rows; 4 dev anchors x (A+B ranker+calibration) + 16 quarterly "
                           "x 2 fits (~40 HGB fits + logistic/isotonic calibrations); expect ~0.5-1 h on Kaggle CPU.")
    print(f"C2 kpack template written to {out_dir} (private; leader uploads)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--build-kpack", default=None)
    ap.add_argument("--max-rows", type=int, default=None)
    a = ap.parse_args()
    if a.build_kpack:
        build_kpack(a.build_kpack)
    elif a.smoke:
        run(smoke=True, out=a.out)
    elif a.full:
        run(smoke=False, out=a.out, max_rows=a.max_rows)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
