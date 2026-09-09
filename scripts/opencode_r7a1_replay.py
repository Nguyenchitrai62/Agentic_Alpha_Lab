"""Opencode R7-A1 (R-AUDIT): continuous portfolio cho A1 fresh-TCN v25 (LOCAL ONLY).

Doc 33 cloud predictions tu training_source (da qua replay audit PASSED) ->
combine theo ensemble_branches cua plan -> swing_signals (combine + choose +
frequency loop: monthly cap + cooldown, time order, causal) -> 2 sizings
{1x, dd_guard own-book past-only theo tien le v03} -> 3 scenarios
(normal + fee_stress 0.00055 + execution_stress FillStress(5,5,5,.00055,False))
+ monthly geometric theo configs/swing_v15_continuous_folds.json.

KHONG train, KHONG cloud, KHONG live. So voi standing_best
(majority_1x 2.935%/mo, confirmed_dd_guard 2.79%/mo DD-safe) va gate
(5%/mo, DD 20%, 30 fills). Tat ca labels exploratory.
"""
import torch  # noqa: F401  (import truoc pandas: DLL load-order tren Windows host)
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.backtest.swing import swing_signals  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402

DD_TRIGGER, DD_GUARD_LEV = 0.1, 0.5
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def partition_indices(decisions, parent):
    end = pd.Timestamp(parent["complete_evaluation_until"])
    parts, previous = [], None
    for start, stop in parent["folds"]:
        start, stop = pd.Timestamp(start), pd.Timestamp(stop)
        if start >= stop or (previous is not None and start != previous):
            raise ValueError("Continuous plan has a gap or overlap")
        previous = stop
        mask = ((decisions.signal_time >= start) & (decisions.signal_time < stop)
                & (decisions.label_end < end)).to_numpy()
        parts.append(np.flatnonzero(mask))
    if previous != end:
        raise ValueError("Final fold does not match evaluation cutoff")
    expected = np.flatnonzero(((decisions.signal_time >= pd.Timestamp(parent["folds"][0][0]))
                               & (decisions.signal_time < end)
                               & (decisions.label_end < end)).to_numpy())
    np.testing.assert_array_equal(np.concatenate(parts), expected)
    return parts


def dd_guard_leverage(signals, trades):
    """0.5 khi equity 1x own-book dang >10% duoi trailing peak (past-only), else 1.0."""
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"]):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out)


def run_branch(candles, signals, costs, execution, years, bdir):
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diag = run_stress(candles, signals, 100, costs, execution,
                                  FillStress(5, 5, 5, 0.00055, False))
    out = {}
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", stress, st)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": ratio ** (1 / years) - 1,
                      "monthly_geometric_net": ratio ** (1 / (12 * years)) - 1}
        rows = [asdict(t) for t in items]
        dest = bdir / f"{label}_trades.csv"
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(dest, index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(dest, index=False)
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def main(a):
    spec = json.loads(a.config.read_text())
    plan = json.loads((ROOT / spec["model_plan"]).read_text())
    parent = json.loads((ROOT / spec["parent_plan"]).read_text())
    source = ROOT / spec["training_source"]
    audit = json.loads((ROOT / spec["audit"]["output"] / "audit.json").read_text())
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(source / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_dir = ROOT / spec["portfolio"]["output"]
    out_file = out_dir / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    ds = ROOT / spec["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    partitions = partition_indices(decisions, parent)
    forecasts, indices = [], []
    for fold in range(len(parent["folds"])):
        selected = partitions[fold]
        batch = []
        for seed in plan["seeds"]:
            path = source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            pred = np.load(path, allow_pickle=False)
            if pred.shape != (len(selected), 16, 6) or not np.isfinite(pred).all():
                raise ValueError(f"Prediction shape/values mismatch: {path}")
            batch.append(pred)
        forecasts.append(np.stack(batch))
        indices.append(selected)
    indices = np.concatenate(indices)
    part = decisions.iloc[indices].reset_index(drop=True)
    stacked = np.concatenate(forecasts, axis=1)  # (seeds, decisions, 16, 6)
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    gate, branches = spec["gate"], {}
    for branch in plan["ensemble_branches"]:
        name = branch["name"]
        if name not in spec["portfolio"]["ensemble_bases"]:
            continue
        combined, _ = combine(stacked, branch["penalty"])
        signals = swing_signals(combined, part, cfg)
        if len(signals) != audit["identical_policy_signals"][name]:
            raise ValueError(f"Portfolio signals khac audit parity: {name}")
        b1 = out_dir / f"{name}_1x"
        b1.mkdir(parents=True, exist_ok=True)
        base = signals.drop(columns=["leverage"], errors="ignore").copy()
        base.to_parquet(b1 / "signals.parquet", index=False)
        exec1x = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        res1x, trades1x = run_branch(candles, base, costs, exec1x, years, b1)
        guard = dd_guard_leverage(base, trades1x)
        bdd = out_dir / f"{name}_dd_guard"
        bdd.mkdir(parents=True, exist_ok=True)
        gsig = base.copy()
        gsig["leverage"] = guard
        gsig.to_parquet(bdd / "signals.parquet", index=False)
        execdd = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                 max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
        resdd, _ = run_branch(candles, gsig, costs, execdd, years, bdd)
        months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                                 part.signal_time.iloc[-1].tz_localize(None), freq="M")
        for key, res, sig in ((f"{name}_1x", res1x, base),
                              (f"{name}_dd_guard", resdd, gsig)):
            counts = sig.signal_time.dt.strftime("%Y-%m").value_counts() if len(sig) else {}
            branches[key] = {
                "scenarios": res,
                "n_signals": int(len(sig)),
                "n_decisions": int(len(part)),
                "coverage": float(len(sig) / len(part)),
                "signals_by_month": {str(m): int(counts.get(str(m), 0)) for m in months},
                "passes_gate_all_scenarios": bool(all(
                    res[s]["monthly_geometric_net"] >= gate["monthly_min"]
                    and res[s]["max_drawdown"] >= -gate["dd_max"]
                    and res[s]["trades"] >= gate["fills_min"]
                    for s in gate["scenarios"])),
                "dd_safe_all_scenarios": bool(all(
                    res[s]["max_drawdown"] >= -gate["dd_max"] for s in gate["scenarios"])),
            }
            print(json.dumps({"branch": key, "gate": branches[key]["passes_gate_all_scenarios"],
                              "metrics": {s: {k: res[s][k] for k in
                                              ("total_return", "max_drawdown", "trades",
                                               "monthly_geometric_net", "gross_pnl", "fees",
                                               "funding", "profit_factor", "win_rate")}
                                          for s in gate["scenarios"]}}), flush=True)
    report = {"experiment": spec["experiment"], "branches": branches,
              "duration_years": years, "gate": gate,
              "standing_best": spec["standing_best"],
              "comparison": "So truc tiep voi standing_best (majority_1x 2.935%/mo DD breach; confirmed_dd_guard 2.79%/mo DD-safe) va gate.",
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-book 1x equity, trigger 10%, lev 0.5/1.0, past-only (tien le v03)",
                           "frequency": "swing_signals: monthly cap + cooldown, giong audit parity"},
              "audit_sha256": sha256(ROOT / spec["audit"]["output"] / "audit.json"),
              "training_summary_sha256": sha256(source / "summary.json"),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "Opened development interval only (2023-2026). Drawdown close-sampled; stop/timeout market-like. KHONG live approval."}
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(out_file))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=ROOT / "configs/opencode_v29a_a1.json")
    main(p.parse_args())
