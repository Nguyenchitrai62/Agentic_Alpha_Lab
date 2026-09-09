"""Opencode v104 (R36-A2 VERIFYV55CCAL): independent rebuild of B-v55ccal identity + isoall.

Rebuilds from FROZEN inputs only (read, never refit):
  predictions = artifacts/kaggle/v55c_rankonly_download/rankonly-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/predictions.npy (33 files,
                RAW rank logits (n,16), NOT v8 blocks)
  candles/costs/decisions/labels = data/processed/swing_regime_research_v4/
  B policy + B numbers are READ-ONLY references (values frozen into
  configs/opencode_v104_verifyv55ccal.json at pre-spec time; this driver never
  imports B's driver (scripts/opencode_r35b_v55ccal) nor any
  opencode_r17b_rankonly_* / train modules, nor src causal_calibration module).

Own implementation (independent, float64):
  - own_combine: arithmetic mean_3seeds of RAW rank logits per fold-test.
  - own top1/margin: argmax first-max deterministic; margin = top1 - max(other 15).
  - own identity gate: margin > threshold_en(fold) strict, NO fallback, WAIT else.
  - own calibration: causal-isotonic past-only all-quarter, embargo 8d, min 50
    else warmup WAIT (sklearn IsotonicRegression out_of_bounds=clip direct).
  - own isoall gate: absolute 0.0 on calibrated (mapped[top1] > 0.0 strict),
    warmup inf -> WAIT, NO fallback.
  - own geometry: verbatim formula from dataset cfg (no import of B driver).
  - own frequency: global chronological monthly-cap-4 + cooldown-5d loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 4 branches (shared frames, fee-only difference):
      verify_identity_1x_normal (fee 0.0002) + verify_identity_1x_fee055 (0.00055)
      verify_isoall_1x_normal (fee 0.0002) + verify_isoall_1x_fee055 (0.00055),
      all via run_backtest (mirrors B run_branch normal/fee legs; no stress here).
  - compares total_return / max_drawdown / monthly_geometric_net /
    final_equity within 1e-6 + trades/long/short/n_signals exact vs B published.

Scope: verification backtests only. Exploratory labels, opened interval.
"""

import torch  # noqa: F401  (torch before pandas: DLL load-order on this host)
import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.training import sha256

SEED_EQUITY = 100.0


def own_combine_mean3(batch3):
    """Independent mean_3seeds combine of RAW rank logits.

    batch3: (3, n, 16) float arrays. Returns (n,16) float64 arithmetic mean.
    No penalty, no median, no weighting.
    """
    arr = np.asarray(batch3, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[0] != 3 or arr.shape[2] != 16:
        raise ValueError("Expected (3, n, 16) prediction stack")
    if not np.isfinite(arr).all():
        raise ValueError("Nonfinite frozen predictions")
    return arr.mean(axis=0)


def own_top1_margin(logits):
    """Independent top1 (first-max) + margin = top1_logit - max(other 15)."""
    mat = np.asarray(logits, dtype=np.float64)
    if mat.ndim != 2 or mat.shape[1] != 16:
        raise ValueError("Expected [n,16] rank logits")
    if not np.isfinite(mat).all():
        raise ValueError("Nonfinite ensemble logits")
    top1 = np.argmax(mat, axis=1).astype(np.int64)  # first-max -> deterministic
    best = np.take_along_axis(mat, top1[:, None], axis=1)[:, 0]
    mask = np.ones_like(mat, dtype=bool)
    mask[np.arange(len(mat)), top1] = False
    second = np.where(mask, mat, -np.inf).max(axis=1)
    return top1, (best - second)


def own_grid(cfg):
    return np.asarray(
        [[s, e, *b, d]
         for s in (1, -1)
         for e in cfg["entry_atr_5m"]
         for b in cfg["brackets_atr_4h"]
         for d in cfg["holding_days"]],
        dtype=np.float64,
    )


def own_prices(close, atr5, atr4, candidate, cfg):
    side, offset, stop, tp1, tp2, days = map(float, np.asarray(candidate, dtype=np.float64).reshape(-1))
    if not np.isfinite([close, atr5, atr4]).all() or min(close, atr5, atr4) <= 0:
        raise ValueError("Invalid price/ATR")
    unit = max(float(atr4), float(close) * float(cfg["minimum_risk_fraction"]))
    entry = float(close) - side * float(offset) * float(atr5)
    stop_px = entry - side * float(stop) * unit
    tp1_px = entry + side * float(tp1) * unit
    tp2_px = entry + side * float(tp2) * unit
    levels = [stop_px, entry, tp1_px, tp2_px]
    if min(levels) <= 0 or not np.all(np.diff(np.asarray(levels) * side) > 0):
        raise ValueError("Invalid ordered bracket")
    return {
        "direction": int(side),
        "entry_limit": float(entry),
        "stop_loss": float(stop_px),
        "take_profit_1": float(tp1_px),
        "take_profit_2": float(tp2_px),
        "holding_bars": int(float(days) * 288),
        "leverage": 1.0,
    }


def own_eligible_mask(part, asof, lookback_start, embargo_days=8):
    """Independent past-only eligible-history mask (no import of shared calibrator)."""
    if int(embargo_days) < 8:
        raise ValueError("Calibration requires at least 8 days label-end embargo")
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=int(embargo_days))
    return ((part["signal_time"] >= pd.Timestamp(lookback_start))
            & (part["signal_time"] < pd.Timestamp(asof))
            & (part["label_end"] < cutoff)).to_numpy()


