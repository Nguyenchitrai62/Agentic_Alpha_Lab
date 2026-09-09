"""Opencode v30 (R7-N): probabilistic-fill execution realism on FROZEN v15 ensemble signals.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94)
Pre-specified matrix (fixed in configs/opencode_v30_probfill.json BEFORE running):
  p_fill {1.0, 0.5, 0.2} x p_slip {0.0, 0.5} x base {majority_1x} = 6
  + confirmed_1x x {(1.0,0.0) control, (0.2,0.5) worst-case} = 8 branches total.
Each branch x 2 scenarios (normal fee 0.0002 / fee_stress 0.00055). NO exec-stress
(this IS the more realistic stress). Fixed 1x baseline.

Prob-fill model (seeded, deterministic, causal past-only, precompute = tien xu ly):
  Per-signal j (0-indexed in bar_index-sorted signals), rng_j =
  numpy.random.default_rng(1729 + j). Scan expiry bars in order:
    LONG:  no-touch if low > limit; open-through if low<=limit and open<=limit
           (guaranteed, no fill draw); touch-only if low<=limit and open>limit
           (draw U<p_fill else skip bar, try next within expiry).
    SHORT: no-touch if high < limit; open-through if high>=limit and open>=limit;
           touch-only if high>=limit and open<limit (same draw rule).
  This classification mirrors engine _entry_fill branches
  (min(open,limit)/limit vs max(open,limit)/limit).
  On fill: one slip draw U2<p_slip -> entry_price += direction*0.1 (adverse tick).
  Each branch resets RNG (fair comparison). p_fill=1.0/p_slip=0.0 must be
  bit-identical to engine ohlc-v2 (control gate) or STOP.
Rest of backtest (stops/TPs/funding/compounding/overlap/holding) is a verbatim
copy of engine run_backtest (stop_first, TP1 50%, funding long 0.0001/8h).
Exploratory: opened 2023-2026 development interval, NOT an independent test.
p_fill/p_slip are subjective seeded stress assumptions, NOT measured maker
fill probability or queue position from OHLC.
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
from agentic_alpha_lab.data.training import sha256

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def entry_kind(bar, direction, limit):
    o = float(bar["open"])
    if direction == 1:
        if float(bar["low"]) > limit:
            return "no-touch"
        return "open-through" if o <= limit else "touch-only"
    if float(bar["high"]) < limit:
        return "no-touch"
    return "open-through" if o >= limit else "touch-only"


def precompute_probfill(candles, signals, execution, p_fill, p_slip, seed_base, tick):
    """Deterministic per-signal entry precompute. Returns (entries, diag_rows, stats)."""
    n = len(signals)
    entries = [None] * n
    diag = []
    n_fill_draws = 0
    n_slip_draws = 0
    n_touch_only_fills = 0
    n_open_through_fills = 0
    n_slipped = 0
    n_skipped_touches = 0
    for j in range(n):
        row = signals.iloc[j]
        direction = int(row["direction"])
        limit = float(row["entry_limit"])
        signal_index = int(row["bar_index"])
        first = signal_index + 1
        last = min(signal_index + execution.entry_expiry_bars, len(candles) - 1)
        rng = np.random.default_rng(int(seed_base) + int(j))
        entry_index = None
        entry_price = None
        fill_kind = None
        slip = False
        skipped = 0
        draws_fill = 0
        draws_slip = 0
        first_kind = None
        for idx in range(first, last + 1):
            bar = candles.iloc[idx]
            kind = entry_kind(bar, direction, limit)
            if kind == "no-touch":
                continue
            if first_kind is None:
                first_kind = kind
            if kind == "open-through":
                cand = eng._entry_fill(bar, direction, limit)
                assert cand is not None
                entry_index = idx
                entry_price = float(cand)
                fill_kind = "open-through"
                u2 = float(rng.random())
                draws_slip += 1
                if u2 < p_slip:
                    entry_price = entry_price + direction * float(tick)
                    slip = True
                break
            # touch-only
            u = float(rng.random())
            draws_fill += 1
            if u < p_fill:
                cand = eng._entry_fill(bar, direction, limit)
                assert cand is not None
                entry_index = idx
                entry_price = float(cand)
                fill_kind = "touch-only"
                u2 = float(rng.random())
                draws_slip += 1
                if u2 < p_slip:
                    entry_price = entry_price + direction * float(tick)
                    slip = True
                break
            skipped += 1
        n_fill_draws += draws_fill
        n_slip_draws += draws_slip
        n_skipped_touches += skipped
        if fill_kind == "touch-only":
            n_touch_only_fills += 1
        elif fill_kind == "open-through":
            n_open_through_fills += 1
        if slip:
            n_slipped += 1
        if entry_index is not None:
            entries[j] = (entry_index, float(entry_price))
        diag.append({"pos": j, "bar_index": signal_index,
                     "direction": direction, "entry_limit": limit,
                     "pre_entry_index": entry_index,
                     "pre_entry_price": entry_price,
                     "fill_kind": fill_kind, "first_kind": first_kind,
                     "slip_applied": bool(slip),
                     "skipped_touches": int(skipped),
                     "draws_fill": int(draws_fill), "draws_slip": int(draws_slip)})
    stats = {"n_fill_draws": int(n_fill_draws), "n_slip_draws": int(n_slip_draws),
             "n_draws_total": int(n_fill_draws + n_slip_draws),
             "n_pre_fills": int(n_touch_only_fills + n_open_through_fills),
             "n_touch_only_fills": int(n_touch_only_fills),
             "n_open_through_fills": int(n_open_through_fills),
             "n_pre_slipped": int(n_slipped),
             "n_skipped_touches": int(n_skipped_touches)}
    return entries, pd.DataFrame(diag), stats


def run_probfill_backtest(candles, signals, pre_entries, initial_equity=100.0,
                          costs=None, execution=None):
    """Verbatim engine run_backtest except entry-search uses precomputed probfill."""
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
    assert len(pre_entries) == len(signals), "precompute length mismatch"
    equity = float(initial_equity)
    equity_points = [equity]
    trades = []
    next_available_index = 0
    rejected = 0
    for j, signal in enumerate(signals.itertuples(index=False)):
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
        pre = pre_entries[j]
        if pre is None:
            rejected += 1
            continue
        entry_index, entry_price = int(pre[0]), float(pre[1])
        if entry_index + holding_bars >= len(candles):
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


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    expected = ["majority_pf100_ps00", "majority_pf100_ps50", "majority_pf050_ps00",
                "majority_pf050_ps50", "majority_pf020_ps00", "majority_pf020_ps50",
                "confirmed_pf100_ps00", "confirmed_pf020_ps50"]
    assert list(cfg["branches"]) == expected, "branches must be pre-specified 8-branch matrix"
    assert list(cfg["p_fill"]) == [1.0, 0.5, 0.2]
    assert list(cfg["p_slip"]) == [0.0, 0.5]
    assert cfg["seed_base"] == 1729 and abs(float(cfg["tick"]) - 0.1) < 1e-12
    assert list(cfg["scenarios"]) == ["normal", "fee_stress"]
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

    # ---- CONTROL: majority_pf100_ps00 must reproduce published majority_1x ----
    spec0 = cfg["branch_specs"]["majority_pf100_ps00"]
    assert spec0 == {"base": "majority_1x", "p_fill": 1.0, "p_slip": 0.0}
    sig0 = base_sigs["majority_1x"]
    ent0, diag0, stats0 = precompute_probfill(candles, sig0, execution, 1.0, 0.0,
                                              cfg["seed_base"], cfg["tick"])
    res_n0, tr_n0 = run_probfill_backtest(candles, sig0, ent0, 100.0, costs, execution)
    ref = cfg["control_reference"]
    match = bool(abs(res_n0.total_return - ref["total_return"]) < 1e-9
                 and abs(res_n0.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_n0.trades == ref["trades"])
    print(json.dumps({"control_check": {"reproduced": {"total_return": res_n0.total_return,
                                                       "max_drawdown": res_n0.max_drawdown,
                                                       "trades": res_n0.trades},
                                        "reference": ref, "match": match,
                                        "precompute_stats": stats0}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_n0), "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; majority_pf100_ps00 != +165.18%/-20.09%/63", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        base = spec["base"]
        pf = float(spec["p_fill"])
        ps = float(spec["p_slip"])
        sig = base_sigs[base]
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        entries, diag, stats = precompute_probfill(candles, sig, execution, pf, ps,
                                                   cfg["seed_base"], cfg["tick"])
        diag.to_csv(bdir / "probfill_draws.csv", index=False)
        scenarios = {}
        for label, cm in (("normal", costs), ("fee_stress", fee_costs)):
            res, trs = run_probfill_backtest(candles, sig, entries, 100.0, cm, execution)
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
            if rows:
                pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            else:
                pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            # executed slip audit: count trades whose entry deviates from raw _entry_fill by ~tick
            n_exec_slip = 0
            for t in trs:
                j = diag.loc[diag["pre_entry_index"] == t.entry_index]
                if len(j) and bool(j.iloc[0]["slip_applied"]):
                    n_exec_slip += 1
            scenarios[label]["executed_slipped_fills"] = int(n_exec_slip)
        results[branch] = {"base": base, "p_fill": pf, "p_slip": ps,
                           "n_signals": int(len(sig)), "scenarios": scenarios,
                           "seeds": {"seed_base": int(cfg["seed_base"]),
                                     "per_signal_seed": f"seed_base + pos (pos=0..{len(sig)-1})",
                                     "rng": "numpy.random.default_rng(seed_base+pos), sequential per-signal stream"},
                           "draws": stats}
        print(json.dumps({"branch": branch, "base": base, "p_fill": pf, "p_slip": ps,
                          "draws": stats,
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades",
                                            "executed_slipped_fills"]}
                                      for s in ("normal", "fee_stress")},
                          "gate": {s: scenarios[s]["gate"] for s in ("normal", "fee_stress")}},
                         default=str), flush=True)
    report = {"branches": results, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_n0.total_return,
                                               "max_drawdown": res_n0.max_drawdown,
                                               "trades": res_n0.trades},
                                "match": True},
              "formulas": {"touch_definition": cfg["touch_definition"],
                           "rng_scheme": cfg["rng_scheme"],
                           "slippage": cfg["slippage"],
                           "monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "scenarios": "normal + fee_stress only (no exec-stress; probfill IS the stress)"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "p_fill/p_slip are subjective seeded stress assumptions, NOT measured "
                          "maker fill probability or queue position from OHLC. "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
                          "Do not promote any branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["majority_1x"], cfg["bases"]["confirmed_1x"],
                                "configs/opencode_v30_probfill.json")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
