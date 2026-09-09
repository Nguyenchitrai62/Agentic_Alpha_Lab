"""Opencode v14 (R3-B3 breakthrough): B1 non-price models as VETO on frozen v30.

Frozen inputs (never refit):
  v30   artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet (94)
  flow  artifacts/research/opencode_v09_deriv/flow40_1x/signals.parquet
  deriv artifacts/research/opencode_v09_deriv/deriv40_1x/signals.parquet

Pre-specified matrix (configs/opencode_v14_derivveto.json, fixed BEFORE running):
  veto {flow, deriv, either-agrees, both-agree} x sizing {1x, dd_guard}
  = 8 branches + unvetoed control_1x = 9 branches.
Veto rule: keep a v30 row iff (bar_index, direction) exists in the veto-source
key set with the SAME direction. Causal past-only: both models' outputs are
available at the same decision time (v30 frozen; B1 purged walk-forward);
no future decisions are consulted.

Key-compatibility gate (runs BEFORE any backtest): require shared columns,
overlapping bar_index ranges, >0 overlapping signal_time stamps, identical
direction encoding. Else STOP with a negative audit, no forced match.

Sizing:
  1x       : fixed 1.0 leverage (base_exec 1.0/1.0).
  dd_guard : lev = 0.5 while UNVETOED-CONTROL control_1x sampled equity is
             >10% under its trailing peak (past-only), else 1.0. Guard state
             for EVERY dd_guard branch derives from the control run's sampled
             equity (trade exit_time/equity_after, 1-microsecond cutoff,
             100.0 seed), applied at each veto-kept signal's own signal_time.

Scenarios per branch: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x only.
Monthly geometric uses duration from configs/swing_v15_continuous_folds.json.
Control check: control_1x normal must reproduce +122.80%/-20.09%/65
  (total_return 1.2279837998661565, max_drawdown -0.20086073993367803,
  65 fills) within 1e-6, else STOP and report.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
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

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def dd_guard_leverage(signals, trades):
    """Disclosed control-equity guard (same method as r1c/r2e1 probes).

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal
    time uses only exits strictly before the signal timestamp (past-only,
    100.0 seed).
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


