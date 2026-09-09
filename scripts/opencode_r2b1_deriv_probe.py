"""Opencode v09 (R2-B1 breakthrough): non-price signal sources x dd_guard.

NEW signal source test: price-based 5m approaches saturate ~2.4%/mo, so this
probe uses ZERO raw-price features in 3 of 4 model branches:
  candle40    = frozen examples.npz features (control; attributes any gap to source)
  deriv40     = daily derivatives OI/positioning lag48 archive scenario (pure positioning)
  flow40      = causal closed-candle flow/activity (buy imbalance, trade activity)
  flowderiv80 = flow40 + deriv40 (pure non-price combo)
Model: shared HGB net/fill regressors, EXACTLY v8 hyperparams, purged monthly
walk-forward (trailing 730d, 8d embargo >= 7d horizon), single seed 1729.
Policy: standard choose() + identical frequency loop (cooldown 5d, max 4/month).
Each model branch x sizing {1x, dd_guard} = 8 backtest branches x 3 scenarios.
Exploratory: opened development interval only; derivatives lag is a disclosed
archive proxy (point_in_time_availability_verified=false upstream), NOT live
evidence. No live approval.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.flow_features import flow_features
from agentic_alpha_lab.data.swing import choose, grid
from agentic_alpha_lab.data.training import sha256, validate_source

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def action_features(features, candidates):
    features, candidates = np.asarray(features), np.asarray(candidates)
    n, k = len(features), len(candidates)
    return np.concatenate((np.repeat(features, k, axis=0), np.tile(candidates, (n, 1))), axis=1)


def gen_signals(pred_slice, part, cfg):
    """Replica of swing_signals loop with identical frequency policy."""
    signals, monthly = [], Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    for p, row in zip(pred_slice, part.itertuples()):
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= cfg["policy"]["maximum_signals_per_month"]:
            continue
        signal = choose(p, row.close, row.atr5, row.atr4, cfg)
        if signal["action"] == "WAIT":
            continue
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp, **signal})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=cfg["policy"]["cooldown_days"])
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def dd_guard_leverage(signals, trades):
    """Past-only guard on own-branch 1x sampled equity (r1a formula)."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in trades]
    equity_at.sort()
    eq = pd.Series({ts: eq for ts, eq in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, execution, duration_years, out_dir):
    scenarios = {}
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diagnostic = run_stress(candles, signals, 100, costs, execution,
                                        FillStress(5, 5, 5, 0.00055, False))
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                 ("execution_stress", stress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        rows = [asdict(t) for t in items]
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(
                out_dir / f"{label}_trades.csv", index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(
                out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios, trades


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    decisions = pd.read_parquet(root / cfg["decisions"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    with np.load(root / "data/processed/swing_regime_research_v4/examples.npz") as z:
        candle40, labels = z["features"], z["labels"]
    with np.load(root / cfg["feature_sources"]["deriv40_lag48"].split(":")[0]) as z:
        deriv40 = z["features"]
    flow40, flow_names = flow_features(
        validate_source(pd.read_parquet(root / cfg["candles"])), decisions.signal_time)
    assert (len(decisions) == len(candle40) == len(labels) == len(deriv40) == len(flow40) == 5628)
    assert np.isfinite(flow40).all() and np.isfinite(deriv40).all()
    assert decisions.signal_time.is_monotonic_increasing and not decisions.signal_time.duplicated().any()
    feat = {"candle40": candle40.astype(np.float64), "deriv40_lag48": deriv40.astype(np.float64),
            "flow40": flow40.astype(np.float64),
            "flowderiv80": np.concatenate((flow40, deriv40), axis=1).astype(np.float64)}
    candidates = grid(ds_cfg)
    assert candidates.shape == (16, 6)

    costs = CostModel(**ds_cfg["costs"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    months = pd.date_range("2023-06-01", "2026-03-01", freq="MS", tz="UTC")
    oos_mask = (decisions.signal_time >= months[0]).to_numpy()
    oos_idx = np.where(oos_mask)[0]
    part = decisions.iloc[oos_idx].reset_index(drop=True)
    oos_pos = {idx: i for i, idx in enumerate(oos_idx)}
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    results, fits_provenance = {}, {}
    with threadpool_limits(limits=2):
        for fbranch, keys in cfg["feature_branches"].items():
            parts = [feat[k] for k in keys]
            X = np.concatenate(parts, axis=1) if len(parts) > 1 else parts[0]
            n_feat = X.shape[1]
            prediction = np.full((len(oos_idx), len(candidates), 6), np.nan, np.float32)
            prov = []
            for fit_at in months:
                label = fit_at.strftime("%Y-%m")
                mask = ((decisions.label_end < fit_at - pd.Timedelta(days=8))
                        & (decisions.signal_time >= fit_at - pd.Timedelta(days=730))).to_numpy()
                if mask.sum() < 200:
                    raise ValueError(f"Insufficient mature training decisions at {label}: {mask.sum()}")
                Xa = action_features(X[mask], candidates)
                HP = ("loss", "learning_rate", "max_iter", "max_leaf_nodes",
                      "min_samples_leaf", "l2_regularization", "max_bins",
                      "early_stopping", "random_state")
                params = {k: v for k, v in cfg["model"].items() if k in HP}
                models = {name: HistGradientBoostingRegressor(**params).fit(
                    Xa, labels[mask][..., col].reshape(-1))
                    for name, col in (("net", 0), ("fill", 1))}
                sel = decisions.signal_time.dt.strftime("%Y-%m").to_numpy() == label
                sel_idx = np.where(sel & oos_mask)[0]
                if len(sel_idx) == 0:
                    continue
                if (decisions.signal_time.iloc[sel_idx] < fit_at).any():
                    raise ValueError("Predictions before fitting clock")
                net = models["net"].predict(action_features(X[sel_idx], candidates)
                                            ).reshape(len(sel_idx), len(candidates))
                fill = np.clip(models["fill"].predict(action_features(X[sel_idx], candidates)
                                                      ).reshape(net.shape), 1e-6, 1 - 1e-6)
                rows = np.array([oos_pos[i] for i in sel_idx])
                prediction[rows, :, 0] = (net / fill).astype(np.float32)
                prediction[rows, :, 4] = np.log(fill / (1 - fill)).astype(np.float32)
                prov.append({"fit_at": str(fit_at), "train_decisions": int(mask.sum()),
                             "eval_decisions": int(len(sel_idx)), "n_features": n_feat})
                print({"fbranch": fbranch, "month": label, "train": int(mask.sum()),
                       "eval": int(len(sel_idx))}, flush=True)
            if not np.isfinite(prediction[:, :, [0, 4]]).all():
                raise ValueError(f"Missing OOS predictions for {fbranch}")
            # Unexecuted channels: no quantile / win-score estimates (documented
            # equivalent of the standard path; choose() uses only ch0 + ch4).
            prediction[:, :, 1:4] = 0.0
            prediction[:, :, 5] = 0.0
            fits_provenance[fbranch] = prov
            np.save(a.output / f"predictions_{fbranch}.npy", prediction)

            base_sig = gen_signals(prediction, part, ds_cfg)
            print({"fbranch": fbranch, "n_signals": int(len(base_sig))}, flush=True)
            sig1 = base_sig.drop(columns=["leverage"]) if "leverage" in base_sig.columns else base_sig.copy()
            bdir1 = a.output / f"{fbranch}_1x"
            bdir1.mkdir()
            sig1.to_parquet(bdir1 / "signals.parquet", index=False)
            execution1 = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                         max_holding_bars=2016, leverage=1.0, max_leverage=1.0)
            scenarios1, trades_1x = run_branch(candles, sig1, costs, execution1, duration, bdir1)
            results[f"{fbranch}_1x"] = scenarios1
            print(json.dumps({"branch": f"{fbranch}_1x", "n_signals": int(len(base_sig)),
                              "metrics": {s: {k: scenarios1[s][k] for k in
                                              ["total_return", "max_drawdown", "trades",
                                               "monthly_geometric_net", "gross_pnl", "fees",
                                               "funding", "profit_factor", "win_rate"]}
                                          for s in ("normal", "fee_stress", "execution_stress")}},
                             default=str), flush=True)
            for sizing in ("dd_guard",):
                branch = f"{fbranch}_{sizing}"
                bdir = a.output / branch
                bdir.mkdir()
                if True:
                    levs = dd_guard_leverage(base_sig, trades_1x) if len(base_sig) else np.array([], dtype=float)
                    sig = base_sig.copy()
                    sig["leverage"] = levs
                    sig.to_parquet(bdir / "signals.parquet", index=False)
                    execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                                max_holding_bars=2016, leverage=LEV_MIN, max_leverage=LEV_MAX)
                    scenarios, _ = run_branch(candles, sig, costs, execution, duration, bdir)
                results[branch] = scenarios
                print(json.dumps({"branch": branch, "n_signals": int(len(base_sig)),
                                  "metrics": {s: {k: scenarios[s][k] for k in
                                                  ["total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net", "gross_pnl", "fees",
                                                   "funding", "profit_factor", "win_rate"]}
                                              for s in ("normal", "fee_stress", "execution_stress")}},
                                 default=str), flush=True)

    for branch, scenarios in results.items():
        for scen, metrics in scenarios.items():
            if scen not in ("normal", "fee_stress", "execution_stress"):
                continue
            try:
                m_pass = bool(metrics["monthly_geometric_net"] >= gate["monthly_min"])
                d_pass = bool(metrics["max_drawdown"] >= -abs(gate["dd_max"]))
                f_pass = bool(metrics["trades"] >= gate["fills_min"])
            except (KeyError, TypeError):
                continue
            metrics["gate"] = {"monthly_geometric_net_ge_5pct": m_pass,
                               "drawdown_within_20pct": d_pass,
                               "fills_ge_30": f_pass,
                               "pass_all": bool(m_pass and d_pass and f_pass)}
    report = {"branches": results, "config": cfg, "fits": fits_provenance,
              "n_oos_decisions": int(len(oos_idx)),
              "formulas": {"model": "shared HGB net/fill, v8 hyperparams, monthly purged refit 730d/8d",
                           "policy": "choose() 0.3%/0.25 + cooldown 5d + max 4/month; dd_guard 0.5x on own-branch 1x equity >10% under peak",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio^(1/(12*duration_years))-1, swing_v15 duration"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on opened development data only. Derivatives lag48 is a disclosed archive proxy, not observed receipt time. Drawdown is trade-candle-close sampled. Stop/timeout exits market-like at scenario fee.",
              "input_sha256": {"decisions": sha256(root / cfg["decisions"]),
                               "candles": sha256(root / cfg["candles"]),
                               "dataset_config": sha256(root / cfg["dataset_config"]),
                               "parent_plan": sha256(root / cfg["parent_plan"]),
                               "examples": sha256(root / "data/processed/swing_regime_research_v4/examples.npz"),
                               "deriv_cache_manifest": sha256(root / "artifacts/features/btc_derivatives_lag48_v1/manifest.json")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
