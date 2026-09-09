"""Opencode v115 (A2-ARCH VERIFYV41VALFIT, 6th verification): independent rebuild of R-v41valfit (v112).

Rebuilds from FROZEN inputs only (read, never refit):
  predictions = artifacts/kaggle/v41_acc2_download/valuescale-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/{predictions,val_predictions}.npy
                (33 test + 33 val, map-v8 RAW TRADEABLE percent (n,16,6); VERIFY else STOP)
  candles/costs/decisions/labels = data/processed/swing_regime_research_v4/
  R policy + R numbers are READ-ONLY references (values frozen into
  configs/opencode_v115_verifyv41valfit.json at pre-spec time; this driver never
  imports R's driver scripts/opencode_r40a_v41valfit.py, nor ensemble_value.combine,
  nor opencode_r30m_v41_model, nor any train module).

Own implementation (independent, float64):
  - own_ensemble_fold: per-seed expected = ch0*sigmoid(ch4); arithmetic mean_3seeds;
    own fill_logit = logit(mean sigmoid(ch4)) for tie-break only.
  - own_best_index: max(exp); tie set within eps=1e-6; fill-logit desc;
    holding asc; index min.
  - own geometry: grid/prices formulas re-derived from dataset cfg (no import).
  - own calibration: per-fold TRUE val-fit isotonic VAL-ONLY, NO winsor (faithful
    to R v112 which has no winsor); warmup WAIT (<50/nonfinite/unique<2) -> RAW;
    past-only assert per fold; sampled order-preservation assert viol==0.
  - own gate: v41 policy floor en_best > 0.0 + fallback top-8/fold-test on the
    same scale; own chronological monthly-cap-4 + cooldown-5d frequency loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 4 branches: identity/calibrated x normal/fee055 via run_backtest (shared
    ohlc-v2 infra only); compares total_return / max_drawdown /
    monthly_geometric_net / final_equity within 1e-6 + trades/long/short/n_signals
    exact vs R v112 published.

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
WANT = ["verify_v41_identity_1x_normal", "verify_v41_identity_1x_fee055",
        "verify_v41_valfit_calibrated_1x_normal", "verify_v41_valfit_calibrated_1x_fee055"]


def own_sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, dtype=np.float64), -40.0, 40.0)))


def own_ensemble_fold(batch3):
    """Independent mean_3seeds ensemble of map-v8 blocks.

    batch3: (3, n, 16, 6) float. Returns (exp_mean (n,16), fill_logit (n,16)).
    exp per seed = ch0 * sigmoid(ch4); fill_logit = logit(mean sigmoid(ch4)).
    """
    arr = np.asarray(batch3, dtype=np.float64)
    if arr.ndim != 4 or arr.shape[0] != 3 or arr.shape[2] != 16 or arr.shape[3] != 6:
        raise ValueError("Expected (3, n, 16, 6) prediction stack")
    if not np.isfinite(arr).all():
        raise ValueError("Nonfinite frozen predictions")
    fill_prob = own_sigmoid(arr[..., 4])
    exp = arr[..., 0] * fill_prob
    exp_mean = exp.mean(axis=0)
    fill_mean = np.clip(fill_prob.mean(axis=0), 1e-6, 1.0 - 1e-6)
    fill_logit = np.log(fill_mean / (1.0 - fill_mean))
    return exp_mean, fill_logit


def own_best_index(exp_row, fill_row, candidates, eps=1e-6):
    """Independent v41 tie-break: max; tie within eps; fill desc; holding asc; index min."""
    exp = np.asarray(exp_row, dtype=np.float64).reshape(-1)
    fil = np.asarray(fill_row, dtype=np.float64).reshape(-1)
    cand = np.asarray(candidates, dtype=np.float64)
    if exp.shape[0] != 16 or fil.shape[0] != 16 or cand.shape != (16, 6):
        raise ValueError("Tie-break expects (16,) expected/fill + (16,6) candidates")
    if not (np.isfinite(exp).all() and np.isfinite(fil).all()):
        raise ValueError("Nonfinite tie-break inputs")
    if not float(eps) == 1e-6:
        raise ValueError("tie_break_eps must be 1e-6")
    m = float(np.max(exp))
    tied = np.flatnonzero((m - exp) < float(eps))
    if len(tied) == 1:
        return int(tied[0])
    fmax = float(np.max(fil[tied]))
    tied_f = tied[(fil[tied] >= fmax - 1e-9)]
    if len(tied_f) == 1:
        return int(tied_f[0])
    holdings = cand[tied_f, 5].astype(np.float64)
    hmin = float(np.min(holdings))
    tied_h = tied_f[holdings <= hmin + 1e-12]
    return int(np.min(tied_h))


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


def own_frame(exp_mat, fill_mat, cand_grid, fold_of, part, ds_cfg, expiry, tag):
    """Own v41 signal builder: gate en_best>0 + top-8/fold fallback + freq loop."""
    exp_mat = np.asarray(exp_mat, dtype=np.float64)
    fill_mat = np.asarray(fill_mat, dtype=np.float64)
    n = len(part)
    if exp_mat.shape != (n, 16) or fill_mat.shape != (n, 16):
        raise ValueError("expected/fill shape mismatch")
    en_best = exp_mat.max(axis=1)
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        gate = idx[en_best[idx] > 0.0]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= 8:
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            top = idx[np.argsort(-en_best[idx], kind="stable")[:min(8, len(idx))]]
            selected.update(gate.tolist())
            selected.update(top.tolist())
            fallback_adds[str(f)] = int(len(set(top.tolist()) - set(gate.tolist())))
    policy_max = int(ds_cfg["policy"]["maximum_signals_per_month"])
    policy_cd = int(ds_cfg["policy"]["cooldown_days"])
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    rows = []
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        ts = pd.Timestamp(row.signal_time)
        month = ts.strftime("%Y-%m")
        if ts < next_allowed or monthly[month] >= policy_max:
            continue
        k = own_best_index(exp_mat[i], fill_mat[i], cand_grid, eps=1e-6)
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        rows.append({"bar_index": int(row.bar_index), "signal_time": ts,
                     "fold_test": int(fold_of[i]),
                     "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
                     "direction": int(cand_grid[k, 0]), "candidate_id": int(k),
                     **geo,
                     "expected_net_percent": float(exp_mat[i, k]),
                     "en_best": float(en_best[i]),
                     "calibrated": bool(tag == "valfit"),
                     "entry_expiry_bars": int(expiry), "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = ts + pd.Timedelta(days=policy_cd)
    frame = pd.DataFrame(rows)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": int(len(frame))}
    return frame, info, en_best


def own_monthly(final_equity_value, span_years):
    return float((float(final_equity_value) / 100.0) ** (1.0 / (12.0 * span_years)) - 1.0)


def own_rank_corr(exp_mat, tgt_mat):
    a = pd.DataFrame(np.asarray(exp_mat, dtype=np.float64)).rank(axis=1).to_numpy()
    b = pd.DataFrame(np.asarray(tgt_mat, dtype=np.float64)).rank(axis=1).to_numpy()
    a -= a.mean(axis=1, keepdims=True)
    b -= b.mean(axis=1, keepdims=True)
    den = np.sqrt((a * a).sum(axis=1) * (b * b).sum(axis=1))
    valid = den > 0
    out = np.full(exp_mat.shape[0], np.nan)
    out[valid] = (a * b).sum(axis=1)[valid] / den[valid]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]

    assert list(cfg["branches"]) == WANT, "v115 pre-spec must be exactly the 4 identity+valfit branches"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"
    fc = cfg["frozen_constants"]
    assert list(map(int, fc["seeds"])) == [1729, 1730, 1731]
    assert int(fc["n_folds"]) == 11
    assert int(fc["n_decisions_expected"]) == 4076
    assert int(fc["maximum_signals_per_month"]) == 4
    assert int(fc["cooldown_days"]) == 5
    assert abs(float(fc["tp1_fraction"]) - 0.5) < 1e-12
    assert int(fc["min_eligible_decisions"]) == 50
    assert abs(float(fc["tie_break_eps"]) - 1e-6) < 1e-18
    assert float(fc["gate_floor"]) == 0.0
    assert int(fc["fallback_topk_per_fold"]) == 8

    plan = json.loads((root / cfg["frozen_inputs"]["model_plan"]).read_text(encoding="utf-8"))
    assert plan.get("model_family") == fc["model_family_expected"], "plan must be v41"

    # --- VERIFY frozen v41 download presence: 33 test + 33 val else STOP ---
    src = root / cfg["frozen_inputs"]["predictions_dir"]
    miss_t, miss_v = [], []
    for seed in fc["seeds"]:
        for fold in range(int(fc["n_folds"])):
            t = src / cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            v = src / cfg["frozen_inputs"]["val_predictions_pattern"].format(seed=seed, fold=fold)
            if not t.exists():
                miss_t.append(str(t))
            if not v.exists():
                miss_v.append(str(v))
    print(json.dumps({"verify_v41": {"expected_test": 33, "found_test": 33 - len(miss_t),
                                     "expected_val": 33, "found_val": 33 - len(miss_v),
                                     "missing_test": miss_t[:3], "missing_val": miss_v[:3]}}), flush=True)
    if miss_t or miss_v:
        raise FileNotFoundError(f"STOP: missing test {len(miss_t)}/33 or val {len(miss_v)}/33")

    # --- frozen decisions / candles / costs / labels / plan ---
    decisions = pd.read_parquet(root / cfg["frozen_inputs"]["decisions"])
    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    ds_cfg = json.loads((root / cfg["frozen_inputs"]["dataset_config"]).read_text(encoding="utf-8"))
    assert abs(float(ds_cfg["costs"]["fee_rate_per_fill"]) - float(fc["dataset_base_fee"])) < 1e-12
    expiry = int(ds_cfg["entry_expiry_bars"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert expiry == int(fc["entry_expiry_bars_expected"]) == 12
    assert cap == int(fc["holding_cap_bars_expected"]) == 2016
    assert int(ds_cfg["policy"]["maximum_signals_per_month"]) == 4
    assert int(ds_cfg["policy"]["cooldown_days"]) == 5
    parent = json.loads((root / cfg["frozen_inputs"]["parent_plan"]).read_text(encoding="utf-8"))
    span_years = ((pd.Timestamp(parent["complete_evaluation_until"])
                   - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    with np.load(root / cfg["frozen_inputs"]["labels"], allow_pickle=False) as z:
        labels_all = z["labels"]
    assert labels_all.shape[1] == 16 and labels_all.shape[2] == 3, "labels shape"

    # --- R published cross-check (read-only: frozen config values must equal R summary file) ---
    r_sum = json.loads((root / cfg["frozen_inputs"]["r_summary_read_only"]).read_text(encoding="utf-8"))
    for branch, spec in cfg["branch_spec"].items():
        pub = cfg["r_published_exact"][branch]
        rval = r_sum["branches"][spec["r_branch"]][spec["r_scenario"]]
        for k in ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"):
            assert float(pub[k]) == float(rval[k]), f"R published drift {branch} {k}"
        assert int(pub["trades"]) == int(rval["trades"]), f"R published drift {branch} trades"

    # --- partitions (frozen continuous folds, label_end < global end) ---
    end = pd.Timestamp(parent["complete_evaluation_until"])
    partitions = []
    for s, e in parent["folds"]:
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        partitions.append(np.flatnonzero(((decisions["signal_time"] >= s)
                                          & (decisions["signal_time"] < e)
                                          & (decisions["label_end"] < end)).to_numpy()))
    indices = np.concatenate(partitions)
    assert int(len(indices)) == 4076, f"decision count changed: {len(indices)}"
    part = decisions.iloc[indices].reset_index(drop=True)
    fold_of = np.concatenate([np.full(len(p), f, dtype=np.int64) for f, p in enumerate(partitions)])
    labsub = np.asarray(labels_all[indices], dtype=np.float64)

    cand_grid = own_grid(ds_cfg)
    assert cand_grid.shape == (16, 6), f"candidate schema changed: {cand_grid.shape}"

    # --- own test ensemble per fold (concatenated in fold order) ---
    exp_parts, fill_parts = [], []
    for fold, sel in enumerate(partitions):
        batch = []
        for seed in fc["seeds"]:
            q = src / cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            arr = np.load(str(q), allow_pickle=False)
            if arr.shape != (len(sel), 16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"Invalid test prediction {q}: {arr.shape}")
            batch.append(arr)
        e_mean, f_logit = own_ensemble_fold(np.stack(batch, axis=0))
        exp_parts.append(e_mean)
        fill_parts.append(f_logit)
    exp_raw = np.concatenate(exp_parts, axis=0)
    fill_logits = np.concatenate(fill_parts, axis=0)
    assert exp_raw.shape == (4076, 16) and fill_logits.shape == (4076, 16)

    # --- own TRUE val-fit per-fold isotonic VAL-ONLY (NO winsor, faithful to R v112) ---
    n = len(part)
    cal = np.zeros_like(exp_raw)
    calib_records, fold_offsets = [], []
    off = 0
    for fold, sel in enumerate(partitions):
        fold_offsets.append(off)
        cur = slice(off, off + len(sel))
        vbatch = []
        for seed in fc["seeds"]:
            q = src / cfg["frozen_inputs"]["val_predictions_pattern"].format(seed=seed, fold=fold)
            arr = np.load(str(q), allow_pickle=False)
            if arr.shape[1:] != (16, 6) or not np.isfinite(arr).all():
                raise ValueError(f"Invalid val prediction {q}: {arr.shape}")
            vbatch.append(arr)
        vidx_ref = None
        for seed in fc["seeds"]:
            q = src / cfg["frozen_inputs"]["indices_pattern"].format(seed=seed, fold=fold)
            with np.load(str(q), allow_pickle=False) as ix:
                v = np.asarray(ix["validation"])
                if vidx_ref is None:
                    vidx_ref = v
                elif not np.array_equal(vidx_ref, v):
                    raise ValueError(f"Val indices differ across seeds fold {fold}")
        with np.load(str(src / cfg["frozen_inputs"]["indices_pattern"].format(
                seed=fc["seeds"][0], fold=fold)), allow_pickle=False) as ix:
            vidx = np.asarray(ix["validation"])
        v_times = decisions.iloc[vidx]["signal_time"]
        t_global = np.flatnonzero(fold_of == fold)
        t_times = part.iloc[t_global]["signal_time"]
        past_only = bool(v_times.max() < t_times.min())
        if not past_only:
            raise ValueError(f"fold {fold} val NOT past-only vs test")
        vexp, _ = own_ensemble_fold(np.stack(vbatch, axis=0))
        X = np.asarray(vexp, dtype=np.float64).ravel()
        y = np.asarray(labels_all[vidx][..., 0], dtype=np.float64).ravel()
        n_val = int(len(vidx))
        warmup = None
        if n_val < int(fc["min_eligible_decisions"]):
            warmup = "WAIT"
        if not (np.isfinite(X).all() and np.isfinite(y).all()):
            raise ValueError(f"fold {fold} nonfinite val fit inputs")
        if len(np.unique(X)) < 2:
            warmup = "WAIT"
        if warmup is not None:
            cal[cur] = exp_raw[cur]
            calib_records.append({"fold": fold, "warmup": "WAIT", "eligible_rows": n_val,
                                  "val_signal_max": str(v_times.max()),
                                  "test_signal_min": str(t_times.min()), "past_only": past_only})
        else:
            model = IsotonicRegression(out_of_bounds="clip").fit(X, y)
            mapped = model.predict(np.asarray(exp_raw[cur], dtype=np.float64).ravel())
            cal[cur] = mapped.reshape(exp_raw[cur].shape)
            xv = np.asarray(model.X_thresholds_, dtype=np.float64)
            yv = np.asarray(model.y_thresholds_, dtype=np.float64)
            assert bool(np.all(np.diff(xv) >= 0)), f"fold {fold} iso x not sorted"
            assert bool(np.all(np.diff(yv) >= -1e-12)), f"fold {fold} iso y not monotone"
            calib_records.append({"fold": fold, "warmup": None, "eligible_rows": n_val,
                                  "val_signal_max": str(v_times.max()),
                                  "test_signal_min": str(t_times.min()), "past_only": past_only,
                                  "iso_x_len": int(len(xv)), "iso_y_len": int(len(yv)),
                                  "x_min": float(xv.min()), "x_max": float(xv.max()),
                                  "y_min": float(yv.min()), "y_max": float(yv.max()),
                                  "x": [float(v) for v in xv], "y": [float(v) for v in yv]})
        off += len(sel)

    # --- own within-fold order-preservation assert (sampled, seed 0) ---
    for fold in range(int(fc["n_folds"])):
        if calib_records[fold].get("warmup") is not None:
            continue
        start = fold_offsets[fold]
        cur = slice(start, start + len(partitions[fold]))
        raw_f = exp_raw[cur].ravel()
        map_f = cal[cur].ravel()
        rng = np.random.default_rng(0)
        m = min(20000, raw_f.size * 2)
        ii = rng.integers(0, raw_f.size, size=m)
        jj = rng.integers(0, raw_f.size, size=m)
        viol = int(((raw_f[ii] < raw_f[jj] - 1e-12) & (map_f[ii] > map_f[jj] + 1e-9)).sum())
        assert viol == 0, f"fold {fold} isotonic order violated: {viol}"
    print(json.dumps({"order_assert": {"viol_order": 0,
                                       "assert": "pass (monotone up-to-ties)"}}), flush=True)
    print(json.dumps({"calibration": {"folds": len(calib_records),
                                      "warmup_folds": [r["fold"] for r in calib_records
                                                       if r.get("warmup")]}}), flush=True)

    # --- own signal frames ---
    sig_identity, info_identity, _ = own_frame(exp_raw, fill_logits, cand_grid, fold_of,
                                               part, ds_cfg, expiry, "raw")
    sig_cal, info_cal, _ = own_frame(cal, fill_logits, cand_grid, fold_of,
                                     part, ds_cfg, expiry, "valfit")
    print(json.dumps({"branch_signals": "verify_v41_identity", "n_signals": int(len(sig_identity)),
                      "coverage": float(len(sig_identity) / len(part))}), flush=True)
    print(json.dumps({"branch_signals": "verify_v41_valfit_calibrated",
                      "n_signals": int(len(sig_cal)),
                      "coverage": float(len(sig_cal) / len(part))}), flush=True)

    # --- engine sanity markers (shared infra unchanged) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    frames = {"verify_v41_identity_1x_normal": sig_identity,
              "verify_v41_identity_1x_fee055": sig_identity,
              "verify_v41_valfit_calibrated_1x_normal": sig_cal,
              "verify_v41_valfit_calibrated_1x_fee055": sig_cal}
    ds_costs = ds_cfg["costs"]
    execution = ExecutionConfig(entry_expiry_bars=int(expiry), max_holding_bars=int(cap),
                                tp1_fraction=0.5, leverage=1.0, max_leverage=1.0)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"),
                                               encoding="utf-8")

    reproduced = {}
    for branch in WANT:
        fee = float(cfg["branch_spec"][branch]["fee_rate_per_fill"])
        costs = CostModel(fee_rate_per_fill=fee,
                          funding_long_rate=float(ds_costs["funding_long_rate"]),
                          funding_short_rate=float(ds_costs["funding_short_rate"]),
                          funding_interval_hours=int(ds_costs["funding_interval_hours"]))
        base = frames[branch].drop(columns=["leverage"], errors="ignore").copy()
        res, trs = run_backtest(candles, base.copy(), SEED_EQUITY, costs, execution)
        rec = asdict(res)
        rec["monthly_geometric_net"] = own_monthly(res.final_equity, span_years)
        rec["annual_geometric_net"] = float((res.final_equity / 100.0) ** (1.0 / span_years) - 1.0)
        rec["branch_fee"] = fee
        rec["n_signals"] = int(len(base))
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
                          "trades": rec["trades"], "long": rec["long_trades"],
                          "short": rec["short_trades"], "n_signals": rec["n_signals"]},
                         default=str), flush=True)

    # --- own bias/rank/coverage deltas (is the mild worsening real?) ---
    per_raw = own_rank_corr(exp_raw, labsub[..., 0])
    per_cal = own_rank_corr(cal, labsub[..., 0])
    valid_raw = per_raw[~np.isnan(per_raw)]
    valid_cal = per_cal[~np.isnan(per_cal)]
    topk = 408
    for tag, mat in (("raw", exp_raw), ("valfit", cal)):
        order = np.argsort(mat.max(axis=1), kind="stable")[-topk:]
        k = mat[order].argmax(axis=1)
        pe = mat[order, k]
        rn = labsub[order, k, 0]
        print(json.dumps({"topdecile_" + tag: {"pred_mean": float(pe.mean()),
                                               "obs_mean": float(rn.mean()),
                                               "bias": float(pe.mean() - rn.mean())}}), flush=True)
    print(json.dumps({"rank_raw": float(valid_raw.mean()), "rank_cal": float(valid_cal.mean()),
                      "n_valid_raw": int(len(valid_raw)),
                      "n_valid_cal": int(len(valid_cal))}), flush=True)

    deltas, verdicts = {}, {}
    for branch in WANT:
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
            "n_decisions": int(len(indices)),
            "n_signals_identity": int(len(sig_identity)),
            "n_signals_calibrated": int(len(sig_cal)),
            "gate_hits_identity": info_identity["gate_hits_by_fold"],
            "gate_hits_calibrated": info_cal["gate_hits_by_fold"],
            "fallback_adds_identity": info_identity["fallback_adds_by_fold"],
            "fallback_adds_calibrated": info_cal["fallback_adds_by_fold"],
            "calib_eligible_rows": [r["eligible_rows"] for r in calib_records],
            "calib_warmup_folds": [r["fold"] for r in calib_records if r.get("warmup")],
            "candidate_causes_ordered": [
                "(1) own ensemble mean vs R combine (penalty/dtype/fill-logit path)",
                "(2) own tie-break vs R deterministic_best_index (eps/fill/holding/index order)",
                "(3) own geometry vs R prices/grid (unit/min-risk/ordered checks)",
                "(4) isotonic fit inputs (val ravel order, labels ch0, clip bounds)",
                "(5) gate floor strictness / fallback top-8 stable-order",
                "(6) frequency loop order (partition vs global chronological)",
                "(7) fee application path / monthly duration window",
                "(8) frozen-prediction presence/order drift (33+33 identity)",
                "(9) engine version drift (ohlc-v2 markers checked above)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v115-verifyv41valfit",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "mission_claim": cfg["mission_claim"],
        "span_years": span_years,
        "tolerance_abs": tol,
        "r_published_exact": cfg["r_published_exact"],
        "reproduced": reproduced,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "selection_detail": {
            "gate_hits_identity": info_identity["gate_hits_by_fold"],
            "fallback_adds_identity": info_identity["fallback_adds_by_fold"],
            "n_selected_identity": info_identity["n_selected"],
            "n_signals_identity": int(len(sig_identity)),
            "gate_hits_calibrated": info_cal["gate_hits_by_fold"],
            "fallback_adds_calibrated": info_cal["fallback_adds_by_fold"],
            "n_selected_calibrated": info_cal["n_selected"],
            "n_signals_calibrated": int(len(sig_cal)),
        },
        "calibration_records": calib_records,
        "triage": triage,
        "artifacts": {b: f"{b}/{{signals.parquet,trades.csv,metrics.json}}" for b in WANT},
        "causal_notes": ("past-only closed-candle; TRUE val-fit per-fold VAL-ONLY, NO winsor "
                         "(faithful to R v112); per-fold val past-only vs test verified; "
                         "fills from next bar; exploratory labels on opened 2023-2026 interval"),
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
        "warning": ("Exploratory verification on the opened development interval only. "
                    "Drawdown is trade-candle-close sampled. No promotion, no live claim."),
        "input_sha256": {q: sha256(root / q) for q in
                         (cfg["frozen_inputs"]["candles"],
                          cfg["frozen_inputs"]["decisions"],
                          cfg["frozen_inputs"]["labels"],
                          cfg["frozen_inputs"]["dataset_config"],
                          cfg["frozen_inputs"]["parent_plan"],
                          cfg["frozen_inputs"]["model_plan"],
                          cfg["frozen_inputs"]["r_config_read_only"],
                          "configs/opencode_v115_verifyv41valfit.json",
                          "scripts/opencode_r41a_verifyv41valfit.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
