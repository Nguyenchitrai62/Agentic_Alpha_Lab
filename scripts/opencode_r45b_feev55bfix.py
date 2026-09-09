"""Opencode v124 (R45-B-feev55bfix): fee-tier ladder tim break-even tren FROZEN v55b-fix.

Closes ladder on all audited books: majority ~79bps (v39), PF7 band2confirmed
~140bps (v71), v41 ~239/265bps (v119), L3combo ~510bps (v81),
s0004pool ~544bps (v76), confirmed ~808bps (v87); v55b-fix NEVER measured.

Frozen input (never refit):
  artifacts/research/opencode_v111b_replay/rankonly_en_1x/signals.parquet (128)
Pre-specified matrix (fixed in configs/opencode_v124_feev55bfix.json TRUOC khi chay):
  fee_rate_per_fill {0.0002, 0.00055, 0.0010} x 1x = 3 branches
  + 1 dd_guard control re (fee 0.0002) = 4 branches, moi branch 1 scenario.
  Fee IS the stress: KHONG chay them fee_stress/execution_stress rieng.
  Chi doi fee; funding (long 0.0001/8h, short 0) + execution giu nguyen.
  Full dd_guard ladder SKIP + record (book am o control; v39: guard khong
  keo dai break-even).
  Monthly geometric theo configs/swing_v15_continuous_folds.json.
Control gate: fee0002_1x phai khop published v55b-fix rankonly_en_1x normal v111b
  (total_return -0.1624624435323999, max_drawdown -0.3438452766331609,
   85 trades, 128 signals) trong 1e-9 + exact counts hoac STOP.
dd_guard (disclose): lev=0.5 khi equity CONTROL fee0002_1x CUA CHINH EXPERIMENT
  NAY sampled hon 10% duoi trailing peak (past-only, 1-microsecond cutoff,
  seed 100.0), else 1.0; ap dung cho branch fee0002_dd_guard duy nhat
  (giong v39/v05/v15/v71/v87/v119). Execution dd_guard: leverage=0.25/max=1.0
  (clip giu 0.5/1.0; dong nhat audit 0.5/max=1.0).
Break-even: noi suy tuyen tinh neu cat 0 trong thang do; neu khong thi
  ngoai suy OLS (monthly ~ a + b*fee, be = -a/b) nhu v39, record ca hai.
  Ky vong BE AM/khong xac dinh tren book thua — bao cao trung thuc, khong ep.
Exploratory: opened 2023-2026 development interval, NOT independent test.
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
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER = 0.10
DD_GUARD_LEV = 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]

EXPECTED_BRANCHES = ["fee0002_1x", "fee00055_1x", "fee0010_1x", "fee0002_dd_guard"]
EXPECTED_FEES = {"fee0002_1x": 0.0002, "fee00055_1x": 0.00055,
                 "fee0010_1x": 0.001, "fee0002_dd_guard": 0.0002}
EXPECTED_SIZING = {"fee0002_1x": "1x", "fee00055_1x": "1x",
                   "fee0010_1x": "1x", "fee0002_dd_guard": "dd_guard"}


def dd_guard_leverage(signals, trades):
    """Disclosed method shared with v39/r1a/v15/v71/v87/v119 probes.

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal time
    uses only exits strictly before the signal timestamp (past-only, 100.0 seed).
    Reference is the fee0002_1x CONTROL book of THIS experiment.
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


def breakeven_fee(fees_sorted, monthlies):
    """Linear interpolation of fee where monthly_geometric_net crosses 0.

    fees_sorted asc; monthlies aligned. Returns None if no crossing inside
    range (all positive -> above max; all negative -> below min, disclosed).
    """
    for i in range(1, len(fees_sorted)):
        m0, m1 = monthlies[i - 1], monthlies[i]
        if m0 > 0 and m1 <= 0:
            f0, f1 = fees_sorted[i - 1], fees_sorted[i]
            if m1 == m0:
                return float(f1)
            w = float(m0 / (m0 - m1))
            return float(f0 + w * (f1 - f0))
        if m0 == 0:
            return float(fees_sorted[i - 1])
    return None