def own_calibrate_fold(scores_full, targets_full, part, asof, lookback_start, cur_scores,
                        embargo_days=8, min_rows=50):
    """Independent causal-isotonic fit for one fold (sklearn direct).

    Returns (mapped_cur, detail_dict, mask).
    Warmup (mask.sum() < min_rows): mapped zeros + detail warmup WAIT.
    """
    mask = own_eligible_mask(part, asof, lookback_start, embargo_days)
    if int(mask.sum()) < int(min_rows):
        return (np.zeros_like(np.asarray(cur_scores, dtype=np.float64)),
                {"warmup": "WAIT", "eligible_rows": int(mask.sum())}, mask)
    x = np.asarray(scores_full)[mask].ravel().astype(np.float64)
    y = np.asarray(targets_full)[mask].ravel().astype(np.float64)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Nonfinite calibration inputs")
    model = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    cur = np.asarray(cur_scores, dtype=np.float64)
    mapped = model.predict(cur.ravel()).reshape(cur.shape)
    detail = {"asof": str(asof), "lookback_start": str(lookback_start),
              "embargo_days": int(embargo_days),
              "eligible_rows": int(mask.sum()),
              "latest_label_end": str(part.loc[mask, "label_end"].max()),
              "x": [float(v) for v in model.X_thresholds_.tolist()],
              "y": [float(v) for v in model.y_thresholds_.tolist()],
              "warmup": None}
    return mapped, detail, mask


def verify_monthly(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / (12.0 * span_years)) - 1.0)


