"""Opencode v107 (R37-A2-scopes33topdec): scopes x sizing tren chan v33-topdec dong bang.

Pre-spec: configs/opencode_v107_scopes33.json (viet TRUOC khi chay).
Frozen input (never refit):
  artifacts/research/opencode_v42_v33cal/v33-iso-topdec/signals.parquet (114 signals)
Matrix: scopes {all, long_only, s0004, t050} x sizing {1x, dd_guard} = 8 branches.
  Scopes la causal post-filter tren frozen fields:
    all = control; long_only: direction==1;
    s0004: 0<=UTC hour<4; t050: expected_net_percent>=0.50.
  dd_guard: lev 0.5/1.0 tu OWN control (v33topdec_all_1x) equity qua khu
    (trigger 10%, cutoff 1-microsecond, seed 100.0), ap tai signal_time rieng
    cua tung branch. Single shared control reference, disclosed trong config.
CONTROL gate: v33topdec_all_1x normal phai reproduce
  (+0.8726992824360695 / -0.15540522960493264 / 72 trades / 114 signals)
  trong 1e-6 + exact counts hoac STOP.
Backtest: candles/costs data/processed/swing_regime_research_v4/;
  run_backtest + run_stress FillStress(5,5,5,.00055,False); fee stress .00055;
  monthly geometric theo configs/swing_v15_continuous_folds.json duration.
Headline = NORMAL, stresses reference. Exploratory, causal past-only,
local only, khong live.
"""
import torch  # noqa: F401  (import order: torch truoc pandas tren host nay)
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v107_scopes33.json"