def key_compat_audit(v30, flow, deriv):
    """Compare decision-key schemas; STOP-grade incompatibility if no overlap."""
    audit = {}
    for name, frame in (("v30", v30), ("flow40_1x", flow), ("deriv40_1x", deriv)):
        audit[name] = {
            "n_signals": int(len(frame)),
            "columns": list(frame.columns),
            "bar_index_min": int(frame["bar_index"].min()),
            "bar_index_max": int(frame["bar_index"].max()),
            "signal_time_min": str(pd.to_datetime(frame["signal_time"], utc=True).min()),
            "signal_time_max": str(pd.to_datetime(frame["signal_time"], utc=True).max()),
            "directions": sorted(int(x) for x in frame["direction"].unique()),
            "direction_counts": {str(k): int(v) for k, v in frame["direction"].value_counts().items()},
        }
    for name, frame in (("v30", v30), ("flow40_1x", flow), ("deriv40_1x", deriv)):
        for col in ("bar_index", "signal_time", "direction"):
            if col not in frame.columns:
                audit["compatible"] = False
                audit["reason"] = f"{name} missing key column {col}"
                return audit
    vb, fb, db = set(v30["bar_index"]), set(flow["bar_index"]), set(deriv["bar_index"])
    st_v = set(pd.to_datetime(v30["signal_time"], utc=True).astype(str))
    st_f = set(pd.to_datetime(flow["signal_time"], utc=True).astype(str))
    st_d = set(pd.to_datetime(deriv["signal_time"], utc=True).astype(str))
    audit["overlap"] = {
        "bar_v30xflow": int(len(vb & fb)),
        "bar_v30xderiv": int(len(vb & db)),
        "time_v30xflow": int(len(st_v & st_f)),
        "time_v30xderiv": int(len(st_v & st_d)),
        "samekey_v30xflow": int(len(set(zip(v30["bar_index"], v30["direction"]))
                                    & set(zip(flow["bar_index"], flow["direction"])))),
        "samekey_v30xderiv": int(len(set(zip(v30["bar_index"], v30["direction"]))
                                     & set(zip(deriv["bar_index"], deriv["direction"])))),
    }
    audit["same_clock"] = bool(
        pd.to_datetime(v30["signal_time"], utc=True).dt.tz is not None
        and audit["overlap"]["time_v30xflow"] > 0
        and audit["overlap"]["time_v30xderiv"] > 0)
    audit["compatible"] = bool(
        audit["overlap"]["bar_v30xflow"] > 0 and audit["overlap"]["bar_v30xderiv"] > 0
        and audit["overlap"]["time_v30xflow"] > 0 and audit["overlap"]["time_v30xderiv"] > 0
        and all(audit[n]["directions"] == [-1, 1] for n in ("v30", "flow40_1x", "deriv40_1x")))
    if not audit["compatible"]:
        audit["reason"] = "decision-key spaces do not overlap; forcing a match is prohibited"
    else:
        audit["reason"] = "shared bar_index space, shared UTC clock, identical direction encoding"
    return audit


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["inputs"]["candles"])
    v30 = pd.read_parquet(root / cfg["inputs"]["v30_signals"])
    flow = pd.read_parquet(root / cfg["inputs"]["veto_flow_signals"])
    deriv = pd.read_parquet(root / cfg["inputs"]["veto_deriv_signals"])
    ds_cfg = json.loads((root / cfg["inputs"]["dataset_config"]).read_text())
    parent = json.loads((root / cfg["inputs"]["parent_plan"]).read_text())

    # Key-compatibility gate BEFORE any backtest.
    audit = key_compat_audit(v30, flow, deriv)
    print(json.dumps({"key_compatibility": audit}, default=str), flush=True)
    if not audit["compatible"]:
        raise SystemExit(f"NEGATIVE AUDIT, STOP: {audit['reason']} | {json.dumps(audit, default=str)}")

    # Pre-specified veto sets on (bar_index, direction).
    flow_keys = set(zip(flow["bar_index"].to_numpy(), flow["direction"].to_numpy()))
    deriv_keys = set(zip(deriv["bar_index"].to_numpy(), deriv["direction"].to_numpy()))
    either_keys = flow_keys | deriv_keys
    both_keys = flow_keys & deriv_keys
    veto_sets = {"flow": flow_keys, "deriv": deriv_keys, "either": either_keys, "both": both_keys}
    assert len(cfg["branches"]) == 9, "matrix must be 9 branches (control + 4 veto x 2 sizing)"

    def apply_veto(frame, source):
        if source is None:
            return frame.copy()
        keys = veto_sets[source]
        mask = np.array([(b, d) in keys for b, d in
                         zip(frame["bar_index"].to_numpy(), frame["direction"].to_numpy())])
        return frame[mask].copy()

    keep_rates = {}
    for b in cfg["branches"]:
        filt = apply_veto(v30, b["veto"])
        keep_rates[b["name"]] = {"n_kept": int(len(filt)), "n_base": int(len(v30)),
                                 "keep_rate": float(len(filt) / len(v30)) if len(v30) else 0.0,
                                 "kept_bar_index": [int(x) for x in filt["bar_index"].tolist()]}
        print(json.dumps({"branch": b["name"], **keep_rates[b["name"]]}), flush=True)

    costs = CostModel(**ds_cfg["costs"])
    base_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=1.0, max_leverage=1.0)
    guard_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                 max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                 leverage=float(cfg["lev_min"]), max_leverage=float(cfg["lev_max"]))
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    # Reference run: unvetoed control 1x. Guard state for all dd_guard
    # branches derives from this control run's sampled equity.
    ref_signals = apply_veto(v30, None)
    if "leverage" in ref_signals.columns:
        ref_signals = ref_signals.drop(columns=["leverage"])
    ref_dir = a.output / "control_1x"
    ref_dir.mkdir()
    ref_signals.to_parquet(ref_dir / "signals.parquet", index=False)
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, base_exec, duration, ref_dir)
    results = {"control_1x": ref_scenarios}
    print(json.dumps({"branch": "control_1x",
                      "n_signals": int(len(ref_signals)),
                      "metrics": {s: {k: ref_scenarios[s][k] for k in
                                       ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
                                        "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
                                        "long_trades", "short_trades"]}
                                  for s in ("normal", "fee_stress", "execution_stress")}}),
            flush=True)

    # Control check: must reproduce +122.80%/-20.09%/65 normal or STOP.
    cc = cfg.get("control_check", {})
    n = ref_scenarios["normal"]
    ok = (abs(float(n["total_return"]) - float(cc.get("total_return", n["total_return"]))) <= float(cc.get("tolerance", 1e-6))
          and abs(float(n["max_drawdown"]) - float(cc.get("max_drawdown", n["max_drawdown"]))) <= float(cc.get("tolerance", 1e-6))
          and int(n["trades"]) == int(cc.get("trades", n["trades"])))
    print(json.dumps({"control_check": {"expected": cc, "observed": {
        "total_return": n["total_return"], "max_drawdown": n["max_drawdown"], "trades": n["trades"]},
        "pass": bool(ok)}}), flush=True)
    if not ok:
        raise SystemExit(f"CONTROL CHECK FAILED: {n['total_return']=} {n['max_drawdown']=} {n['trades']=}; STOP, no further branches")

    guard_all = dd_guard_leverage(v30, ref_trades)
    guard_by_pos = dict(zip(range(len(v30)), guard_all))

    for b in cfg["branches"]:
        name = b["name"]
        if name in results:
            continue
        filt = apply_veto(v30, b["veto"])
        # Map guard state by original v30 row position (past-only, causal).
        pos = v30.reset_index(drop=True)
        pos_index = {tuple(r): i for i, r in
                     enumerate(zip(pos["bar_index"], pos["direction"], pos["signal_time"].astype(str)))}
        levs = np.array([guard_by_pos[pos_index[(r.bar_index, r.direction, str(pd.Timestamp(r.signal_time)))]] for r in filt.itertuples()],
                        dtype=float) if len(filt) else np.array([], dtype=float)
        bdir = a.output / name
        bdir.mkdir()
        if b["sizing"] == "1x":
            sig = filt.drop(columns=["leverage"]) if "leverage" in filt.columns else filt.copy()
            sig.to_parquet(bdir / "signals.parquet", index=False)
            scenarios, _ = run_branch(candles, sig, costs, base_exec, duration, bdir)
        else:
            sig = filt.copy()
            sig["leverage"] = levs
            sig.to_parquet(bdir / "signals.parquet", index=False)
            scenarios, _ = run_branch(candles, sig, costs, guard_exec, duration, bdir)
        results[name] = scenarios
        print(json.dumps({"branch": name,
                          "n_signals": int(len(filt)),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
                                            "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")}}),
              flush=True)

    for branch, scenarios in results.items():
        for scen, metrics in scenarios.items():
            if not isinstance(metrics.get("total_return"), (int, float)):
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
              "key_compatibility": audit,
              "keep_rates": keep_rates,
              "formulas": {"veto_key": "(bar_index, direction) in veto-source key set, SAME direction required",
                           "veto_sources": "flow=flow40_1x keys; deriv=deriv40_1x keys; either=union; both=intersection",
                           "causality": "veto consults only same-decision B1 model outputs (frozen/purged past-only); no future decisions",
                           "dd_guard": "0.5x while UNVETOED-CONTROL control_1x sampled equity >10% under trailing peak, "
                           "past-only 1-microsecond cutoff, 100.0 seed; trade-candle-close sampled DD; "
                           "applies to ALL veto dd_guard branches at their own veto-kept signal times",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric": "ratio=final/100; monthly=ratio**(1/(12*duration_years))-1, swing_v15 duration"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
              "Veto keep-rates are thin by construction; low-fill branches report few fills by design, not by tuning.",
              "input_sha256": {str(k): sha256(root / v) for k, v in
                               (("v30_signals", cfg["inputs"]["v30_signals"]),
                                ("veto_flow_signals", cfg["inputs"]["veto_flow_signals"]),
                                ("veto_deriv_signals", cfg["inputs"]["veto_deriv_signals"]),
                                ("candles", cfg["inputs"]["candles"]),
                                ("dataset_config", cfg["inputs"]["dataset_config"]),
                                ("parent_plan", cfg["inputs"]["parent_plan"]))},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
