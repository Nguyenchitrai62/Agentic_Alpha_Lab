"""Opencode v92 (R30-A2 VERIFYV40): independent rebuild of R-v40audit identity rank_en_1x.

Rebuilds from FROZEN inputs only (read, never refit):
  predictions = artifacts/kaggle/v40_capatpolicy_download/capatpolicy-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/predictions.npy (33 files)
  candles/costs/decisions = data/processed/swing_regime_research_v4/
  v40 policy + R numbers are READ-ONLY references (values copied into
  configs/opencode_v92_verifyv40.json at pre-spec time; this driver never
  imports R's driver nor any opencode_r25m_v40_* / opencode_v38b_replay modules).

Own implementation (independent):
  - own_combine: mean_3seeds penalty 0.0 in float64 (expected=ch0*sigmoid(ch4)).
  - own gate: en_best_capped>0 per fold-test + fallback top-8 (stable, causal).
  - own deterministic tie-break eps=1e-6 among fill>=0.25 (fill-desc, holding-asc, index).
  - own geometry: prices() verbatim formula from dataset cfg (no import of R driver).
  - own frequency: global chronological monthly-cap-4 + cooldown-5d loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 2 branches (shared identity frame, fee-only difference):
      verify_identity_1x_normal (fee 0.0002) + verify_identity_1x_fee055 (fee 0.00055).
  - compares total_return / max_drawdown / monthly_geometric_net /
    final_equity within 1e-6 + trades/long/short exact.

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
EPS_TIE = 1e-6
FILL_MIN = 0.25


def own_sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, dtype=np.float64), -40.0, 40.0)))


def own_combine_mean(stack3):
    """Independent mean_3seeds combine (penalty 0.0).

    stack3: (3, n, 16, 6) float arrays (capped map-v8 exports).
    Returns (ensemble_expected (n,16), ensemble_fill (n,16), ensemble_logit (n,16)).
    Formula mirrors library semantics without importing R's driver:
      fill_s = sigmoid(ch4_s); exp_s = ch0_s * fill_s;
      ensemble_expected = mean_s exp_s; ensemble_fill = mean_s fill_s.
    """
    arr = np.asarray(stack3, dtype=np.float64)
    if arr.ndim != 4 or arr.shape[0] != 3 or arr.shape[2] != 16 or arr.shape[3] != 6:
        raise ValueError("Expected (3, n, 16, 6) prediction stack")
    if not np.isfinite(arr).all():
        raise ValueError("Nonfinite frozen predictions")
    fill = own_sigmoid(arr[..., 4])
    expected = arr[..., 0] * fill
    ens_exp = expected.mean(axis=0)
    ens_fill = fill.mean(axis=0)
    ens_fill = np.clip(ens_fill, 1e-6, 1.0 - 1e-6)
    ens_logit = np.log(ens_fill / (1.0 - ens_fill))
    return ens_exp, ens_fill, ens_logit


def own_best_index_among_eligible(exp_row, logit_row, cand, elig_idx):
    """Deterministic tie-break among eligible indices only (causal, no fit)."""
    exp = np.asarray(exp_row, dtype=np.float64).reshape(-1)
    logit = np.asarray(logit_row, dtype=np.float64).reshape(-1)
    cand = np.asarray(cand, dtype=np.float64)
    elig = np.asarray(elig_idx, dtype=np.int64)
    if exp.shape[0] != 16 or logit.shape[0] != 16 or cand.shape != (16, 6):
        raise ValueError("Tie-break expects (16,) rows + (16,6) candidates")
    if len(elig) == 0:
        raise ValueError("No eligible candidate")
    m = float(np.max(exp[elig]))
    tied = elig[(m - exp[elig]) < EPS_TIE]
    if len(tied) == 1:
        return int(tied[0])
    fmax = float(np.max(logit[tied]))
    tied_f = tied[(logit[tied] >= fmax - 1e-9)]
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


def verify_monthly(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / (12.0 * span_years)) - 1.0)


def verify_annual(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / span_years) - 1.0)


def build_branch_costs(ds_costs, branch_fee):
    return CostModel(
        fee_rate_per_fill=float(branch_fee),
        funding_long_rate=float(ds_costs["funding_long_rate"]),
        funding_short_rate=float(ds_costs["funding_short_rate"]),
        funding_interval_hours=int(ds_costs["funding_interval_hours"]),
    )


def build_1x_execution(expiry_bars, cap_bars, tp1_frac):
    return ExecutionConfig(
        entry_expiry_bars=int(expiry_bars),
        max_holding_bars=int(cap_bars),
        leverage=1.0,
        max_leverage=1.0,
        tp1_fraction=float(tp1_frac),
    )


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
    assert list(cfg["branches"]) == want, "v92 pre-spec must be exactly the 2 identity-fee branches"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"

    fc = cfg["frozen_constants"]
    assert list(map(int, fc["seeds"])) == [1729, 1730, 1731]
    assert int(fc["n_folds"]) == 11
    assert abs(float(fc["tie_break_eps"]) - 1e-6) < 1e-18
    assert abs(float(fc["minimum_fill_score"]) - 0.25) < 1e-12
    assert int(fc["maximum_signals_per_month"]) == 4
    assert int(fc["cooldown_days"]) == 5
    assert abs(float(fc["tp1_fraction"]) - 0.5) < 1e-12

    # --- frozen prediction presence: 33 files else STOP ---
    pred_dir = root / cfg["frozen_inputs"]["predictions_dir"]
    pred_files = sorted(pred_dir.rglob("predictions.npy"))
    if len(pred_files) != int(cfg["frozen_inputs"]["predictions_n_expected"]):
        raise SystemExit(
            f"STOP: frozen v40 predictions count {len(pred_files)} != "
            f"{cfg['frozen_inputs']['predictions_n_expected']}"
        )
    assert len(pred_files) == 33, "v40 must have exactly 33 predictions.npy (3 seeds x 11 folds)"

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
    # holding days are {3,7} in column 5
    assert set(np.unique(cand_grid[:, 5]).tolist()) == {3.0, 7.0}

    # --- ensemble per fold (own combine), concatenate in fold order ---
    ens_exp_parts, ens_fill_parts, ens_logit_parts = [], [], []
    for fold, sel in enumerate(partitions):
        stack = []
        for seed in fc["seeds"]:
            pat = cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            path = pred_dir / pat
            pred = np.load(str(path), allow_pickle=False)
            if pred.shape != (len(sel), 16, 6) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path} {pred.shape} vs {(len(sel),16,6)}")
            stack.append(np.asarray(pred, dtype=np.float64))
        stack = np.stack(stack, axis=0)
        e_exp, e_fill, e_logit = own_combine_mean(stack)
        # bounded check at policy (capped unconditional must be within +-0.02 + eps)
        unb = e_exp  # ensemble expected IS unconditional (mean of capped)
        if float(np.max(np.abs(unb))) > 0.02 + 1e-6 + 1e-9:
            raise ValueError(f"Policy boundedness violated at fold {fold}: max|unb|={float(np.max(np.abs(unb)))}")
        ens_exp_parts.append(e_exp)
        ens_fill_parts.append(e_fill)
        ens_logit_parts.append(e_logit)
    ens_exp = np.concatenate(ens_exp_parts, axis=0)
    ens_fill = np.concatenate(ens_fill_parts, axis=0)
    ens_logit = np.concatenate(ens_logit_parts, axis=0)
    assert ens_exp.shape == (len(indices), 16)

    part = decisions.iloc[indices].reset_index(drop=True)
    # fold_of was built in partition order == part row order (fold0..fold10 chronological)
    en_best = ens_exp.max(axis=1)

    # --- own gate per fold-test ---
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(fold_of.tolist())):
        idx = np.flatnonzero(fold_of == f)
        gate = idx[en_best[idx] > float(fc["policy_margin"])]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= int(fc["policy_n_min"]):
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            order = np.argsort(-en_best[idx], kind="stable")[:min(int(fc["policy_n_min"]), len(idx))]
            top = idx[order]
            selected.update(gate.tolist())
            selected.update(top.tolist())
            fallback_adds[str(f)] = int(len(set(top.tolist()) - set(gate.tolist())))

    # --- own candidate + geometry + frequency loop ---
    policy_max = int(ds_cfg["policy"]["maximum_signals_per_month"])
    policy_cd = int(ds_cfg["policy"]["cooldown_days"])
    assert policy_max == int(fc["maximum_signals_per_month"]) == 4
    assert policy_cd == int(fc["cooldown_days"]) == 5
    monthly = Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    signals = []
    n_wait_ineligible = 0
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy_max:
            continue
        elig = np.flatnonzero(ens_fill[i] >= float(fc["minimum_fill_score"]))
        if len(elig) == 0:
            n_wait_ineligible += 1
            continue
        k = own_best_index_among_eligible(ens_exp[i], ens_logit[i], cand_grid, elig)
        geo = own_prices(float(row.close), float(row.atr5), float(row.atr4), cand_grid[k], ds_cfg)
        signals.append({
            "bar_index": int(row.bar_index),
            "signal_time": timestamp,
            "fold_test": int(fold_of[i]),
            "action": "LONG" if int(cand_grid[k, 0]) == 1 else "SHORT",
            "direction": int(cand_grid[k, 0]),
            "candidate_id": int(k),
            **geo,
            "expected_net_percent": float(ens_exp[i, k]),
            "en_best": float(en_best[i]),
            "ohlc_fill_score": float(ens_fill[i, k]),
            "calibrated": False,
            "entry_expiry_bars": int(expiry),
            "tp1_fraction": float(fc["tp1_fraction"]),
        })
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=policy_cd)

    frame_all = pd.DataFrame(signals)
    assert int(len(frame_all)) == int(fc["n_signals_expected"]) == 135, (
        f"identity signal count changed: {len(frame_all)} != 135 "
        f"(gate_hits={gate_hits}, fallback={fallback_adds})"
    )
    ordered_flag = bool((frame_all["bar_index"].to_numpy()[:-1]
                         <= frame_all["bar_index"].to_numpy()[1:]).all())
    # deterministic backtest order (stable; no-op if already chronological)
    frame_all = frame_all.sort_values("bar_index", kind="mergesort").reset_index(drop=True)

    # identity 1x frame: drop leverage column if present (own_prices sets 1.0; engine uses ExecutionConfig)
    base = frame_all.drop(columns=["leverage"], errors="ignore").copy()

    # --- engine identity sanity (own markers, ohlc-v2) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    execution = build_1x_execution(expiry, cap, float(fc["tp1_fraction"]))

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    reproduced = {}
    for branch in want:
        spec = cfg["branch_spec"][branch]
        fee = float(spec["fee_rate_per_fill"])
        costs = build_branch_costs(ds_costs, fee)
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
              and dd["trades"] == 0 and dd["long_trades"] == 0 and dd["short_trades"] == 0)
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
            "n_selected": int(len(selected)),
            "n_signals": int(len(frame_all)),
            "gate_hits_by_fold": gate_hits,
            "fallback_adds_by_fold": fallback_adds,
            "n_wait_no_fill_eligible": int(n_wait_ineligible),
            "execution": {"lev": 1.0, "max": 1.0, "tp1": float(fc["tp1_fraction"]),
                          "expiry": expiry, "holding_cap": cap},
            "candidate_causes_ordered": [
                "(1) combine penalty/mean (own float64 mean vs R combine)",
                "(2) gate capped-vs-raw / margin 0.0 / fallback top-8 order",
                "(3) tie-break eligible-set + fill/logit-desc + holding-asc + index order",
                "(4) fill-eligibility threshold 0.25 (prob vs logit)",
                "(5) geometry/prices (unit/min-risk/order checks)",
                "(6) frequency monthly-4/cooldown-5d chronological order",
                "(7) fee application path (branch CostModel rebuild)",
                "(8) monthly/duration formula drift (parent plan window)",
                "(9) frozen-prediction count/order drift (33-file identity)",
                "(10) engine version drift (ohlc-v2 markers)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v92-verifyv40",
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
            "gate_hits_by_fold": gate_hits,
            "fallback_adds_by_fold": fallback_adds,
            "n_selected": int(len(selected)),
            "n_signals": int(len(frame_all)),
            "n_wait_no_fill_eligible": int(n_wait_ineligible),
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
                          "configs/opencode_v92_verifyv40.json",
                          "scripts/opencode_r30a_verifyv40.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
