"""Opencode v98 (R34-A2 VERIFYV55C): independent rebuild of R-v55c audit rankonly_en_1x.

Rebuilds from FROZEN inputs only (read, never refit):
  predictions = artifacts/kaggle/v55c_rankonly_download/rankonly-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/predictions.npy (33 files,
                RAW rank logits (n,16), NOT v8 blocks)
  candles/costs/decisions = data/processed/swing_regime_research_v4/
  v55 policy + R numbers are READ-ONLY references (values frozen into
  configs/opencode_v98_verifyv55c.json at pre-spec time; this driver never
  imports R's driver (opencode_r33a_v55d_portfolio) nor any
  opencode_r17b_rankonly_* / train_tcn_kaggle modules).

Own implementation (independent, float64):
  - own_combine: arithmetic mean_3seeds of RAW rank logits per fold-test.
  - own top1/margin: argmax first-max deterministic; margin = top1 - max(other 15).
  - own gate: margin > threshold_en(fold) strict, NO fallback, WAIT else.
  - own geometry: prices() verbatim formula from dataset cfg (no import of R driver).
  - own frequency: global chronological monthly-cap-4 + cooldown-5d loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 2 branches (shared identity frame, fee-only difference):
      verify_identity_1x_normal (fee 0.0002) + verify_identity_1x_fee055 (fee 0.00055),
      both via run_backtest (mirrors R run_branch legs; no run_stress here).
  - compares total_return / max_drawdown / monthly_geometric_net /
    final_equity within 1e-6 + trades/long/short exact vs R published.

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

    want = ["verify_identity_1x_normal", "verify_identity_1x_fee055"]
    assert list(cfg["branches"]) == want, "v98 pre-spec must be exactly the 2 identity-fee branches"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"

    fc = cfg["frozen_constants"]
    assert list(map(int, fc["seeds"])) == [1729, 1730, 1731]
    assert int(fc["n_folds"]) == 11
    assert int(fc["maximum_signals_per_month"]) == 4
    assert int(fc["cooldown_days"]) == 5
    assert abs(float(fc["tp1_fraction"]) - 0.5) < 1e-12

    # --- frozen prediction presence: 33 files else STOP ---
    pred_dir = root / cfg["frozen_inputs"]["predictions_dir"]
    pred_files = sorted(pred_dir.rglob("predictions.npy"))
    if len(pred_files) != int(cfg["frozen_inputs"]["predictions_n_expected"]):
        raise SystemExit(
            f"STOP: frozen v55c predictions count {len(pred_files)} != "
            f"{cfg['frozen_inputs']['predictions_n_expected']}"
        )
    assert len(pred_files) == 33, "v55c must have exactly 33 predictions.npy (3 seeds x 11 folds)"

    # --- frozen decisions / candles / costs ---
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

    # --- thresholds: frozen pre-spec copy must equal R audit file (read-only check) ---
    audit_ro = json.loads((root / cfg["frozen_inputs"]["r_audit_read_only"]).read_text(encoding="utf-8"))
    thr_audit = audit_ro["thresholds_ensemble_mean"]
    thr_frozen = {str(k): float(v) for k, v in fc["thresholds_ensemble_mean"].items()}
    assert set(thr_frozen) == set(thr_audit), "threshold fold keys differ from R audit"
    for k in thr_frozen:
        assert thr_frozen[k] == float(thr_audit[k]), f"threshold fold {k} differs from R audit"

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
    assert set(np.unique(cand_grid[:, 5]).tolist()) == {3.0, 7.0}

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
    top1, margins = own_top1_margin(ensemble)

    # --- own gate per fold-test: margin > threshold, NO fallback ---
    chosen = np.full(len(part), -1, dtype=np.int64)
    picks_by_fold = {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        thr = float(thr_frozen[str(f)])
        pick = idx[margins[idx] > thr]
        chosen[pick] = top1[pick]
        picks_by_fold[str(f)] = int(len(pick))
    n_picked = int((chosen >= 0).sum())
    pick_rate = float((chosen >= 0).mean())

    # --- own frequency loop (global chronological, partition order) ---
    policy_max = int(ds_cfg["policy"]["maximum_signals_per_month"])
    policy_cd = int(ds_cfg["policy"]["cooldown_days"])
    assert policy_max == int(fc["maximum_signals_per_month"]) == 4
    assert policy_cd == int(fc["cooldown_days"]) == 5
    monthly = Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    signals = []
    for i, row in enumerate(part.itertuples()):
        k = int(chosen[i])
        if k < 0:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy_max:
            continue
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        signals.append({
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

    frame_all = pd.DataFrame(signals)
    ordered_flag = bool((frame_all["bar_index"].to_numpy()[:-1]
                         <= frame_all["bar_index"].to_numpy()[1:]).all()) if len(frame_all) else True

    # --- identity diagnostics vs R (soft: still backtest on mismatch, verdict FAIL) ---
    exp_picks = {str(k): int(v) for k, v in fc["picks_by_fold_expected"].items()}
    signal_identity = (
        n_picked == int(fc["picks_pre_frequency_expected"])
        and picks_by_fold == exp_picks
        and int(len(frame_all)) == int(fc["n_signals_expected"])
    )

    # --- engine identity sanity (own markers, ohlc-v2) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    # identity 1x frame: drop leverage column (engine uses ExecutionConfig)
    base = frame_all.drop(columns=["leverage"], errors="ignore").copy()
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

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    reproduced = {}
    for branch in want:
        spec = cfg["branch_spec"][branch]
        fee = float(spec["fee_rate_per_fill"])
        costs = build_branch_costs(fee)
        res, trs = run_backtest(candles, base.copy(), SEED_EQUITY, costs, execution)
        rec = asdict(res)
        rec["monthly_geometric_net"] = verify_monthly(res.final_equity, span_years)
        rec["annual_geometric_net"] = verify_annual(res.final_equity, span_years)
        rec["branch_fee"] = fee
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
                          "long": rec.get("long_trades"),
                          "short": rec.get("short_trades")}, default=str), flush=True)

    deltas, verdicts = {}, {}
    for branch in want:
        pub = cfg["r_published_exact"][branch]
        rep = reproduced[branch]
        dd = {k: float(rep[k] - pub[k]) for k in
              ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity")}
        dd["trades"] = int(rep["trades"] - pub["trades"])
        dd["long_trades"] = int(rep.get("long_trades", -1) - pub["long_trades"])
        dd["short_trades"] = int(rep.get("short_trades", -1) - pub["short_trades"])
        ok = (all(abs(dd[k]) <= tol for k in
                  ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"))
              and dd["trades"] == 0 and dd["long_trades"] == 0 and dd["short_trades"] == 0
              and signal_identity)
        deltas[branch] = dd
        verdicts[branch] = "PASS" if ok else "FAIL"

    overall = all(v == "PASS" for v in verdicts.values())
    triage = {"status": "no mismatch - independent rebuild agrees" if overall
              else "MISMATCH - cause under investigation",
              "diagnostics": {}}
    if not overall:
        triage["diagnostics"] = {
            "input_sorted_by_bar_index": ordered_flag,
            "span_years": span_years,
            "n_predictions": len(pred_files),
            "n_decisions": int(len(indices)),
            "signal_identity_match": bool(signal_identity),
            "n_picked_pre_frequency": n_picked,
            "n_picked_expected": int(fc["picks_pre_frequency_expected"]),
            "pick_rate_pre_frequency": pick_rate,
            "picks_by_fold": picks_by_fold,
            "picks_by_fold_expected": exp_picks,
            "n_signals": int(len(frame_all)),
            "n_signals_expected": int(fc["n_signals_expected"]),
            "execution": {"lev": 1.0, "max": 1.0, "tp1": float(fc["tp1_fraction"]),
                          "expiry": expiry, "holding_cap": cap},
            "candidate_causes_ordered": [
                "(1) combine mean-vs-median/penalty/dtype (own float64 mean vs R stacked.mean)",
                "(2) gate threshold copy vs audit / fallback present-vs-absent / strict-vs-nonstrict >",
                "(3) top1 first-max vs last-max / margin second-max definition",
                "(4) geometry/prices (unit/min-risk/order checks)",
                "(5) frequency monthly-4/cooldown-5d chronological or partition order",
                "(6) fee application path (branch CostModel rebuild vs R run_branch fee leg)",
                "(7) monthly/duration formula drift (parent plan window)",
                "(8) frozen-prediction count/order drift (33-file identity, RAW logits vs v8 blocks)",
                "(9) engine version drift (ohlc-v2 markers)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v98-verifyv55c",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "frozen_inputs": cfg["frozen_inputs"],
        "policy_frozen": cfg["policy_frozen"],
        "input_sorted_by_bar_index": ordered_flag,
        "span_years": span_years,
        "tolerance_abs": tol,
        "r_published_exact": cfg["r_published_exact"],
        "reproduced": reproduced,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "selection_detail": {
            "n_picked_pre_frequency": n_picked,
            "pick_rate_pre_frequency": pick_rate,
            "picks_by_fold": picks_by_fold,
            "n_signals": int(len(frame_all)),
            "signal_identity_match": bool(signal_identity),
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
                          "configs/opencode_v98_verifyv55c.json",
                          "scripts/opencode_r34a_verifyv55c.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
