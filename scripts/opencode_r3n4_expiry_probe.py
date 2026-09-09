"""Opencode v17 (R3-N4): limit-entry patience matrix on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet (94)
Pre-specified matrix (configs/opencode_v17_expiry.json, written BEFORE any backtest):
  entry_expiry_bars {6, 12, 24} x sizing {1x, dd_guard} = 6 branches.
  Base expiry 12 read from data/processed/swing_regime_research_v4/config.json,
  so matrix is {base/2, base, base*2}. Vary ONLY ExecutionConfig.entry_expiry_bars;
  everything else identical (max_holding_bars=2016, tp1_fraction=0.5,
  intrabar_policy=stop_first, costs/dataset frozen).

Stress-path verification (read before running; disclosed, not assumed):
  src/agentic_alpha_lab/backtest/execution_stress.py run_stress line 81 loops
    range(index+1, min(index+execution.entry_expiry_bars+1, len(frame)))
  i.e. it HONORS execution.entry_expiry_bars with the same inclusive window
  (signal+1 .. signal+expiry) as engine.py run_backtest lines 203-205.
  Frozen per-signal entry_expiry_bars (=12) and tp1_fraction (=0.5) columns in
  signals.parquet are inert metadata: neither engine reads them (no getattr);
  ExecutionConfig is authoritative for expiry (and TP fraction).

Sizing:
  1x       : fixed 1.0 leverage (ExecutionConfig 1.0/1.0, leverage col dropped).
  dd_guard : lev = 0.5 while BASE-EXPIRY CONTROL (e12_1x) sampled equity is
             >10% under its trailing peak (past-only), else 1.0.
             Control equity sampled from trade exit_time/equity_after
             (trade-candle-close sampled, NOT mark/intrabar). Guard at each
             branch signal time uses only control exits strictly before that
             timestamp (1-microsecond cutoff), seed level 100.0. Shared
             reference for ALL dd_guard branches (disclosed, per v11).

Scenarios per branch: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x only.
Monthly geometric uses duration from configs/swing_v15_continuous_folds.json.
Control gate: e12_1x normal must reproduce +122.80% / -20.09% / 65 or STOP.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0
MAX_HOLDING_BARS = 7 * 288  # 2016, frozen base holding cap
TP1_FRACTION = 0.5

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from base-expiry control equity, evaluated at given signal times.

    Past-only: at each signal time, uses only control exits strictly before
    signal timestamp (1-microsecond cutoff), seed level 100.0.
    """
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signal_times, utc=True):
        ts = pd.Timestamp(ts)
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, fee_costs, execution, stress, duration_years, out_dir):
    scenarios = {}
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    estress, st, diagnostic = run_stress(candles, signals, 100, costs, execution, stress)
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                 ("execution_stress", estress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        rows = [asdict(t) for t in items]
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(out_dir / f"{label}_trades.csv", index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios, trades


def gate_flags(scenarios, gate):
    flags = {}
    for s in ("normal", "fee_stress", "execution_stress"):
        m = scenarios[s]
        flags[s] = {"monthly_pass": bool(m["monthly_geometric_net"] >= gate["monthly_min"]),
                    "dd_pass": bool(abs(m["max_drawdown"]) <= gate["dd_max"]),
                    "fills_pass": bool(m["trades"] >= gate["fills_min"])}
        flags[s]["scenario_pass"] = all(flags[s].values())
    flags["overall_pass"] = all(flags[s]["scenario_pass"] for s in
                                ("normal", "fee_stress", "execution_stress"))
    return flags


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
    base_signals = pd.read_parquet(root / cfg["signals"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())

    # Pre-specification audit (config written before running).
    assert ds_cfg["entry_expiry_bars"] == 12, "base expiry must be 12"
    assert cfg["base_entry_expiry_bars"] == 12
    assert list(cfg["expiries"]) == [6, 12, 24], "expiry matrix must be [6,12,24]"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert len(base_signals) == 94, f"frozen signal count must be 94, got {len(base_signals)}"
    assert set(base_signals["holding_bars"].unique().tolist()) <= {3 * 288, 7 * 288}
    assert int(base_signals["holding_bars"].max()) == MAX_HOLDING_BARS
    assert float(base_signals["entry_expiry_bars"].unique()[0]) == 12.0
    assert float(base_signals["tp1_fraction"].unique()[0]) == TP1_FRACTION

    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))

    def exec_for(expiry, sizing):
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=int(expiry),
                                   max_holding_bars=MAX_HOLDING_BARS,
                                   tp1_fraction=TP1_FRACTION,
                                   leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=int(expiry),
                               max_holding_bars=MAX_HOLDING_BARS,
                               tp1_fraction=TP1_FRACTION,
                               leverage=LEV_MIN, max_leverage=LEV_MAX)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    results = {}

    # --- Control: base expiry e12_1x (reproduction gate) ---
    cdir = a.output / "e12_1x"
    cdir.mkdir()
    ref_signals = base_signals.drop(columns=["leverage"]) if "leverage" in base_signals.columns else base_signals.copy()
    ref_signals.to_parquet(cdir / "signals.parquet", index=False)
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, fee_costs,
                                           exec_for(12, "1x"), stress, duration, cdir)
    n = ref_scenarios["normal"]
    ok = (abs(n["total_return"] - 1.2280) < 0.005 and abs(n["max_drawdown"] - (-0.2009)) < 0.005
          and n["trades"] == 65)
    print(json.dumps({"branch": "e12_1x", "n_signals": len(ref_signals),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL"}), flush=True)
    if not ok:
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    results["e12_1x"] = {"scenarios": ref_scenarios, "n_signals": len(ref_signals),
                         "entry_expiry_bars": 12, "sizing": "1x"}

    # Guard reference = base-expiry control normal trades (single run handle above; no refit).
    guard_cache = {}

    def guard_for(sig):
        key = tuple(pd.to_datetime(sig["signal_time"], utc=True).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(pd.to_datetime(sig["signal_time"], utc=True),
                                                    ref_trades)
        return guard_cache[key]

    plan = [("e6_1x", 6, "1x"), ("e24_1x", 24, "1x"),
            ("e6_dd_guard", 6, "dd_guard"), ("e12_dd_guard", 12, "dd_guard"),
            ("e24_dd_guard", 24, "dd_guard")]
    for branch, expiry, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        if sizing == "1x":
            sig = base_signals.drop(columns=["leverage"]) if "leverage" in base_signals.columns else base_signals.copy()
            ex = exec_for(expiry, "1x")
        else:
            sig = base_signals.copy()
            sig["leverage"] = guard_for(base_signals)
            ex = exec_for(expiry, "dd_guard")
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": len(sig),
                           "entry_expiry_bars": expiry, "sizing": sizing}
        print(json.dumps({"branch": branch, "n_signals": len(sig),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
               flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": v["n_signals"], "entry_expiry_bars": v["entry_expiry_bars"],
                   "sizing": v["sizing"], "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "control_check": {"branch": "e12_1x",
                                "normal": {k: ref_scenarios["normal"][k] for k in
                                           ("total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net")},
                                "match": True},
              "formulas": {"entry_expiry_bars": cfg["expiries"],
                           "max_holding_bars": MAX_HOLDING_BARS,
                           "tp1_fraction": TP1_FRACTION,
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "dd_guard_reference": cfg["dd_guard_reference"],
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio=final/100; monthly=ratio^(1/(12*duration_years))-1",
                           "stress_path": "run_stress honors entry_expiry_bars (execution_stress.py:81, inclusive signal+1..signal+expiry, same as engine.py:203-205); frozen per-signal entry_expiry_bars/tp1_fraction columns are inert metadata"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY labels: opened 2023-2026 development interval only ("
                          + str(parent["complete_evaluation_until"]) + "). Expiry is a frozen "
                          "constant per branch (no fitting, no adaptation). Signals/scores never "
                          "refit. Do not promote any branch or claim validation. Drawdown is "
                          "trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed "
                          "maker/limit fills. Do not claim maker fill probability or queue "
                          "position from OHLC alone."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["signals"], cfg["dataset_config"],
                                cfg["parent_plan"], "configs/opencode_v17_expiry.json")},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
