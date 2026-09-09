"""Opencode v18 (R4-E2): majority/confirmed base x scope filters x sizing.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet
  artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet
Pre-specified matrix (configs/opencode_v18_majcombo.json BEFORE running):
  bases {majority, confirmed} x scopes {all, s0004, t050, long_s0004} x sizing {1x, dd_guard}
  = 16 branches. Scopes are causal post-filters on frozen signal fields
  (direction, signal_time UTC hour, expected_net_percent); column availability
  verified before running (all present in both bases).
dd_guard: lev = 0.5 while OWN majority-control (majority_all_1x) sampled equity
  is >10% under its trailing peak (past-only, 1-microsecond cutoff, 100.0 seed),
  else 1.0; applied at each branch's OWN base+scope-filtered signal times.
  Single shared majority-control reference disclosed in config (v11/v13 convention).
Control gate: majority_all_1x normal must reproduce B4 majority_1x
  (+165.17829563633006% / -20.086073993367803% / 63 trades) or STOP.
Backtest: candles/costs data/processed/swing_regime_research_v4/;
  run_backtest + run_stress FillStress(5,5,5,.00055,False); fee stress .00055;
  monthly geometric from configs/swing_v15_continuous_folds.json duration.
Exploratory: the 2023-2026 interval is opened development data, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256


DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0
T050 = 0.50
SESSION_START, SESSION_END = 0, 4

# B4 published majority_1x normal reference (control gate).
PUBLISHED = {"total_return": 1.6517829563633004,
             "max_drawdown": -0.20086073993367803, "trades": 63}


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from reference (control) equity, evaluated at given signal times."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: eq for ts, eq in equity_at})
    out = []
    for ts in signal_times:
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
        pd.DataFrame([asdict(t) for t in items]).to_csv(out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios


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
    expected = ["majority_all_1x", "majority_all_dd_guard", "majority_s0004_1x",
                "majority_s0004_dd_guard", "majority_t050_1x", "majority_t050_dd_guard",
                "majority_long_s0004_1x", "majority_long_s0004_dd_guard",
                "confirmed_all_1x", "confirmed_all_dd_guard", "confirmed_s0004_1x",
                "confirmed_s0004_dd_guard", "confirmed_t050_1x", "confirmed_t050_dd_guard",
                "confirmed_long_s0004_1x", "confirmed_long_s0004_dd_guard"]
    assert list(cfg["branches"]) == expected, "branches must be pre-specified 16-branch base x scope x sizing matrix"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    bases = {b: pd.read_parquet(root / q) for b, q in cfg["bases"].items()}
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    score_col = cfg["score_column"]
    for b, df in bases.items():
        assert score_col in df.columns, f"score column {score_col} missing from base {b}"
        assert "direction" in df.columns, f"direction column missing from base {b}"
        assert "signal_time" in df.columns, f"signal_time column missing from base {b}"
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    base_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=1.0, max_leverage=1.0)
    sized_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                 max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                 leverage=LEV_MIN, max_leverage=LEV_MAX)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def filtered(base_df, scope):
        out = base_df
        if scope == "long_s0004":
            out = out[out["direction"] == 1]
        if scope in ("s0004", "long_s0004"):
            hours = pd.to_datetime(out["signal_time"], utc=True).dt.hour
            out = out[(hours >= SESSION_START) & (hours < SESSION_END)]
        if scope == "t050":
            out = out[out[score_col] >= T050]
        if scope not in ("all", "s0004", "t050", "long_s0004"):
            raise ValueError(f"unknown scope {scope}")
        return out.copy().reset_index(drop=True)

    # --- control 1x first (reproduction gate): majority_all_1x ---
    results = {}
    cdir = a.output / "majority_all_1x"
    cdir.mkdir()
    ref_signals = filtered(bases["majority"], "all")
    if "leverage" in ref_signals.columns:
        ref_signals = ref_signals.drop(columns=["leverage"])
    ref_signals.to_parquet(cdir / "signals.parquet", index=False)
    ref_scenarios = run_branch(candles, ref_signals, costs, fee_costs, base_exec,
                               stress, duration, cdir)
    n = ref_scenarios["normal"]
    ok = (abs(n["total_return"] - PUBLISHED["total_return"]) < 1e-6
          and abs(n["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
          and n["trades"] == PUBLISHED["trades"])
    print(json.dumps({"branch": "majority_all_1x", "n_signals": len(ref_signals),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL",
                      "published": PUBLISHED}), flush=True)
    if not ok:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"published": PUBLISHED,
             "reproduced": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    results["majority_all_1x"] = {"scenarios": ref_scenarios, "n_signals": len(ref_signals),
                                  "base": "majority", "scope": "all", "sizing": "1x"}

    # guard reference = OWN majority control (majority_all_1x) trades via fresh reference run
    _, control_trades = run_backtest(candles, ref_signals, 100, costs, base_exec)
    guard_cache = {}

    def guard_for(sig):
        key = tuple(pd.to_datetime(sig["signal_time"], utc=True).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(
                pd.to_datetime(sig["signal_time"], utc=True), control_trades)
        return guard_cache[key]

    plan = [("majority_all_dd_guard", "majority", "all", "dd_guard"),
            ("majority_s0004_1x", "majority", "s0004", "1x"),
            ("majority_s0004_dd_guard", "majority", "s0004", "dd_guard"),
            ("majority_t050_1x", "majority", "t050", "1x"),
            ("majority_t050_dd_guard", "majority", "t050", "dd_guard"),
            ("majority_long_s0004_1x", "majority", "long_s0004", "1x"),
            ("majority_long_s0004_dd_guard", "majority", "long_s0004", "dd_guard"),
            ("confirmed_all_1x", "confirmed", "all", "1x"),
            ("confirmed_all_dd_guard", "confirmed", "all", "dd_guard"),
            ("confirmed_s0004_1x", "confirmed", "s0004", "1x"),
            ("confirmed_s0004_dd_guard", "confirmed", "s0004", "dd_guard"),
            ("confirmed_t050_1x", "confirmed", "t050", "1x"),
            ("confirmed_t050_dd_guard", "confirmed", "t050", "dd_guard"),
            ("confirmed_long_s0004_1x", "confirmed", "long_s0004", "1x"),
            ("confirmed_long_s0004_dd_guard", "confirmed", "long_s0004", "dd_guard")]
    for branch, base, scope, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        sig = filtered(bases[base], scope)
        if sizing == "1x":
            if "leverage" in sig.columns:
                sig = sig.drop(columns=["leverage"])
            ex = base_exec
        else:
            sig["leverage"] = guard_for(sig)
            ex = sized_exec
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = run_branch(candles, sig, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": len(sig),
                           "base": base, "scope": scope, "sizing": sizing}
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
                   "n_signals": v["n_signals"], "base": v["base"],
                   "scope": v["scope"], "sizing": v["sizing"],
                   "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "control_check": {"published": PUBLISHED,
                                "reproduced": {k: n[k] for k in
                                               ("total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net")},
                                "match": True},
              "formulas": {"score_column": score_col, "t050": T050,
                           "session_utc": [SESSION_START, SESSION_END],
                           "scopes": cfg["scopes"], "bases": cfg["bases"],
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "dd_guard_reference": cfg["dd_guard_reference"],
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio^(1/(12*duration_years))-1"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY ONLY: opened 2023-2026 development interval "
                          "(until " + parent["complete_evaluation_until"] + "). Scopes are frozen "
                          "constants per branch (no fitting). Majority/confirmed bases are frozen v15 "
                          "agreement-row geometry; do not promote any branch or claim validation. "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills."),
              "input_sha256": {**{f"base_{b}": sha256(root / q) for b, q in cfg["bases"].items()},
                               **{str(q): sha256(root / q) for q in
                                  (cfg["candles"], cfg["dataset_config"],
                                   cfg["parent_plan"], "configs/opencode_v18_majcombo.json")}},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
