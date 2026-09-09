"""Opencode v74 (R24-L3 RISK REDUCER): risk matrix on FROZEN signals.

L2 output artifacts/research/opencode_v73_L2filter/<best-filter>/signals.parquet
was ABSENT at pre-spec time -> this driver runs SMOKE on frozen v38-identity
signals (artifacts/research/opencode_v59_v38cal/v38-identity/signals.parquet,
135 signals, raw rank_en WITHOUT isoall). L2 rerun: pass --signals <l2 parquet>
+ amend config (signals path, control-check values, mae_cap_X per L2 X-rule).

Pre-specified matrix (configs/opencode_v74_L3risk.json, all frozen):
  control_1x | dd_guard | tp075_1x | mae_stop_1x | dd_guard_tp075 |
  full_dd_tp075_mae  (+ diagnostic-only aux _ref_mae_tp075_1x as own-book
  guard reference for full; excluded from the 6-branch table).
dd_guard: 0.5x while OWN-BOOK 1x reference equity >10% under trailing peak
  (past-only, 1-microsecond cutoff, 100.0 seed), else 1.0.
MAE-stop (NEW): stop_loss tighten with entry_limit proxy, keep TPs:
  LONG  applied = max(orig, entry_limit*(1-X));
  SHORT applied = min(orig, entry_limit*(1+X)); no-op counted.
Control gate (smoke): control_1x normal must reproduce
  +57.1208% / -29.6389% / 81 trades or STOP.
3 scenarios: normal / fee 0.00055 / FillStress(5,5,5,0.00055,False).
Monthly geometric from configs/swing_v15_continuous_folds.json.
Per branch: Ret/DD/Mo/N/PF + MAE-mean/p50/p75/p90 + funding/fees +
  risk-cost accounting. Exploratory; no live approval; never overwrites.
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

DD_TRIGGER_KEY = "dd_trigger"
DD_LEV_KEY = "dd_guard_lev"


def dd_guard_leverage_at(signal_times, ref_trades, trigger, lev):
    """Guard state from own-book reference equity at given signal times."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in signal_times:
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(lev if level / peak < 1.0 - trigger else 1.0)
    return np.array(out, dtype=float)


def apply_mae_stop(signals, x):
    """Tighten stop_loss with entry_limit proxy. Returns (frame, n_noop)."""
    assert 0 < x < 1, f"mae_cap_X must satisfy 0<X<1, got {x}"
    sig = signals.copy()
    noop = 0
    new_stops = []
    for row in sig.itertuples():
        el, sl = float(row.entry_limit), float(row.stop_loss)
        if int(row.direction) == 1:
            assert sl < el, f"LONG stop not below entry_limit: {sl} vs {el}"
            cand = el * (1.0 - x)
            assert cand < el
            applied = max(sl, cand)
        elif int(row.direction) == -1:
            assert sl > el, f"SHORT stop not above entry_limit: {sl} vs {el}"
            cand = el * (1.0 + x)
            assert cand > el
            applied = min(sl, cand)
        else:
            raise ValueError("direction must be +-1")
        if applied == sl:
            noop += 1
        new_stops.append(applied)
    sig["stop_loss"] = new_stops
    return sig, noop


def mae_stats(trades, candles):
    """5m-only per-trade MAE magnitude stats (diagnostic, post-entry extremes)."""
    if not trades:
        return {"n": 0, "mean": None, "p50": None, "p75": None, "p90": None, "max": None}
    lo = candles["low"].to_numpy()
    hi = candles["high"].to_numpy()
    mag = []
    for t in trades:
        seg_lo = lo[t.entry_index:t.exit_index + 1].min()
        seg_hi = hi[t.entry_index:t.exit_index + 1].max()
        if t.direction == 1:
            adv = (seg_lo - t.entry_price) / t.entry_price
        else:
            adv = (t.entry_price - seg_hi) / t.entry_price
        mag.append(max(0.0, -adv))
    m = np.asarray(mag, dtype=float)
    return {"n": int(len(mag)), "mean": float(m.mean()) * 100,
            "p50": float(np.quantile(m, 0.5)) * 100,
            "p75": float(np.quantile(m, 0.75)) * 100,
            "p90": float(np.quantile(m, 0.9)) * 100,
            "max": float(m.max()) * 100}