def verify_annual(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / span_years) - 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]

    want = ["verify_identity_1x_normal", "verify_identity_1x_fee055",
            "verify_isoall_1x_normal", "verify_isoall_1x_fee055"]
    assert list(cfg["branches"]) == want, "v104 pre-spec must be exactly the 4 identity+isoall branches"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"

    fc = cfg["frozen_constants"]
    assert list(map(int, fc["seeds"])) == [1729, 1730, 1731]
    assert int(fc["n_folds"]) == 11
    assert int(fc["maximum_signals_per_month"]) == 4
    assert int(fc["cooldown_days"]) == 5
    assert abs(float(fc["tp1_fraction"]) - 0.5) < 1e-12
    assert int(fc["embargo_days"]) == 8
    assert int(fc["min_eligible_decisions"]) == 50

    # --- frozen prediction presence: 33 files else STOP ---
    pred_dir = root / cfg["frozen_inputs"]["predictions_dir"]
    pred_files = sorted(pred_dir.rglob("predictions.npy"))
    if len(pred_files) != int(cfg["frozen_inputs"]["predictions_n_expected"]):
        raise SystemExit(
            f"STOP: frozen v55c predictions count {len(pred_files)} != "
            f"{cfg['frozen_inputs']['predictions_n_expected']}"
        )
    assert len(pred_files) == 33, "v55c must have exactly 33 predictions.npy (3 seeds x 11 folds)"
    print(json.dumps({"verify_v55c": {"expected": 33, "found": len(pred_files), "missing": []}}), flush=True)

    # --- frozen decisions / candles / costs / labels ---
    decisions = pd.read_parquet(root / cfg["frozen_inputs"]["decisions"])
    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    ds_cfg = json.loads((root / cfg["frozen_inputs"]["dataset_config"]).read_text(encoding="utf-8"))
    ds_costs = ds_cfg["costs"]
    assert abs(float(ds_costs["fee_rate_per_fill"]) - float(fc["dataset_base_fee"])) < 1e-12
    expiry = int(ds_cfg["entry_expiry_bars"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert expiry == int(fc["entry_expiry_bars_expected"]) == 12
    assert cap == int(fc["holding_cap_bars_expected"]) == 2016
    parent = json.loads((root / cfg["frozen_inputs"]["parent_plan"]).read_text(encoding="utf-8"))
    span_years = ((pd.Timestamp(parent["complete_evaluation_until"])
                   - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    with np.load(root / cfg["frozen_inputs"]["labels"], allow_pickle=False) as z:
        labels_all = z["labels"]
    assert labels_all.shape[1] == 16 and labels_all.shape[2] == 3, "labels shape"

    # --- thresholds: frozen pre-spec copy must equal R audit file (read-only check) ---
    audit_ro = json.loads((root / cfg["frozen_inputs"]["r_audit_read_only"]).read_text(encoding="utf-8"))
    thr_audit = audit_ro["thresholds_ensemble_mean"]
    thr_frozen = {str(k): float(v) for k, v in fc["thresholds_ensemble_mean"].items()}
    assert set(thr_frozen) == set(str(k) for k in thr_audit), "threshold fold keys differ from R audit"
    for k in thr_frozen:
        assert thr_frozen[k] == float(thr_audit[k]), f"threshold fold {k} differs from R audit"

    # --- B published cross-check (read-only, frozen into config at pre-spec) ---
    b_sum = json.loads((root / cfg["frozen_inputs"]["b_summary_read_only"]).read_text(encoding="utf-8"))
    b_map = {"verify_identity_1x_normal": ("v55c-identity_1x", "normal"),
             "verify_identity_1x_fee055": ("v55c-identity_1x", "fee_stress"),
             "verify_isoall_1x_normal": ("v55c-isoall_1x", "normal"),
             "verify_isoall_1x_fee055": ("v55c-isoall_1x", "fee_stress")}
    for branch, (bb, ss) in b_map.items():
        pub = cfg["b_published_exact"][branch]
        bval = b_sum["branches"][bb][ss]
        for k in ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"):
            assert float(pub[k]) == float(bval[k]), f"B published drift {branch} {k}"
        assert int(pub["trades"]) == int(bval["trades"]), f"B published drift {branch} trades"

    # --- partitions (frozen quarterly folds, label_end < global end) ---
    end = pd.Timestamp(parent["complete_evaluation_until"])
    partitions = []
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        idx = np.flatnonzero(((decisions["signal_time"] >= start)
                              & (decisions["signal_time"] < stop)
                              & (decisions["label_end"] < end)).to_numpy())
        partitions.append(idx)
    indices = np.concatenate(partitions)
    assert int(len(indices)) == int(fc["n_decisions_expected"]) == 4076
    fold_of = np.concatenate([np.full(len(p), f, dtype=np.int64) for f, p in enumerate(partitions)])

    # --- candidate grid (own, order pre-spec) ---
    cand_grid = own_grid(ds_cfg)
    assert cand_grid.shape == (16, 6), f"candidate schema changed: {cand_grid.shape}"

    # --- ensemble per fold (own combine), concatenated in fold order ---
    ens_parts = []
    for fold, sel in enumerate(partitions):
        batch = []
        for seed in fc["seeds"]:
            pat = cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            path = pred_dir / pat
            pred = np.load(str(path), allow_pickle=False)
            if pred.shape != (len(sel), 16) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path} {pred.shape} vs {(len(sel),16)}")
            batch.append(np.asarray(pred, dtype=np.float64))
        ens_parts.append(own_combine_mean3(np.stack(batch, axis=0)))
    ensemble = np.concatenate(ens_parts, axis=0)
    assert ensemble.shape == (len(indices), 16)

    part = decisions.iloc[indices].reset_index(drop=True)
    labsub = labels_all[indices]
    top1, margins = own_top1_margin(ensemble)

    # --- own identity gate per fold-test: margin > threshold, NO fallback ---
    chosen = np.full(len(part), -1, dtype=np.int64)
    picks_by_fold = {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        thr = float(thr_frozen[str(f)])
        pick = idx[margins[idx] > thr]
        chosen[pick] = top1[pick]
        picks_by_fold[str(f)] = int(len(pick))
    n_picked = int((chosen >= 0).sum())

    # --- own frequency loop for identity (global chronological, partition order) ---
    policy_max = int(ds_cfg["policy"]["maximum_signals_per_month"])
    policy_cd = int(ds_cfg["policy"]["cooldown_days"])
    assert policy_max == int(fc["maximum_signals_per_month"]) == 4
    assert policy_cd == int(fc["cooldown_days"]) == 5
    monthly = Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    id_signals = []
    for i, row in enumerate(part.itertuples()):
        k = int(chosen[i])
        if k < 0:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy_max:
            continue
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        id_signals.append({
            "bar_index": int(row.bar_index),
            "signal_time": timestamp,
            "fold_test": int(fold_of[i]),
            "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
            "direction": int(cand_grid[k, 0]),
            "candidate_id": int(k),
            **geo,
            "rank_margin_logit": float(margins[i]),
            "rank_threshold_logit": float(thr_frozen[str(int(fold_of[i]))]),
            "calibrated": False,
            "entry_expiry_bars": int(expiry),
            "tp1_fraction": float(fc["tp1_fraction"]),
        })
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy_cd)
    frame_identity = pd.DataFrame(id_signals)

    # --- own causal-isotonic maps per fold (all-quarter, embargo 8d, min 50) ---
    n = len(part)
    mapped_all = np.zeros_like(ensemble)
    gate0 = np.full(n, np.inf)  # isoall absolute-0.0 gate (inf = warmup WAIT)
    calib_records = []
    fold_offsets = []
    off = 0
    left = parent["folds"][0][0]
    tgt_full = np.asarray(labsub[..., 0], dtype=np.float64)
    for fold, sel in enumerate(partitions):
        fold_offsets.append(off)
        cur = slice(off, off + len(sel))
        asof = parent["folds"][fold][0]
        cur_scores = ensemble[cur]
        mapped, rec, _mask = own_calibrate_fold(
            ensemble, tgt_full, part, asof, left, cur_scores,
            embargo_days=int(fc["embargo_days"]), min_rows=int(fc["min_eligible_decisions"]))
        if rec.get("warmup") is not None:
            mapped_all[cur] = np.zeros_like(cur_scores)
            gate0[cur] = np.inf
            calib_records.append({"fold": fold, "asof": str(asof), "lookback_start": str(left),
                                  "warmup": "WAIT", "eligible_rows": int(rec["eligible_rows"]),
                                  "t_best90": None, "iso_x_len": 0, "iso_y_len": 0,
                                  "latest_label_end": rec.get("latest_label_end")})
        else:
            mapped_all[cur] = mapped
            gate0[cur] = 0.0
            calib_records.append({"fold": fold, "asof": str(asof), "lookback_start": str(left),
                                  "warmup": None, "eligible_rows": int(rec["eligible_rows"]),
                                  "latest_label_end": str(rec["latest_label_end"]),
                                  "t_best90": None, "iso_x_len": len(rec["x"]), "iso_y_len": len(rec["y"])})
            calib_records[-1]["x"] = [float(v) for v in rec["x"]]
            calib_records[-1]["y"] = [float(v) for v in rec["y"]]
        off += len(sel)
    print(json.dumps({"calibration": {"folds": len(calib_records),
                                      "warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
                                      "eligible_rows": [r["eligible_rows"] for r in calib_records]}}), flush=True)

    # --- own isoall gated frame (absolute 0.0, no fallback, chronological) ---
    monthly2 = Counter()
    next_allowed2 = pd.Timestamp.min.tz_localize("UTC")
    iso_signals = []
    for i, row in enumerate(part.itertuples()):
        ts = pd.Timestamp(row.signal_time)
        month = ts.strftime("%Y-%m")
        if ts < next_allowed2 or monthly2[month] >= policy_max:
            continue
        m_row = np.asarray(mapped_all[i], dtype=np.float64)
        if not np.isfinite(m_row).all():
            raise ValueError("Nonfinite gated inputs")
        T = float(gate0[i])
        if not np.isfinite(T):
            continue
        eligible = (m_row > T)
        if not eligible.any():
            continue
        k = int(np.argmax(np.where(eligible, m_row, -np.inf)))
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        iso_signals.append({"bar_index": int(row.bar_index), "signal_time": ts,
                            "fold_test": int(fold_of[i]),
                            "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
                            "direction": int(geo["direction"]), "candidate_id": k,
                            "entry_limit": float(geo["entry_limit"]),
                            "stop_loss": float(geo["stop_loss"]),
                            "take_profit_1": float(geo["take_profit_1"]),
                            "take_profit_2": float(geo["take_profit_2"]),
                            "holding_bars": int(geo["holding_bars"]), "leverage": 1.0,
                            "expected_net_percent": float(m_row[k]),
                            "cal_threshold": float(T),
                            "calibrated": True, "entry_expiry_bars": int(expiry),
                            "tp1_fraction": float(fc["tp1_fraction"])})
        monthly2[month] += 1
        next_allowed2 = ts + pd.Timedelta(days=policy_cd)
    if iso_signals:
        frame_isoall = pd.DataFrame(iso_signals)
    else:
        frame_isoall = pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    print(json.dumps({"branch_signals": "verify_identity", "n_signals": int(len(frame_identity)),
                      "coverage": float(len(frame_identity) / len(part)) if len(part) else 0.0}), flush=True)
    print(json.dumps({"branch_signals": "verify_isoall", "n_signals": int(len(frame_isoall)),
                      "coverage": float(len(frame_isoall) / len(part)) if len(part) else 0.0}), flush=True)

    # --- engine identity sanity (own markers, ohlc-v2) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    frames = {"verify_identity": frame_identity, "verify_isoall": frame_isoall}
    execution = ExecutionConfig(
        entry_expiry_bars=int(expiry),
        max_holding_bars=int(cap),
        tp1_fraction=float(fc["tp1_fraction"]),
        leverage=1.0,
        max_leverage=1.0,
    )

    def build_branch_costs(branch_fee):
        return CostModel(
            fee_rate_per_fill=float(branch_fee),
            funding_long_rate=float(ds_costs["funding_long_rate"]),
            funding_short_rate=float(ds_costs["funding_short_rate"]),
            funding_interval_hours=int(ds_costs["funding_interval_hours"]),
        )

    frame_of_branch = {"verify_identity_1x_normal": "verify_identity",
                       "verify_identity_1x_fee055": "verify_identity",
                       "verify_isoall_1x_normal": "verify_isoall",
                       "verify_isoall_1x_fee055": "verify_isoall"}

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    reproduced = {}
    for branch in want:
        spec = cfg["branch_spec"][branch]
        fee = float(spec["fee_rate_per_fill"])
        costs = build_branch_costs(fee)
        base = frames[frame_of_branch[branch]].drop(columns=["leverage"], errors="ignore").copy()
        res, trs = run_backtest(candles, base.copy(), SEED_EQUITY, costs, execution)
        rec = asdict(res)
        rec["monthly_geometric_net"] = verify_monthly(res.final_equity, span_years)
        rec["annual_geometric_net"] = verify_annual(res.final_equity, span_years)
        rec["branch_fee"] = fee
        rec["n_signals"] = int(len(base))
        # long/short from Trade objects (engine result has no split; count here)
        rec["long_trades"] = int(sum(1 for t in trs if t.direction == 1))
        rec["short_trades"] = int(sum(1 for t in trs if t.direction == -1))
        reproduced[branch] = rec

        bdir = a.output / branch
        bdir.mkdir()
        base.to_parquet(bdir / "signals.parquet", index=False)
        rows = [asdict(t) for t in trs]
        if rows:
            cols = sorted(rows[0].keys())
            pd.DataFrame(rows)[cols].to_csv(bdir / "trades.csv", index=False)
        else:
            pd.DataFrame([]).to_csv(bdir / "trades.csv", index=False)
        (bdir / "metrics.json").write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"verify_branch": branch, "fee": fee,
                          "total_return": rec["total_return"],
                          "max_drawdown": rec["max_drawdown"],
                          "monthly": rec["monthly_geometric_net"],
                          "trades": rec["trades"],
                          "long": rec["long_trades"],
                          "short": rec["short_trades"],
                          "n_signals": rec["n_signals"]}, default=str), flush=True)

    deltas, verdicts = {}, {}
    for branch in want:
        pub = cfg["b_published_exact"][branch]
        rep = reproduced[branch]
        dd = {k: float(rep[k] - pub[k]) for k in
              ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity")}
        dd["trades"] = int(rep["trades"] - pub["trades"])
        dd["long_trades"] = int(rep["long_trades"] - pub["long_trades"])
        dd["short_trades"] = int(rep["short_trades"] - pub["short_trades"])
        dd["n_signals"] = int(rep["n_signals"] - pub["n_signals"])
        ok = (all(abs(dd[k]) <= tol for k in
                  ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"))
              and dd["trades"] == 0 and dd["long_trades"] == 0 and dd["short_trades"] == 0
              and dd["n_signals"] == 0)
        deltas[branch] = dd
        verdicts[branch] = "PASS" if ok else "FAIL"

    overall = all(v == "PASS" for v in verdicts.values())
    triage = {"status": "no mismatch - independent rebuild agrees" if overall
              else "MISMATCH - cause under investigation",
              "diagnostics": {}}
    if not overall:
        triage["diagnostics"] = {
            "span_years": span_years,
            "n_predictions": len(pred_files),
            "n_decisions": int(len(indices)),
            "n_picked_pre_frequency_identity": n_picked,
            "n_picked_expected": int(fc["picks_pre_frequency_expected_identity"]),
            "picks_by_fold": picks_by_fold,
            "n_signals_identity": int(len(frame_identity)),
            "n_signals_isoall": int(len(frame_isoall)),
            "calib_eligible_rows": [r["eligible_rows"] for r in calib_records],
            "calib_warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
            "execution": {"lev": 1.0, "max": 1.0, "tp1": float(fc["tp1_fraction"]),
                          "expiry": expiry, "holding_cap": cap},
            "candidate_causes_ordered": [
                "(1) combine mean-vs-median/penalty/dtype (own float64 mean vs B stacked.mean)",
                "(2) identity gate threshold copy vs audit / fallback present-vs-absent / strict-vs-nonstrict >",
                "(3) top1 first-max vs last-max / margin second-max definition",
                "(4) isotonic eligible-window (all-quarter left) / embargo 8d / min50 / clip-vs-noclip / x-y ravel order",
                "(5) gate0 absolute-0.0 vs percentile / warmup-inf handling / eligible-masked argmax",
                "(6) geometry/prices (unit/min-risk/order checks)",
                "(7) frequency monthly-4/cooldown-5d chronological or partition order",
                "(8) fee application path (branch CostModel rebuild vs B run_branch fee leg)",
                "(9) monthly/duration formula drift (parent plan window)",
                "(10) frozen-prediction count/order drift (33-file identity, RAW logits vs v8 blocks)",
                "(11) engine version drift (ohlc-v2 markers)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v104-verifyv55ccal",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "mission_claim": cfg["mission_claim"],
        "frozen_inputs": cfg["frozen_inputs"],
        "policy_frozen": cfg["policy_frozen"],
        "span_years": span_years,
        "tolerance_abs": tol,
        "b_published_exact": cfg["b_published_exact"],
        "reproduced": reproduced,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "selection_detail": {
            "n_picked_pre_frequency_identity": n_picked,
            "picks_by_fold_identity": picks_by_fold,
            "n_signals_identity": int(len(frame_identity)),
            "n_signals_isoall": int(len(frame_isoall)),
        },
        "calibration_records": calib_records,
        "triage": triage,
        "artifacts": {b: f"{b}/{{signals.parquet,trades.csv,metrics.json}}" for b in want},
        "causal_notes": cfg["causal_notes"],
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
        "warning": ("Exploratory verification on the opened development interval only. "
                    "Fee tiers are subjective robustness assumptions, not measured live "
                    "fees/slippage. Drawdown is trade-candle-close sampled; stops/timeouts "
                    "market-like at branch fee. No promotion, no validation, no live claim."),
        "input_sha256": {q: sha256(root / q) for q in
                         (cfg["frozen_inputs"]["candles"],
                          cfg["frozen_inputs"]["decisions"],
                          cfg["frozen_inputs"]["labels"],
                          cfg["frozen_inputs"]["dataset_config"],
                          cfg["frozen_inputs"]["parent_plan"],
                          cfg["frozen_inputs"]["b_config_read_only"],
                          "configs/opencode_v104_verifyv55ccal.json",
                          "scripts/opencode_r36a_verifyv55ccal.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
