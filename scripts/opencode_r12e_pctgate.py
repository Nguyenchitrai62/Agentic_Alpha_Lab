"""Opencode R12-E (E-EXPLOIT): percentile-gate (R11-B leg) x majority/confirmed strong bases.

Pre-spec: configs/opencode_v43_pctgate.json (viet TRUOC khi chay).
Frozen inputs: artifacts/research/opencode_v15_mapensemble/{majority_1x,confirmed_1x}/signals.parquet
  + data/processed/swing_regime_research_v4/{candles.parquet,config.json}.
Score column: expected_net_percent EXISTS (iso4 choose output; 50/43 unique) -> expanding-p90 gate.
  t050 fallback NOT triggered (ghi nhan trong config).
Rule (causal past-only): threshold_i = p90(history expected_net_percent j<i, min_history 10 else WAIT);
  keep iff score_i >= threshold_i and fill_i >= 0.25. Subset filter (limitation disclosed in config).
Branches (8): {majority_control, majority_pctgate, confirmed_control, confirmed_pctgate} x {1x, dd_guard}.
  dd_guard reference = MY majority_control_1x equity (past-only, trigger 10%, 0.5/1.0),
  applied at each branch's own signal times; exec leverage=0.25/max=1.0 (v15 convention).
Scenarios: normal + fee 0.00055 + FillStress(5,5,5,.00055,False).
Monthly geometric theo configs/swing_v15_continuous_folds.json.
Labels exploratory, causal past-only, local only, khong live.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
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

SPEC_PATH = ROOT / "configs/opencode_v43_pctgate.json"
EXPECTED_BRANCHES = ["majority_control_1x", "majority_control_dd_guard",
                     "majority_pctgate_1x", "majority_pctgate_dd_guard",
                     "confirmed_control_1x", "confirmed_control_dd_guard",
                     "confirmed_pctgate_1x", "confirmed_pctgate_dd_guard"]
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]
MIN_HISTORY = 10
QUANTILE = 0.9
FILL_FLOOR = 0.25
BARS_PER_DAY = 288


def expanding_p90_gate(base):
    """Causal expanding-percentile subset. Returns (kept_df, record_rows)."""
    df = base.sort_values("signal_time", kind="stable").reset_index(drop=True)
    scores = df["expected_net_percent"].to_numpy(dtype=float)
    fills = df["ohlc_fill_score"].to_numpy(dtype=float)
    if not np.isfinite(scores).all() or not np.isfinite(fills).all():
        raise ValueError("Nonfinite gate inputs")
    keep, rows = [], []
    for i in range(len(df)):
        ts = pd.Timestamp(df.loc[i, "signal_time"])
        hist = scores[:i]
        if len(hist) < MIN_HISTORY:
            thr, warmup, passed = None, True, False
        else:
            thr = float(np.quantile(hist, QUANTILE))
            warmup = False
            passed = bool(scores[i] >= thr and fills[i] >= FILL_FLOOR)
        rows.append({"pos": int(i), "signal_time": str(ts),
                     "expected_net_percent": float(scores[i]),
                     "ohlc_fill_score": float(fills[i]),
                     "history_n": int(len(hist)),
                     "warmup_wait": bool(warmup),
                     "threshold_p90": thr, "kept": bool(passed)})
        if passed:
            keep.append(i)
    kept = df.iloc[keep].reset_index(drop=True) if keep else df.iloc[0:0].copy()
    return kept, rows


def dd_guard_leverage(signals, ref_trades):
    """Guard tu MY majority-control equity; ap dung tai signal times cua branch (v15 convention)."""
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(0.5 if level / peak < 0.9 else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, execution, years):
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
                      "annual_geometric_net": float(ratio ** (1 / years) - 1),
                      "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        out[label]["_trades_rows"] = [asdict(t) for t in items]
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text())
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches phai pre-spec dung 8 nhanh v43"
    assert list(spec["sizings"]) == ["1x", "dd_guard"]
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"]
    assert spec["gate_rule"]["exact_rule"][2].startswith("Warmup: if len(history_i) < 10")
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    base = spec["base"]
    ds = ROOT / base["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    parent = json.loads((ROOT / base["parent_plan"]).read_text())
    candles = pd.read_parquet(ds / "candles.parquet")
    maj = pd.read_parquet(ROOT / base["majority_signals"])
    conf = pd.read_parquet(ROOT / base["confirmed_signals"])
    assert "expected_net_percent" in maj.columns and "expected_net_percent" in conf.columns, \
        "score column missing -> STOP per mission (khong tu che scores)"
    assert "ohlc_fill_score" in maj.columns and "ohlc_fill_score" in conf.columns
    print(json.dumps({"score_columns": {
        "majority": {"n": int(len(maj)), "exp_unique": int(maj.expected_net_percent.nunique()),
                     "exp_min": float(maj.expected_net_percent.min()),
                     "exp_p90": float(maj.expected_net_percent.quantile(0.9)),
                     "exp_max": float(maj.expected_net_percent.max())},
        "confirmed": {"n": int(len(conf)), "exp_unique": int(conf.expected_net_percent.nunique()),
                      "exp_min": float(conf.expected_net_percent.min()),
                      "exp_p90": float(conf.expected_net_percent.quantile(0.9)),
                      "exp_max": float(conf.expected_net_percent.max())}}}), flush=True)
    maj_gate, maj_rec = expanding_p90_gate(maj)
    conf_gate, conf_rec = expanding_p90_gate(conf)
    print(json.dumps({"pctgate_kept": {"majority": int(len(maj_gate)), "confirmed": int(len(conf_gate)),
                                       "warmup_dropped_maj": int(sum(1 for r in maj_rec if r["warmup_wait"])),
                                       "warmup_dropped_conf": int(sum(1 for r in conf_rec if r["warmup_wait"]))}}), flush=True)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * BARS_PER_DAY)
    assert cap == 2016, "holding cap"
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=0.25, max_leverage=1.0)
    # ---- CONTROL CHECKS (STOP neu lech) ----
    ref = spec["control_reference"]
    checks = {}
    for tag, sig in (("majority", maj), ("confirmed", conf)):
        r = ref[tag]
        base_sig = sig.drop(columns=["leverage"], errors="ignore").copy()
        res_c, _ = run_backtest(candles, base_sig, 100, costs, exec1x)
        match = bool(abs(res_c.total_return - float(r["total_return"])) < 1e-9
                     and abs(res_c.max_drawdown - float(r["max_drawdown"])) < 1e-9
                     and res_c.trades == int(r["trades"])
                     and len(sig) == int(r["n_signals"]))
        checks[tag] = {"reproduced": {"total_return": res_c.total_return,
                                      "max_drawdown": res_c.max_drawdown,
                                      "trades": res_c.trades,
                                      "n_signals": int(len(sig))},
                       "reference": r, "match": match}
        print(json.dumps({"control_check": {tag: checks[tag]}}), flush=True)
    if not (checks["majority"]["match"] and checks["confirmed"]["match"]):
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(checks, indent=2, default=str))
        print("CONTROL MISMATCH: STOP", flush=True)
        sys.exit(1)
    # ---- Guard reference: MY majority-control 1x trades ----
    _, ref_trades = run_backtest(candles, maj.drop(columns=["leverage"], errors="ignore").copy(),
                                 100, costs, exec1x)
    sigsets = {"majority_control": maj, "majority_pctgate": maj_gate,
               "confirmed_control": conf, "confirmed_pctgate": conf_gate}
    gate = spec["gate"]
    results, diagnostics, guard_info = {}, {}, {}

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    for stem, base_sig in sigsets.items():
        for sizing in ("1x", "dd_guard"):
            branch = f"{stem}_{sizing}"
            bdir = a.output / branch
            bdir.mkdir()
            sig = base_sig.copy()
            if sizing == "dd_guard":
                levs = dd_guard_leverage(sig, ref_trades) if len(sig) else np.array([], dtype=float)
                sig["leverage"] = levs
                guard_info[branch] = {"reference": "MY majority_control_1x equity (this run)",
                                      "n_guarded": int((levs == 0.5).sum()) if len(sig) else 0,
                                      "guard_fraction": float((levs == 0.5).mean()) if len(sig) else 0.0}
                execution = execdd
            else:
                if "leverage" in sig.columns:
                    sig = sig.drop(columns=["leverage"])
                execution = exec1x
            sig.to_parquet(bdir / "signals.parquet", index=False)
            if "pctgate" in stem:
                rec = maj_rec if "majority" in stem else conf_rec
                (bdir / "gate_record.json").write_text(json.dumps(
                    {"rule": "expanding-p90-subset (quantile 0.9, min_history 10, fill>=0.25, warmup WAIT)",
                     "n_base": int(len(base_sig)), "n_kept": int(len(sig)),
                     "per_signal": rec}, indent=2, default=str))
            exec_sig = sig.drop(columns=["leverage"], errors="ignore").copy() if len(sig) else sig.copy()
            if len(exec_sig) == 0:
                exec_sig = pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
            scen, _ = run_branch(candles, exec_sig, costs, execution, years)
            branch_metrics = {}
            for label in ("normal", "fee_stress", "execution_stress"):
                rows = scen[label].pop("_trades_rows")
                d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                     for k, v in scen[label].items() if k != "diagnostics"}
                if label == "execution_stress":
                    d["diagnostics"] = scen[label].get("diagnostics")
                d["gate"] = gate_flags(d)
                branch_metrics[label] = d
                if rows:
                    pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
                else:
                    pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
                (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
            results[branch] = branch_metrics
            diagnostics[branch] = {
                "n_signals": int(len(sig)),
                "score_stats": {k: float(v) for k, v in
                                sig["expected_net_percent"].describe(
                                    percentiles=[0.5, 0.8, 0.9]).items()} if len(sig) else {},
                "dd_guard": guard_info.get(branch, {"reference": "none (1x)"})}
            print(json.dumps({"branch": branch, "signals": int(len(sig)),
                              "metrics": {s: {k: branch_metrics[s][k] for k in
                                              ("total_return", "max_drawdown", "trades",
                                               "monthly_geometric_net", "gross_pnl", "fees",
                                               "funding", "profit_factor", "win_rate")}
                                          for s in ("normal", "fee_stress", "execution_stress")},
                              "gate": {s: branch_metrics[s]["gate"] for s in
                                       ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)
    input_files = [base["majority_signals"], base["confirmed_signals"], base["candles"],
                   "data/processed/swing_regime_research_v4/config.json",
                   base["parent_plan"], "configs/opencode_v43_pctgate.json",
                   "scripts/opencode_r12e_pctgate.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "diagnostics": diagnostics, "control_check": checks,
              "gate_definition_record": {"rule": spec["gate_rule"],
                                         "t050_fallback_triggered": False,
                                         "score_column": "expected_net_percent (frozen iso4 choose output)"},
              "guard_info": guard_info, "duration_years": years, "gate": gate,
              "formulas": {"monthly_geometric_net": spec["monthly_formula"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": spec["dd_guard"]["formula"]},
              "config": spec, "independent_test": False, "exploratory": True,
              "live_approved": False,
              "causality": "past-only closed-candle; percentile thresholds tu strictly-past scores; guard tu strictly-past exits; fill tu nen ke tiep",
              "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                          "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                          "Stop/timeout market-like o scenario fee. Khong live approval."),
              "input_sha256": {q: sha256(ROOT / q) for q in input_files},
              "output_note": "moi file duoi output dir la moi; khong ghi de lich su"}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))

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
