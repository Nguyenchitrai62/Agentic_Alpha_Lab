"""Opencode R27-L2 (L2-BUILDER): complete 4h UTC session evidence on frozen L1 pool.

Pre-spec: configs/opencode_v83_poolsessions.json (written BEFORE running).
Frozen L1 pool (sibling L1): artifacts/research/opencode_v72_L1pool/pool/signals.parquet
  (326 signals; union v38+v33+majority, high-recall noisy by design).

Matrix: 6x 4h UTC sessions x sizing {1x} (+ dd_guard on the best NON-s0004
session ONLY if its normal monthly strictly beats reproduced control monthly,
else skip+record) = 6-7 branches.
Session = pure function of signal_time UTC hour (inherently causal).
  s0004_1x [0,4) reference (expect ~= v73 +190.84%/101 fills, record match)
  s0408_1x [4,8), s0812_1x [8,12), s1216_1x [12,16), s1620_1x [16,20),
  s2024_1x [20,24). Empty sessions (6h decision clock) record 0/0, not errors.

Control gate: pool_1x rerun (full 326, 1x, normal) MUST reproduce L1 reference
  (+139.70% total_return 1.3970002948657974 / -21.09% DD / 131 trades,
  n_signals 326) within 1e-9 + exact trades/signals, else STOP.
Scenarios per branch: normal + fee 0.00055 + FillStress(5,5,5,.00055,False).
Monthly geometric per configs/swing_v15_continuous_folds.json.
Headline = NORMAL; stresses are reference.
MAE via scripts/opencode_mae.py VERBATIM (L1-delivered).
Labels exploratory, causal past-only, local only, no live orders.
"""

import torch  # noqa: F401  (torch before pandas: DLL load-order on Windows host)
import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402

import importlib.util as _ilu
_MAE_SPEC = _ilu.spec_from_file_location(
    "opencode_mae", str(ROOT / "scripts" / "opencode_mae.py"))
opencode_mae = _ilu.module_from_spec(_MAE_SPEC)
_MAE_SPEC.loader.exec_module(opencode_mae)  # noqa: E402  (L1-delivered MAE metric)

SPEC_PATH = ROOT / "configs/opencode_v83_poolsessions.json"
EXPECTED_BRANCHES = ["s0004_1x", "s0408_1x", "s0812_1x",
                     "s1216_1x", "s1620_1x", "s2024_1x"]
EXPECTED_SESSIONS = {"s0004_1x": [0, 4], "s0408_1x": [4, 8],
                     "s0812_1x": [8, 12], "s1216_1x": [12, 16],
                     "s1620_1x": [16, 20], "s2024_1x": [20, 24]}
REQUIRED_SIGNAL_COLS = ["bar_index", "signal_time", "direction",
                        "entry_limit", "stop_loss", "take_profit_1", "take_profit_2"]
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]
BARS_PER_DAY = 288
DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5


def dd_guard_leverage(signals, ref_trades):
    eq = pd.Series({pd.Timestamp(t.exit_time): t.equity_after
                    for t in sorted(ref_trades, key=lambda t: pd.Timestamp(t.exit_time))})
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out, dtype=float)