def run_branch(candles, signals, costs, fee_costs, execution, stress, years, bdir):
    scenarios, trade_lists = {}, {}
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    estress, st, diagnostic = run_stress(candles, signals, 100, costs, execution, stress)
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                ("execution_stress", estress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * years)) - 1,
                            "mae": mae_stats(items, candles)}
        trade_lists[label] = items
        pd.DataFrame([asdict(t) for t in items]).to_csv(bdir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios, trade_lists


def gate_flags(scenarios, gate):
    flags = {}
    for s in ("normal", "fee_stress", "execution_stress"):
        m = scenarios[s]
        flags[s] = {"monthly_pass": bool(m["monthly_geometric_net"] >= gate["monthly_geometric_net_min"]),
                    "dd_pass": bool(abs(m["max_drawdown"]) <= gate["drawdown_max"]),
                    "fills_pass": bool(m["trades"] >= gate["fills_min"])}
        flags[s]["scenario_pass"] = all(flags[s].values())
    flags["overall_pass"] = all(flags[s]["scenario_pass"] for s in
                                ("normal", "fee_stress", "execution_stress"))
    return flags


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--signals", type=Path, default=None,
                   help="Override frozen signals (L2 parquet when present).")
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    root = Path(__file__).resolve().parents[1]

    # Runtime VERIFY: stress path honors tp1_fraction AND signal.stop_loss.
    stress_src = (root / "src/agentic_alpha_lab/backtest/execution_stress.py").read_text()
    assert "execution.tp1_fraction" in stress_src, "stress path ignores tp1_fraction"
    assert "signal.stop_loss" in stress_src, "stress path ignores stop_loss"

    sig_path = root / a.signals if a.signals else root / cfg["smoke_base"]
    l2_expected = root / cfg["l2_expected"].replace("<best-filter>", "*")
    candles = pd.read_parquet(root / cfg["candles"])
    base_signals = pd.read_parquet(sig_path)
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    X = float(cfg["frozen_constants"]["mae_cap_X"])
    TRG = float(cfg["frozen_constants"][DD_TRIGGER_KEY])
    GLV = float(cfg["frozen_constants"][DD_LEV_KEY])
    LEV_MIN = float(cfg["frozen_constants"]["lev_min"])
    LEV_MAX = float(cfg["frozen_constants"]["lev_max"])
    TP_C = float(cfg["frozen_constants"]["tp1_control"])
    TP_75 = float(cfg["frozen_constants"]["tp1_tp075"])
    assert 0 < TP_C < 1 and 0 < TP_75 < 1 and 0 < X < 1

    def exec_for(tp1, sizing):
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                   tp1_fraction=tp1, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=tp1, leverage=LEV_MIN, max_leverage=LEV_MAX)

    def prepared(tp1, sizing, stops="original", guard_vec=None):
        sig = base_signals.copy()
        sig["tp1_fraction"] = tp1  # provenance only; engine reads ExecutionConfig
        if stops == "mae_tightened":
            sig, _ = apply_mae_stop(sig, X)
        if sizing == "1x":
            if "leverage" in sig.columns:
                sig = sig.drop(columns=["leverage"])
        else:
            assert guard_vec is not None
            sig["leverage"] = guard_vec
        return sig.reset_index(drop=True)

    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    gate = cfg["gate"]
    results, trade_store, meta = {}, {}, {}

    def run_and_store(branch, sig, ex):
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, trades = run_branch(candles, sig, costs, fee_costs, ex, stress, years, bdir)
        results[branch] = scenarios
        trade_store[branch] = trades
        return scenarios

    # --- control first (reproduction gate) ---
    ref_sig = prepared(TP_C, "1x", "original")
    ref_scen = run_and_store("control_1x", ref_sig, exec_for(TP_C, "1x"))
    n = ref_scen["normal"]
    cc = cfg["control_check_smoke"]
    ok = (abs(n["total_return"] - cc["total_return"]) < cc["tolerance_return"]
          and abs(n["max_drawdown"] - cc["max_drawdown"]) < cc["tolerance_dd"]
          and n["trades"] == cc["trades"])
    print(json.dumps({"branch": "control_1x", "n_signals": len(ref_sig),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL"}), flush=True)
    if not ok:
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} "
                         f"{n['max_drawdown']=} {n['trades']=}; STOP")
    _, control_trades = run_backtest(candles, ref_sig, 100, costs, exec_for(TP_C, "1x"))
    meta["control_1x"] = {"n_signals": len(ref_sig), "stops": "original",
                          "tp1_fraction": TP_C, "sizing": "1x", "mae_noop": 0}

    def guard_from_own_book(one_x_sig, one_x_trades):
        return dd_guard_leverage_at(pd.to_datetime(one_x_sig["signal_time"]),
                                    one_x_trades, TRG, GLV)

    # dd_guard (own-book = control equity)
    g = guard_from_own_book(ref_sig, control_trades)
    sig = prepared(TP_C, "dd_guard", "original", g)
    run_and_store("dd_guard", sig, exec_for(TP_C, "dd_guard"))
    meta["dd_guard"] = {"n_signals": len(sig), "stops": "original", "tp1_fraction": TP_C,
                        "sizing": "dd_guard", "guard_ref": "own-book control_1x",
                        "guard_low_frac": float((g == GLV).mean())}

    # tp075_1x
    sig75 = prepared(TP_75, "1x", "original")
    run_and_store("tp075_1x", sig75, exec_for(TP_75, "1x"))
    tr75_1x = trade_store["tp075_1x"]["normal"]
    meta["tp075_1x"] = {"n_signals": len(sig75), "stops": "original",
                        "tp1_fraction": TP_75, "sizing": "1x", "mae_noop": 0}

    # mae_stop_1x
    sig_mae, noop = apply_mae_stop(base_signals.copy(), X)
    sig_mae["tp1_fraction"] = TP_C
    if "leverage" in sig_mae.columns:
        sig_mae = sig_mae.drop(columns=["leverage"])
    sig_mae = sig_mae.reset_index(drop=True)
    run_and_store("mae_stop_1x", sig_mae, exec_for(TP_C, "1x"))
    meta["mae_stop_1x"] = {"n_signals": len(sig_mae), "stops": "mae_tightened",
                           "tp1_fraction": TP_C, "sizing": "1x",
                           "mae_cap_X": X, "mae_noop": int(noop),
                           "mae_noop_frac": float(noop / len(sig_mae))}

    # dd_guard_tp075 (own-book = tp075_1x equity)
    g75 = guard_from_own_book(sig75, tr75_1x)
    sig = prepared(TP_75, "dd_guard", "original", g75)
    run_and_store("dd_guard_tp075", sig, exec_for(TP_75, "dd_guard"))
    meta["dd_guard_tp075"] = {"n_signals": len(sig), "stops": "original",
                              "tp1_fraction": TP_75, "sizing": "dd_guard",
                              "guard_ref": "own-book tp075_1x",
                              "guard_low_frac": float((g75 == GLV).mean())}

    # aux mae+tp075 1x (diagnostic-only guard reference for full)
    aux, aux_noop = apply_mae_stop(base_signals.copy(), X)
    aux["tp1_fraction"] = TP_75
    if "leverage" in aux.columns:
        aux = aux.drop(columns=["leverage"])
    aux = aux.reset_index(drop=True)
    _, aux_trades_1x = run_backtest(candles, aux, 100, costs, exec_for(TP_75, "1x"))
    gfull = guard_from_own_book(aux, aux_trades_1x)
    sig = prepared(TP_75, "dd_guard", "mae_tightened", gfull)
    run_and_store("full_dd_tp075_mae", sig, exec_for(TP_75, "dd_guard"))
    meta["full_dd_tp075_mae"] = {"n_signals": len(sig), "stops": "mae_tightened",
                                 "tp1_fraction": TP_75, "sizing": "dd_guard",
                                 "guard_ref": "own-book aux _ref_mae_tp075_1x",
                                 "guard_low_frac": float((gfull == GLV).mean()),
                                 "mae_cap_X": X, "mae_noop": int(aux_noop),
                                 "mae_noop_frac": float(aux_noop / len(sig))}

    # --- report ---
    ctrl = results["control_1x"]
    flagged = {}
    for branch, scenarios in results.items():
        rc = {}
        for s in ("normal", "fee_stress", "execution_stress"):
            m, c = scenarios[s], ctrl[s]
            d_cost = (c["monthly_geometric_net"] - m["monthly_geometric_net"]) * 100
            d_dd = (m["max_drawdown"] - c["max_drawdown"]) * 100
            mae_c = c["mae"]["mean"] if c["mae"]["mean"] is not None else float("nan")
            mae_m = m["mae"]["mean"] if m["mae"]["mean"] is not None else float("nan")
            d_mae = mae_c - mae_m
            rc[s] = {"monthly_cost_pp_vs_control": d_cost,
                     "dd_bought_pp": d_dd,
                     "mae_mean_reduction_pp": d_mae,
                     "cost_per_dd_pp": (d_cost / d_dd) if d_dd > 1e-9 else None,
                     "cost_per_mae_pp": (d_cost / d_mae) if d_mae > 1e-9 else None}
        flagged[branch] = {"gate": gate_flags(scenarios, gate), "meta": meta[branch],
                           "risk_cost_vs_control": rc, "scenarios": scenarios}
        print(json.dumps({"branch": branch, "n_signals": meta[branch]["n_signals"],
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "mae_normal": scenarios["normal"]["mae"],
                          "gate": gate_flags(scenarios, gate)["overall_pass"]}), flush=True)

    sig_src = str(a.signals) if a.signals else cfg["smoke_base"]
    report = {"branches": flagged, "config": cfg,
              "mode": "SMOKE-v38-identity (L2 absent; no data invented)" if not a.signals else "L2",
              "signals_source": sig_src,
              "duration_years": years, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened development interval only ("
                          + parent["complete_evaluation_until"] + "). MAE cap X chosen "
                          "from full-sample MAE (in-sample). Smoke base is raw v38 "
                          "rank_en WITHOUT isoall calibration. Do not promote or claim "
                          "validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], sig_src, cfg["dataset_config"],
                                cfg["parent_plan"], "configs/opencode_v74_L3risk.json")},
              "gate": {"monthly_min": gate["monthly_geometric_net_min"],
                       "dd_max": gate["drawdown_max"], "fills_min": gate["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