def ols_breakeven(fees, values):
    """OLS values ~ intercept + slope*fee; break-even = -intercept/slope.

    Giong v39 (breakeven_extrapolated_ols): luon record intercept/slope;
    extrapolated fee chi co nghia khi slope < 0 va intercept > 0.
    Tren book thua (intercept <= 0): BE am hoac None — bao cao trung thuc.
    """
    f = np.asarray(fees, dtype=float)
    v = np.asarray(values, dtype=float)
    slope, intercept = [float(x) for x in np.polyfit(f, v, 1)]
    be = None
    if slope < 0 and intercept > 0:
        be = float(-intercept / slope)
    return {"ols_intercept": intercept, "ols_slope_per_fee": slope,
            "breakeven_fee_extrapolated": be}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == EXPECTED_BRANCHES, "branches must be pre-specified 4-branch fee x sizing matrix"
    assert cfg["fee_tiers"] == [0.0002, 0.00055, 0.001]
    for b, f in EXPECTED_FEES.items():
        assert abs(float(cfg["branch_specs"][b]["fee_rate_per_fill"]) - f) < 1e-12, f"fee mismatch {b}"
        assert cfg["branch_specs"][b]["base"] == "v55bfix_identity", f"base mismatch {b}"
        assert cfg["branch_specs"][b]["sizing"] == EXPECTED_SIZING[b], f"sizing mismatch {b}"
    assert abs(float(cfg["control_reference"]["total_return"]) - (-0.1624624435323999)) < 1e-12
    assert abs(float(cfg["control_reference"]["max_drawdown"]) - (-0.3438452766331609)) < 1e-12
    assert int(cfg["control_reference"]["trades"]) == 85
    assert int(cfg["control_reference"]["n_signals"]) == 128
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    sig = pd.read_parquet(root / cfg["bases"]["v55bfix_identity"]).sort_values("bar_index").reset_index(drop=True)
    assert len(sig) == 128, f"frozen v55b-fix count changed: {len(sig)}"
    for col in ("bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
                "take_profit_1", "take_profit_2", "holding_bars"):
        assert col in sig.columns, f"missing {col}"
    base_costs = CostModel(**ds_cfg["costs"])
    assert abs(base_costs.fee_rate_per_fill - 0.0002) < 1e-12, "dataset base fee must be 0.0002"
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert cap == int(cfg["execution"]["holding_cap_bars"]) == 2016
    exec_1x = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                              max_holding_bars=cap, leverage=1.0, max_leverage=1.0,
                              tp1_fraction=0.5)
    exec_dd = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                              max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX,
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

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok,
                "drawdown_within_20pct": dd_ok, "fills_ge_30": f_ok,
                "pass_all": bool(m_ok and dd_ok and f_ok)}

    # ---- CONTROL: fee0002_1x must reproduce published v55b-fix rankonly_en_1x ----
    sig_1x = sig.drop(columns=["leverage"]) if "leverage" in sig.columns else sig.copy()
    res_c, tr_c = run_backtest(candles, sig_1x, 100.0, base_costs, exec_1x)
    ref = cfg["control_reference"]
    match = bool(abs(res_c.total_return - ref["total_return"]) < 1e-9
                 and abs(res_c.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_c.trades == ref["trades"]
                 and len(sig) == ref["n_signals"])
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_c.total_return,
                       "max_drawdown": res_c.max_drawdown, "trades": res_c.trades,
                       "n_signals": len(sig)},
        "reference": ref, "match": match}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_c), "reference": ref, "n_signals": len(sig)}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; fee0002_1x != -16.2%/-34.4%/85/128", flush=True)
        sys.exit(1)

    # ---- SINGLE guard from control (disclosed), applied to fee0002_dd_guard ----
    guard_levs = dd_guard_leverage(sig, tr_c) if len(sig) else np.array([], dtype=float)
    guard_frac = float((guard_levs == DD_GUARD_LEV).mean()) if len(guard_levs) else 0.0
    print(json.dumps({"dd_guard": {"reference": "fee0002_1x control (v55b-fix, THIS experiment)",
                                   "n_signals": int(len(sig)),
                                   "n_guarded": int((guard_levs == DD_GUARD_LEV).sum()),
                                   "guard_fraction": guard_frac}}), flush=True)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        fee = float(spec["fee_rate_per_fill"])
        sizing = spec["sizing"]
        cm = CostModel(**{**asdict(base_costs), "fee_rate_per_fill": fee})
        bdir = a.output / branch
        bdir.mkdir()
        if sizing == "1x":
            bsig = sig_1x.copy()
            bsig.to_parquet(bdir / "signals.parquet", index=False)
            res, trs = run_backtest(candles, bsig, 100.0, cm, exec_1x)
        else:
            bsig = sig.copy()
            bsig["leverage"] = guard_levs
            bsig.to_parquet(bdir / "signals.parquet", index=False)
            res, trs = run_backtest(candles, bsig, 100.0, cm, exec_dd)
        d = with_geo(res)
        d["gate"] = gate_flags(d)
        d["fee_rate_per_fill"] = fee
        d["sizing"] = sizing
        results[branch] = d
        rows = [asdict(t) for t in trs]
        pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
            bdir / "trades.csv", index=False)
        (bdir / "metrics.json").write_text(json.dumps(d, indent=2, default=str))
        print(json.dumps({"branch": branch, "fee": fee, "sizing": sizing,
                          "metrics": {k: d[k] for k in
                                      ["total_return", "max_drawdown", "trades",
                                       "monthly_geometric_net", "gross_pnl", "fees",
                                       "funding", "profit_factor", "win_rate",
                                       "long_trades", "short_trades"]},
                          "gate": d["gate"]}, default=str), flush=True)

    # ---- break-even tren 1x ladder (3 diem fee): interpolation + OLS (like v39) ----
    fees, mos, trs_ = [], [], []
    for branch in cfg["branches"]:
        if cfg["branch_specs"][branch]["sizing"] == "1x":
            fees.append(float(results[branch]["fee_rate_per_fill"]))
            mos.append(float(results[branch]["monthly_geometric_net"]))
            trs_.append(float(results[branch]["total_return"]))
    order = np.argsort(fees)
    fs = [fees[i] for i in order]
    ms = [mos[i] for i in order]
    ts = [trs_[i] for i in order]
    be = breakeven_fee(fs, ms)
    if be is None:
        note = ("above_max" if all(m > 0 for m in ms)
                else ("below_min" if all(m <= 0 for m in ms) else "no_crossing"))
    else:
        note = "interpolated"
    breakeven = {"1x": {"fees": fs, "monthlies": ms,
                        "breakeven_fee": be, "status": note}}
    mo_ols = ols_breakeven(fs, ms)
    tr_ols = ols_breakeven(fs, ts)
    breakeven_ols = {"1x": {
        "ols_intercept": mo_ols["ols_intercept"],
        "ols_slope_per_fee": mo_ols["ols_slope_per_fee"],
        "monthly_breakeven_fee_extrapolated": mo_ols["breakeven_fee_extrapolated"],
        "total_return_breakeven_fee_extrapolated": tr_ols["breakeven_fee_extrapolated"],
        "total_return_ols_intercept": tr_ols["ols_intercept"],
        "total_return_ols_slope_per_fee": tr_ols["ols_slope_per_fee"]}}
    if be is None and mo_ols["breakeven_fee_extrapolated"] is not None:
        breakeven["1x"]["note"] = (
            f"khong cat 0 trong thang do (monthly min {min(ms):.4%} o fee {fs[int(np.argmin(ms))]:.4f}); "
            f"OLS ngoai suy ~{mo_ols['breakeven_fee_extrapolated']:.4f}")
    elif be is not None:
        breakeven["1x"]["note"] = "noi suy trong thang do"
    else:
        breakeven["1x"]["note"] = (
            "khong cat 0 (book am ca thang do) va OLS khong ngoai suy duoc "
            "(intercept <= 0, slope < 0 -> BE am/khong xac dinh); bao cao trung thuc")
    breakeven["dd_guard"] = {"status": "single_point_no_ladder",
                             "note": "chi 1 diem fee0002_dd_guard (control re); full dd_guard ladder SKIP + record theo pre-spec (book am o control)"}
    # fills/DD survival per branch
    survival = []
    for branch in cfg["branches"]:
        d = results[branch]
        survival.append({"branch": branch, "fee": d["fee_rate_per_fill"],
                         "sizing": d["sizing"], "trades": d["trades"],
                         "max_drawdown": d["max_drawdown"],
                         "monthly": d["monthly_geometric_net"],
                         "fills_ok": bool(d["gate"]["fills_ge_30"]),
                         "dd_ok": bool(d["gate"]["drawdown_within_20pct"])})
    survival.sort(key=lambda r: (r["fee"], r["sizing"]))

    report = {"branches": results, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_c.total_return,
                                               "max_drawdown": res_c.max_drawdown,
                                               "trades": res_c.trades,
                                               "n_signals": len(sig)},
                                "match": True},
              "dd_guard_disclosure": {
                  "reference": "fee0002_1x control trades (v55b-fix, fee 0.0002, 1x, THIS experiment)",
                  "formula": "lev=0.5 while control sampled equity >10% under trailing peak else 1.0",
                  "past_only": "exits strictly before signal timestamp (1-microsecond cutoff), seed 100.0",
                  "applied_to": "fee0002_dd_guard only (full dd_guard fee ladder SKIPPED per pre-spec)",
                  "n_guarded": int((guard_levs == DD_GUARD_LEV).sum()),
                  "guard_fraction": guard_frac,
                  "execution": "leverage=0.25/max=1.0, signal leverage 0.5/1.0"},
              "breakeven": breakeven,
              "breakeven_extrapolated_ols": breakeven_ols,
              "survival": survival,
              "formulas": {"monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "breakeven": "linear interpolation on monthly_geometric_net vs fee_rate_per_fill between last positive and first non-positive tier; OLS fallback monthly ~ a + b*fee, be=-a/b (like v39)"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "Fee tiers are subjective robustness assumptions, NOT measured live fees/slippage. "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
                          "Do not promote any branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["v55bfix_identity"],
                                "configs/opencode_v124_feev55bfix.json",
                                "scripts/opencode_r45b_feev55bfix.py")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
