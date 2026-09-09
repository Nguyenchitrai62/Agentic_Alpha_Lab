"""Opencode v125 (A2-ARCH VERIFICATION 8th): independent rebuild of R-v55bfixcal identity-1x + isoall-1x normal + fee .00055.

Frozen inputs only (read, never refit):
  predictions = artifacts/kaggle/v55bfix_acc2_download/v55b-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/predictions.npy (33 files,
                CAPPED rank logits (n,16) |logit|<=3.0)
  candles/costs/decisions/labels = data/processed/swing_regime_research_v4/
  R numbers are READ-ONLY references frozen into configs/opencode_v125_verifyv55bfixcal.json.
  This driver never imports R's driver (opencode_r45a_v55bfixcal) nor
  causal_calibration module; own isotonic + gate below (sklearn directly).

Own implementation (independent, float64):
  - own_combine_mean3: arithmetic mean of 3 seeds per fold-test (no recap/penalty/median).
  - own_top1_margin: argmax first-max deterministic; margin = top1 - max(other 15).
  - own_grid/own_prices: verbatim formula from dataset cfg (no R-driver import).
  - own_eligible_history: signal_time in [lookback,asof) AND label_end < asof-8d.
  - own_causal_isotonic: sklearn IsotonicRegression(out_of_bounds=clip) on past-only
    (score=capped-logit ordinal, target=realized net%); <50 rows -> warmup WAIT
    (mapped zeros, gate inf).
  - own identity gate: margin > threshold_en(fold) frozen p70 strict >, NO fallback.
  - own isoall gate: absolute 0.0 on calibrated (mapped row > 0.0 eligible-pick argmax),
    warmup WAIT, NO fallback (topdec-gate branch NOT verified here).
  - own frequency: global chronological monthly-cap-4 + cooldown-5d loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 4 branches (2 frames x 2 fees): verify_identity_1x_normal/fee055 +
    verify_isoall_1x_normal/fee055, all via run_backtest (no run_stress).
  - compares total_return / max_drawdown / monthly_geometric_net / final_equity
    within 1e-6 + trades/long/short/n_signals exact vs R published.

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
    arr = np.asarray(batch3, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[0] != 3 or arr.shape[2] != 16:
        raise ValueError("Expected (3, n, 16) prediction stack")
    if not np.isfinite(arr).all():
        raise ValueError("Nonfinite frozen predictions")
    return arr.mean(axis=0)


def own_top1_margin(logits):
    mat = np.asarray(logits, dtype=np.float64)
    if mat.ndim != 2 or mat.shape[1] != 16:
        raise ValueError("Expected [n,16] rank logits")
    if not np.isfinite(mat).all():
        raise ValueError("Nonfinite ensemble logits")
    top1 = np.argmax(mat, axis=1).astype(np.int64)
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


def own_eligible_history(decisions, asof, lookback_start, embargo_days=8):
    if int(embargo_days) < 8:
        raise ValueError("Calibration requires at least 8 days label-end embargo")
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=int(embargo_days))
    return ((decisions["signal_time"] >= pd.Timestamp(lookback_start))
            & (decisions["signal_time"] < pd.Timestamp(asof))
            & (decisions["label_end"] < cutoff)).to_numpy()


def own_causal_isotonic(scores, targets, decisions, asof, lookback_start, current_scores,
                        embargo_days=8, min_eligible=50):
    mask = own_eligible_history(decisions, asof, lookback_start, embargo_days)
    n_elig = int(mask.sum())
    if n_elig < int(min_eligible):
        return (np.zeros_like(np.asarray(current_scores, dtype=np.float64)),
                {"warmup": "WAIT", "eligible_rows": n_elig}, mask)
    x = np.asarray(scores)[mask].ravel()
    y = np.asarray(targets)[mask].ravel()
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Nonfinite calibration inputs")
    model = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    mapped = model.predict(np.asarray(current_scores).ravel()).reshape(np.asarray(current_scores).shape)
    details = {"asof": str(asof), "lookback_start": str(lookback_start),
               "embargo_days": int(embargo_days), "eligible_rows": n_elig,
               "latest_label_end": str(decisions.loc[mask, "label_end"].max()),
               "x": [float(v) for v in model.X_thresholds_],
               "y": [float(v) for v in model.y_thresholds_], "warmup": None}
    np.testing.assert_allclose(
        mapped,
        np.interp(np.asarray(current_scores),
                  np.asarray(model.X_thresholds_), np.asarray(model.y_thresholds_)).reshape(np.asarray(current_scores).shape),
        atol=1e-12)
    return mapped, details, mask


def verify_monthly(final_equity_value, span_years):
    return float(float(final_equity_value) / 100.0 ** (1.0 / (12.0 * span_years)) - 0.0) if False else float((float(final_equity_value) / 100.0) ** (1.0 / (12.0 * span_years)) - 1.0)


def verify_annual(final_equity_value, span_years):
    return float((float(final_equity_value) / 100.0) ** (1.0 / span_years) - 1.0)


def build_identity_frame(part, fold_of, ensemble, cand_grid, ds_cfg, thr_frozen, expiry, tp1):
    top1, margins = own_top1_margin(ensemble)
    chosen = np.full(len(part), -1, dtype=np.int64)
    picks_by_fold = {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        thr = float(thr_frozen[str(f)])
        pick = idx[margins[idx] > thr]
        chosen[pick] = top1[pick]
        picks_by_fold[str(f)] = int(len(pick))
    monthly = Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    signals = []
    for i, row in enumerate(part.itertuples()):
        k = int(chosen[i])
        if k < 0:
            continue
        ts = pd.Timestamp(row.signal_time)
        month = ts.strftime("%Y-%m")
        if ts < next_allowed or monthly[month] >= int(ds_cfg["policy"]["maximum_signals_per_month"]):
            continue
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        signals.append({
            "bar_index": int(row.bar_index), "signal_time": ts,
            "fold_test": int(fold_of[i]),
            "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
            "direction": int(cand_grid[k, 0]), "candidate_id": int(k),
            **geo,
            "rank_margin_logit": float(margins[i]),
            "rank_threshold_logit": float(thr_frozen[str(int(fold_of[i]))]),
            "calibrated": False, "entry_expiry_bars": int(expiry),
            "tp1_fraction": float(tp1),
        })
        monthly[month] += 1
        next_allowed = ts + pd.Timedelta(days=int(ds_cfg["policy"]["cooldown_days"]))
    frame = pd.DataFrame(signals)
    return frame, {"picks_pre_frequency": int((chosen >= 0).sum()),
                   "pick_rate": float((chosen >= 0).mean()),
                   "picks_by_fold": picks_by_fold}, chosen, margins, top1


def build_isoall_frame(part, fold_of, mapped_all, gate0, cand_grid, ds_cfg, expiry, tp1):
    monthly = Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    signals = []
    for i, row in enumerate(part.itertuples()):
        ts = pd.Timestamp(row.signal_time)
        month = ts.strftime("%Y-%m")
        if ts < next_allowed or monthly[month] >= int(ds_cfg["policy"]["maximum_signals_per_month"]):
            continue
        m_row = np.asarray(mapped_all[i], dtype=np.float64)
        if not np.isfinite(m_row).all():
            raise ValueError("Nonfinite calibrated row")
        T = float(gate0[i])
        if not np.isfinite(T):
            continue
        eligible = (m_row > T)
        if not eligible.any():
            continue
        k = int(np.argmax(np.where(eligible, m_row, -np.inf)))
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        signals.append({
            "bar_index": int(row.bar_index), "signal_time": ts,
            "fold_test": int(fold_of[i]),
            "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
            "direction": int(geo["direction"]), "candidate_id": int(k),
            "entry_limit": float(geo["entry_limit"]), "stop_loss": float(geo["stop_loss"]),
            "take_profit_1": float(geo["take_profit_1"]), "take_profit_2": float(geo["take_profit_2"]),
            "holding_bars": int(geo["holding_bars"]), "leverage": 1.0,
            "expected_net_percent": float(m_row[k]), "cal_threshold": float(T),
            "calibrated": True, "entry_expiry_bars": int(expiry),
            "tp1_fraction": float(tp1),
        })
        monthly[month] += 1
        next_allowed = ts + pd.Timedelta(days=int(ds_cfg["policy"]["cooldown_days"]))
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


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
    assert list(cfg["branches"]) == want, "v125 pre-spec must be exactly the 4 identity+isoall x normal/fee055 branches"
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

    pred_dir = root / cfg["frozen_inputs"]["predictions_dir"]
    pred_files = sorted(pred_dir.rglob("predictions.npy"))
    if len(pred_files) != int(cfg["frozen_inputs"]["predictions_n_expected"]):
        raise SystemExit(
            f"STOP: frozen v55bfix predictions count {len(pred_files)} != "
            f"{cfg['frozen_inputs']['predictions_n_expected']}"
        )
    assert len(pred_files) == 33, "v55bfix must have exactly 33 predictions.npy (3 seeds x 11 folds)"

    decisions = pd.read_parquet(root / cfg["frozen_inputs"]["decisions"])
    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    ds_cfg = json.loads((root / cfg["frozen_inputs"]["dataset_config"]).read_text(encoding="utf-8"))
    ds_costs = ds_cfg["costs"]
    assert abs(float(ds_costs["fee_rate_per_fill"]) - float(fc["dataset_base_fee"])) < 1e-12
    expiry = int(ds_cfg["entry_expiry_bars"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert expiry == 12 and cap == 2016
    parent = json.loads((root / cfg["frozen_inputs"]["parent_plan"]).read_text(encoding="utf-8"))
    span_years = ((pd.Timestamp(parent["complete_evaluation_until"])
                   - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    with np.load(str(root / cfg["frozen_inputs"]["labels"]), allow_pickle=False) as z:
        labels_all = z["labels"]
    assert labels_all.shape[1] == 16 and labels_all.shape[2] == 3, "labels shape"

    audit_ro = json.loads((root / cfg["frozen_inputs"]["r_audit_read_only"]).read_text(encoding="utf-8"))
    thr_audit = audit_ro["thresholds_ensemble_mean"]
    thr_frozen = {str(k): float(v) for k, v in fc["thresholds_ensemble_mean"].items()}
    assert set(thr_frozen) == set(str(k) for k in thr_audit), "threshold fold keys differ"
    for k in thr_frozen:
        assert thr_frozen[k] == float(thr_audit[k]), f"threshold fold {k} differs from R audit"

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
    part = decisions.iloc[indices].reset_index(drop=True)
    labsub = labels_all[indices]
    targets_net = np.asarray(labsub[..., 0], dtype=np.float64)

    cand_grid = own_grid(ds_cfg)
    assert cand_grid.shape == (16, 6), f"candidate schema changed: {cand_grid.shape}"

    bound = float(fc["prediction_bound"])
    ens_parts = []
    for fold, sel in enumerate(partitions):
        batch = []
        for seed in fc["seeds"]:
            pat = cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            path = pred_dir / pat
            if not path.exists():
                raise SystemExit(f"STOP: missing frozen prediction {path}")
            pred = np.load(str(path), allow_pickle=False)
            if pred.shape != (len(sel), 16) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path} {pred.shape}")
            if not (np.abs(np.asarray(pred, dtype=np.float64)) <= bound).all():
                raise ValueError(f"Prediction violates cap bound |logit|<={bound}: {path}")
            batch.append(np.asarray(pred, dtype=np.float64))
        ens_parts.append(own_combine_mean3(np.stack(batch, axis=0)))
    ensemble = np.concatenate(ens_parts, axis=0)
    assert ensemble.shape == (len(indices), 16)

    frame_identity, info_id, _, _, _ = build_identity_frame(
        part, fold_of, ensemble, cand_grid, ds_cfg, thr_frozen, expiry, float(fc["tp1_fraction"]))

    n = len(part)
    mapped_all = np.zeros_like(ensemble, dtype=np.float64)
    gate0 = np.full(n, np.inf, dtype=np.float64)
    calib_records = []
    off = 0
    for fold, sel in enumerate(partitions):
        cur = slice(off, off + len(sel))
        asof = parent["folds"][fold][0]
        left = parent["folds"][0][0]
        cur_scores = ensemble[cur]
        mapped, rec, _mask = own_causal_isotonic(
            ensemble, targets_net, part, asof, left, cur_scores,
            embargo_days=int(fc["embargo_days"]), min_eligible=int(fc["min_eligible_decisions"]))
        if rec.get("warmup") is not None:
            mapped_all[cur] = np.zeros_like(cur_scores)
            gate0[cur] = np.inf
            calib_records.append({"fold": fold, "warmup": "WAIT",
                                  "eligible_rows": int(rec["eligible_rows"])})
        else:
            mapped_all[cur] = mapped
            gate0[cur] = 0.0
            xv = np.asarray(rec["x"], dtype=np.float64)
            yv = np.asarray(rec["y"], dtype=np.float64)
            assert bool(np.all(np.diff(xv) >= 0)), f"fold {fold} iso x not sorted"
            assert bool(np.all(np.diff(yv) >= -1e-12)), f"fold {fold} iso y not monotone"
            calib_records.append({"fold": fold, "warmup": None,
                                  "eligible_rows": int(rec["eligible_rows"]),
                                  "t_iso_for_isoall": 0.0})
        off += len(sel)

    frame_isoall = build_isoall_frame(
        part, fold_of, mapped_all, gate0, cand_grid, ds_cfg, expiry, float(fc["tp1_fraction"]))

    frames = {"verify_identity": frame_identity, "verify_isoall": frame_isoall}
    for name, fr in frames.items():
        print(json.dumps({"verify_frame": name, "n_signals": int(len(fr)),
                          "coverage": float(len(fr) / len(part)) if len(part) else 0.0}), flush=True)

    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    execution = ExecutionConfig(entry_expiry_bars=int(expiry), max_holding_bars=int(cap),
                                tp1_fraction=float(fc["tp1_fraction"]),
                                leverage=1.0, max_leverage=1.0)

    def build_costs(fee):
        return CostModel(fee_rate_per_fill=float(fee),
                         funding_long_rate=float(ds_costs["funding_long_rate"]),
                         funding_short_rate=float(ds_costs["funding_short_rate"]),
                         funding_interval_hours=int(ds_costs["funding_interval_hours"]))

    frame_of = {"verify_identity_1x_normal": frame_identity, "verify_identity_1x_fee055": frame_identity,
                "verify_isoall_1x_normal": frame_isoall, "verify_isoall_1x_fee055": frame_isoall}

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    reproduced = {}
    for branch in want:
        spec = cfg["branch_spec"][branch]
        fee = float(spec["fee_rate_per_fill"])
        costs = build_costs(fee)
        base = frame_of[branch].drop(columns=["leverage"], errors="ignore").copy()
        res, trs = run_backtest(candles, base.copy(), SEED_EQUITY, costs, execution)
        rec = asdict(res)
        rec["monthly_geometric_net"] = verify_monthly(res.final_equity, span_years)
        rec["annual_geometric_net"] = verify_annual(res.final_equity, span_years)
        rec["branch_fee"] = fee
        rec["long_trades"] = int(sum(1 for t in trs if int(t.direction) == 1))
        rec["short_trades"] = int(sum(1 for t in trs if int(t.direction) == -1))
        rec["n_signals"] = int(len(frame_of[branch]))
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
        print(json.dumps({"verify_branch": branch, "fee": fee, "total_return": rec["total_return"],
                          "max_drawdown": rec["max_drawdown"],
                          "monthly": rec["monthly_geometric_net"], "trades": rec["trades"],
                          "long": rec["long_trades"], "short": rec["short_trades"],
                          "n_signals": rec["n_signals"]}, default=str), flush=True)

    deltas, verdicts = {}, {}
    for branch in want:
        pub = cfg["r_published_exact"][branch]
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
            "n_signals_identity": int(len(frame_identity)),
            "n_signals_isoall": int(len(frame_isoall)),
            "calib_warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
            "execution": {"lev": 1.0, "max": 1.0, "tp1": float(fc["tp1_fraction"]),
                          "expiry": expiry, "holding_cap": cap},
            "candidate_causes_ordered": [
                "(1) combine mean-vs-median/penalty/dtype/capped-vs-raw+recap",
                "(2) identity gate threshold copy vs audit / fallback present-vs-absent / strict-vs-nonstrict >",
                "(3) top1 first-max vs last-max / margin second-max definition",
                "(4) causal isotonic eligible window/embargo/min_eligible/warmup handling or IsotonicRegression out_of_bounds/clip vs other",
                "(5) isoall gate absolute 0.0 vs percentile/replace, eligible-pick argmax vs global-top1 shortcut",
                "(6) geometry/prices (unit/min-risk/order checks, float32-vs-float64 grid)",
                "(7) frequency monthly-4/cooldown-5d chronological or partition order",
                "(8) fee application path (branch CostModel rebuild vs R run_branch fee leg)",
                "(9) monthly/duration formula drift (parent plan window)",
                "(10) frozen-prediction count/order drift (33-file identity, CAPPED logits)",
                "(11) engine version drift (ohlc-v2 markers)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v125-verifyv55bfixcal",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "frozen_inputs": cfg["frozen_inputs"],
        "policy_frozen": cfg["policy_frozen"],
        "own_method": cfg["own_method"],
        "span_years": span_years,
        "tolerance_abs": tol,
        "r_published_exact": cfg["r_published_exact"],
        "reproduced": reproduced,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "selection_detail": {
            "n_signals_identity": int(len(frame_identity)),
            "n_signals_isoall": int(len(frame_isoall)),
            "picks_pre_frequency_identity": int(info_id["picks_pre_frequency"]),
            "picks_by_fold_identity": info_id["picks_by_fold"],
            "calib_records": calib_records,
        },
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
                          cfg["frozen_inputs"]["dataset_config"],
                          cfg["frozen_inputs"]["parent_plan"],
                          "configs/opencode_v125_verifyv55bfixcal.json",
                          "scripts/opencode_r46a_verifyv55bfixcal.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
