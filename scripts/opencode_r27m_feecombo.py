"""Opencode v81 (R27-M-feecombo): fee-tier ladder tim break-even tren FINAL L3 combo shipped.

Tiep noi N-feeladder v39 (majority ~79bps, OLS), v71 (PF7 band2confirmed ~140bps),
v76 (s0004 L2-filter ~544bps); CHUA BAO GIO do tren FINAL L3 combo dd_guard_tp075
(210 signals frozen leverage 203x1.0+7x0.5, tp1 0.75, +165.90%/-16.57%/101 normal
DD-safe, monthly 2.94%) — day la he thong shipped, khong re-derive.

Frozen input (never refit):
  artifacts/research/opencode_v75_L3real/dd_guard_tp075/signals.parquet (210 rows -> 101 fills)
Pre-specified matrix (fixed in configs/opencode_v81_feecombo.json TRUOC khi chay):
  fee_rate_per_fill {0.0002, 0.00055, 0.0010}
  x sizing {as-combo-frozen} = 3 branches, moi branch 1 scenario (fee cua no).
  Fee IS the stress: KHONG chay them fee_stress/execution_stress rieng.
  Giu NGUYEN cot leverage (no re-derivation); execution leverage=0.25/max=1.0
  de engine clip giu nguyen 0.5/1.0; tp1_fraction=0.75.
  Monthly geometric theo configs/swing_v15_continuous_folds.json.
Control gate: fee0002_combo phai khop published L3 dd_guard_tp075 v75
  (+165.90074162267956% total_return 1.6590074162267956,
   -16.573345360670333% max_drawdown -0.16573345360670333, 101 trades)
  trong 1e-9 hoac STOP.
Break-even: noi suy tuyen tinh neu cat 0 trong thang do; neu khong thi
  ngoai suy OLS (monthly ~ a + b*fee, be = -a/b) nhu v39, record ca hai.
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

LEV_MIN, LEV_MAX = 0.25, 1.0
TP1 = 0.75

TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]

EXPECTED_BRANCHES = ["fee0002_combo", "fee00055_combo", "fee0010_combo"]
EXPECTED_FEES = {"fee0002_combo": 0.0002, "fee00055_combo": 0.00055,
                 "fee0010_combo": 0.001}


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
    assert list(cfg["branches"]) == EXPECTED_BRANCHES, "branches must be pre-specified 3-branch fee x frozen-combo matrix"
    assert list(cfg["sizings"]) == ["as-combo-frozen"]
    assert cfg["fee_tiers"] == [0.0002, 0.00055, 0.001]
    for b, f in EXPECTED_FEES.items():
        assert abs(float(cfg["branch_specs"][b]["fee_rate_per_fill"]) - f) < 1e-12, f"fee mismatch {b}"
        assert cfg["branch_specs"][b]["sizing"] == "as-combo-frozen", f"sizing mismatch {b}"
        assert cfg["branch_specs"][b]["base"] == "L3combo-dd_guard_tp075", f"base mismatch {b}"
    assert abs(float(cfg["control_reference"]["total_return"]) - 1.6590074162267956) < 1e-12
    assert abs(float(cfg["control_reference"]["max_drawdown"]) - (-0.16573345360670333)) < 1e-12
    assert int(cfg["control_reference"]["trades"]) == 101
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    sig = pd.read_parquet(root / cfg["frozen_signals"]["path"]).sort_values("bar_index").reset_index(drop=True)
    assert len(sig) == 210, f"frozen L3 combo count changed: {len(sig)}"
    assert "leverage" in sig.columns, "frozen combo must carry leverage column"
    levs = set(np.unique(sig["leverage"].to_numpy()).tolist())
    assert levs <= {0.5, 1.0}, f"unexpected leverage values {levs}"
    assert int((sig["leverage"] == 0.5).sum()) == 7, "frozen guard count changed (0.5)"
    assert int((sig["leverage"] == 1.0).sum()) == 203, "frozen guard count changed (1.0)"
    assert "tp1_fraction" in sig.columns, "missing tp1_fraction"
    assert bool((sig["tp1_fraction"] == TP1).all()), "frozen combo tp1 must be 0.75"
    for col in ("bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
                "take_profit_1", "take_profit_2", "holding_bars"):
        assert col in sig.columns, f"missing {col}"
    frozen_leverage = sig["leverage"].to_numpy().copy()
    base_costs = CostModel(**ds_cfg["costs"])
    assert abs(base_costs.fee_rate_per_fill - 0.0002) < 1e-12, "dataset base fee must be 0.0002"
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert cap == int(cfg["execution"]["holding_cap_bars"]) == 2016
    assert int(ds_cfg["entry_expiry_bars"]) == int(cfg["execution"]["entry_expiry_bars"]) == 12
    assert abs(float(cfg["execution"]["tp1_fraction"]) - TP1) < 1e-12
    exec_combo = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                                 max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX,
                                 tp1_fraction=TP1)
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

    # ---- CONTROL: fee0002_combo must reproduce published L3 dd_guard_tp075 ----
    sig_frozen = sig.copy()
    res_c, tr_c = run_backtest(candles, sig_frozen, 100.0, base_costs, exec_combo)
    ref = cfg["control_reference"]
    match = bool(abs(res_c.total_return - ref["total_return"]) < 1e-9
                 and abs(res_c.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_c.trades == ref["trades"])
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_c.total_return,
                       "max_drawdown": res_c.max_drawdown, "trades": res_c.trades},
        "reference": ref, "match": match}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_c), "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; fee0002_combo != +165.90%/-16.57%/101", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        fee = float(spec["fee_rate_per_fill"])
        cm = CostModel(**{**asdict(base_costs), "fee_rate_per_fill": fee})
        bdir = a.output / branch
        bdir.mkdir()
        # shipped system as-is: leverage column EXACTLY, no re-derivation
        bsig = sig.copy()
        assert np.array_equal(bsig["leverage"].to_numpy(), frozen_leverage), "leverage mutated"
        bsig.to_parquet(bdir / "signals.parquet", index=False)
        res, trs = run_backtest(candles, bsig, 100.0, cm, exec_combo)
        d = with_geo(res)
        d["gate"] = gate_flags(d)
        d["fee_rate_per_fill"] = fee
        d["sizing"] = "as-combo-frozen"
        results[branch] = d
        rows = [asdict(t) for t in trs]
        pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
            bdir / "trades.csv", index=False)
        (bdir / "metrics.json").write_text(json.dumps(d, indent=2, default=str))
        print(json.dumps({"branch": branch, "fee": fee, "sizing": "as-combo-frozen",
                          "metrics": {k: d[k] for k in
                                      ["total_return", "max_drawdown", "trades",
                                       "monthly_geometric_net", "gross_pnl", "fees",
                                       "funding", "profit_factor", "win_rate",
                                       "long_trades", "short_trades"]},
                          "gate": d["gate"]}, default=str), flush=True)

    # ---- break-even (single sizing): interpolation + OLS extrapolation (v39 pattern) ----
    fees, mos, trs_ = [], [], []
    for branch in cfg["branches"]:
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
    breakeven = {"as-combo-frozen": {"fees": fs, "monthlies": ms,
                                     "breakeven_fee": be, "status": note}}
    mo_ols = ols_breakeven(fs, ms)
    tr_ols = ols_breakeven(fs, ts)
    breakeven_ols = {"as-combo-frozen": {
        "ols_intercept": mo_ols["ols_intercept"],
        "ols_slope_per_fee": mo_ols["ols_slope_per_fee"],
        "monthly_breakeven_fee_extrapolated": mo_ols["breakeven_fee_extrapolated"],
        "total_return_breakeven_fee_extrapolated": tr_ols["breakeven_fee_extrapolated"],
        "total_return_ols_intercept": tr_ols["ols_intercept"],
        "total_return_ols_slope_per_fee": tr_ols["ols_slope_per_fee"]}}
    breakeven["as-combo-frozen"]["note"] = (
        f"khong cat 0 trong thang do (monthly min {min(ms):.4%} o fee {fs[int(np.argmin(ms))]:.4f}); "
        f"OLS ngoai suy ~{mo_ols['breakeven_fee_extrapolated']:.4f}"
        if be is None and mo_ols["breakeven_fee_extrapolated"] is not None
        else ("noi suy trong thang do" if be is not None else "khong ngoai suy duoc"))
    # fills/DD survival
    survival = {"as-combo-frozen": []}
    for branch in cfg["branches"]:
        d = results[branch]
        survival["as-combo-frozen"].append({"branch": branch, "fee": d["fee_rate_per_fill"],
                                            "trades": d["trades"], "max_drawdown": d["max_drawdown"],
                                            "monthly": d["monthly_geometric_net"],
                                            "fills_ok": bool(d["gate"]["fills_ge_30"]),
                                            "dd_ok": bool(d["gate"]["drawdown_within_20pct"])})
    survival["as-combo-frozen"].sort(key=lambda r: r["fee"])

    report = {"branches": results, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_c.total_return,
                                               "max_drawdown": res_c.max_drawdown,
                                               "trades": res_c.trades},
                                "match": True},
              "frozen_combo_disclosure": {
                  "reference": "FROZEN cot leverage cua shipped L3 dd_guard_tp075 (THIS experiment giu nguyen, khong recompute)",
                  "formula": "khong co cong thuc guard — giu 203x1.0 + 7x0.5 tu file",
                  "past_only": "N/A (no derivation); guard goc tu v75 own-book tp075_1x past-only",
                  "applied_to": "ALL 3 fee branches (same leverage array, bit-identical)",
                  "n_guarded": 7,
                  "guard_fraction": float(7 / 210),
                  "execution": "leverage=0.25/max=1.0, signal leverage 0.5/1.0 (engine clip giu nguyen)",
                  "tp1_fraction": TP1},
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
                                cfg["frozen_signals"]["path"],
                                "configs/opencode_v81_feecombo.json",
                                "scripts/opencode_r27m_feecombo.py")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