def run_3scenarios(candles, signals, costs, fee_costs, execution, stress, years):
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    st, st_trades, diag = run_stress(candles, signals, 100, costs, execution, stress)
    out = {}
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", st, st_trades)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": float(ratio ** (1 / years) - 1),
                      "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        out[label]["_trades_rows"] = [asdict(t) for t in items]
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def mae_stats(candles_sorted, trades):
    """L1-delivered MAE (scripts/opencode_mae.py). OHLC-sampled, normal scenario."""
    frame = opencode_mae.mae_mfe_for_trades(
        [{"direction": int(t.direction), "entry_index": int(t.entry_index),
          "exit_index": int(t.exit_index), "entry_price": float(t.entry_price),
          "signal_index": int(t.signal_index), "entry_time": t.entry_time,
          "exit_time": t.exit_time, "exit_reason": t.exit_reason,
          "net_pnl": float(t.net_pnl), "equity_before": float(t.equity_before)}
         for t in trades], candles_sorted) if trades else None
    if frame is None or not len(frame):
        return {"n": 0, "note": "0 filled trades",
                "definition": "L1 scripts/opencode_mae.py (no filled trades)"}
    dist = opencode_mae.mae_distribution(frame)
    dist["definition"] = ("L1 scripts/opencode_mae.py::mae_mfe_for_trades: "
                          "LONG MAE=(entry-min_low)/entry, SHORT MAE=(max_high-entry)/entry, "
                          "window candles[entry_index:exit_index] inclusive, fractions, "
                          "filled trades only, OHLC-sampled not true intrabar")
    return dist


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    p.add_argument("--skip-dd-guard", action="store_true")
    a = p.parse_args()
    t0 = time.time()
    spec = json.loads(Path(a.config).read_text())
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches must be pre-spec 6x session matrix"
    assert list(spec["sizings"]) == ["1x"]
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"]
    assert dict(spec["sessions"]) == EXPECTED_SESSIONS, "sessions must be 6x 4h UTC pre-spec"
    assert spec["execution"]["holding_cap_bars"] == 2016
    assert abs(float(spec["fee_stress_rate"]) - 0.00055) < 1e-12
    cr = spec["control_reference"]
    assert abs(float(cr["total_return"]) - 1.3970002948657974) < 1e-12
    assert abs(float(cr["max_drawdown"]) - (-0.21088445493348884)) < 1e-12
    assert int(cr["trades"]) == 131 and int(cr["n_signals"]) == 326
    sr = spec["s0004_reference"]
    assert abs(float(sr["total_return"]) - 1.9084116914559015) < 1e-12
    assert abs(float(sr["max_drawdown"]) - (-0.2285874934965051)) < 1e-12
    assert int(sr["trades"]) == 101 and int(sr["n_signals"]) == 210
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")

    pool_path = ROOT / spec["base"]["l1_pool"]
    assert Path(pool_path).exists(), f"Frozen L1 pool missing: {pool_path} -> STOP"
    pool = pd.read_parquet(pool_path)
    assert int(len(pool)) == 326, f"Frozen pool must be 326 signals, got {len(pool)} -> STOP"
    missing = [c for c in REQUIRED_SIGNAL_COLS if c not in pool.columns]
    assert not missing, f"L1 pool missing executable columns {missing} -> STOP"

    ds = ROOT / spec["base"]["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    parent = json.loads((ROOT / spec["base"]["parent_plan"]).read_text())
    candles = pd.read_parquet(ROOT / spec["base"]["candles"])
    candles_sorted = candles.sort_values("open_time", kind="stable").reset_index(drop=True)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    assert abs(costs.fee_rate_per_fill - 0.0002) < 1e-12, "dataset base fee must be 0.0002"
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    stress = FillStress(5, 5, 5, 0.00055, False)
    cap = int(max(cfg["holding_days"]) * BARS_PER_DAY)
    assert cap == 2016, "holding cap must be 2016"
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=0.25, max_leverage=1.0)

    # ---- CONTROL VERIFICATION (rerun pool_1x normal; STOP on mismatch) ----
    pool_1x = pool.drop(columns=["leverage"], errors="ignore").copy()
    ctrl_res, ctrl_trades = run_backtest(candles, pool_1x, 100, costs, exec1x)
    ctrl_ratio = ctrl_res.final_equity / 100
    ctrl_monthly = float(ctrl_ratio ** (1 / (12 * years)) - 1)
    ctrl_match = bool(abs(ctrl_res.total_return - float(cr["total_return"])) < 1e-9
                      and abs(ctrl_res.max_drawdown - float(cr["max_drawdown"])) < 1e-9
                      and ctrl_res.trades == int(cr["trades"])
                      and int(len(pool)) == int(cr["n_signals"]))
    control_check = {"reference": cr,
                     "reproduced": {"total_return": float(ctrl_res.total_return),
                                    "max_drawdown": float(ctrl_res.max_drawdown),
                                    "trades": int(ctrl_res.trades),
                                    "monthly_geometric_net": ctrl_monthly,
                                    "final_equity": float(ctrl_res.final_equity)},
                     "n_signals": int(len(pool)), "match": ctrl_match}
    print(json.dumps({"control_check": control_check}, default=str), flush=True)
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    if not ctrl_match:
        (a.output / "CONTROL_MISMATCH.json").write_text(
            json.dumps(control_check, indent=2, default=str))
        print("CONTROL MISMATCH: STOP", flush=True)
        sys.exit(1)
    ctrl_mae = mae_stats(candles_sorted, ctrl_trades)

    # ---- session split (function of signal_time UTC hour only, causal) ----
    hrs = pd.to_datetime(pool["signal_time"], utc=True).dt.hour
    filt, records = {}, {}
    for branch in EXPECTED_BRANCHES:
        lo, hi = EXPECTED_SESSIONS[branch]
        kept = pool[(hrs >= lo) & (hrs < hi)].copy().reset_index(drop=True)
        filt[branch] = kept
        records[branch] = {"rule": f"{lo:02d} <= UTC hour(signal_time) < {hi:02d}",
                           "hour_start": lo, "hour_end": hi,
                           "n_base": int(len(pool)), "n_kept": int(len(kept)),
                           "causal": "function of frozen signal_time hour only"}
    print(json.dumps({"session_kept": {k: int(len(v)) for k, v in filt.items()}}), flush=True)

    def gate_flags(d, gate):
        try:
            m = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m = dd = f = False
        return {"monthly_geometric_net_ge_5pct": m, "drawdown_within_20pct": dd,
                "fills_ge_30": f, "pass_all": bool(m and dd and f)}

    def save_branch(bdir, sig, scen, gate):
        metrics = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            rows = scen[label].pop("_trades_rows")
            d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                 for k, v in scen[label].items() if k != "diagnostics"}
            if label == "execution_stress":
                d["diagnostics"] = scen[label].get("diagnostics")
            d["gate"] = gate_flags(d, gate)
            metrics[label] = d
            (pd.DataFrame(rows, columns=TRADE_COLUMNS) if rows
             else pd.DataFrame(columns=TRADE_COLUMNS)).to_csv(
                bdir / f"{label}_trades.csv", index=False)
            (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
        return metrics

    results, maes, kept_counts = {}, {}, {}
    for branch in EXPECTED_BRANCHES:
        bdir = a.output / branch
        bdir.mkdir()
        sig = filt[branch].copy()
        kept_counts[branch] = int(len(sig))
        for drop_col in ("leverage",):
            if drop_col in sig.columns:
                sig = sig.drop(columns=[drop_col])
        sig.to_parquet(bdir / "signals.parquet", index=False)
        (bdir / "gate_record.json").write_text(json.dumps(records[branch], indent=2, default=str))
        exec_sig = sig.copy() if len(sig) else pd.DataFrame(
            columns=["bar_index", "direction", "signal_time"])
        scen, normal_trades = run_3scenarios(candles, exec_sig, costs, fee_costs,
                                             exec1x, stress, years)
        m = save_branch(bdir, sig, scen, spec["gate"])
        results[branch] = m
        ms = mae_stats(candles_sorted, normal_trades)
        maes[branch] = ms
        print(json.dumps({"branch": branch, "signals": int(len(sig)),
                          "metrics": {s: {k: m[s][k] for k in
                                          ("total_return", "max_drawdown", "trades",
                                           "monthly_geometric_net", "gross_pnl", "fees",
                                           "funding", "profit_factor", "win_rate")}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "mae_mean": ms.get("mae_mean"), "mae_p90": ms.get("mae_p90"),
                          "gate": {s: m[s]["gate"] for s in
                                   ("normal", "fee_stress", "execution_stress")}},
                         default=str), flush=True)

    # ---- s0004 reference match vs v73 (recorded, not fatal) ----
    n_s0004 = results["s0004_1x"]["normal"]
    s0004_match = bool(abs(n_s0004["total_return"] - float(sr["total_return"])) < 1e-9
                       and abs(n_s0004["max_drawdown"] - float(sr["max_drawdown"])) < 1e-9
                       and n_s0004["trades"] == int(sr["trades"])
                       and kept_counts["s0004_1x"] == int(sr["n_signals"]))
    s0004_check = {"reference": sr,
                   "reproduced": {k: n_s0004[k] for k in
                                  ("total_return", "max_drawdown", "trades",
                                   "monthly_geometric_net", "final_equity")},
                   "n_signals": kept_counts["s0004_1x"], "match": s0004_match}
    print(json.dumps({"s0004_check": s0004_check}, default=str), flush=True)

    # ---- dd_guard conditional: best NON-s0004 session ONLY if beats control monthly ----
    dd_info = {"ran": False}
    non_s0004 = [b for b in EXPECTED_BRANCHES if b != "s0004_1x"]
    cands = [(b, float(results[b]["normal"]["monthly_geometric_net"]))
             for b in non_s0004 if kept_counts[b] > 0]
    beaters = [(b, mo) for b, mo in cands if mo > ctrl_monthly]
    elapsed_1x = time.time() - t0
    if not a.skip_dd_guard and beaters and elapsed_1x < 600:
        best = max(beaters, key=lambda x: x[1])[0]
        bdir = a.output / f"{best}_dd_guard"
        bdir.mkdir()
        sig = filt[best].drop(columns=["leverage"], errors="ignore").copy()
        levs = dd_guard_leverage(sig, ctrl_trades)
        sig["leverage"] = levs
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scen, _ = run_3scenarios(candles, sig, costs, fee_costs, execdd, stress, years)
        m = save_branch(bdir, sig, scen, spec["gate"])
        ms = mae_stats(candles_sorted,
                       run_backtest(candles, sig, 100, costs, execdd)[1])
        maes[f"{best}_dd_guard"] = ms
        kept_counts[f"{best}_dd_guard"] = int(len(sig))
        dd_info = {"ran": True, "branch": f"{best}_dd_guard", "base": best,
                   "rule": spec["dd_guard_conditional"]["rule"],
                   "reference": ("control_1x equity of THIS run (pool rerun, past-only, "
                                 "1-microsecond cutoff, seed 100.0)"),
                   "formula": spec["dd_guard_conditional"]["formula"],
                   "control_monthly": ctrl_monthly,
                   "base_monthly": float(results[best]["normal"]["monthly_geometric_net"]),
                   "n_guarded": int((levs == 0.5).sum()),
                   "guard_fraction": float((levs == 0.5).mean()) if len(levs) else 0.0,
                   "elapsed_1x_s": round(elapsed_1x, 1),
                   "metrics": m, "mae": ms,
                   "note": ("keep-column v49 convention: engine reads per-signal "
                            "leverage clamped into [0.25, 1.0]")}
        print(json.dumps({"dd_guard": {k: dd_info[k] for k in
                                       ("branch", "n_guarded", "guard_fraction")}}, default=str),
              flush=True)
    else:
        dd_info = {"ran": False,
                   "rule": spec["dd_guard_conditional"]["rule"],
                   "control_monthly": ctrl_monthly,
                   "candidates_monthly": {b: mo for b, mo in cands},
                   "beaters": [b for b, _ in beaters],
                   "reason": (f"skip_dd_guard={a.skip_dd_guard}, "
                              f"candidates={len(cands)}, beaters={len(beaters)}, "
                              f"elapsed_1x_s={round(elapsed_1x, 1)}; "
                              "guard runs only if a non-s0004 session beats control monthly") if not beaters
                   else f"guard skipped by flag/time (elapsed_1x_s={round(elapsed_1x, 1)})"}
        print(json.dumps({"dd_guard": dd_info}, default=str), flush=True)

    # ---- MAE shift vs reproduced control ----
    mae_shift = {}
    for b, ms in maes.items():
        if (not ms.get("mae_mean") or not ctrl_mae.get("mae_mean")
                or not ms.get("mae_p90") or not ctrl_mae.get("mae_p90")):
            mae_shift[b] = {"delta_mean_vs_control": None, "delta_p90_vs_control": None}
        else:
            mae_shift[b] = {"delta_mean_vs_control": float(ms["mae_mean"] - ctrl_mae["mae_mean"]),
                            "delta_p90_vs_control": float(ms["mae_p90"] - ctrl_mae["mae_p90"])}
    (a.output / "control_verification").mkdir(exist_ok=True)
    (a.output / "control_verification" / "control_check.json").write_text(
        json.dumps(control_check, indent=2, default=str))
    (a.output / "control_verification" / "mae.json").write_text(json.dumps(
        {"mae": ctrl_mae,
         "note": "reproduced control pool_1x normal MAE (verification only, not a branch)"},
        indent=2, default=str))
    for b, ms in maes.items():
        (a.output / b / "mae.json").write_text(json.dumps(
            {"mae": ms, "shift_vs_control": mae_shift[b]}, indent=2, default=str))

    input_files = [str(pool_path), spec["base"]["candles"],
                   "data/processed/swing_regime_research_v4/config.json",
                   spec["base"]["parent_plan"],
                   "configs/opencode_v83_poolsessions.json",
                   "scripts/opencode_r27L2_poolsessions.py",
                   "scripts/opencode_mae.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "kept_counts": kept_counts, "mae": maes,
              "mae_shift_vs_control": mae_shift,
              "control_mae": ctrl_mae,
              "control_check": control_check, "s0004_check": s0004_check,
              "session_records": records,
              "dd_guard_conditional": dd_info, "duration_years": years,
              "gate": spec["gate"],
              "formulas": {"monthly_geometric_net": spec["monthly_formula"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": spec["dd_guard_conditional"]["formula"],
                           "session": "keep iff hour_start <= UTC hour(signal_time) < hour_end"},
              "config": spec, "independent_test": False, "exploratory": True,
              "live_approved": False, "causality": spec["causality"],
              "headline": "NORMAL scenario is headline; fee/execution stresses are reference only",
              "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                          "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                          "Stop/timeout market-like at scenario fee. MAE is OHLC-sampled, "
                          "not true intrabar adverse excursion. No live approval."),
              "input_sha256": {q: (sha256(ROOT / q) if not Path(q).is_absolute()
                                   else sha256(Path(q)))
                               for q in input_files if (ROOT / q).exists()
                               or Path(q).exists()},
              "output_note": "every file under output dir is new; no history overwritten"}
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
