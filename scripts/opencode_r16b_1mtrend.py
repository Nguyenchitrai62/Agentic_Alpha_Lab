"""Opencode v53 (R16-B): 1m micro-trend agreement filter on frozen majority_1x.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  candles 5m + 1m audit dir (local existing data only, NO new crawl).
Pre-specified matrix (configs/opencode_v53_1mtrend.json BEFORE running):
  {control, trend60-agree, trend240-agree} x {1x, dd_guard} = 6 branches.
Micro-trend for lookback L: sign(last-1m-close - first-1m-open) over the L
1m bars with close_time <= signal_time (strictly causal, asserted).
KEEP iff trend_sign == direction (flat counts as disagree). Kept rows keep
byte-identical frozen geometry (pure row filter).
Signals lacking full L-bar 1m history are DROPPED (never extrapolated).
Scenarios: normal / fee .00055 / run_stress FillStress(5,5,5,.00055,False).
Monthly geometric from configs/swing_v15_continuous_folds.json duration.
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

# B4 published majority_1x normal reference (control gate, exact).
PUBLISHED = {"total_return": 1.6517829563633004,
             "max_drawdown": -0.20086073993367803, "trades": 63}


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from reference (control_1x) equity, at given signal times."""
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
    assert list(cfg["branches"]) == ["control_1x", "control_dd_guard", "trend60_agree_1x",
                                     "trend60_agree_dd_guard", "trend240_agree_1x",
                                     "trend240_agree_dd_guard"], "branches must be pre-specified"
    assert list(cfg["trend_formula"]["lookbacks"]) == [60, 240]
    root = Path(__file__).resolve().parents[1]

    candles = pd.read_parquet(root / cfg["base"]["candles_5m"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    frozen = pd.read_parquet(root / cfg["base"]["signals"])
    assert len(frozen) == cfg["base"]["n_signals_frozen"] == 94, "frozen majority count changed"
    m1dir = root / cfg["base"]["m1dir"]
    files_1m = sorted(m1dir.glob("klines_*_1m_*.parquet"))
    m1 = pd.concat([pd.read_parquet(f) for f in files_1m], ignore_index=True)
    m1 = m1.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    m1["close_time"] = pd.to_datetime(m1["close_time"], utc=True)
    m1_idx = {t: i for i, t in enumerate(m1["open_time"])}

    # ---- coverage + micro-trend per L (causal: close_time <= signal_time) ----
    LOOKBACKS = [int(x) for x in cfg["trend_formula"]["lookbacks"]]
    per_L = {}
    for L in LOOKBACKS:
        rows = []
        for pos, r in enumerate(frozen.itertuples()):
            bar = candles.iloc[int(r.bar_index)]
            S = pd.Timestamp(bar["close_time"])
            assert pd.Timestamp(r.signal_time) == S, "signal_time != candle close"
            base = S.floor("min")
            exp = [base - pd.Timedelta(minutes=k) for k in range(L - 1, -1, -1)]
            found = [t for t in exp if t in m1_idx]
            assert all(m1.iloc[m1_idx[t]]["close_time"] <= S for t in found), f"non-causal 1m at {S}"
            if len(found) == L and list(exp) == found:
                first_open = float(m1.iloc[m1_idx[exp[0]]]["open"])
                last_close = float(m1.iloc[m1_idx[exp[-1]]]["close"])
                trend = last_close - first_open
                tsign = 1 if trend > 0 else (-1 if trend < 0 else 0)
                d = int(r.direction)
                rows.append({"pos": pos, "bar_index": int(r.bar_index),
                             "direction": d, "trend": trend, "trend_sign": tsign,
                             "agree": bool(tsign == d), "flat": bool(tsign == 0),
                             "first_open": first_open, "last_close": last_close})
        full_pos = {x["pos"] for x in rows}
        agree_pos = sorted(x["pos"] for x in rows if x["agree"])
        disag_pos = sorted(x["pos"] for x in rows if not x["agree"])
        n_full = len(rows)
        n_part = sum(1 for pos, r in enumerate(frozen.itertuples())
                     if pos not in full_pos and any(
                         (pd.Timestamp(candles.iloc[int(r.bar_index)]["close_time"]).floor("min")
                          - pd.Timedelta(minutes=k)) in m1_idx for k in range(L - 1, -1, -1)))
        per_L[L] = {"rows": rows, "full": n_full, "partial_or_zero_dropped": len(frozen) - n_full,
                    "agree": agree_pos, "disagree": disag_pos,
                    "n_agree": len(agree_pos), "n_disagree": len(disag_pos),
                    "n_flat": sum(1 for x in rows if x["flat"]),
                    "agree_long": sum(1 for x in rows if x["agree"] and x["direction"] == 1),
                    "agree_short": sum(1 for x in rows if x["agree"] and x["direction"] == -1),
                    "agreement_rate": (len(agree_pos) / n_full) if n_full else float("nan"),
                    "trend_bps": [x["trend"] / x["first_open"] * 1e4 for x in rows]}
        print(json.dumps({"lookback": L, "coverage": {"n_frozen": len(frozen), "full": n_full,
                                                      "dropped": len(frozen) - n_full},
                          "agreement": {"agree": len(agree_pos), "disagree": len(disag_pos),
                                        "flat": per_L[L]["n_flat"],
                                        "agree_long": per_L[L]["agree_long"],
                                        "agree_short": per_L[L]["agree_short"],
                                        "rate": per_L[L]["agreement_rate"]}}), flush=True)
    overlap60_240 = sorted(set(per_L[60]["agree"]) & set(per_L[240]["agree"]))
    print(json.dumps({"agree_overlap_60_240": len(overlap60_240)}), flush=True)

    ds_cfg = json.loads((root / cfg["base"]["dataset_config"]).read_text())
    parent = json.loads((root / cfg["base"]["parent_plan"]).read_text())
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
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                   tp1_fraction=0.5, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=0.5, leverage=LEV_MIN, max_leverage=LEV_MAX)

    def build(positions):
        df = frozen.iloc[sorted(positions)].copy().reset_index(drop=True)
        if "leverage" in df.columns:
            df = df.drop(columns=["leverage"])
        return df

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    results, n_sigs, specs = {}, {}, {}

    # ---- control_1x first (reproduction gate on 94) ----
    cdir = a.output / "control_1x"
    cdir.mkdir()
    full_sig = build(range(len(frozen)))
    full_sig.to_parquet(cdir / "signals.parquet", index=False)
    full_scen, control_trades = run_branch(candles, full_sig, costs, fee_costs,
                                           exec_for("1x"), stress, duration, cdir)
    n = full_scen["normal"]
    ok = (abs(n["total_return"] - PUBLISHED["total_return"]) < 1e-6
          and abs(n["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
          and n["trades"] == PUBLISHED["trades"])
    print(json.dumps({"branch": "control_1x", "n_signals": len(full_sig),
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
    results["control_1x"] = {"scenarios": full_scen, "filter": "none", "sizing": "1x"}
    n_sigs["control_1x"] = len(full_sig)
    specs["control_1x"] = list(range(len(frozen)))

    # ---- remaining 5 pre-specified branches ----
    plan = [("control_dd_guard", list(range(len(frozen))), "dd_guard"),
            ("trend60_agree_1x", per_L[60]["agree"], "1x"),
            ("trend60_agree_dd_guard", per_L[60]["agree"], "dd_guard"),
            ("trend240_agree_1x", per_L[240]["agree"], "1x"),
            ("trend240_agree_dd_guard", per_L[240]["agree"], "dd_guard")]
    for branch, positions, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        sig = build(positions)
        guard_frac = None
        if sizing == "dd_guard":
            guard_vec = dd_guard_leverage_at(pd.to_datetime(sig["signal_time"], utc=True),
                                             control_trades)
            sig = sig.copy()
            sig["leverage"] = guard_vec
            guard_frac = float((guard_vec == DD_GUARD_LEV).mean())
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, fee_costs,
                                  exec_for(sizing), stress, duration, bdir)
        results[branch] = {"scenarios": scenarios,
                           "filter": branch.replace(f"_{sizing}", ""),
                           "sizing": sizing, "guard_frac_low": guard_frac}
        n_sigs[branch] = len(sig)
        specs[branch] = sorted(positions)
        print(json.dumps({"branch": branch, "n_signals": len(sig),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades",
                                            "rejected_or_unfilled_signals"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
              flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": n_sigs[b], "filter": v["filter"], "sizing": v["sizing"],
                   "guard_frac_low": v.get("guard_frac_low"),
                   "signal_positions": specs[b],
                   "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "control_check": {"published": PUBLISHED,
                                "reproduced": {k: n[k] for k in
                                               ("total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net")},
                                "match": True},
              "coverage_agreement": {
                  str(L): {"n_frozen": len(frozen), "full_history": per_L[L]["full"],
                           "dropped_no_history": per_L[L]["partial_or_zero_dropped"],
                           "n_agree": per_L[L]["n_agree"], "n_disagree": per_L[L]["n_disagree"],
                           "n_flat": per_L[L]["n_flat"], "agree_long": per_L[L]["agree_long"],
                           "agree_short": per_L[L]["agree_short"],
                           "agreement_rate": per_L[L]["agreement_rate"],
                           "trend_bps": {"mean": float(np.mean(per_L[L]["trend_bps"])),
                                         "median": float(np.median(per_L[L]["trend_bps"]))},
                           "agree_positions": per_L[L]["agree"],
                           "disagree_positions": per_L[L]["disagree"]}
                  for L in LOOKBACKS},
              "agree_overlap_60_240": {"n": len(overlap60_240), "positions": overlap60_240},
              "dd_guard": {"reference": ("control_1x (94-signal, frozen) sampled equity from THIS run "
                                         "(trade exit_time/equity_after), past-only 1-microsecond cutoff, "
                                         "100.0 seed; trigger 10%, lev 0.5; applied at each branch's OWN "
                                         "signal times via leverage column only; geometry untouched."),
                           "trigger": DD_TRIGGER, "lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY ONLY: opened 2023-2026 development interval. Dropped-signal subsets "
                          "(54/94 per L lack full 1m history) are a disclosed auxiliary-data limitation, not "
                          "a trade filter. Drawdown is trade-candle-close sampled, not true mark-price/intrabar "
                          "drawdown. Stop/timeout exits are market-like at the scenario fee, not guaranteed "
                          "maker fills."),
              "input_sha256": {"base_majority": sha256(root / cfg["base"]["signals"]),
                               **{str(q): sha256(root / q) for q in
                                  (cfg["base"]["candles_5m"], cfg["base"]["dataset_config"],
                                   cfg["base"]["parent_plan"], "configs/opencode_v53_1mtrend.json")},
                               "manifest_1m": sha256(m1dir / "manifest.json"),
                               "n_1m_files": len(files_1m), "n_1m_rows": int(len(m1))},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
