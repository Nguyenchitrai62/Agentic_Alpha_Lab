"""Opencode v58 (R18-B): 1m-range realized-volatility regime filter on frozen majority_1x.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  candles 5m + 1m audit dir (local existing data only, NO new crawl).
Pre-specified matrix (configs/opencode_v58_1mvol.json BEFORE running):
  {control, low-vol-only, mid-vol-only, high-vol-only} x {1x, dd_guard} = 8 branches.
Volatility for each signal: std (ddof=1) of 1m close log-returns over the trailing
1440 1m bars with close_time in (S-24h, S] (S = signal_time), annualized by
sqrt(365.2425*24*60). Strictly causal (close_time <= S asserted).
Bands from pooled vol distribution over vol-computable signals, frozen in config:
  low: vol <= p33; mid: p33 < vol <= p66; high: vol > p66.
Signals lacking full 1440-bar history are DROPPED (never extrapolated).
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
L_BARS = 1440

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
    assert list(cfg["branches"]) == ["control_1x", "control_dd_guard", "lowvol_1x",
                                     "lowvol_dd_guard", "midvol_1x", "midvol_dd_guard",
                                     "highvol_1x", "highvol_dd_guard"], "branches must be pre-specified"
    assert cfg["vol_formula"]["n_bars"] == L_BARS == 1440
    assert cfg["vol_formula"]["n_returns"] == 1439
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
    closes = m1["close"].to_numpy(dtype=float)
    ANN = float(cfg["vol_formula"]["annualization_factor"])
    assert abs(ANN - float(np.sqrt(365.2425 * 24 * 60))) < 1e-9, "annualization factor mismatch"

    # ---- trailing-24h 1m realized vol per signal (causal) ----
    vols = {}  # frozen pos -> ann vol
    for pos, r in enumerate(frozen.itertuples()):
        bar = candles.iloc[int(r.bar_index)]
        S = pd.Timestamp(bar["close_time"])
        assert pd.Timestamp(r.signal_time) == S, "signal_time != candle close"
        base = S.floor("min")
        exp = [base - pd.Timedelta(minutes=k) for k in range(L_BARS - 1, -1, -1)]
        found = [t for t in exp if t in m1_idx]
        assert all(m1.iloc[m1_idx[t]]["close_time"] <= S for t in found), f"non-causal 1m at {S}"
        if len(found) == L_BARS and list(exp) == found:
            idx = [m1_idx[t] for t in exp]
            c = closes[idx]
            assert np.all(c > 0), "non-positive 1m close"
            lr = np.log(c[1:] / c[:-1])
            vols[pos] = float(np.std(lr, ddof=1)) * ANN
    n_full = len(vols)
    n_dropped = len(frozen) - n_full
    print(json.dumps({"coverage": {"n_frozen": len(frozen), "full_1440": n_full,
                                   "dropped_no_history": n_dropped}}), flush=True)

    # ---- pre-specified tercile bands (assert honesty before backtests) ----
    assert n_full == cfg["bands"]["pooled_n"] == 19, f"coverage changed: {n_full}"
    assert n_dropped == cfg["bands"]["dropped_no_history"] == 75
    arr = np.array(sorted(vols.values()))
    p33 = float(np.quantile(arr, 1 / 3))
    p66 = float(np.quantile(arr, 2 / 3))
    assert abs(p33 - cfg["bands"]["p33"]) < 1e-9, f"p33 drift {p33}"
    assert abs(p66 - cfg["bands"]["p66"]) < 1e-9, f"p66 drift {p66}"
    low_pos = sorted(pos for pos, v in vols.items() if v <= cfg["bands"]["p33"])
    mid_pos = sorted(pos for pos, v in vols.items()
                     if v > cfg["bands"]["p33"] and v <= cfg["bands"]["p66"])
    high_pos = sorted(pos for pos, v in vols.items() if v > cfg["bands"]["p66"])
    assert low_pos == cfg["bands"]["expected_positions"]["low"], f"low drift {low_pos}"
    assert mid_pos == cfg["bands"]["expected_positions"]["mid"], f"mid drift {mid_pos}"
    assert high_pos == cfg["bands"]["expected_positions"]["high"], f"high drift {high_pos}"
    assert len(low_pos) == cfg["bands"]["expected_counts"]["low"] == 7
    assert len(mid_pos) == cfg["bands"]["expected_counts"]["mid"] == 6
    assert len(high_pos) == cfg["bands"]["expected_counts"]["high"] == 6
    print(json.dumps({"bands": {"p33": p33, "p66": p66,
                                "low": {"n": len(low_pos), "positions": low_pos},
                                "mid": {"n": len(mid_pos), "positions": mid_pos},
                                "high": {"n": len(high_pos), "positions": high_pos}}}), flush=True)

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

    # ---- remaining 7 pre-specified branches ----
    plan = [("control_dd_guard", list(range(len(frozen))), "dd_guard"),
            ("lowvol_1x", low_pos, "1x"),
            ("lowvol_dd_guard", low_pos, "dd_guard"),
            ("midvol_1x", mid_pos, "1x"),
            ("midvol_dd_guard", mid_pos, "dd_guard"),
            ("highvol_1x", high_pos, "1x"),
            ("highvol_dd_guard", high_pos, "dd_guard")]
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
        filt = "control" if branch.startswith("control") else branch.replace(f"_{sizing}", "")
        results[branch] = {"scenarios": scenarios, "filter": filt,
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
    per_sig = [{"pos": pos, "signal_time": str(pd.Timestamp(
        candles.iloc[int(frozen.iloc[pos]["bar_index"])]["close_time"])),
        "direction": int(frozen.iloc[pos]["direction"]),
        "vol_ann": vols[pos]} for pos in sorted(vols)]
    report = {"branches": flagged, "config": cfg,
              "control_check": {"published": PUBLISHED,
                                "reproduced": {k: n[k] for k in
                                               ("total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net")},
                                "match": True},
              "coverage_vol": {"n_frozen": len(frozen), "full_history_1440": n_full,
                               "dropped_no_history": n_dropped,
                               "pooled_vol_ann": {"min": float(arr.min()),
                                                  "p33": p33, "median": float(np.median(arr)),
                                                  "p66": p66, "max": float(arr.max())},
                               "low_positions": low_pos, "mid_positions": mid_pos,
                               "high_positions": high_pos,
                               "per_signal": per_sig},
              "dd_guard": {"reference": ("control_1x (94-signal, frozen) sampled equity from THIS run "
                                         "(trade exit_time/equity_after), past-only 1-microsecond cutoff, "
                                         "100.0 seed; trigger 10%, lev 0.5; applied at each branch's OWN "
                                         "signal times via leverage column only; geometry untouched."),
                           "trigger": DD_TRIGGER, "lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY ONLY: opened 2023-2026 development interval. Vol-computable subset "
                          "is 19/94 (75 dropped for lacking full 1440-bar 1m history) — a disclosed "
                          "auxiliary-data limitation, not a trade filter. Band thresholds are pooled terciles "
                          "frozen BEFORE backtests. Drawdown is trade-candle-close sampled, not true "
                          "mark-price/intrabar drawdown. Stop/timeout exits are market-like at the scenario "
                          "fee, not guaranteed maker fills."),
              "input_sha256": {"base_majority": sha256(root / cfg["base"]["signals"]),
                               **{str(q): sha256(root / q) for q in
                                  (cfg["base"]["candles_5m"], cfg["base"]["dataset_config"],
                                   cfg["base"]["parent_plan"], "configs/opencode_v58_1mvol.json")},
                               "manifest_1m": sha256(m1dir / "manifest.json"),
                               "n_1m_files": len(files_1m), "n_1m_rows": int(len(m1))},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
