"""Opencode v22 (R4-N4): funding-timestamp avoidance filter on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet (94)
Pre-specified matrix (configs/opencode_v22_funding.json, written BEFORE any backtest):
  K {0, 6, 12} x sizing {1x, dd_guard} = 6 branches.
  RULE: for K>0 drop a LONG signal iff a funding_flags() candle open_time
  (hour%8==0 & min==0 & sec==0) has bar_index in [signal_bar_index+1, signal_bar_index+K],
  equivalently a funding timestamp in (signal_time, signal_time+K*5min].
  K=0 keeps all (control). SHORT signals always kept (short funding zero).
  Everything else identical (entry_expiry_bars=12, max_holding_bars=2016,
  tp1_fraction=0.5, intrabar_policy=stop_first, costs/dataset frozen).

Causality: the funding schedule is deterministic UTC 00/08/16, known in advance
like a calendar; checking it at signal_time uses NO market future (NOT leakage).

Sizing:
  1x       : fixed 1.0 leverage (ExecutionConfig 1.0/1.0, leverage col dropped).
  dd_guard : lev = 0.5 while K=0 CONTROL (k0_1x) sampled equity is >10% under
             its trailing peak (past-only), else 1.0. Control equity sampled
             from trade exit_time/equity_after (trade-candle-close sampled,
             NOT mark/intrabar). Guard at each branch signal time uses only
             control exits strictly before that timestamp (1-microsecond
             cutoff), seed level 100.0. Shared reference for ALL dd_guard
             branches (disclosed, per v11/v17).

Scenarios per branch: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x only.
Monthly geometric uses duration from configs/swing_v15_continuous_folds.json.
Control gate: k0_1x normal must reproduce +122.80% / -20.09% / 65 or STOP.
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
from agentic_alpha_lab.data.swing import funding_flags
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0
MAX_HOLDING_BARS = 7 * 288  # 2016, frozen base holding cap
TP1_FRACTION = 0.5
ENTRY_EXPIRY_BARS = 12  # frozen base patience; family varies ONLY the signal subset

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def funding_filter(base_signals, flags, k):
    """Return (kept signals, n_dropped_longs). SHORT signals always kept."""
    if k == 0:
        return base_signals.copy(), 0
    n = len(flags)
    keep = []
    dropped = 0
    for _, row in base_signals.iterrows():
        if int(row["direction"]) == 1:
            b = int(row["bar_index"])
            lo, hi = b + 1, min(b + k, n - 1)
            if lo <= hi and bool(flags[lo:hi + 1].any()):
                dropped += 1
                continue
        keep.append(row)
    kept = pd.DataFrame(keep, columns=base_signals.columns).reset_index(drop=True) \
        if keep else base_signals.iloc[0:0].copy()
    return kept, dropped


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from K=0 control equity, evaluated at given signal times.

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
    assert list(cfg["ks"]) == [0, 6, 12], "K matrix must be [0,6,12]"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert cfg["entry_expiry_bars"] == 12 == ds_cfg["entry_expiry_bars"]
    assert len(base_signals) == 94, f"frozen signal count must be 94, got {len(base_signals)}"
    assert set(base_signals["direction"].unique().tolist()) <= {1, -1}
    assert int((base_signals["direction"] == 1).sum()) == 60
    assert int((base_signals["direction"] == -1).sum()) == 34
    assert int(base_signals["holding_bars"].max()) == MAX_HOLDING_BARS
    assert float(base_signals["entry_expiry_bars"].unique()[0]) == 12.0
    assert float(base_signals["tp1_fraction"].unique()[0]) == TP1_FRACTION

    flags = funding_flags(candles)
    assert len(flags) == len(candles)
    # Funding schedule audit: deterministic 8h boundaries.
    assert int(ds_cfg["costs"]["funding_interval_hours"]) == 8
    assert float(ds_cfg["costs"]["funding_long_rate"]) == 0.0001
    assert float(ds_cfg["costs"]["funding_short_rate"]) == 0.0

    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))

    def exec_for(sizing):
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ENTRY_EXPIRY_BARS,
                                   max_holding_bars=MAX_HOLDING_BARS,
                                   tp1_fraction=TP1_FRACTION,
                                   leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ENTRY_EXPIRY_BARS,
                               max_holding_bars=MAX_HOLDING_BARS,
                               tp1_fraction=TP1_FRACTION,
                               leverage=LEV_MIN, max_leverage=LEV_MAX)

    # Funding-filtered subsets (frozen rule, no fitting).
    subsets, drop_counts = {}, {}
    for k in cfg["ks"]:
        kept, dropped = funding_filter(base_signals, flags, int(k))
        subsets[int(k)] = kept
        drop_counts[int(k)] = {"n_base": len(base_signals),
                               "n_kept": len(kept),
                               "n_dropped_longs": int(dropped),
                               "n_dropped_shorts": 0}
        print(json.dumps({"K": int(k), **drop_counts[int(k)]}), flush=True)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    results = {}

    # --- Control: K=0 1x (reproduction gate) ---
    cdir = a.output / "k0_1x"
    cdir.mkdir()
    ref_signals = subsets[0].drop(columns=["leverage"]) if "leverage" in subsets[0].columns \
        else subsets[0].copy()
    ref_signals.to_parquet(cdir / "signals.parquet", index=False)
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, fee_costs,
                                           exec_for("1x"), stress, duration, cdir)
    n = ref_scenarios["normal"]
    ok = (abs(n["total_return"] - 1.2280) < 0.005 and abs(n["max_drawdown"] - (-0.2009)) < 0.005
          and n["trades"] == 65)
    print(json.dumps({"branch": "k0_1x", "n_signals": len(ref_signals),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL"}), flush=True)
    if not ok:
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    results["k0_1x"] = {"scenarios": ref_scenarios, "n_signals": len(ref_signals),
                        "K": 0, "sizing": "1x",
                        "drop": drop_counts[0]}

    # Guard reference = K=0 control normal trades (single run handle above; no refit).
    guard_cache = {}

    def guard_for(sig):
        key = tuple(pd.to_datetime(sig["signal_time"], utc=True).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(pd.to_datetime(sig["signal_time"], utc=True),
                                                    ref_trades)
        return guard_cache[key]

    plan = [("k6_1x", 6, "1x"), ("k12_1x", 12, "1x"),
            ("k0_dd_guard", 0, "dd_guard"), ("k6_dd_guard", 6, "dd_guard"),
            ("k12_dd_guard", 12, "dd_guard")]
    for branch, k, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        base = subsets[int(k)]
        if sizing == "1x":
            sig = base.drop(columns=["leverage"]) if "leverage" in base.columns else base.copy()
            ex = exec_for("1x")
        else:
            sig = base.copy()
            sig["leverage"] = guard_for(base)
            ex = exec_for("dd_guard")
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": len(sig),
                           "K": int(k), "sizing": sizing, "drop": drop_counts[int(k)]}
        print(json.dumps({"branch": branch, "n_signals": len(sig),
                          "drop": drop_counts[int(k)],
                          "metrics": {s: {kk: scenarios[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
               flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": v["n_signals"], "K": v["K"],
                   "sizing": v["sizing"], "drop": v["drop"],
                   "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "drop_counts_per_K": {str(k): drop_counts[int(k)] for k in cfg["ks"]},
              "control_check": {"branch": "k0_1x",
                                "normal": {k: ref_scenarios["normal"][k] for k in
                                           ("total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net")},
                                "match": True},
              "formulas": {"filter_rule": cfg["filter_rule"],
                           "entry_expiry_bars": ENTRY_EXPIRY_BARS,
                           "max_holding_bars": MAX_HOLDING_BARS,
                           "tp1_fraction": TP1_FRACTION,
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "dd_guard_reference": cfg["dd_guard_reference"],
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio=final/100; monthly=ratio^(1/(12*duration_years))-1",
                           "funding_schedule": "funding_flags() on candles open_time: (hour%8==0)&(min==0)&(sec==0); deterministic UTC 00/08/16, known in advance (NOT leakage)"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY labels: opened 2023-2026 development interval only ("
                          + str(parent["complete_evaluation_until"]) + "). K-filter is a frozen "
                          "calendar rule per branch (no fitting, no adaptation). Signals/scores never "
                          "refit. Do not promote any branch or claim validation. Drawdown is "
                          "trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed "
                          "maker/limit fills. Do not claim maker fill probability or queue "
                          "position from OHLC alone."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["signals"], cfg["dataset_config"],
                                cfg["parent_plan"], "configs/opencode_v22_funding.json")},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
