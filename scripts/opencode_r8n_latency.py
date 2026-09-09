"""Opencode v33 (R8-N): entry-delay latency stress on FROZEN v15 ensemble signals.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94)
Pre-specified matrix (fixed in configs/opencode_v33_latency.json BEFORE running):
  branches {majority_d1 (control), majority_d2, confirmed_d2}
  x scenarios {normal, fee_stress 0.00055, execution_stress FillStress(5,5,5,.00055,False)}
  = 9 scenario-cells (6 required + 3 confirmed bonus). Fixed 1x baseline.

Latency model (Nautilus idea, causal, cheap):
  Control (delay=1): first_entry_bar = signal_index + 1,
    last_entry_bar = min(signal_index + entry_expiry_bars, len-1) — verbatim engine.
  Delay (delay=2): first_entry_bar = signal_index + 2,
    last_entry_bar = min(signal_index + entry_expiry_bars + 1, len-1) —
    same expiry LENGTH (12 bars), holding counted from actual entry per engine.
  Method choice: the engine entry-search loop is copied with a parameterized
  first_entry_bar (NOT bar_index+1 preprocessing, so Trade.signal_index stays
  identical to frozen signals and delay=1 is bit-identical to engine).
  Everything else (stops/TPs/funding/compounding/overlap/holding) is a verbatim
  copy of engine run_backtest (normal/fee) and execution_stress run_stress
  (execution_stress, exposure <=1x only).
Control gate: majority_d1 normal must reproduce published majority_1x
  (+165.17829563633% total_return, -20.09% max_drawdown, 63 trades) or STOP.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import agentic_alpha_lab.backtest.engine as eng
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.backtest.execution_stress import FillStress
from agentic_alpha_lab.data.training import sha256

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def run_latency_backtest(candles, signals, entry_delay=1, initial_equity=100.0,
                         costs=None, execution=None):
    """Verbatim engine run_backtest except entry window shifted by entry_delay.

    delay=1 -> first=signal+1, last=min(signal+expiry, n-1) [engine verbatim].
    delay=2 -> first=signal+2, last=min(signal+expiry+1, n-1) [same length].
    """
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
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = signals.sort_values("bar_index").reset_index(drop=True)
    equity = float(initial_equity)
    equity_points = [equity]
    trades = []
    next_available_index = 0
    rejected = 0
    for signal in signals.itertuples(index=False):
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
        entry_index = None
        entry_price = None
        first_entry_bar = signal_index + int(entry_delay)
        last_entry_bar = min(signal_index + execution.entry_expiry_bars + int(entry_delay) - 1,
                             len(candles) - 1)
        for index in range(first_entry_bar, last_entry_bar + 1):
            candidate = eng._entry_fill(candles.iloc[index], direction, float(signal.entry_limit))
            if candidate is not None:
                entry_index = index
                entry_price = candidate
                break
        if entry_index is None or entry_price is None or entry_index + holding_bars >= len(candles):
            rejected += 1
            continue
        equity_before = equity
        requested_leverage = float(getattr(signal, "leverage", execution.leverage))
        leverage = min(max(requested_leverage, execution.leverage), execution.max_leverage)
        notional = equity_before * leverage
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
    return result, trades


def run_latency_stress(candles, signals, entry_delay=1, initial_equity=100.0,
                       costs=None, execution=None, stress=None):
    """Verbatim execution_stress run_stress except entry window shifted by delay.

    delay=1 -> range(index+1, min(index+expiry+1, n)) [stress verbatim].
    delay=2 -> range(index+2, min(index+expiry+2, n)) [same length].
    Exposure <=1x only; no liquidation model (same as run_stress).
    """
    from agentic_alpha_lab.backtest.execution_stress import entry_fill, target_fill
    costs, execution, stress = costs or CostModel(), execution or ExecutionConfig(), stress or FillStress()
    stress.validate()
    if not (0 < execution.leverage <= execution.max_leverage <= 1):
        raise ValueError("Stress simulator supports exposure <=1x only; no liquidation model")
    if initial_equity <= 0 or not 0 < execution.tp1_fraction < 1 or execution.intrabar_policy != "stop_first":
        raise ValueError("Invalid equity, TP fraction or intrabar policy")
    if execution.entry_expiry_bars < 1 or execution.max_holding_bars < 1:
        raise ValueError("Invalid execution horizon")
    if costs.funding_interval_hours < 1 or 24 % costs.funding_interval_hours:
        raise ValueError("Funding interval must divide 24")
    frame = candles.sort_values("open_time").reset_index(drop=True)
    signals = signals.sort_values("bar_index").reset_index(drop=True)
    equity, available, rejected = float(initial_equity), 0, 0
    curve, adverse_curve, trades = [equity], [equity], []
    exit_fee_rate = costs.fee_rate_per_fill if stress.market_exit_fee_rate is None else stress.market_exit_fee_rate
    delay = int(entry_delay)
    for signal in signals.itertuples(index=False):
        if equity <= 0:
            break
        index, side = int(signal.bar_index), int(signal.direction)
        if side not in (-1, 1) or index < available:
            rejected += 1
            continue
        if index < 0 or index >= len(frame):
            raise ValueError("Signal index outside source")
        hold = int(getattr(signal, "holding_bars", execution.max_holding_bars))
        if not 1 <= hold <= execution.max_holding_bars:
            raise ValueError("Holding horizon outside cap")
        requested = float(getattr(signal, "leverage", execution.leverage))
        if not np.isfinite(requested) or requested <= 0 or requested > 1:
            raise ValueError("Signal exposure must be positive and <=1x")
        leverage = min(max(requested, execution.leverage), execution.max_leverage)
        entry_index, price = None, None
        for j in range(index + delay, min(index + delay + execution.entry_expiry_bars, len(frame))):
            fill = entry_fill(frame.iloc[j], side, float(signal.entry_limit), stress)
            if fill is not None:
                entry_index, price = j, fill
                break
        if entry_index is None or entry_index + hold >= len(frame):
            rejected += 1
            continue
        before, notional = equity, equity * leverage
        fees, funding, gross, remaining = notional * costs.fee_rate_per_fill, 0., 0., 1.
        equity -= fees
        curve.append(equity)
        adverse_curve.append(equity)
        tp1_done, exit_reason, end = False, "time", entry_index + hold

        def close_fraction(fill, fraction, rate):
            nonlocal equity, fees, gross, remaining
            pnl = side * (fill / price - 1) * notional * fraction
            charge = notional * fraction * fill / price * rate
            gross += pnl
            fees += charge
            equity += pnl - charge
            remaining -= fraction

        for j in range(entry_index, end):
            bar = frame.iloc[j]
            if j > entry_index and eng._is_funding_time(pd.Timestamp(bar.open_time), costs.funding_interval_hours):
                rate = costs.funding_long_rate if side == 1 else costs.funding_short_rate
                charge = notional / price * float(bar.open) * remaining * rate
                funding += charge
                equity -= charge
            stop = eng._stop_fill(bar, side, float(signal.stop_loss))
            if stop is not None:
                fill = stop * (1 - side * stress.market_exit_slippage_bps / 10000)
                close_fraction(fill, remaining, exit_fee_rate)
                exit_reason, end = "stop", j
                curve.append(equity)
                adverse_curve.append(equity)
                break
            adverse = float(bar.low if side == 1 else bar.high)
            adverse_curve.append(max(0., equity + side * (adverse / price - 1) * notional * remaining))
            opened_fill = (side == 1 and float(bar.open) <= float(signal.entry_limit)) or (side == -1 and float(bar.open) >= float(signal.entry_limit))
            allow_targets = j != entry_index or opened_fill
            if allow_targets:
                if not tp1_done:
                    fill = target_fill(bar, side, float(signal.take_profit_1), stress)
                    if fill is not None:
                        close_fraction(fill, execution.tp1_fraction, costs.fee_rate_per_fill)
                        tp1_done = True
                fill = target_fill(bar, side, float(signal.take_profit_2), stress)
                if remaining > 0 and fill is not None:
                    close_fraction(fill, remaining, costs.fee_rate_per_fill)
                    exit_reason, end = "tp2", j
                    curve.append(equity)
                    adverse_curve.append(equity)
                    break
            mark_equity = max(0., equity + side * (float(bar.close) / price - 1) * notional * remaining)
            curve.append(mark_equity)
            adverse_curve.append(mark_equity)
        if remaining > 0:
            bar = frame.iloc[end]
            if eng._is_funding_time(pd.Timestamp(bar.open_time), costs.funding_interval_hours):
                rate = costs.funding_long_rate if side == 1 else costs.funding_short_rate
                charge = notional / price * float(bar.open) * remaining * rate
                funding += charge
                equity -= charge
            fill = float(bar.open) * (1 - side * stress.market_exit_slippage_bps / 10000)
            close_fraction(fill, remaining, exit_fee_rate)
            exit_reason = "time_after_tp1" if tp1_done else "time"
            curve.append(equity)
            adverse_curve.append(equity)
        trades.append(eng.Trade(index, side, leverage, entry_index, pd.Timestamp(frame.open_time.iloc[entry_index]).isoformat(),
                                float(price), end, pd.Timestamp(frame.open_time.iloc[end]).isoformat(), exit_reason,
                                float(gross), float(fees), float(funding), float(equity - before), float(before), float(equity), end - entry_index, None))
        curve.append(equity)
        adverse_curve.append(equity)
        available = end + 1
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]
    result = eng.BacktestResult(float(initial_equity), float(equity), float(equity - initial_equity), float(equity / initial_equity - 1),
                                eng._max_drawdown(curve), len(trades), sum(t.direction == 1 for t in trades),
                                sum(t.direction == -1 for t in trades), len(wins) / len(trades) if trades else 0.,
                                sum(wins) / abs(sum(losses)) if losses else None, sum(t.gross_pnl for t in trades),
                                sum(t.fees for t in trades), sum(t.funding for t in trades), 0, rejected)
    diagnostics = {"engine": "ohlc-stress-v1-latency", "stress": asdict(stress), "entry_delay": delay,
                   "adverse_price_sampled_drawdown": eng._max_drawdown(adverse_curve),
                   "warning": "OHLC penetration is NOT a queue model; market slippage/fees are scenarios. Adverse-price DD uses possible pre-TP extrema and prior closes, not true intrabar or exchange mark DD. No liquidation model; exposure <=1x only."}
    return result, trades, diagnostics


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == ["majority_d1", "majority_d2", "confirmed_d2"], "branches must be pre-specified 3-branch matrix"
    assert cfg["branch_specs"]["majority_d1"] == {"base": "majority_1x", "entry_delay": 1}
    assert cfg["branch_specs"]["majority_d2"] == {"base": "majority_1x", "entry_delay": 2}
    assert cfg["branch_specs"]["confirmed_d2"] == {"base": "confirmed_1x", "entry_delay": 2}
    assert list(cfg["scenarios"]) == ["normal", "fee_stress", "execution_stress"]
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
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
    sc = cfg["stress"]
    stress = FillStress(int(sc["entry_penetration_bps"]), int(sc["target_penetration_bps"]),
                        int(sc["market_exit_slippage_bps"]), float(sc["market_exit_fee_rate"]),
                        bool(sc["allow_limit_price_improvement"]))
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

    # ---- CONTROL: majority_d1 must reproduce published majority_1x ----
    sig0 = base_sigs["majority_1x"]
    res_n0, tr_n0 = run_latency_backtest(candles, sig0, 1, 100.0, costs, execution)
    # cross-check delay=1 against pristine engine (must be bit-identical)
    eng_res, _ = eng.run_backtest(candles, sig0, 100.0, costs, execution)
    ref = cfg["control_reference"]
    match = bool(abs(res_n0.total_return - ref["total_return"]) < 1e-9
                 and abs(res_n0.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_n0.trades == ref["trades"])
    identical = bool(abs(res_n0.total_return - eng_res.total_return) < 1e-12
                     and abs(res_n0.max_drawdown - eng_res.max_drawdown) < 1e-12
                     and res_n0.trades == eng_res.trades)
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_n0.total_return,
                       "max_drawdown": res_n0.max_drawdown, "trades": res_n0.trades},
        "engine_crosscheck": {"total_return": eng_res.total_return,
                              "max_drawdown": eng_res.max_drawdown, "trades": eng_res.trades,
                              "bit_identical": identical},
        "reference": ref, "match": match}}), flush=True)
    if not (match and identical):
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_n0), "engine": asdict(eng_res),
             "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; majority_d1 != +165.18%/-20.09%/63", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        sig = base_sigs[spec["base"]]
        delay = int(spec["entry_delay"])
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = {}
        res_n, trs_n = run_latency_backtest(candles, sig, delay, 100.0, costs, execution)
        res_f, trs_f = run_latency_backtest(candles, sig, delay, 100.0, fee_costs, execution)
        res_e, trs_e, diag_e = run_latency_stress(candles, sig, delay, 100.0, costs, execution, stress)
        for label, res, trs in (("normal", res_n, trs_n), ("fee_stress", res_f, trs_f),
                                ("execution_stress", res_e, trs_e)):
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
            scenarios[label] = d
            rows = [asdict(t) for t in trs]
            pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
                bdir / f"{label}_trades.csv", index=False)
        scenarios["execution_stress"]["diagnostics"] = diag_e
        results[branch] = {"base": spec["base"], "entry_delay": delay,
                           "n_signals": int(len(sig)), "scenarios": scenarios}
        print(json.dumps({"branch": branch, "base": spec["base"], "entry_delay": delay,
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": {s: scenarios[s]["gate"] for s in ("normal", "fee_stress", "execution_stress")}},
                         default=str), flush=True)

    # latency decay: majority_d2 vs majority_d1 per scenario
    decay = {}
    for scen in ("normal", "fee_stress", "execution_stress"):
        c = results["majority_d1"]["scenarios"][scen]
        d2 = results["majority_d2"]["scenarios"][scen]
        decay[scen] = {
            "ret_d1": c["total_return"], "ret_d2": d2["total_return"],
            "ret_lost_frac": float((c["total_return"] - d2["total_return"]) / c["total_return"]) if c["total_return"] else None,
            "mo_d1": c["monthly_geometric_net"], "mo_d2": d2["monthly_geometric_net"],
            "mo_lost_frac": float((c["monthly_geometric_net"] - d2["monthly_geometric_net"]) / c["monthly_geometric_net"]) if c["monthly_geometric_net"] else None,
            "fills_d1": c["trades"], "fills_d2": d2["trades"],
            "dd_d1": c["max_drawdown"], "dd_d2": d2["max_drawdown"]}

    report = {"branches": results, "config": cfg, "latency_decay": decay,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_n0.total_return,
                                               "max_drawdown": res_n0.max_drawdown,
                                               "trades": res_n0.trades},
                                "engine_bit_identical": identical, "match": True},
              "formulas": {"entry_window": cfg["entry_window"],
                           "monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "Entry delay is a subjective latency stress assumption, NOT measured "
                          "live latency. Drawdown is trade-candle-close sampled, not true "
                          "mark-price/intrabar drawdown. Stop/timeout exits are market-like at "
                          "the scenario fee, not guaranteed maker fills. Do not promote any "
                          "branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["majority_1x"], cfg["bases"]["confirmed_1x"],
                                "configs/opencode_v33_latency.json")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
