"""Opencode v12 (R2-N2): realized-vol regime on/off gate x dd_guard on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet
Pre-specified matrix (fixed in configs/opencode_v12_volregime.json BEFORE running; signals/scores untouched):
  bands  {control (always), low vol_ann<0.30, mid 0.30<=vol_ann<=0.60, high vol_ann>0.60}
  sizing {1x, dd_guard}
  = 8 branches: control_1x, control_dd_guard, low_1x, low_dd_guard,
                mid_1x, mid_dd_guard, high_1x, high_dd_guard
Realized vol: trailing-30-calendar-day std of 5m close log-returns strictly
  before signal_time (1-microsecond cutoff), annualized x sqrt(365.2425*288).
  Computed with a .loc mask (replaces deprecated .last(), behavior identical).
  <100 bars -> NaN (excluded from gated bands, kept in control only).
  THIS IS AN ON/OFF REGIME GATE, not v03 vol-target continuous leverage sizing
  (DEAD per ledger: vol_target_15 0.71%/mo). Never tried on this book.
dd_guard lev = 0.5 while the UNGATED-CONTROL (control_1x) base-1x sampled equity
  is >10% under its trailing peak (past-only), else 1.0. Guard state for EVERY
  dd_guard branch derives from the control base-1x run's sampled equity
  (trade exit_time/equity_after; same disclosed method as
  scripts/opencode_risk_overlay_probe.py / session probe), applied at each
  regime-gated signal's own signal_time with a 1-microsecond cutoff.
Control gate: control_1x normal must reproduce +122.798%/-20.086%/65 or STOP.
Each branch x 3 scenarios (normal / fee_stress / execution_stress), reported even
for low-fill bands.
Exploratory: the 2023-2026 interval is opened development data, NOT an independent test.
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
VOL_LOOKBACK_DAYS = 30
MIN_VOL_BARS = 100
ANN_FACTOR = float(np.sqrt(365.2425 * 288))

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def trailing_vol_ann(candles, signal_times, lookback_days=VOL_LOOKBACK_DAYS):
    """Causal past-only annualized realized vol per signal time.

    Uses a boolean .loc mask on the log-return index (this is the fix for the
    deprecated ``.last()`` selector; behavior identical: strictly-before cutoff,
    calendar-day lookback, dropna, sample std x sqrt(365.2425*288)).
    """
    closes = candles.set_index("open_time")["close"].sort_index()
    logret = np.log(closes / closes.shift(1))
    out = np.full(len(signal_times), np.nan)
    sts = pd.to_datetime(signal_times, utc=True)
    for i, ts in enumerate(sts):
        cutoff = ts - pd.Timedelta(microseconds=1)
        mask = (logret.index <= cutoff) & (logret.index > cutoff - pd.Timedelta(days=lookback_days))
        window = logret.loc[mask].dropna()
        if len(window) < MIN_VOL_BARS:
            out[i] = np.nan
            continue
        out[i] = float(window.std() * ANN_FACTOR)
    return out


def dd_guard_leverage(signals, trades):
    """Disclosed method shared with risk_overlay / side_ddguard / session probes.

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal time
    uses only exits strictly before the signal timestamp (past-only, 100.0 seed).
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
    return np.array(out)


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
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    base_signals = pd.read_parquet(root / cfg["signals"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    costs = CostModel(**ds_cfg["costs"])
    execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=LEV_MIN, max_leverage=LEV_MAX)
    base_exec = ExecutionConfig(entry_expiry_bars=execution.entry_expiry_bars,
                                max_holding_bars=execution.max_holding_bars,
                                leverage=1.0, max_leverage=1.0)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    order = ["control", "low", "mid", "high"]
    assert list(cfg["bands"].keys()) == order, f"bands must be pre-specified as {order}"
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    vol_ann = trailing_vol_ann(candles, base_signals["signal_time"],
                               cfg.get("vol_lookback_days", VOL_LOOKBACK_DAYS))
    vol_series = pd.Series(vol_ann, index=base_signals.index)
    (pd.DataFrame({"signal_time": pd.to_datetime(base_signals["signal_time"], utc=True).astype(str),
                   "vol_ann": vol_ann})
     .to_csv(a.output / "signal_vol.csv", index_label="base_index"))
    masks = {
        "control": np.ones(len(base_signals), dtype=bool),
        "low": (vol_ann < 0.30) & np.isfinite(vol_ann),
        "mid": (vol_ann >= 0.30) & (vol_ann <= 0.60) & np.isfinite(vol_ann),
        "high": (vol_ann > 0.60) & np.isfinite(vol_ann),
    }
    filters = {name: base_signals[masks[name]].copy() for name in order}
    for name in order:
        print(json.dumps({"band": name, "n_signals": int(len(filters[name])),
                          "vol_nan": int(np.isnan(vol_ann[masks[name]]).sum()) if name == "control"
                          else 0}), flush=True)

    # Reference run: control base-1x. Must reproduce frozen control or STOP.
    ref_signals = filters["control"].copy()
    if "leverage" in ref_signals.columns:
        ref_signals = ref_signals.drop(columns=["leverage"])
    ref_dir = a.output / "control_1x"
    ref_dir.mkdir()
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, base_exec, duration, ref_dir)
    ref_signals.to_parquet(ref_dir / "signals.parquet", index=False)
    n = ref_scenarios["normal"]
    exp = cfg["control_reproduction"]
    ok = (abs(n["total_return"] - exp["normal_total_return"]) <= exp["tolerance_return"]
          and abs(n["max_drawdown"] - exp["normal_max_drawdown"]) <= exp["tolerance_dd"]
          and n["trades"] == exp["normal_trades"])
    print(json.dumps({"control_check": {"total_return": n["total_return"],
                                        "max_drawdown": n["max_drawdown"],
                                        "trades": n["trades"],
                                        "expected": exp, "match": bool(ok)}}), flush=True)
    if not ok:
        raise SystemExit("CONTROL MISMATCH: STOP. Expected +122.80%/-20.09%/65 normal.")
    results = {"control_1x": ref_scenarios}

    guard_all = dd_guard_leverage(base_signals, ref_trades)
    guard_by_index = dict(zip(base_signals.index.to_numpy(), guard_all))

    for band in order:
        for sizing in ("1x", "dd_guard"):
            branch = f"{band}_{sizing}"
            if branch in results:
                continue
            filt = filters[band]
            bdir = a.output / branch
            bdir.mkdir()
            if sizing == "1x":
                sig = filt.drop(columns=["leverage"]) if "leverage" in filt.columns else filt.copy()
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, base_exec, duration, bdir)
            else:
                levs = np.array([guard_by_index[i] for i in filt.index.to_numpy()],
                                dtype=float) if len(filt) else np.array([], dtype=float)
                sig = filt.copy()
                sig["leverage"] = levs
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, execution, duration, bdir)
            results[branch] = scenarios
            print(json.dumps({"branch": branch,
                              "n_signals": int(len(filt)),
                              "metrics": {s: {k: scenarios[s][k] for k in
                                               ["total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net", "gross_pnl", "fees",
                                                "funding", "profit_factor", "win_rate",
                                                "long_trades", "short_trades"]}
                                          for s in ("normal", "fee_stress", "execution_stress")}}),
                  flush=True)

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
              "band_counts": {k: int(len(v)) for k, v in filters.items()},
              "vol_summary": {"n": int(len(vol_ann)),
                              "n_nan": int(np.isnan(vol_ann).sum()),
                              "min": float(np.nanmin(vol_ann)) if np.isfinite(vol_ann).any() else None,
                              "median": float(np.nanmedian(vol_ann)) if np.isfinite(vol_ann).any() else None,
                              "max": float(np.nanmax(vol_ann)) if np.isfinite(vol_ann).any() else None},
              "formulas": {"vol_definition": cfg["vol_definition"],
                           "band_key": cfg["band_key"],
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "guard_reference": cfg["dd_guard_reference"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
              "Regime vol is causal past-only but bands were inspected on this same interval; "
              "low-fill bands report few/zero fills by construction. "
              "Distinct from DEAD v03 vol-target sizing: this is a binary on/off regime gate.",
              "input_sha256": {str(k): sha256(root / v) for k, v in
                               (("candles", cfg["candles"]), ("signals", cfg["signals"]),
                                ("dataset_config", cfg["dataset_config"]), ("parent_plan", cfg["parent_plan"]))},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
