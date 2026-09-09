"""Opencode v32 (R8-N): volume-cap fills on FROZEN v15 majority_1x signals.

Frozen input (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
Pre-specified matrix (fixed in configs/opencode_v32_volcap.json BEFORE running):
  k {1.0 (control bypass), 0.25, 0.10, 0.05} x scenarios {normal, fee_stress}
  = 4 branches x 2 scenarios = 8 evaluations. NO exec-stress (this IS the stress).
Fixed 1x baseline, initial equity indexed 100.

Volcap model (deterministic, no RNG, causal past-only):
  For each signal in bar_index order, scan expiry bars idx=signal_index+1..+12:
    cand = engine._entry_fill(bar, direction, limit); if None -> next bar.
    if k >= 1.0 -> fill at cand (control bypass, bit-identical to engine ohlc-v2).
    else: notional = current_equity * leverage(1x); qty = notional / cand;
      cap = k * float(bar[volume_column]); fill iff qty <= cap else skip bar
      (volcap_skip+1) and try next bar within expiry. No partial fills.
  Rest of backtest is a verbatim copy of engine run_backtest (stop_first,
  TP1 50%, funding long 0.0001/8h short 0).
Exploratory: opened 2023-2026 development interval, NOT an independent test.
k is a subjective stress assumption, NOT measured liquidity/queue from OHLC.
Caveat: full-bar volume is strictly known only after the bar closes
(mild intrabar look-ahead), applied uniformly to all branches.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import agentic_alpha_lab.backtest.engine as eng
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.data.training import sha256

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def run_volcap_backtest(candles, signals, k, volume_column,
                        initial_equity=100.0, costs=None, execution=None):
    """Verbatim engine run_backtest except entry-search adds volcap gate."""
    costs = costs or CostModel()
    execution = execution or ExecutionConfig()
    if execution.intrabar_policy != "stop_first":
        raise ValueError("Only conservative stop_first intrabar policy is supported")
    if not 0.0 < execution.tp1_fraction < 1.0:
        raise ValueError("tp1_fraction must be between zero and one")
    if execution.leverage <= 0 or execution.max_leverage < execution.leverage:
        raise ValueError("Leverage must be positive and not exceed max_leverage")
    if initial_equity <= 0 or execution.max_holding_bars < 1 or execution.entry_expiry_bars < 1:
        raise ValueError("Capital and execution horizons must be positive")
    if costs.funding_interval_hours < 1 or 24 % costs.funding_interval_hours:
        raise ValueError("Funding interval must divide 24 hours")
    if volume_column not in candles.columns:
        raise ValueError(f"volume column missing: {volume_column}")
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = signals.sort_values("bar_index").reset_index(drop=True)
    equity = float(initial_equity)
    equity_points = [equity]
    trades = []
    diag_rows = []
    next_available_index = 0
    rejected = 0
    n_volcap_skipped_bars = 0
    n_delayed = 0
    n_lost_vs_engine = 0
    max_qty_cap_ratio = 0.0
    for pos, signal in enumerate(signals.itertuples(index=False)):
        if equity <= 0:
            break
        signal_index = int(signal.bar_index)
        direction = int(signal.direction)
        if direction == 0 or signal_index < next_available_index:
            rejected += 1
            continue
        holding_bars = int(getattr(signal, "holding_bars", execution.max_holding_bars))
        if holding_bars < 1 or holding_bars > execution.max_holding_bars:
            raise ValueError("Signal holding_bars must be within execution horizon cap")
        requested_leverage = float(getattr(signal, "leverage", execution.leverage))
        leverage = min(max(requested_leverage, execution.leverage), execution.max_leverage)
        notional = equity * leverage
        first_entry_bar = signal_index + 1
        last_entry_bar = min(signal_index + execution.entry_expiry_bars, len(candles) - 1)
        # raw engine entry (price-only, for diagnostics)
        engine_entry = None
        for index in range(first_entry_bar, last_entry_bar + 1):
            cand0 = eng._entry_fill(candles.iloc[index], direction, float(signal.entry_limit))
            if cand0 is not None:
                engine_entry = index
                break
        entry_index = None
        entry_price = None
        skipped = 0
        entry_vol = None
        entry_cap = None
        entry_qty = None
        entry_ratio = None
        for index in range(first_entry_bar, last_entry_bar + 1):
            bar = candles.iloc[index]
            cand = eng._entry_fill(bar, direction, float(signal.entry_limit))
            if cand is None:
                continue
            if float(k) >= 1.0:
                entry_index = index
                entry_price = float(cand)
                entry_vol = float(bar[volume_column])
                entry_cap = float("inf")
                entry_qty = float(notional / float(cand))
                entry_ratio = 0.0
                break
            vol = float(bar[volume_column])
            if not math.isfinite(vol) or vol < 0:
                vol = 0.0
            cap = float(k) * vol
            qty = float(notional / float(cand))
            ratio = float(qty / cap) if cap > 0 else float("inf")
            if math.isfinite(ratio):
                max_qty_cap_ratio = max(max_qty_cap_ratio, ratio)
            if qty <= cap:
                entry_index = index
                entry_price = float(cand)
                entry_vol = vol
                entry_cap = cap
                entry_qty = qty
                entry_ratio = ratio
                break
            skipped += 1
        n_volcap_skipped_bars += skipped
        if engine_entry is not None and entry_index is None:
            n_lost_vs_engine += 1
        if engine_entry is not None and entry_index is not None and entry_index > engine_entry:
            n_delayed += 1
        diag_rows.append({"pos": int(pos), "bar_index": signal_index,
                          "direction": direction,
                          "entry_limit": float(signal.entry_limit),
                          "engine_entry_index": engine_entry,
                          "volcap_entry_index": entry_index,
                          "delay_bars": (int(entry_index - engine_entry)
                                         if (engine_entry is not None and entry_index is not None) else None),
                          "skipped_volcap_bars": int(skipped),
                          "entry_price": entry_price,
                          "entry_volume": entry_vol,
                          "cap": entry_cap,
                          "qty": entry_qty,
                          "qty_cap_ratio": entry_ratio,
                          "equity_before": float(equity)})
        if entry_index is None or entry_price is None or entry_index + holding_bars >= len(candles):
            rejected += 1
            continue
        equity_before = equity
        entry_fee = notional * costs.fee_rate_per_fill
        equity -= entry_fee
        equity_points.append(equity)
        fees = entry_fee
        funding = 0.0
        gross_pnl = 0.0
        remaining = 1.0
        tp1_done = False
        exit_reason = "time"
        exit_index = min(entry_index + holding_bars, len(candles) - 1)
        final_exit_price = float(candles.iloc[exit_index]["open"])
        liquidation_price = eng._liquidation_price(
            entry_price, direction, leverage, execution.maintenance_margin_rate)
        for index in range(entry_index, exit_index):
            bar = candles.iloc[index]
            bar_time = pd.Timestamp(bar["open_time"])
            if index > entry_index and eng._is_funding_time(bar_time, costs.funding_interval_hours):
                rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
                charge = notional / entry_price * float(bar["open"]) * remaining * rate
                funding += charge
                equity -= charge
            liquidation_fill = eng._liquidation_fill(bar, direction, liquidation_price)
            stop_fill = eng._stop_fill(bar, direction, float(signal.stop_loss))
            if liquidation_fill is not None and stop_fill is not None:
                opened_beyond_liquidation = (
                    direction == 1 and float(bar["open"]) <= float(liquidation_price)
                ) or (
                    direction == -1 and float(bar["open"]) >= float(liquidation_price)
                )
                stop_before_liquidation = direction * (float(signal.stop_loss) - float(liquidation_price)) > 0
                if not opened_beyond_liquidation and stop_before_liquidation:
                    liquidation_fill = None
            if liquidation_fill is not None:
                fraction = remaining
                pnl = direction * (liquidation_fill - entry_price) / entry_price * notional * fraction
                exit_fee = (notional * fraction * (liquidation_fill / entry_price)
                            * execution.liquidation_taker_fee_rate)
                gross_pnl += pnl
                fees += exit_fee
                equity = max(0.0, equity + pnl - exit_fee)
                remaining = 0.0
                exit_reason = "liquidation"
                exit_index = index
                final_exit_price = liquidation_fill
                equity_points.append(equity)
                break
            if stop_fill is not None:
                fraction = remaining
                pnl = direction * (stop_fill - entry_price) / entry_price * notional * fraction
                exit_fee = notional * fraction * (stop_fill / entry_price) * costs.fee_rate_per_fill
                gross_pnl += pnl
                fees += exit_fee
                equity += pnl - exit_fee
                remaining = 0.0
                exit_reason = "stop"
                exit_index = index
                final_exit_price = stop_fill
                equity_points.append(equity)
                break
            entry_at_open = (direction == 1 and float(bar["open"]) <= float(signal.entry_limit)) or (
                direction == -1 and float(bar["open"]) >= float(signal.entry_limit)
            )
            allow_targets = index != entry_index or entry_at_open
            if not tp1_done and allow_targets:
                tp1_fill = eng._take_profit_fill(bar, direction, float(signal.take_profit_1))
                if tp1_fill is not None:
                    fraction = execution.tp1_fraction
                    pnl = direction * (tp1_fill - entry_price) / entry_price * notional * fraction
                    exit_fee = notional * fraction * (tp1_fill / entry_price) * costs.fee_rate_per_fill
                    gross_pnl += pnl
                    fees += exit_fee
                    equity += pnl - exit_fee
                    remaining -= fraction
                    tp1_done = True
            tp2_fill = eng._take_profit_fill(bar, direction, float(signal.take_profit_2)) if allow_targets else None
            if remaining > 0 and tp2_fill is not None:
                fraction = remaining
                pnl = direction * (tp2_fill - entry_price) / entry_price * notional * fraction
                exit_fee = notional * fraction * (tp2_fill / entry_price) * costs.fee_rate_per_fill
                gross_pnl += pnl
                fees += exit_fee
                equity += pnl - exit_fee
                remaining = 0.0
                exit_reason = "tp2"
                exit_index = index
                final_exit_price = tp2_fill
                equity_points.append(equity)
                break
            mark_price = float(bar["close"])
            mark_pnl = direction * (mark_price - entry_price) / entry_price * notional * remaining
            equity_points.append(max(0.0, equity + mark_pnl))
        if remaining > 0:
            bar = candles.iloc[exit_index]
            bar_time = pd.Timestamp(bar["open_time"])
            if eng._is_funding_time(bar_time, costs.funding_interval_hours):
                rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
                charge = notional / entry_price * float(bar["open"]) * remaining * rate
                funding += charge
                equity -= charge
            final_exit_price = float(bar["open"])
            pnl = direction * (final_exit_price - entry_price) / entry_price * notional * remaining
            exit_fee = notional * remaining * (final_exit_price / entry_price) * costs.fee_rate_per_fill
            gross_pnl += pnl
            fees += exit_fee
            equity += pnl - exit_fee
            exit_reason = "time_after_tp1" if tp1_done else "time"
            remaining = 0.0
            equity_points.append(equity)
        trade = eng.Trade(
            signal_index=signal_index, direction=direction, leverage=leverage,
            entry_index=entry_index,
            entry_time=pd.Timestamp(candles["open_time"].iloc[entry_index]).isoformat(),
            entry_price=float(entry_price), exit_index=exit_index,
            exit_time=pd.Timestamp(candles["open_time"].iloc[exit_index]).isoformat(),
            exit_reason=exit_reason, gross_pnl=float(gross_pnl), fees=float(fees),
            funding=float(funding), net_pnl=float(equity - equity_before),
            equity_before=float(equity_before), equity_after=float(equity),
            holding_bars=int(exit_index - entry_index),
            liquidation_price=float(liquidation_price) if liquidation_price is not None else None)
        trades.append(trade)
        equity_points.append(equity)
        next_available_index = exit_index + 1
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    result = eng.BacktestResult(
        initial_equity=float(initial_equity), final_equity=float(equity),
        net_profit=float(equity - initial_equity),
        total_return=float(equity / initial_equity - 1.0),
        max_drawdown=eng._max_drawdown(equity_points), trades=len(trades),
        long_trades=sum(t.direction == 1 for t in trades),
        short_trades=sum(t.direction == -1 for t in trades),
        win_rate=float(len(wins) / len(trades)) if trades else 0.0,
        profit_factor=float(profit_factor) if profit_factor is not None else None,
        gross_pnl=float(sum(t.gross_pnl for t in trades)),
        fees=float(sum(t.fees for t in trades)),
        funding=float(sum(t.funding for t in trades)),
        liquidations=sum(t.exit_reason == "liquidation" for t in trades),
        rejected_or_unfilled_signals=rejected)
    stats = {"n_volcap_skipped_bars": int(n_volcap_skipped_bars),
             "n_delayed_vs_engine": int(n_delayed),
             "n_lost_vs_engine": int(n_lost_vs_engine),
             "max_qty_cap_ratio": float(max_qty_cap_ratio)}
    return result, trades, pd.DataFrame(diag_rows), stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == ["majority_k100", "majority_k25",
                                     "majority_k10", "majority_k05"], "branches must be pre-specified 4-branch k matrix"
    assert list(cfg["k_levels"]) == [1.0, 0.25, 0.1, 0.05]
    assert cfg["branch_specs"]["majority_k100"] == {"base": "majority_1x", "k": 1.0}
    assert cfg["branch_specs"]["majority_k05"] == {"base": "majority_1x", "k": 0.05}
    assert list(cfg["scenarios"]) == ["normal", "fee_stress"]
    assert cfg["seed_base"] == 1729
    assert cfg["volume_column"] == "volume"
    assert abs(float(cfg["fee_stress_rate"]) - 0.00055) < 1e-12
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
    assert cfg["volume_column"] in candles.columns, "volume column missing in candles"
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    base_sigs = {}
    for base, rel in cfg["bases"].items():
        df = pd.read_parquet(root / rel).sort_values("bar_index").reset_index(drop=True)
        assert len(df) == 94, f"frozen {base} count changed: {len(df)}"
        for col in ("bar_index", "direction", "entry_limit", "stop_loss",
                    "take_profit_1", "take_profit_2", "holding_bars"):
            assert col in df.columns, f"{base} missing {col}"
        base_sigs[base] = df
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": float(cfg["fee_stress_rate"])})
    cap = int(max(ds_cfg["holding_days"]) * 288)
    execution = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                                max_holding_bars=cap, leverage=1.0, max_leverage=1.0,
                                tp1_fraction=0.5)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def with_geo(result):
        d = asdict(result)
        ratio = result.final_equity / 100.0
        d["annual_geometric_net"] = float(ratio ** (1 / duration) - 1)
        d["monthly_geometric_net"] = float(ratio ** (1 / (12 * duration)) - 1)
        return d

    # ---- CONTROL: majority_k100 must reproduce published majority_1x ----
    sig0 = base_sigs["majority_1x"]
    res_n0, tr_n0, _, stats0 = run_volcap_backtest(
        candles, sig0, 1.0, cfg["volume_column"], 100.0, costs, execution)
    ref = cfg["control_reference"]
    match = bool(abs(res_n0.total_return - ref["total_return"]) < 1e-9
                 and abs(res_n0.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_n0.trades == ref["trades"])
    print(json.dumps({"control_check": {"reproduced": {"total_return": res_n0.total_return,
                                                       "max_drawdown": res_n0.max_drawdown,
                                                       "trades": res_n0.trades},
                                        "reference": ref, "match": match,
                                        "volcap_stats": stats0}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_n0), "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; majority_k100 != +165.18%/-20.09%/63", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        base = spec["base"]
        k = float(spec["k"])
        sig = base_sigs[base]
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = {}
        diag_by_scenario = {}
        for label, cm in (("normal", costs), ("fee_stress", fee_costs)):
            res, trs, diag, stats = run_volcap_backtest(
                candles, sig, k, cfg["volume_column"], 100.0, cm, execution)
            d = with_geo(res)
            try:
                m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
                dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
                f_ok = bool(d["trades"] >= gate["fills_min"])
            except (KeyError, TypeError):
                m_ok = dd_ok = f_ok = False
            d["gate"] = {"monthly_geometric_net_ge_5pct": m_ok,
                         "drawdown_within_20pct": dd_ok, "fills_ge_30": f_ok,
                         "pass_all": bool(m_ok and dd_ok and f_ok)}
            d["volcap"] = {"k": k, "volume_column": cfg["volume_column"], **stats}
            scenarios[label] = d
            rows = [asdict(t) for t in trs]
            if rows:
                pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            else:
                pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            diag.to_csv(bdir / f"{label}_volcap_diag.csv", index=False)
            diag_by_scenario[label] = stats
        results[branch] = {"base": base, "k": k,
                           "n_signals": int(len(sig)), "scenarios": scenarios,
                           "seeds": {"seed_base": int(cfg["seed_base"]),
                                     "rng": "none (deterministic volcap; seed recorded for ordering reproducibility)"},
                           "volcap_stats": diag_by_scenario}
        print(json.dumps({"branch": branch, "base": base, "k": k,
                          "volcap_stats": diag_by_scenario,
                          "metrics": {s: {kk: scenarios[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress")},
                          "gate": {s: scenarios[s]["gate"] for s in ("normal", "fee_stress")}},
                         default=str), flush=True)
    report = {"branches": results, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_n0.total_return,
                                               "max_drawdown": res_n0.max_drawdown,
                                               "trades": res_n0.trades},
                                "match": True},
              "formulas": {"volcap": cfg["volcap_formula"],
                           "rng_scheme": cfg["rng_scheme"],
                           "monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "scenarios": "normal + fee_stress only (no exec-stress; volcap IS the stress)"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "k is a subjective stress assumption, NOT measured liquidity or queue position from OHLC. "
                          "Full-bar volume is known only after bar close (mild intrabar look-ahead), applied uniformly. "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
                          "Indexed capital 100 at fixed 1x: no claim for much larger capital. "
                          "Do not promote any branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["majority_1x"],
                                "configs/opencode_v32_volcap.json",
                                "scripts/opencode_r8n_volcap.py")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
