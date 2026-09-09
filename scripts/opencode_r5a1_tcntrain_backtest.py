"""Opencode R5-A1: backtest plumbing cho SMOKE predictions (KHONG phai ket qua).

Doc predictions.npy cua smoke (fold_0, seed 1729) -> choose() tung row voi
dataset policy config -> frequency loop giong probes (monthly cap + cooldown
5d, time order) -> run_backtest normal + fee_stress (0.00055) + run_stress.

Chi chung minh dau ra smoke chay duoc qua engine chuan. Moi so deu gan nhan
SMOKE, khong so voi standing_best (majority_1x 2.935%/mo, confirmed_dd_guard
2.79%/mo DD-safe).
"""
import torch  # noqa: F401  (import truoc pandas)
import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.swing import choose  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402

BARS_PER_DAY = 288
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def build_signals(pred, part, cfg):
    rows, monthly = [], Counter()
    nxt = pd.Timestamp.min.tz_localize("UTC")
    cap = int(cfg["policy"]["maximum_signals_per_month"])
    cool = int(cfg["policy"]["cooldown_days"])
    for i, row in enumerate(part.itertuples()):
        out = choose(pred[i], row.close, row.atr5, row.atr4, cfg)
        if out.get("action") == "WAIT":
            continue
        ts = pd.Timestamp(row.signal_time)
        if ts < nxt or monthly[ts.strftime("%Y-%m")] >= cap:
            continue
        sig = dict(out)
        sig.pop("action", None)
        rows.append({"bar_index": row.bar_index, "signal_time": ts, **sig})
        monthly[ts.strftime("%Y-%m")] += 1
        nxt = ts + pd.Timedelta(days=cool)
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def run_all(candles, signals, costs, execution, years, out_dir):
    out = {}
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diag = run_stress(candles, signals, 100, costs, execution,
                                  FillStress(5, 5, 5, 0.00055, False))
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", stress, st)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": ratio ** (1 / years) - 1,
                      "monthly_geometric_net": ratio ** (1 / (12 * years)) - 1}
        rows = [asdict(t) for t in items]
        dest = out_dir / f"{label}_trades.csv"
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(dest, index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(dest, index=False)
    out["execution_stress"]["diagnostics"] = diag
    return out


def main(a):
    if a.output.exists():
        raise FileExistsError("Chon output moi; khong ghi de bang chung cu")
    plan = json.loads((ROOT / "configs/opencode_v25_tcnarch.json").read_text())
    parent = json.loads((ROOT / plan["parent_plan"]).read_text())
    ds = ROOT / plan["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    candles = pd.read_parquet(ds / "candles.parquet")
    decisions = pd.read_parquet(ds / "decisions.parquet")
    idx = np.load(a.smoke / "indices.npz")
    pred = np.load(a.smoke / "predictions.npy")
    test = idx["test"]
    assert len(pred) == len(test)
    part = decisions.iloc[test].reset_index(drop=True)
    start, stop = map(pd.Timestamp, parent["folds"][0])
    years = (stop - start).total_seconds() / (365.2425 * 86400)
    signals = build_signals(pred, part, cfg)
    cap = int(max(cfg["holding_days"]) * BARS_PER_DAY)
    execution = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],
                                max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    costs = CostModel(**cfg["costs"])
    a.output.mkdir(parents=True)
    signals.to_parquet(a.output / "signals.parquet", index=False)
    scenarios = run_all(candles, signals, costs, execution, years, a.output)
    keep = ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
            "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
            "long_trades", "short_trades"]
    compact = {s: {k: scenarios[s][k] for k in keep} for s in
               ("normal", "fee_stress", "execution_stress")}
    print(json.dumps({"smoke_signals": int(len(signals)), "metrics": compact}, default=str), flush=True)
    report = {"scenarios": scenarios, "n_signals": int(len(signals)),
              "fold": ["2023-06-01T00:00:00Z", "2023-09-01T00:00:00Z"],
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "frequency": "monthly cap 4 + cooldown 5d, giong probes"},
              "standing_best_anchor": {
                  "majority_1x": "2.935%/mo (DD breach, tran toan bo 2023-2026)",
                  "confirmed_dd_guard": "2.79/2.67/2.06 DD-safe all scenarios"},
              "comparison": "KHONG so sanh: smoke = 1 fold x 2 epochs CPU plumbing; standing_best = toan bo development interval voi model day du.",
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": "SMOKE plumbing only. Drawdown close-sampled; stop/timeout market-like.",
              "inputs": {"predictions": str(a.smoke / "predictions.npy"),
                         "smoke_sha256": sha256(a.smoke / "predictions.npy"),
                         "decisions": sha256(ds / "decisions.parquet"),
                         "candles": sha256(ds / "candles.parquet")}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", type=Path,
                   default=ROOT / "artifacts/research/opencode_v25_tcnarch/smoke/seed1729/fold_0")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v25_tcnarch/smoke_backtest")
    main(p.parse_args())
