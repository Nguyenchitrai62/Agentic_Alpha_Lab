"""Opencode v15 (R3-B4): calibration-mapping ensemble vote on FROZEN v30 outputs.

Frozen inputs (never refit):
  artifacts/research/opencode_v02_reproduce_v30/{isotonic_2,isotonic_4,isotonic_all}/predictions.npz
Pre-specified matrix (fixed in configs/opencode_v15_mapensemble.json before running):
  votes {iso4_only, majority 2-of-3, unanimous 3-of-3, iso4-confirmed-by-isoall}
  x sizing {1x, dd_guard} = 8 branches.
Method (causal past-only; mappings frozen, per-row; voting uses same-row outputs only):
  - Per decision row, compute choose() per map with the identical dataset policy
    config. Direction: LONG=+1, SHORT=-1, WAIT=0.
  - Vote filters gate rows BEFORE the frequency loop; each branch then runs the
    IDENTICAL frequency loop (monthly cap 4 + 5-day cooldown, time order) over
    its passing rows. Emitted geometry/scores are ALWAYS the iso4 choose()
    output on that row ("take iso4 geometry on agreement rows").
  - majority: exists d!=0 with count>=2 AND d4==d (iso4 in the majority).
  - unanimous: d2==d4==dAll!=0. confirmed: d4!=0 and dAll==d4.
  dd_guard lev = 0.5 while CONTROL (iso4_only_1x) sampled equity is >10% under
  its trailing peak (past-only, 1-microsecond cutoff, 100.0 seed), else 1.0;
  applied at each branch's own signal times. Same formula as
  scripts/opencode_r1a_holding_probe.py.
Each branch x 3 scenarios (normal / fee_stress / execution_stress).
Exploratory: the 2023-2026 interval is opened development data, NOT an independent test.
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

# Published isotonic_4 exposure1.0 normal reference (control gate).
PUBLISHED = {"total_return": 1.2279837998661565, "max_drawdown": -0.20086073993367803,
             "trades": 65}


def dir_of(out):
    if out.get("action") == "LONG":
        return 1
    if out.get("action") == "SHORT":
        return -1
    return 0


def gen_from_mask(mask, iso4_outs, part, cfg):
    """Identical frequency loop over pre-filtered rows; emits iso4 geometry."""
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
        if timestamp < next_allowed or monthly[month] >= cfg["policy"]["maximum_signals_per_month"]:
            continue
        sig = dict(out)
        sig.pop("action", None)
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp, **sig})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=cfg["policy"]["cooldown_days"])
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def dd_guard_leverage(signals, trades):
    """Disclosed method shared with r1a holding probe.

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal time
    uses only exits strictly before the signal timestamp (past-only, 100.0 seed).
    Reference is the CONTROL (iso4_only_1x) book for every branch.
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
    expected = ["iso4_only_1x", "iso4_only_dd_guard", "majority_1x", "majority_dd_guard",
                "unanimous_1x", "unanimous_dd_guard", "confirmed_1x", "confirmed_dd_guard"]
    assert list(cfg["branches"]) == expected, "branches must be pre-specified 8-branch vote x sizing matrix"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    decisions = pd.read_parquet(root / cfg["decisions"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    preds = {}
    idx = None
    for m in ("isotonic_2", "isotonic_4", "isotonic_all"):
        with np.load(root / cfg["predictions"][m]) as z:
            preds[m] = {"prediction": z["prediction"], "decision_indices": z["decision_indices"]}
        if idx is None:
            idx = preds[m]["decision_indices"]
        else:
            assert bool((idx == preds[m]["decision_indices"]).all()), "decision_indices must match across maps"
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

    # ---- Per-row frozen choose() per map (same-row only) ----
    outs = {}
    dirs = {}
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
    mask_iso4_only = d4 != 0
    mask_majority = np.array([
        (d4[i] != 0) and ([d2[i], d4[i], dall[i]].count(int(d4[i])) >= 2)
        for i in range(n)], dtype=bool)
    mask_unanimous = (d2 == d4) & (d4 == dall) & (d4 != 0)
    mask_confirmed = (d4 != 0) & (dall == d4)
    masks = {"iso4_only": mask_iso4_only, "majority": mask_majority,
             "unanimous": mask_unanimous, "confirmed": mask_confirmed}
    agreement = {
        "n_rows": int(n),
        "nonwait_iso2": int((d2 != 0).sum()),
        "nonwait_iso4": int((d4 != 0).sum()),
        "nonwait_isoall": int((dall != 0).sum()),
        "pass_iso4_only": int(mask_iso4_only.sum()),
        "pass_majority": int(mask_majority.sum()),
        "pass_unanimous": int(mask_unanimous.sum()),
        "pass_confirmed": int(mask_confirmed.sum()),
        "agree_iso4_isoall_given_iso4": float(mask_confirmed.sum() / mask_iso4_only.sum()) if mask_iso4_only.sum() else 0.0,
        "agree_unanimous_given_iso4": float(mask_unanimous.sum() / mask_iso4_only.sum()) if mask_iso4_only.sum() else 0.0,
        "agree_majority_given_iso4": float(mask_majority.sum() / mask_iso4_only.sum()) if mask_iso4_only.sum() else 0.0,
    }
    print(json.dumps({"agreement_row_level": agreement}, default=str), flush=True)

    cap = int(max(ds_cfg["holding_days"]) * BARS_PER_DAY)

    def exec_for(sizing):
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX)

    # ---- Control: iso4_only @1x (must reproduce published) ----
    base_sigs = {k: gen_from_mask(m, outs["isotonic_4"], part, ds_cfg) for k, m in masks.items()}
    for k, s in base_sigs.items():
        print(json.dumps({"filter": k, "n_signals": int(len(s))}), flush=True)
    control_signals = base_sigs["iso4_only"]
    ref_dir = a.output / "iso4_only_1x"
    ref_dir.mkdir()
    ref_scenarios, ref_trades = run_branch(candles, control_signals.drop(
        columns=["leverage"]) if "leverage" in control_signals.columns else control_signals,
        costs, exec_for("1x"), duration, ref_dir)
    control_signals.to_parquet(ref_dir / "signals.parquet", index=False)
    results = {"iso4_only_1x": ref_scenarios}

    normal = ref_scenarios["normal"]
    control_check = {
        "published": PUBLISHED,
        "reproduced": {"total_return": normal["total_return"],
                       "max_drawdown": normal["max_drawdown"], "trades": normal["trades"],
                       "n_signals": int(len(control_signals))},
        "match": bool(abs(normal["total_return"] - PUBLISHED["total_return"]) < 1e-6
                      and abs(normal["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
                      and normal["trades"] == PUBLISHED["trades"]),
    }
    print(json.dumps({"control_check": control_check}, default=str), flush=True)
    if not control_check["match"]:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(control_check, indent=2))
        print("CONTROL MISMATCH: STOP; iso4_only_1x does not match published "
              "+122.80%/-20.09%/65 normal", flush=True)
        sys.exit(1)

    # ---- Remaining 7 branches ----
    for vote in ("iso4_only", "majority", "unanimous", "confirmed"):
        for sizing in ("1x", "dd_guard"):
            branch = f"{vote}_{sizing}"
            if branch in results:
                continue
            bdir = a.output / branch
            bdir.mkdir()
            base = base_sigs[vote]
            if sizing == "1x":
                sig = base.drop(columns=["leverage"]) if "leverage" in base.columns else base.copy()
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, exec_for("1x"), duration, bdir)
            else:
                levs = dd_guard_leverage(base, ref_trades) if len(base) else np.array([], dtype=float)
                sig = base.copy()
                sig["leverage"] = levs
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, exec_for("dd_guard"), duration, bdir)
            results[branch] = scenarios
            print(json.dumps({"branch": branch, "n_signals": int(len(base)),
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
              "agreement_row_level": agreement,
              "n_signals_per_filter": {k: int(len(v)) for k, v in base_sigs.items()},
              "formulas": {"dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "guard_reference": cfg.get("dd_guard_reference", ""),
                           "vote": "same-row choose() directions only; frequency loop identical per branch; iso4 geometry",
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