DD_TRIGGER = 0.10
DD_GUARD_LEV = 0.5
LEV_MIN, LEV_MAX = 0.5, 1.0
T050 = 0.50
SESSION_START, SESSION_END = 0, 4


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state tu reference (control) equity, danh gia tai signal times cho truoc."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in signal_times:
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
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
                            "annual_geometric_net": float(ratio ** (1 / duration_years) - 1),
                            "monthly_geometric_net": float(ratio ** (1 / (12 * duration_years)) - 1)}
        pd.DataFrame([asdict(t) for t in items]).to_csv(out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios


def gate_flags(scenarios, gate):
    flags = {}
    for s in ("normal", "fee_stress", "execution_stress"):
        m = scenarios[s]
        flags[s] = {"monthly_geometric_net_ge_5pct": bool(m["monthly_geometric_net"] >= gate["monthly_min"]),
                    "drawdown_within_20pct": bool(abs(m["max_drawdown"]) <= gate["dd_max"]),
                    "fills_ge_30": bool(m["trades"] >= gate["fills_min"])}
        flags[s]["scenario_pass"] = all(flags[s].values())
    flags["overall_pass"] = all(flags[s]["scenario_pass"] for s in
                                ("normal", "fee_stress", "execution_stress"))
    return flags


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Chon output dir moi; khong ghi de lich su")
    cfg = json.loads(Path(a.config).read_text())
    expected = ["v33topdec_all_1x", "v33topdec_all_dd_guard",
                "v33topdec_long_only_1x", "v33topdec_long_only_dd_guard",
                "v33topdec_s0004_1x", "v33topdec_s0004_dd_guard",
                "v33topdec_t050_1x", "v33topdec_t050_dd_guard"]
    assert list(cfg["branches"]) == expected, "branches phai pre-spec dung 8 nhanh scope x sizing"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert cfg["score_column"] == "expected_net_percent"
    assert abs(float(cfg["t050"]) - T050) < 1e-12
    assert list(cfg["session_utc"]) == [SESSION_START, SESSION_END]
    assert cfg["scenarios"] == ["normal", "fee_stress", "execution_stress"]

    candles = pd.read_parquet(ROOT / cfg["candles"])
    base = pd.read_parquet(ROOT / cfg["base"]["signals"])
    for col in ("direction", "signal_time", cfg["score_column"]):
        assert col in base.columns, f"thieu cot bat buoc {col} trong base dong bang"
    ds_cfg = json.loads((ROOT / cfg["dataset_config"]).read_text())
    parent = json.loads((ROOT / cfg["parent_plan"]).read_text())
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    base_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=1.0, max_leverage=1.0)
    sized_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                 max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                 leverage=LEV_MIN, max_leverage=LEV_MAX)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def filtered(scope):
        out = base
        if scope == "all":
            pass
        elif scope == "long_only":
            out = out[out["direction"] == 1]
        elif scope == "s0004":
            hours = pd.to_datetime(out["signal_time"], utc=True).dt.hour
            out = out[(hours >= SESSION_START) & (hours < SESSION_END)]
        elif scope == "t050":
            out = out[out[cfg["score_column"]] >= T050]
        else:
            raise ValueError(f"unknown scope {scope}")
        return out.copy().reset_index(drop=True)

    results = {}
    # --- control gate (reproduction) ---
    bdir = a.output / "v33topdec_all_1x"
    bdir.mkdir()
    sig = filtered("all")
    exec_sig = sig.drop(columns=["leverage"], errors="ignore").copy()
    sig.to_parquet(bdir / "signals.parquet", index=False)
    scenarios = run_branch(candles, exec_sig, costs, fee_costs, base_exec,
                           stress, duration, bdir)
    n = scenarios["normal"]
    ref = cfg["control_reference"]
    ok = (abs(n["total_return"] - float(ref["total_return"])) < 1e-6
          and abs(n["max_drawdown"] - float(ref["max_drawdown"])) < 1e-6
          and n["trades"] == int(ref["trades"])
          and len(sig) == int(ref["n_signals"]))
    print(json.dumps({"branch": "v33topdec_all_1x", "n_signals": len(sig),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL",
                      "reference": ref}), flush=True)
    if not ok:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reference": ref,
             "reproduced": {k: n[k] for k in ("total_return", "max_drawdown", "trades")},
             "n_signals": len(sig)}, indent=2, default=str))
        raise SystemExit("CONTROL REPRODUCTION FAILED (v33topdec_all_1x): STOP")
    results["v33topdec_all_1x"] = {"scenarios": scenarios, "n_signals": len(sig),
                                  "scope": "all", "sizing": "1x"}

    # guard reference = OWN control trades (fresh reference run, past-only per-signal)
    _, control_trades = run_backtest(candles, exec_sig, 100, costs, base_exec)
    guard_cache = {}

    def guard_for(frame):
        key = tuple(pd.to_datetime(frame["signal_time"], utc=True).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(
                pd.to_datetime(frame["signal_time"], utc=True), control_trades)
        return guard_cache[key]

    plan = [("v33topdec_all_dd_guard", "all", "dd_guard"),
            ("v33topdec_long_only_1x", "long_only", "1x"),
            ("v33topdec_long_only_dd_guard", "long_only", "dd_guard"),
            ("v33topdec_s0004_1x", "s0004", "1x"),
            ("v33topdec_s0004_dd_guard", "s0004", "dd_guard"),
            ("v33topdec_t050_1x", "t050", "1x"),
            ("v33topdec_t050_dd_guard", "t050", "dd_guard")]
    for branch, scope, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        frame = filtered(scope)
        if sizing == "1x":
            frame = frame.drop(columns=["leverage"], errors="ignore")
            ex = base_exec
        else:
            frame["leverage"] = guard_for(frame)
            ex = sized_exec
        frame.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = run_branch(candles, frame, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": len(frame),
                           "scope": scope, "sizing": sizing}
        print(json.dumps({"branch": branch, "n_signals": len(frame),
                          "n_guarded": (int((frame["leverage"] == DD_GUARD_LEV).sum())
                                        if sizing == "dd_guard" else 0),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
              flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": v["n_signals"], "scope": v["scope"], "sizing": v["sizing"],
                   "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {k: results["v33topdec_all_1x"]["scenarios"]["normal"][k]
                                               for k in ("total_return", "max_drawdown", "trades",
                                                         "monthly_geometric_net")},
                                "n_signals": results["v33topdec_all_1x"]["n_signals"],
                                "match": True},
              "formulas": {"score_column": cfg["score_column"], "t050": T050,
                           "session_utc": [SESSION_START, SESSION_END],
                           "scopes": cfg["scopes"],
                           "dd_guard": cfg["dd_guard"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric_net": cfg["monthly_formula"]},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY ONLY: opened 2023-2026 development interval. "
                          "Scopes la frozen constants per branch (khong fitting). "
                          "v33-iso-topdec base la rescued leg tu R11-B; khong promote branch "
                          "hay claim validation. Drawdown trade-candle-close sampled, "
                          "khong phai mark/intrabar day du. Stop/timeout market-like "
                          "o scenario fee, khong phai guaranteed maker fills."),
              "input_sha256": {"base_signals": sha256(ROOT / cfg["base"]["signals"]),
                               **{str(q): sha256(ROOT / q) for q in
                                  (cfg["candles"], cfg["dataset_config"],
                                   cfg["parent_plan"], "configs/opencode_v107_scopes33.json")}},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))

    import hashlib

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()

    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file() and q.name != "summary.json":
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep2 = json.loads((a.output / "summary.json").read_text())
    rep2["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep2, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
