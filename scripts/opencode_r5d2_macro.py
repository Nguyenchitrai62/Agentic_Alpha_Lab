"""Opencode v24 (R5-D2): macro-daily regime-conditional policy on FROZEN majority_1x.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  data/raw/opencode_macro_yahoo_20220101_20260907/{spy,dxy,uup,gld,gcf,spx}.csv (Yahoo free)
Pre-specified matrix (configs/opencode_v24_macro.json, written BEFORE any backtest):
  filters {control, risk_on_only (SPY>MA50), risk_off_only, no_strong_dxy (DXY z60<=1.5)}
  x sizing {1x, dd_guard} = 8 branches.
Method (causal past-only):
  - Regime moi decision: macro date < UTC date cua signal_time (dong cua T-1 tro ve truoc).
  - risk_on = SPY close > MA50 (50 close ket thuc T-1); dxy_z60 = (close-mean60)/std60
    (60 close ket thuc T-1, ddof=1); strong = z > 1.5.
  - amp20 = (max high20 - min low20)/close (mo ta, khong filter).
  - Subset truc tiep 94 tin hieu frozen (KHONG chay lai frequency loop); control rerun
    phai khop +165.178%/ -20.086%/63 hoac STOP.
Sizing:
  1x       : fixed 1.0 (leverage col dropped).
  dd_guard : lev = 0.5 while CONTROL (control_1x rerun) sampled equity >10% under
             trailing peak (past-only, 1-microsecond cutoff, 100.0 seed), else 1.0.
             Reference la control_1x cua chinh probe nay, ap dung tai subset rieng
             cua tung nhanh. Sampled tu trade exit_time/equity_after
             (trade-candle-close sampled, NOT mark/intrabar). Disclosed, giong v15/v22.
Scenarios per branch: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x only.
Monthly geometric uses duration from configs/swing_v15_continuous_folds.json.
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
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0
MAX_HOLDING_BARS = 7 * 288  # 2016, giong v15 (max holding_days * 288)
ENTRY_EXPIRY_BARS = 12  # dataset config frozen

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]

# majority_1x goc (v15 summary normal): control gate.
PUBLISHED = {"total_return": 1.6517829563633004,
             "max_drawdown": -0.20086073993367803, "trades": 63}


def load_macro(macro_dir: Path):
    out = {}
    for name in ("spy", "dxy", "uup", "gld", "gcf", "spx"):
        df = pd.read_csv(macro_dir / f"{name}.csv", parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        out[name] = df
    return out


def add_features(macro):
    spy = macro["spy"].copy()
    spy["ma50"] = spy["close"].rolling(50).mean()
    spy["hi20"] = spy["high"].rolling(20).max()
    spy["lo20"] = spy["low"].rolling(20).min()
    spy["amp20"] = (spy["hi20"] - spy["lo20"]) / spy["close"]
    dxy = macro["dxy"].copy()
    dxy["mean60"] = dxy["close"].rolling(60).mean()
    dxy["std60"] = dxy["close"].rolling(60).std(ddof=1)
    dxy["z60"] = (dxy["close"] - dxy["mean60"]) / dxy["std60"]
    return spy, dxy


def regime_for(signals: pd.DataFrame, spy: pd.DataFrame, dxy: pd.DataFrame) -> pd.DataFrame:
    sig_dates = pd.to_datetime(signals["signal_time"], utc=True).dt.floor("D").dt.tz_localize(None)
    spy_dates = pd.to_datetime(spy["date"])
    dxy_dates = pd.to_datetime(dxy["date"])
    rows = []
    for d in sig_dates:
        si = int((spy_dates < d).sum()) - 1  # last macro date strictly < decision date
        xi = int((dxy_dates < d).sum()) - 1
        s = spy.iloc[si] if si >= 0 else None
        x = dxy.iloc[xi] if xi >= 0 else None
        if s is None or pd.isna(s["ma50"]):
            risk_on = np.nan
            amp20 = float(s["amp20"]) if s is not None and not pd.isna(s["amp20"]) else np.nan
            spy_close = float(s["close"]) if s is not None else np.nan
            spy_ma50 = np.nan
            macro_date_spy = None
        else:
            risk_on = bool(s["close"] > s["ma50"])
            amp20 = float(s["amp20"])
            spy_close = float(s["close"])
            spy_ma50 = float(s["ma50"])
            macro_date_spy = str(s["date"].date()) if hasattr(s["date"], "date") else str(s["date"])
        if x is None or pd.isna(x["z60"]):
            z = np.nan
            dxy_close = float(x["close"]) if x is not None else np.nan
            macro_date_dxy = None
        else:
            z = float(x["z60"])
            dxy_close = float(x["close"])
            macro_date_dxy = str(x["date"].date()) if hasattr(x["date"], "date") else str(x["date"])
        rows.append({"sig_date": str(d.date()), "macro_date_spy": macro_date_spy,
                     "macro_date_dxy": macro_date_dxy, "spy_close": spy_close,
                     "spy_ma50": spy_ma50, "risk_on": risk_on, "dxy_close": dxy_close,
                     "dxy_z60": z, "spy_amp20": amp20})
    return pd.DataFrame(rows)


def dd_guard_leverage_at(signal_times, ref_trades):
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signal_times, utc=True):
        ts = pd.Timestamp(ts)
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
        rows = [asdict(t) for t in items]
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(
                out_dir / f"{label}_trades.csv", index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(
                out_dir / f"{label}_trades.csv", index=False)
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
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    expected = ["control_1x", "control_dd_guard", "risk_on_only_1x", "risk_on_only_dd_guard",
                "risk_off_only_1x", "risk_off_only_dd_guard", "no_strong_dxy_1x",
                "no_strong_dxy_dd_guard"]
    assert list(cfg["branches"]) == expected, "8-branch filter x sizing matrix must be pre-specified"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    root = Path(__file__).resolve().parents[1]
    candles = pd.read_parquet(root / cfg["candles"])
    base_signals = pd.read_parquet(root / cfg["signals"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text(encoding="utf-8"))
    parent = json.loads((root / cfg["parent_plan"]).read_text(encoding="utf-8"))
    macro = load_macro(root / cfg["macro_dir"])
    assert len(base_signals) == 94, f"frozen majority_1x must be 94, got {len(base_signals)}"
    assert set(base_signals["direction"].unique().tolist()) <= {1, -1}
    assert cfg["entry_expiry_bars"] if "entry_expiry_bars" in cfg else True
    assert int(ds_cfg["entry_expiry_bars"]) == ENTRY_EXPIRY_BARS

    spy, dxy = add_features(macro)
    regime = regime_for(base_signals, spy, dxy)
    regime.index = base_signals.index
    n_nan_risk = int(regime["risk_on"].isna().sum())
    n_nan_z = int(regime["dxy_z60"].isna().sum())

    def mask_for(filt):
        if filt == "control":
            return np.ones(len(base_signals), dtype=bool)
        if filt == "risk_on_only":
            return (regime["risk_on"] == True).to_numpy()  # noqa: E712 - NaN -> False (drop)
        if filt == "risk_off_only":
            return (regime["risk_on"] == False).to_numpy()  # noqa: E712 - NaN -> False (drop)
        if filt == "no_strong_dxy":
            z = regime["dxy_z60"].to_numpy(dtype=float)
            return np.array([True if np.isnan(v) else bool(v <= 1.5) for v in z], dtype=bool)
        raise ValueError(filt)

    subsets = {}
    for filt in ("control", "risk_on_only", "risk_off_only", "no_strong_dxy"):
        m = mask_for(filt)
        subsets[filt] = base_signals[m].reset_index(drop=True)
        print(json.dumps({"filter": filt, "n_signals": int(m.sum())}), flush=True)
    exp = cfg.get("expected_n_signals_causal", {})
    for filt, sub in subsets.items():
        if filt in exp:
            print(json.dumps({"filter": filt, "expected": exp[filt],
                              "actual": int(len(sub)),
                              "match": bool(len(sub) == exp[filt])}), flush=True)

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
            return ExecutionConfig(entry_expiry_bars=ENTRY_EXPIRY_BARS,
                                   max_holding_bars=MAX_HOLDING_BARS,
                                   leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ENTRY_EXPIRY_BARS,
                               max_holding_bars=MAX_HOLDING_BARS,
                               leverage=LEV_MIN, max_leverage=LEV_MAX)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"),
                                               encoding="utf-8")
    regime.to_csv(a.output / "regime_per_signal.csv", index=False)
    full = base_signals.copy()
    for c in regime.columns:
        full[c] = regime[c].values
    full.to_parquet(a.output / "macro_features.parquet", index=False)

    results = {}
    # --- Control: control_1x (reproduction gate) ---
    cdir = a.output / "control_1x"
    cdir.mkdir()
    ref_base = subsets["control"]
    ref_signals = ref_base.drop(columns=["leverage"]) if "leverage" in ref_base.columns \
        else ref_base.copy()
    ref_signals.to_parquet(cdir / "signals.parquet", index=False)
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, fee_costs,
                                           exec_for("1x"), stress, duration, cdir)
    n = ref_scenarios["normal"]
    ok = (abs(n["total_return"] - PUBLISHED["total_return"]) < 1e-6
          and abs(n["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
          and n["trades"] == PUBLISHED["trades"])
    control_check = {"published": PUBLISHED,
                     "reproduced": {"total_return": n["total_return"],
                                    "max_drawdown": n["max_drawdown"],
                                    "trades": n["trades"],
                                    "n_signals": int(len(ref_signals))},
                     "match": bool(ok)}
    print(json.dumps({"control_check": control_check}, default=str), flush=True)
    if not ok:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(control_check, indent=2))
        print("CONTROL MISMATCH: STOP; control_1x does not match +165.18%/-20.09%/63", flush=True)
        sys.exit(1)
    results["control_1x"] = {"scenarios": ref_scenarios, "n_signals": int(len(ref_signals)),
                             "filter": "control", "sizing": "1x"}

    guard_cache = {}

    def guard_for(sig):
        key = tuple(pd.to_datetime(sig["signal_time"], utc=True).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(
                pd.to_datetime(sig["signal_time"], utc=True), ref_trades)
        return guard_cache[key]

    plan = [("control_dd_guard", "control", "dd_guard"),
            ("risk_on_only_1x", "risk_on_only", "1x"),
            ("risk_on_only_dd_guard", "risk_on_only", "dd_guard"),
            ("risk_off_only_1x", "risk_off_only", "1x"),
            ("risk_off_only_dd_guard", "risk_off_only", "dd_guard"),
            ("no_strong_dxy_1x", "no_strong_dxy", "1x"),
            ("no_strong_dxy_dd_guard", "no_strong_dxy", "dd_guard")]
    for branch, filt, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        base = subsets[filt]
        if sizing == "1x":
            sig = base.drop(columns=["leverage"]) if "leverage" in base.columns else base.copy()
            ex = exec_for("1x")
        else:
            sig = base.copy()
            sig["leverage"] = guard_for(base) if len(base) else np.array([], dtype=float)
            ex = exec_for("dd_guard")
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": int(len(sig)),
                           "filter": filt, "sizing": sizing}
        print(json.dumps({"branch": branch, "n_signals": int(len(sig)),
                          "metrics": {s: {kk: scenarios[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate_overall": gate_flags(scenarios, cfg["gate"])["overall_pass"]},
                         default=str), flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": v["n_signals"], "filter": v["filter"],
                   "sizing": v["sizing"], "scenarios": v["scenarios"]}
               for b, v in results.items()}
    regime_dist = {"n_base": int(len(base_signals)),
                   "risk_on": int((regime["risk_on"] == True).sum()),  # noqa: E712
                   "risk_off": int((regime["risk_on"] == False).sum()),  # noqa: E712
                   "nan_risk": int(n_nan_risk),
                   "strong_dxy_z_gt_1_5": int((regime["dxy_z60"] > 1.5).sum()),
                   "nan_dxy_z": int(n_nan_z),
                   "spy_amp20_describe": {k: float(v) for k, v in
                                          regime["spy_amp20"].describe().items()},
                   "dxy_z60_describe": {k: float(v) for k, v in
                                        regime["dxy_z60"].describe().items()},
                   "n_signals_per_filter": {f: int(len(s)) for f, s in subsets.items()}}
    macro_cov = {}
    for name in ("spy", "dxy", "uup", "gld", "gcf", "spx"):
        df = macro[name]
        macro_cov[name] = {"rows": int(len(df)), "first": str(df["date"].iloc[0]),
                           "last": str(df["date"].iloc[-1])}
    report = {"branches": flagged, "config": cfg,
              "control_check": control_check,
              "regime_distribution_causal": regime_dist,
              "macro_coverage": macro_cov,
              "formulas": {"risk_on": "SPY close(T-1) > mean(50 SPY closes ending T-1)",
                           "dxy_z60": "(DXY close(T-1)-mean60)/std60(ddof=1), 60 closes ending T-1; strong = z>1.5",
                           "vix_proxy_amp20": "(max high20 - min low20)/close(T-1) SPY; DESCRIPTIVE ONLY",
                           "causality": "macro date < UTC date(signal_time); strictly past-only",
                           "entry_expiry_bars": ENTRY_EXPIRY_BARS,
                           "max_holding_bars": MAX_HOLDING_BARS,
                           "tp1_fraction": 0.5, "intrabar_policy": "stop_first",
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "dd_guard_reference": cfg["dd_guard_reference"],
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": "ratio=final/100; monthly=ratio^(1/(12*duration_years))-1"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY: opened 2023-2026 development interval only. Do NOT promote. "
                          "Subset truc tiep tin hieu frozen (khong chay lai frequency loop). "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar. "
                          "Stop/timeout exits market-like at scenario fee, not guaranteed maker fills."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["signals"], cfg["dataset_config"],
                                cfg["parent_plan"], "configs/opencode_v24_macro.json",
                                *(f"{cfg['macro_dir']}/{n}.csv" for n in
                                  ("spy", "dxy", "uup", "gld", "gcf", "spx")))},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str),
                                           encoding="utf-8")
    print("WROTE", str(a.output / "summary.json"))
