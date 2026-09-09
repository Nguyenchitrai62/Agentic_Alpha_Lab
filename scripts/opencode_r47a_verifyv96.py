"""Opencode v128 (A2-ARCH VERIFYV96, 9th verification): independent rebuild of R-v96audit (v96b).

Rebuilds from FROZEN inputs only (read, never refit):
  predictions = artifacts/kaggle/v96_transformer_download/transformer-training
                seed{1729,1730,1731}/temporal_neural/fold_{0..10}/predictions.npy
                (33 test files, map-v8 RAW TRADEABLE percent (n,16,6); VERIFY else STOP)
  candles/costs/decisions = data/processed/swing_regime_research_v4/
  R policy + R numbers are READ-ONLY references (values frozen into
  configs/opencode_v128_verifyv96.json at pre-spec time; this driver never
  imports R's audit driver nor ensemble_value.combine,
  nor opencode_r32m_transformer_* train/model modules).

Own implementation (independent, float64):
  - own_ensemble_fold: per-seed expected = ch0*sigmoid(ch4); arithmetic mean_3seeds;
    own fill_logit = logit(mean sigmoid(ch4)) for tie-break only.
  - own_best_index: max(exp); tie set within eps=1e-6; fill-logit desc (gap 1e-9);
    holding asc; index min.
  - own geometry: grid/prices formulas re-derived from dataset cfg (no import).
  - own gate: v96 policy floor en_best_raw > 0.0 + fallback top-8/fold-test on the
    same scale; own chronological monthly-cap-4 + cooldown-5d frequency loop.
  - own monthly: ratio^(1/(12*years))-1 with years from parent plan.
  - 2 branches: verify_identity_1x_normal (fee 0.0002) + verify_identity_1x_fee055
    (fee 0.00055, same identity frame, fee-only change) via run_backtest
    (shared ohlc-v2 infra only); compares total_return / max_drawdown /
    monthly_geometric_net / final_equity within 1e-6 + trades/long/short/n_signals
    exact vs R v96b published.

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
WANT = ["verify_identity_1x_normal", "verify_identity_1x_fee055"]


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
    """Independent v96 tie-break: max; tie within eps; fill desc; holding asc; index min."""
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


def own_frame(exp_mat, fill_mat, cand_grid, fold_of, part, ds_cfg, expiry):
    """Own v96 signal builder: gate en_best>0 + top-8/fold fallback + freq loop."""
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
                     "en_best_raw_tradeable": float(en_best[i]),
                     "calibrated": False,
                     "entry_expiry_bars": int(expiry), "tp1_fraction": 0.5})
        monthly[month] += 1
        next_allowed = ts + pd.Timedelta(days=policy_cd)
    frame = pd.DataFrame(rows)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": int(len(frame))}
    return frame, info, en_best


def own_monthly(final_equity_value, span_years):
    return float((float(final_equity_value) / 100.0) ** (1.0 / (12.0 * span_years)) - 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]

    assert list(cfg["branches"]) == WANT, "v128 pre-spec must be exactly the 2 identity branches"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"
    fc = cfg["frozen_constants"]
    assert list(map(int, fc["seeds"])) == [1729, 1730, 1731]
    assert int(fc["n_folds"]) == 11
    assert int(fc["n_decisions_expected"]) == 4076
    assert int(fc["maximum_signals_per_month"]) == 4
    assert int(fc["cooldown_days"]) == 5
    assert abs(float(fc["tp1_fraction"]) - 0.5) < 1e-12
    assert abs(float(fc["tie_break_eps"]) - 1e-6) < 1e-18
    assert float(fc["gate_floor"]) == 0.0
    assert int(fc["fallback_topk_per_fold"]) == 8
    assert int(fc["n_signals_expected"]) == 135
    assert int(fc["picks_pre_frequency_expected"]) == 3934

    plan = json.loads((root / cfg["frozen_inputs"]["model_plan"]).read_text(encoding="utf-8"))
    assert plan.get("model_family") == fc["model_family_expected"], "plan must be v96"

    # --- VERIFY frozen v96 download presence: 33 test files else STOP ---
    src = root / cfg["frozen_inputs"]["predictions_dir"]
    pred_files = sorted(src.rglob("predictions.npy"))
    print(json.dumps({"verify_v96": {"expected_test": 33, "found_test": len(pred_files)}}), flush=True)
    if len(pred_files) != int(cfg["frozen_inputs"]["predictions_n_test_expected"]):
        raise SystemExit(
            f"STOP: frozen v96 predictions count {len(pred_files)} != "
            f"{cfg['frozen_inputs']['predictions_n_test_expected']}"
        )
    assert len(pred_files) == 33, "v96 must have exactly 33 predictions.npy (3 seeds x 11 folds)"
    miss = []
    for seed in fc["seeds"]:
        for fold in range(int(fc["n_folds"])):
            q = src / cfg["frozen_inputs"]["predictions_pattern"].format(seed=seed, fold=fold)
            if not q.exists():
                miss.append(str(q))
    if miss:
        raise FileNotFoundError(f"STOP: missing frozen predictions: {miss[:3]}")

    # --- frozen decisions / candles / costs / plan ---
    decisions = pd.read_parquet(root / cfg["frozen_inputs"]["decisions"])
    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
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

    # --- R published cross-check (read-only: frozen config values must equal R portfolio file) ---
    r_sum = json.loads((root / cfg["frozen_inputs"]["r_summary_read_only"]).read_text(encoding="utf-8"))
    for branch, spec in cfg["branch_spec"].items():
        pub = cfg["r_published_exact"][branch]
        rval = r_sum["branches"][spec["r_branch"]]["scenarios"][spec["r_scenario"]]
        for k in ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"):
            assert float(pub[k]) == float(rval[k]), f"R published drift {branch} {k}"
        assert int(pub["trades"]) == int(rval["trades"]), f"R published drift {branch} trades"
        assert int(pub["long_trades"]) == int(rval["long_trades"]), f"R published drift {branch} long"
        assert int(pub["short_trades"]) == int(rval["short_trades"]), f"R published drift {branch} short"

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

    cand_grid = own_grid(ds_cfg)
    assert cand_grid.shape == (16, 6), f"candidate schema changed: {cand_grid.shape}"
    assert set(np.unique(cand_grid[:, 5]).tolist()) == {3.0, 7.0}

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

    # --- own identity signal frame (shared for both fee branches) ---
    sig_identity, info_identity, en_best = own_frame(exp_raw, fill_logits, cand_grid, fold_of,
                                                     part, ds_cfg, expiry)
    print(json.dumps({"branch_signals": "verify_v96_identity", "n_signals": int(len(sig_identity)),
                      "coverage": float(len(sig_identity) / len(part)),
                      "n_selected": info_identity["n_selected"],
                      "gate_hits": info_identity["gate_hits_by_fold"],
                      "fallback": info_identity["fallback_adds_by_fold"]}), flush=True)

    # --- signal-identity soft check (still backtest on mismatch, verdict FAIL) ---
    exp_picks = {str(k): int(v) for k, v in fc["picks_by_fold_expected"].items()}
    exp_fb = {str(k): int(v) for k, v in fc["fallback_adds_expected"].items()}
    signal_identity = (
        info_identity["n_selected"] == int(fc["picks_pre_frequency_expected"])
        and info_identity["gate_hits_by_fold"] == exp_picks
        and info_identity["fallback_adds_by_fold"] == exp_fb
        and int(len(sig_identity)) == int(fc["n_signals_expected"])
    )

    # --- engine sanity markers (shared infra unchanged) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text(encoding="utf-8")
    for marker in ("def run_backtest", "next_available_index", "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    frames = {"verify_identity_1x_normal": sig_identity,
              "verify_identity_1x_fee055": sig_identity}
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
              and dd["n_signals"] == 0
              and signal_identity)
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
            "n_signals_expected": int(fc["n_signals_expected"]),
            "signal_identity_match": bool(signal_identity),
            "gate_hits_identity": info_identity["gate_hits_by_fold"],
            "gate_hits_expected": exp_picks,
            "fallback_adds_identity": info_identity["fallback_adds_by_fold"],
            "fallback_adds_expected": exp_fb,
            "n_selected": info_identity["n_selected"],
            "n_selected_expected": int(fc["picks_pre_frequency_expected"]),
            "candidate_causes_ordered": [
                "(1) own ensemble mean vs R combine (ch0*sigmoid(ch4) mean vs raw/ch0-only/dtype)",
                "(2) own tie-break vs R deterministic_best_index (eps/fill/holding/index order)",
                "(3) own geometry vs R prices/grid (unit/min-risk/ordered checks)",
                "(4) gate floor strictness / fallback top-8 stable-order",
                "(5) frequency loop order (partition vs global chronological, monthly-4/cooldown-5d)",
                "(6) fee application path (branch CostModel rebuild vs R run_branch fee leg)",
                "(7) monthly/duration formula drift (parent plan window)",
                "(8) frozen-prediction presence/order drift (33-file identity, map-v8 blocks)",
                "(9) engine version drift (ohlc-v2 markers checked above)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v128-verifyv96",
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
            "signal_identity_match": bool(signal_identity),
        },
        "triage": triage,
        "artifacts": {b: f"{b}/{{signals.parquet,trades.csv,metrics.json}}" for b in WANT},
        "causal_notes": ("past-only closed-candle; identity RAW (no calibration); "
                         "per-fold gate en_best>0 + top-8 fallback on same scale; "
                         "fills from next bar; exploratory labels on opened 2023-2026 interval"),
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
        "warning": ("Exploratory verification on the opened development interval only. "
                    "Fee tiers are subjective robustness assumptions, not measured live "
                    "fees/slippage. Drawdown is trade-candle-close sampled. No promotion, no live claim."),
        "input_sha256": {q: sha256(root / q) for q in
                         (cfg["frozen_inputs"]["candles"],
                          cfg["frozen_inputs"]["decisions"],
                          cfg["frozen_inputs"]["dataset_config"],
                          cfg["frozen_inputs"]["parent_plan"],
                          cfg["frozen_inputs"]["model_plan"],
                          "configs/opencode_v128_verifyv96.json",
                          "scripts/opencode_r47a_verifyv96.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
