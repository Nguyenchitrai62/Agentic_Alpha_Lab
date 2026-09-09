"""Opencode v144 (R56-E-relaxcap): relaxed-cap variant on FROZEN majority_1x path.

Pre-spec: configs/opencode_v144_relaxcap.json (written BEFORE running).
Base: VERBATIM v15 majority (frozen v30 iso2/iso4/isoall predictions + choose()
per map, majority = 2-of-3 with iso4 participating, iso4 geometry).
Single-variable change: frequency loop cap 4->10, cooldown 5->2d.
Branches: majority_cap4_cd5_1x (control), majority_cap10_cd2_1x (relaxed),
  majority_cap10_cd2_ddguard (relaxed + dd_guard overlay, cheap).
Each branch x 3 scenarios (normal / fee_stress / execution_stress).
Control gate: majority_cap4_cd5_1x normal must reproduce published majority_1x
  (+165.17829563633006%, -20.086073993367803%, 63 trades; tol 1e-6) or STOP.
Kill criteria + displacement audit per pre-spec (in-sample exploratory).
NO live orders; local backtests only; causal past-only; exploratory labels.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
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

PUBLISHED_MAJORITY = {"total_return": 1.6517829563633004,
                      "max_drawdown": -0.20086073993367803, "trades": 63}


def dir_of(out):
    if out.get("action") == "LONG":
        return 1
    if out.get("action") == "SHORT":
        return -1
    return 0


def gen_from_mask(mask, iso4_outs, part, cap, cooldown_days):
    """Frequency loop VERBATIM replica of r3b4 (gen_from_mask), parameterized
    ONLY in cap/cooldown. Same row order, same skip logic, no re-sorting."""
    signals, monthly = [], Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    for i, row in enumerate(part.itertuples()):
        if not bool(mask[i]):
            continue
        out = iso4_outs[i]
        if out is None or out.get("action") == "WAIT":
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= cap:
            continue
        sig = dict(out)
        sig.pop("action", None)
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp, **sig})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=cooldown_days)
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def dd_guard_leverage(signals, trades):
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
    assert list(cfg["branches"]) == ["majority_cap4_cd5_1x", "majority_cap10_cd2_1x",
                                     "majority_cap10_cd2_ddguard"], "branches must match v144 pre-spec"
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    decisions = pd.read_parquet(root / cfg["decisions"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    # Verbatim policy anchors (must NOT differ from dataset config)
    assert ds_cfg["policy"]["maximum_signals_per_month"] == 4, "dataset cap anchor changed"
    assert ds_cfg["policy"]["cooldown_days"] == 5, "dataset cooldown anchor changed"
    assert ds_cfg["entry_expiry_bars"] == 12
    preds = {}
    idx = None
    for m in ("isotonic_2", "isotonic_4", "isotonic_all"):
        with np.load(root / cfg["predictions"][m]) as z:
            preds[m] = {"prediction": z["prediction"], "decision_indices": z["decision_indices"]}
        if idx is None:
            idx = preds[m]["decision_indices"]
        else:
            assert bool((idx == preds[m]["decision_indices"]).all())
    decision_indices = idx
    part = decisions.iloc[decision_indices].reset_index(drop=True)
    n = len(part)
    for m in ("isotonic_2", "isotonic_4", "isotonic_all"):
        assert preds[m]["prediction"].shape[0] == n
        assert preds[m]["prediction"].shape[1] == len(grid(ds_cfg))

    costs = CostModel(**ds_cfg["costs"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    outs, dirs = {}, {}
    for m in ("isotonic_2", "isotonic_4", "isotonic_all"):
        arr = preds[m]["prediction"]
        olist, dlist = [], []
        for i, row in enumerate(part.itertuples()):
            o = choose(arr[i], row.close, row.atr5, row.atr4, ds_cfg)
            olist.append(None if o.get("action") == "WAIT" else o)
            dlist.append(dir_of(o))
        outs[m] = olist
        dirs[m] = np.array(dlist, dtype=int)
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]
    mask_majority = np.array([(d4[i] != 0) and ([d2[i], d4[i], dall[i]].count(int(d4[i])) >= 2)
                              for i in range(n)], dtype=bool)
    agreement = {"n_rows": int(n), "nonwait_iso2": int((d2 != 0).sum()),
                 "nonwait_iso4": int((d4 != 0).sum()),
                 "nonwait_isoall": int((dall != 0).sum()),
                 "pass_majority": int(mask_majority.sum())}
    print(json.dumps({"agreement_row_level": agreement}), flush=True)

    cap = int(max(ds_cfg["holding_days"]) * BARS_PER_DAY)

    def exec_for(sizing):
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX)

    sig_control = gen_from_mask(mask_majority, outs["isotonic_4"], part, 4, 5)
    sig_relaxed = gen_from_mask(mask_majority, outs["isotonic_4"], part, 10, 2)
    print(json.dumps({"n_signals_control_cap4_cd5": int(len(sig_control)),
                      "n_signals_relaxed_cap10_cd2": int(len(sig_relaxed))}), flush=True)

    # ---- Control branch (must reproduce published) ----
    ref_dir = a.output / "majority_cap4_cd5_1x"
    ref_dir.mkdir()
    ref_scenarios, ref_trades = run_branch(
        candles, sig_control.drop(columns=["leverage"]) if "leverage" in sig_control.columns else sig_control,
        costs, exec_for("1x"), duration, ref_dir)
    sig_control.to_parquet(ref_dir / "signals.parquet", index=False)
    results = {"majority_cap4_cd5_1x": ref_scenarios}

    normal = ref_scenarios["normal"]
    control_check = {
        "published": PUBLISHED_MAJORITY,
        "reproduced": {"total_return": normal["total_return"],
                       "max_drawdown": normal["max_drawdown"], "trades": normal["trades"],
                       "n_signals": int(len(sig_control))},
        "match": bool(abs(normal["total_return"] - PUBLISHED_MAJORITY["total_return"]) < 1e-6
                      and abs(normal["max_drawdown"] - PUBLISHED_MAJORITY["max_drawdown"]) < 1e-6
                      and normal["trades"] == PUBLISHED_MAJORITY["trades"]),
    }
    print(json.dumps({"control_check": control_check}, default=str), flush=True)
    if not control_check["match"]:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(control_check, indent=2))
        print("CONTROL MISMATCH: STOP", flush=True)
        sys.exit(1)

    # ---- Relaxed 1x ----
    rdir = a.output / "majority_cap10_cd2_1x"
    rdir.mkdir()
    sig = sig_relaxed.drop(columns=["leverage"]) if "leverage" in sig_relaxed.columns else sig_relaxed.copy()
    sig.to_parquet(rdir / "signals.parquet", index=False)
    r_scenarios, r_trades = run_branch(candles, sig, costs, exec_for("1x"), duration, rdir)
    results["majority_cap10_cd2_1x"] = r_scenarios
    print(json.dumps({"branch": "majority_cap10_cd2_1x", "n_signals": int(len(sig_relaxed)),
                      "metrics": {s: {k: r_scenarios[s][k] for k in
                                       ["total_return", "max_drawdown", "trades",
                                        "monthly_geometric_net", "gross_pnl", "fees",
                                        "funding", "profit_factor", "win_rate",
                                        "long_trades", "short_trades"]}
                                  for s in ("normal", "fee_stress", "execution_stress")}},
                     default=str), flush=True)

    # ---- Relaxed dd_guard (guard ref = THIS control book) ----
    gdir = a.output / "majority_cap10_cd2_ddguard"
    gdir.mkdir()
    levs = dd_guard_leverage(sig_relaxed, ref_trades) if len(sig_relaxed) else np.array([], dtype=float)
    gsig = sig_relaxed.copy()
    gsig["leverage"] = levs
    gsig.to_parquet(gdir / "signals.parquet", index=False)
    g_scenarios, g_trades = run_branch(candles, gsig, costs, exec_for("dd_guard"), duration, gdir)
    results["majority_cap10_cd2_ddguard"] = g_scenarios
    print(json.dumps({"branch": "majority_cap10_cd2_ddguard", "n_signals": int(len(sig_relaxed)),
                      "metrics": {s: {k: g_scenarios[s][k] for k in
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

    # ---- Kill-criteria audit (in-sample, normal headline; stresses reference) ----
    def kill_audit(tag, scen_metrics, control_metrics):
        mo_c = control_metrics["monthly_geometric_net"]
        mo = scen_metrics["monthly_geometric_net"]
        dd_c = control_metrics["max_drawdown"]
        dd = scen_metrics["max_drawdown"]
        pf = scen_metrics.get("profit_factor")
        wr = scen_metrics.get("win_rate")
        n = scen_metrics["trades"]
        mpf_c = mo_c / control_metrics["trades"] if control_metrics["trades"] else None
        mpf = mo / n if n else None
        dil_drop = (mpf_c - mpf) / abs(mpf_c) if (mpf_c and mpf is not None) else None
        return {
            "monthly_control": mo_c, "monthly": mo,
            "monthly_per_fill_control": mpf_c, "monthly_per_fill": mpf,
            "dilution_drop_vs_control": dil_drop,
            "KILL_dilution_drop_gt20pct": bool(dil_drop is not None and dil_drop > 0.20),
            "profit_factor": pf, "win_rate": wr,
            "KILL_quality_pf_lt_1_5_or_wr_lt_50": bool((pf is not None and pf < 1.5) or (wr is not None and wr < 0.5)),
            "dd_control": dd_c, "dd": dd,
            "dd_worse_by_pp": (abs(dd) - abs(dd_c)) if (dd is not None and dd_c is not None) else None,
            "KILL_risk_dd_worse_gt3pp": bool(dd is not None and dd_c is not None and (abs(dd) - abs(dd_c)) > 0.03),
            "KILL_displacement_monthly_lt_control": bool(mo < mo_c),
            "KILL_fills_lt_100": bool(n < 100),
            "fills": n,
        }

    ctl_n = results["majority_cap4_cd5_1x"]["normal"]
    kill = {}
    for branch in ("majority_cap10_cd2_1x", "majority_cap10_cd2_ddguard"):
        kill[branch] = {}
        for scen in ("normal", "fee_stress", "execution_stress"):
            ka = kill_audit(branch, results[branch][scen], results["majority_cap4_cd5_1x"][scen]
                            if scen != "normal" else ctl_n)
            # displacement kill always vs control NORMAL headline? No: per-scenario vs same-scenario control
            # plus headline check vs control normal recorded separately
            ka["KILL_any"] = bool(ka["KILL_dilution_drop_gt20pct"] or ka["KILL_quality_pf_lt_1_5_or_wr_lt_50"]
                                  or ka["KILL_risk_dd_worse_gt3pp"] or ka["KILL_displacement_monthly_lt_control"]
                                  or ka["KILL_fills_lt_100"])
            kill[branch][scen] = ka
    pass_on = {}
    for branch in ("majority_cap10_cd2_1x", "majority_cap10_cd2_ddguard"):
        kn = kill[branch]["normal"]
        rn = results[branch]["normal"]
        pass_on[branch] = bool(rn["trades"] >= 100 and rn["monthly_geometric_net"] >= ctl_n["monthly_geometric_net"]
                               and rn["max_drawdown"] >= -0.20)

    # ---- Displacement audit (normal) ----
    def trade_key_set(trades_csv):
        df = pd.read_csv(trades_csv)
        return df, set(zip(df["entry_time"].astype(str), df["direction"].astype(int))) if len(df) else set()

    ctl_trades_df, ctl_keys = trade_key_set(ref_dir / "normal_trades.csv")
    rel_trades_df, rel_keys = trade_key_set(rdir / "normal_trades.csv")
    common = ctl_keys & rel_keys
    lost = ctl_keys - rel_keys
    added = rel_keys - ctl_keys
    lost_pnl = float(ctl_trades_df[ctl_trades_df.apply(
        lambda r: (str(r["entry_time"]), int(r["direction"])) in lost, axis=1)]["net_pnl"].sum()) if len(ctl_trades_df) and lost else 0.0
    # signals overlap
    c_sig = pd.read_parquet(ref_dir / "signals.parquet")
    r_sig = pd.read_parquet(rdir / "signals.parquet")
    c_sig["signal_time"] = pd.to_datetime(c_sig["signal_time"], utc=True)
    r_sig["signal_time"] = pd.to_datetime(r_sig["signal_time"], utc=True)
    c_keys = set(zip(c_sig["bar_index"].astype(int), c_sig["direction"].astype(int)))
    r_keys = set(zip(r_sig["bar_index"].astype(int), r_sig["direction"].astype(int)))
    extra_sig = r_keys - c_keys
    # displacement pressure: relaxed signals firing while a control position is open
    # (control position windows from entry_time..exit_time of normal trades)
    pressure = 0
    if len(ctl_trades_df) and len(r_sig):
        ctl_windows = [(pd.Timestamp(e, tz="UTC"), pd.Timestamp(x, tz="UTC"))
                       for e, x in zip(ctl_trades_df["entry_time"], ctl_trades_df["exit_time"])]
        ctl_windows.sort()
        for ts in r_sig["signal_time"]:
            if any(s <= ts <= e for s, e in ctl_windows):
                pressure += 1
    displacement = {
        "n_signals_control": int(len(c_sig)), "n_signals_relaxed": int(len(r_sig)),
        "n_extra_signals": int(len(extra_sig)),
        "n_dropped_signals_vs_control": int(len(c_keys - r_keys)),
        "is_superset": bool(len(c_keys - r_keys) == 0),
        "fills_control": int(len(ctl_trades_df)), "fills_relaxed": int(len(rel_trades_df)),
        "fills_common": int(len(common)), "fills_lost_vs_control": int(len(lost)),
        "fills_added": int(len(added)),
        "lost_trades_net_pnl_sum": round(lost_pnl, 4),
        "relaxed_signals_while_control_position_open": int(pressure),
        "note": "single-position engine: extra signals cannot overlap an open position; "
                "lost winners + pressure count test the union-U1 displacement precedent",
    }

    verdict = {}
    for branch in ("majority_cap10_cd2_1x", "majority_cap10_cd2_ddguard"):
        kn = kill[branch]["normal"]
        verdict[branch] = "KILLED" if kn["KILL_any"] else "SURVIVES"
        # PASS-ON gate (forward leg) is stricter than SURVIVES
        verdict[branch + "__pass_on_to_forward"] = bool(pass_on[branch])

    report = {"branches": results, "config": cfg,
              "control_check": control_check,
              "agreement_row_level": agreement,
              "n_signals": {"majority_cap4_cd5_1x": int(len(sig_control)),
                            "majority_cap10_cd2_1x": int(len(sig_relaxed)),
                            "majority_cap10_cd2_ddguard": int(len(sig_relaxed))},
              "kill_criteria_in_sample": kill,
              "pass_on": pass_on,
              "displacement_audit_normal": displacement,
              "verdict_in_sample": verdict,
              "formulas": {"dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "guard_reference": "THIS control majority_cap4_cd5_1x sampled equity, past-only 1us cutoff, 100.0 seed",
                           "vote": "same-row choose() directions only; frequency loop identical except cap/cooldown; iso4 geometry",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio^(1/(12*duration_years))-1"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills.",
              "input_sha256": {
                  "predictions_isotonic_2": sha256(root / cfg["predictions"]["isotonic_2"]),
                  "predictions_isotonic_4": sha256(root / cfg["predictions"]["isotonic_4"]),
                  "predictions_isotonic_all": sha256(root / cfg["predictions"]["isotonic_all"]),
                  "decisions": sha256(root / cfg["decisions"]),
                  "candles": sha256(root / cfg["candles"]),
                  "dataset_config": sha256(root / cfg["dataset_config"]),
                  "parent_plan": sha256(root / cfg["parent_plan"])},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
