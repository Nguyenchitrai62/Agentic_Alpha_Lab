"""Opencode v05 (R1-A): holding-horizon matrix x dd_guard on FROZEN v30 isotonic-4 outputs.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz
Pre-specified matrix (fixed in configs/opencode_v05_holding.json before running):
  holdings {3,5,7,10,14} x sizing {1x, dd_guard} = 10 branches + control_1x
  (base holding grid [3,7] @1x; must match published +122.80%/-20.09%/65 normal)
Methods (per config; disclosed deviation for novel horizons):
  - h in {3,7}: re-selection. Replicate swing_signals loop EXACTLY (same monthly
    cap + cooldown policy) but call choose() with modified cfg where ONLY
    holding_days=[h]; frozen prediction columns sliced to the matching subset
    (base grid alternates 3d/7d: even idx=3d, odd idx=7d). Entry/brackets/policy
    identical to base. Causal past-only.
  - h in {5,10,14}: execution-holding override. Frozen predictions cover ONLY
    3d/7d candidates, so re-selection would need new inference (forbidden).
    Keep frozen base selection, override holding_bars=h*288 with matching cap.
  dd_guard lev = 0.5 while CONTROL (control_1x) sampled equity is >10% under its
  trailing peak (past-only, 1-microsecond cutoff, 100.0 seed), else 1.0; applied
  at each branch's own signal times. Same formula as
  scripts/opencode_risk_overlay_probe.py / scripts/opencode_side_ddguard_probe.py.
Each branch x 3 scenarios (normal / fee_stress / execution_stress).
Exploratory: the 2023-2026 interval is opened development data, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import copy
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.swing import choose, grid
from agentic_alpha_lab.data.training import sha256


DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0
BARS_PER_DAY = 288

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]

# Published isotonic_4 exposure1.0 normal reference (control gate).
PUBLISHED = {"total_return": 1.2279837998661565, "max_drawdown": -0.20086073993367803,
             "trades": 65}


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
    """Disclosed method shared with risk_overlay / side_ddguard probes.

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal time
    uses only exits strictly before the signal timestamp (past-only, 100.0 seed).
    """
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
    with np.load(root / cfg["predictions"]) as z:
        predictions = z["prediction"]
        decision_indices = z["decision_indices"]
    part = decisions.iloc[decision_indices].reset_index(drop=True)
    assert predictions.shape[0] == len(part) and predictions.shape[1] == len(grid(ds_cfg))

    costs = CostModel(**ds_cfg["costs"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    holdings = list(cfg["holdings"])
    assert holdings == [3, 5, 7, 10, 14], "holdings matrix must be pre-specified as [3,5,7,10,14]"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def exec_for(holding_days, sizing):
        cap = int(max(holding_days) * BARS_PER_DAY)
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX)

    # ---- Control: base holding grid [3,7] @1x (must reproduce published) ----
    control_signals = gen_signals(predictions, part, ds_cfg)
    ref_dir = a.output / "control_1x"
    ref_dir.mkdir()
    control_exec = exec_for(ds_cfg["holding_days"], "1x")
    ref_scenarios, ref_trades = run_branch(candles, control_signals, costs,
                                           control_exec, duration, ref_dir)
    control_signals.to_parquet(ref_dir / "signals.parquet", index=False)
    results = {"control_1x": ref_scenarios}
    n_control_signals = int(len(control_signals))

    normal = ref_scenarios["normal"]
    control_check = {
        "published": PUBLISHED,
        "reproduced": {"total_return": normal["total_return"],
                       "max_drawdown": normal["max_drawdown"], "trades": normal["trades"],
                       "n_signals": n_control_signals},
        "match": bool(abs(normal["total_return"] - PUBLISHED["total_return"]) < 1e-6
                      and abs(normal["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
                      and normal["trades"] == PUBLISHED["trades"]),
    }
    print(json.dumps({"control_check": control_check}, default=str), flush=True)
    if not control_check["match"]:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(control_check, indent=2))
        print("CONTROL MISMATCH: STOP; base-grid reproduce does not match published "
              "+122.80%/-20.09%/65 normal", flush=True)
        sys.exit(1)

    # ---- Holding matrix ----
    branch_method = {}
    for h in holdings:
        if h in (3, 7):
            # Re-selection: slice frozen predictions to the holding subset.
            sl = slice(0, predictions.shape[1], 2) if h == 3 else slice(1, predictions.shape[1], 2)
            mod_cfg = copy.deepcopy(ds_cfg)
            mod_cfg["holding_days"] = [h]
            assert len(grid(mod_cfg)) == predictions[:, sl, :].shape[1]
            base_sig = gen_signals(predictions[:, sl, :], part, mod_cfg)
            assert len(base_sig) == 0 or set(base_sig["holding_bars"].unique()) == {h * BARS_PER_DAY}
            method = f"reselection: choose() with holding_days=[{h}], sliced frozen predictions"
        else:
            # Execution-holding override on frozen base selection (novel horizons
            # have no frozen predictions; refit/inference forbidden).
            base_sig = control_signals.copy()
            base_sig["holding_bars"] = int(h * BARS_PER_DAY)
            method = (f"execution_override: frozen base selection, holding_bars={h * BARS_PER_DAY}, "
                      f"cap={h * BARS_PER_DAY}")
        branch_method[h] = method
        print(json.dumps({"holding": h, "method": method,
                          "n_signals": int(len(base_sig))}), flush=True)
        for sizing in ("1x", "dd_guard"):
            branch = f"h{h}_{sizing}"
            bdir = a.output / branch
            bdir.mkdir()
            if sizing == "1x":
                sig = base_sig.drop(columns=["leverage"]) if "leverage" in base_sig.columns else base_sig.copy()
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, exec_for([h], "1x"),
                                          duration, bdir)
            else:
                levs = dd_guard_leverage(base_sig, ref_trades) if len(base_sig) else np.array([], dtype=float)
                sig = base_sig.copy()
                sig["leverage"] = levs
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, exec_for([h], "dd_guard"),
                                          duration, bdir)
            results[branch] = scenarios
            print(json.dumps({"branch": branch, "method": method,
                              "n_signals": int(len(base_sig)),
                              "metrics": {s: {k: scenarios[s][k] for k in
                                               ["total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net", "gross_pnl", "fees",
                                                "funding", "profit_factor", "win_rate",
                                                "long_trades", "short_trades"]}
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
    report = {"branches": results, "config": cfg,
              "control_check": control_check,
              "branch_method": {str(k): v for k, v in branch_method.items()},
              "n_control_signals": n_control_signals,
              "formulas": {"dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "guard_reference": cfg.get("dd_guard_reference", ""),
                           "reselection_slice": "base grid alternates 3d/7d per candidate index "
                           "(even=3d, odd=7d); holding_days=[h] slices that parity",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio^(1/(12*duration_years))-1"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
              "h5/h10/h14 vary holding at execution only (frozen selection); they are NOT "
              "re-selected expectations for those horizons.",
              "input_sha256": {str(k): sha256(root / v) for k, v in
                               (("predictions", cfg["predictions"]), ("decisions", cfg["decisions"]),
                                ("candles", cfg["candles"]), ("dataset_config", cfg["dataset_config"]),
                                ("parent_plan", cfg["parent_plan"]))},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
