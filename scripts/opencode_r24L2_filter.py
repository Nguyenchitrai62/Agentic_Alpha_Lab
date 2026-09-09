"""Opencode R24-L2 (L2-BUILDER): quality filter on the L1 high-recall pool.

Pre-spec: configs/opencode_v73_L2filter.json (written BEFORE running).
L1 pool (sibling L1 agent): artifacts/research/opencode_v72_L1pool/pool/signals.parquet
  (+ summary.json with L1-pool 1x reference numbers). If L1 pool is absent, this
  driver is used in SMOKE mode only (--pool-override + --allow-no-ref) on
  v38-identity alone; smoke output goes to a SEPARATE smoke dir, never the
  pre-spec final output.

Filter matrix (all causal frozen constants; only columns that EXIST are used):
  control_1x (no-filter; must reproduce L1 1x numbers or STOP),
  pctgate_1x (expanding-p90 top-decile validation-style, v33-topdec pattern),
  t050_1x (score >= 0.50, v11 pattern),
  band2_1x (fund_7d >= 5e-05 via D1 join verbatim, score-free),
  s0004_1x (UTC hour 0<=h<4, score-free)
x sizing {1x} (+ dd_guard on the best-filter branch only if cheap, keep-column
convention per v49 so the engine actually reads per-signal 0.5/1.0 leverage).

Scenarios: normal + fee 0.00055 + FillStress(5,5,5,.00055,False).
Monthly geometric per configs/swing_v15_continuous_folds.json.
MAE computed inline (scripts/opencode_mae.py absent): OHLC-sampled adverse
excursion per filled trade, normal scenario; definition recorded in summary.
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

SPEC_PATH = ROOT / "configs/opencode_v73_L2filter.json"
EXPECTED_BRANCHES = ["control_1x", "pctgate_1x", "t050_1x", "band2_1x", "s0004_1x"]
REQUIRED_SIGNAL_COLS = ["bar_index", "signal_time", "direction",
                        "entry_limit", "stop_loss", "take_profit_1", "take_profit_2"]
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]
BARS_PER_DAY = 288
T050 = 0.50
PCT_QUANTILE = 0.9
PCT_MIN_HISTORY = 10
FILL_FLOOR = 0.25
BAND2_MIN = 5e-05
DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5


def resolve_score(pool, order):
    for col in order:
        if col in pool.columns:
            s = pool[col]
            if pd.api.types.is_numeric_dtype(s) and np.isfinite(
                    s.to_numpy(dtype=float)).all():
                return col
    return None


def score_poor(pool, score_col):
    if score_col is None:
        return True, "no-score-column"
    s = pool[score_col].to_numpy(dtype=float)
    if np.unique(s).size < 2:
        return True, "single-distinct-value"
    if float(np.isnan(s).mean()) > 0.5:
        return True, "null-fraction>50%"
    return False, "scores-rich"


def expanding_p90_gate(pool, score_col, fill_col):
    df = pool.sort_values("signal_time", kind="stable").reset_index(drop=True)
    scores = df[score_col].to_numpy(dtype=float)
    fills = df[fill_col].to_numpy(dtype=float) if fill_col else np.ones(len(df))
    keep, rows = [], []
    for i in range(len(df)):
        hist = scores[:i]
        if len(hist) < PCT_MIN_HISTORY:
            thr, warmup, passed = None, True, False
        else:
            thr = float(np.quantile(hist, PCT_QUANTILE))
            warmup = False
            passed = bool(scores[i] >= thr and fills[i] >= FILL_FLOOR)
        rows.append({"pos": int(i), "signal_time": str(df.loc[i, "signal_time"]),
                     "score": float(scores[i]), "fill": float(fills[i]),
                     "history_n": int(len(hist)), "warmup_wait": bool(warmup),
                     "threshold_p90": thr, "kept": bool(passed)})
        if passed:
            keep.append(i)
    kept = df.iloc[keep].reset_index(drop=True) if keep else df.iloc[0:0].copy()
    return kept, rows


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
    """L1-delivered MAE (scripts/opencode_mae.py, same def as pre-spec inline).
    OHLC-sampled adverse excursion per filled trade, normal scenario."""
    frame = opencode_mae.mae_mfe_for_trades(
        [{"direction": int(t.direction), "entry_index": int(t.entry_index),
          "exit_index": int(t.exit_index), "entry_price": float(t.entry_price),
          "signal_index": int(t.signal_index), "entry_time": t.entry_time,
          "exit_time": t.exit_time, "exit_reason": t.exit_reason,
          "net_pnl": float(t.net_pnl), "equity_before": float(t.equity_before)}
         for t in trades], candles_sorted) if trades else None
    if frame is None or not len(frame):
        return {"n": 0, "note": "0 filled trades",
                "definition": "L1 scripts/opencode_mae.py (no filled trades)"}, 0
    dist = opencode_mae.mae_distribution(frame)
    dist["definition"] = ("L1 scripts/opencode_mae.py::mae_mfe_for_trades: "
                          "LONG MAE=(entry-min_low)/entry, SHORT MAE=(max_high-entry)/entry, "
                          "window candles[entry_index:exit_index] inclusive, fractions, "
                          "filled trades only, OHLC-sampled not true intrabar")
    return dist, 0


def find_control_ref(summary):
    """Liberal lookup of L1-pool 1x reference; returns (ref_dict, path_used, n_signals)."""
    br = (summary.get("branches", {}) or {})
    pool1x = br.get("pool_1x", {})
    cands = [
        ("branches.pool_1x.scenarios.normal",
         (pool1x.get("scenarios", {}) or {}).get("normal"), pool1x.get("n_signals")),
        ("branches.pool_1x.normal", pool1x.get("normal"), pool1x.get("n_signals")),
        ("branches.control_1x.scenarios.normal",
         (br.get("control_1x", {}).get("scenarios", {}) or {}).get("normal"),
         br.get("control_1x", {}).get("n_signals")),
        ("branches.control_1x.normal",
         br.get("control_1x", {}).get("normal"), br.get("control_1x", {}).get("n_signals")),
        ("control_1x.scenarios.normal",
         (summary.get("control_1x", {}) or {}).get("scenarios", {}).get("normal"),
         (summary.get("control_1x", {}) or {}).get("n_signals")),
        ("control_reference", summary.get("control_reference"),
         (summary.get("control_reference", {}) or {}).get("n_signals")),
        ("control", summary.get("control"), (summary.get("control", {}) or {}).get("n_signals")),
    ]
    for path, c, nsig in cands:
        if isinstance(c, dict) and all(k in c for k in
                                       ("total_return", "max_drawdown", "trades")):
            return c, path, nsig
    return None, None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    p.add_argument("--pool-override", type=Path, default=None)
    p.add_argument("--l1summary-override", type=Path, default=None)
    p.add_argument("--allow-no-ref", action="store_true")
    p.add_argument("--skip-dd-guard", action="store_true")
    a = p.parse_args()
    t0 = time.time()
    spec = json.loads(Path(a.config).read_text())
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches must be pre-spec 5x L2 matrix"
    assert list(spec["sizings"]) == ["1x"]
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"]
    assert spec["band2"]["fund_7d_min"] == BAND2_MIN and "fund_7d_max" not in spec["band2"]
    assert spec["t050"]["fixed_threshold"] == T050
    assert spec["topdec"]["quantile"] == PCT_QUANTILE
    assert spec["topdec"]["warmup_min_history"] == PCT_MIN_HISTORY
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")

    smoke = bool(a.pool_override is not None)
    pool_path = a.pool_override or (ROOT / spec["base"]["l1_pool"])
    if not Path(pool_path).exists():
        print(json.dumps({"L1": "absent", "pool_path": str(pool_path),
                          "action": "PREP-ONLY required: L1 sibling has not delivered "
                                    "pool/signals.parquet; rerun with --pool-override for smoke "
                                    "or wait for L1 handoff"}), flush=True)
        sys.exit(2)
    pool = pd.read_parquet(pool_path)
    missing = [c for c in REQUIRED_SIGNAL_COLS if c not in pool.columns]
    assert not missing, f"L1 pool missing executable columns {missing} -> STOP (L1 must deliver)"

    score_col = resolve_score(pool, spec["score_resolution_order"])
    fill_col = spec["fill"]["column"] if spec["fill"]["column"] in pool.columns else None
    poor, poor_reason = score_poor(pool, score_col)
    score_avail = {"resolution_order": spec["score_resolution_order"],
                   "resolved_score_column": score_col,
                   "fill_column": fill_col,
                   "score_poor": bool(poor), "score_poor_reason": poor_reason,
                   "pool_columns": list(pool.columns),
                   "pool_n": int(len(pool))}
    print(json.dumps({"score_availability": {k: v for k, v in score_avail.items()
                                             if k != "pool_columns"},
                      "L1_present": not smoke}), flush=True)

    ds = ROOT / spec["base"]["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    parent = json.loads((ROOT / spec["base"]["parent_plan"]).read_text())
    candles = pd.read_parquet(ROOT / spec["base"]["candles"])
    candles_sorted = candles.sort_values("open_time", kind="stable").reset_index(drop=True)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    stress = FillStress(5, 5, 5, 0.00055, False)
    cap = int(max(cfg["holding_days"]) * BARS_PER_DAY)
    assert cap == 2016, "holding cap must be 2016"
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=0.25, max_leverage=1.0)

    # ---- filters (frozen constants, causal) ----
    t050_skipped = pct_skipped = None
    filt, records = {}, {}
    filt["control"] = pool.copy().reset_index(drop=True)
    records["control"] = {"rule": "no-filter", "n_base": int(len(pool)),
                          "n_kept": int(len(pool))}
    if score_col is None:
        pct_skipped = t050_skipped = "no score column in L1 pool -> SKIP (no invented scores)"
        records["pctgate"] = {"rule": "expanding-p90", "skipped": pct_skipped}
        records["t050"] = {"rule": "score>=0.50", "skipped": t050_skipped}
    else:
        kept_p, rec_p = expanding_p90_gate(pool, score_col, fill_col)
        filt["pctgate"] = kept_p
        records["pctgate"] = {"rule": f"expanding-p90 on {score_col} (q=0.9, min_hist=10, "
                                      f"fill>={FILL_FLOOR} on {fill_col})" if fill_col else
                                      f"expanding-p90 on {score_col} (q=0.9, min_hist=10, "
                                      "no fill column -> score-only, recorded)",
                              "n_base": int(len(pool)), "n_kept": int(len(kept_p)),
                              "per_signal": rec_p}
        kept_t = pool[pool[score_col] >= T050].copy().reset_index(drop=True)
        filt["t050"] = kept_t
        records["t050"] = {"rule": f"{score_col} >= {T050} (score-only, v11 pattern)",
                           "n_base": int(len(pool)), "n_kept": int(len(kept_t)),
                           "fill_stats_kept": ({k: float(v) for k, v in
                                                kept_t[fill_col].describe(
                                                    percentiles=[0.5, 0.9]).items()}
                                               if (fill_col and len(kept_t)) else {})}
    # band2: D1 verbatim join
    fund = pd.read_parquet(ROOT / spec["base"]["funding_features"])
    assert "fund_7d" in fund.columns and "bar_index" in fund.columns
    fmap = fund.set_index("bar_index")["fund_7d"]
    tmp = pool.copy().reset_index(drop=True)
    tmp["fund_7d"] = tmp["bar_index"].map(fmap)
    assert int(tmp["fund_7d"].isna().sum()) == 0, "D1 funding join missing (must be full)"
    clock_st = set(pd.to_datetime(fund["signal_time"], utc=True).astype(str))
    assert bool(pd.to_datetime(tmp["signal_time"], utc=True).astype(str).isin(clock_st).all()), \
        "signal_time outside D1 clock"
    kept_b = tmp[tmp["fund_7d"] >= BAND2_MIN].copy().reset_index(drop=True)
    filt["band2"] = kept_b
    records["band2"] = {"rule": "fund_7d >= 5e-05 verbatim D1 (no upper bound)",
                        "n_base": int(len(pool)), "n_kept": int(len(kept_b)),
                        "long": int((kept_b["direction"] == 1).sum()) if len(kept_b) else 0,
                        "short": int((kept_b["direction"] == -1).sum()) if len(kept_b) else 0,
                        "primary_if_score_poor": bool(poor)}
    # s0004 session
    hrs = pd.to_datetime(pool["signal_time"], utc=True).dt.hour
    kept_s = pool[(hrs >= 0) & (hrs < 4)].copy().reset_index(drop=True)
    filt["s0004"] = kept_s
    records["s0004"] = {"rule": "0 <= UTC hour(signal_time) < 4",
                        "n_base": int(len(pool)), "n_kept": int(len(kept_s))}
    print(json.dumps({"filter_kept": {k: (int(len(v)) if v is not None else None)
                                      for k, v in filt.items()}}), flush=True)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def gate_flags(d, gate):
        try:
            m = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m = dd = f = False
        return {"monthly_geometric_net_ge_5pct": m, "drawdown_within_20pct": dd,
                "fills_ge_30": f, "pass_all": bool(m and dd and f)}

    def save_branch(bdir, sig, scen, gate, filt_key):
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

    order = [("control_1x", "control"), ("pctgate_1x", "pctgate"), ("t050_1x", "t050"),
             ("band2_1x", "band2"), ("s0004_1x", "s0004")]
    results, maes, kept_counts = {}, {}, {}
    for branch, key in order:
        bdir = a.output / branch
        bdir.mkdir()
        if key in ("pctgate", "t050") and key not in filt:
            results[branch] = {"skipped": records[key]["skipped"]}
            kept_counts[branch] = 0
            (bdir / "SKIPPED.json").write_text(json.dumps(records[key], indent=2))
            continue
        sig = filt[key].copy()
        kept_counts[branch] = int(len(sig))
        if "leverage" in sig.columns:
            sig = sig.drop(columns=["leverage"])
        if "fund_7d" in sig.columns:
            sig = sig.drop(columns=["fund_7d"])
        sig.to_parquet(bdir / "signals.parquet", index=False)
        (bdir / "gate_record.json").write_text(json.dumps(records[key], indent=2, default=str))
        exec_sig = sig.copy() if len(sig) else pd.DataFrame(
            columns=["bar_index", "direction", "signal_time"])
        scen, normal_trades = run_3scenarios(candles, exec_sig, costs, fee_costs,
                                             exec1x, stress, years)
        m = save_branch(bdir, sig, scen, spec["gate"], key)
        results[branch] = m
        ms, _ = mae_stats(candles_sorted, normal_trades)
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

    # ---- CONTROL CHECK (STOP on mismatch, unless smoke --allow-no-ref) ----
    l1sum_path = a.l1summary_override or (ROOT / spec["base"]["l1_summary"])
    control_check = {"reference_path": None, "match": None, "smoke": bool(smoke)}
    if Path(l1sum_path).exists():
        l1sum = json.loads(Path(l1sum_path).read_text())
        ref, ref_path, ref_nsig = find_control_ref(l1sum)
        assert ref is not None, f"L1 summary lacks control reference numbers -> STOP ({l1sum_path})"
        n = results["control_1x"]["normal"]
        exp_nsig = int(ref_nsig) if ref_nsig is not None else int(ref.get(
            "n_signals", kept_counts["control_1x"]))
        match = bool(abs(n["total_return"] - float(ref["total_return"])) < 1e-9
                     and abs(n["max_drawdown"] - float(ref["max_drawdown"])) < 1e-9
                     and n["trades"] == int(ref["trades"])
                     and kept_counts["control_1x"] == exp_nsig)
        control_check = {"reference_path": str(l1sum_path), "ref_key_path": ref_path,
                         "reference": ref, "reproduced": {k: n[k] for k in
                                                          ("total_return", "max_drawdown", "trades",
                                                           "monthly_geometric_net")},
                         "n_signals": kept_counts["control_1x"], "match": match,
                         "smoke": bool(smoke)}
        print(json.dumps({"control_check": control_check}, default=str), flush=True)
        if not match:
            (a.output / "CONTROL_MISMATCH.json").write_text(
                json.dumps(control_check, indent=2, default=str))
            print("CONTROL MISMATCH: STOP", flush=True)
            sys.exit(1)
    elif a.allow_no_ref:
        control_check = {"reference_path": None, "match": "smoke-self-consistency",
                         "smoke": True,
                         "note": "L1 absent: no external reference; control is identity "
                                 "of --pool-override input, NOT an L2 result"}
        print(json.dumps({"control_check": control_check}), flush=True)
    else:
        (a.output / "CONTROL_REF_MISSING.json").write_text(json.dumps(
            {"l1_summary": str(l1sum_path), "smoke": bool(smoke)}, indent=2))
        print("L1 summary missing and --allow-no-ref not set: STOP", flush=True)
        sys.exit(1)

    # ---- dd_guard conditional on best-filter branch (non-control, signals>0) ----
    dd_info = {"ran": False}
    cands = [(b, results[b]["normal"]["monthly_geometric_net"])
             for b, k in order[1:] if isinstance(results.get(b), dict)
             and "normal" in results[b] and kept_counts[b] > 0]
    elapsed_1x = time.time() - t0
    if not a.skip_dd_guard and cands and elapsed_1x < 600:
        best = max(cands, key=lambda x: x[1])[0]
        key = dict(order)[best]
        _, ref_trades = run_backtest(
            candles, filt["control"].drop(columns=["leverage", "fund_7d"],
                                          errors="ignore").copy(), 100, costs, exec1x)
        bdir = a.output / f"{best}_dd_guard"
        bdir.mkdir()
        sig = filt[key].drop(columns=["leverage", "fund_7d"], errors="ignore").copy()
        levs = dd_guard_leverage(sig, ref_trades)
        sig["leverage"] = levs
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scen, _ = run_3scenarios(candles, sig, costs, fee_costs, execdd, stress, years)
        m = save_branch(bdir, sig, scen, spec["gate"], key)
        ms, _ = mae_stats(candles_sorted,
                          run_backtest(candles, sig, 100, costs, execdd)[1])
        maes[f"{best}_dd_guard"] = ms
        kept_counts[f"{best}_dd_guard"] = int(len(sig))
        dd_info = {"ran": True, "branch": f"{best}_dd_guard", "base": best,
                   "reference": "control_1x equity of THIS run (shared, past-only, "
                                "1-microsecond cutoff, seed 100.0)",
                   "formula": spec["dd_guard_conditional"]["formula"],
                   "n_guarded": int((levs == 0.5).sum()),
                   "guard_fraction": float((levs == 0.5).mean()),
                   "elapsed_1x_s": round(elapsed_1x, 1),
                   "metrics": m, "mae": ms,
                   "note": "keep-column v49 convention: engine reads per-signal "
                           "leverage clamped into [0.25, 1.0] (v43 dropped the column, "
                           "which would flatten to 0.25x; recorded here, not repeated)"}
        print(json.dumps({"dd_guard": {k: dd_info[k] for k in
                                       ("branch", "n_guarded", "guard_fraction")}}, default=str),
              flush=True)
    else:
        dd_info = {"ran": False,
                   "reason": f"skip_dd_guard={a.skip_dd_guard}, "
                             f"candidates={len(cands)}, elapsed_1x_s={round(elapsed_1x, 1)}"}
        print(json.dumps({"dd_guard": dd_info}), flush=True)

    # ---- MAE shift vs control ----
    cm = maes.get("control_1x", {})
    mae_shift = {}
    for b, ms in maes.items():
        if (b == "control_1x" or not ms.get("mae_mean") or not cm.get("mae_mean")
                or not ms.get("mae_p90") or not cm.get("mae_p90")):
            mae_shift[b] = {"delta_mean_vs_control": None, "delta_p90_vs_control": None}
        else:
            mae_shift[b] = {"delta_mean_vs_control": float(ms["mae_mean"] - cm["mae_mean"]),
                            "delta_p90_vs_control": float(ms["mae_p90"] - cm["mae_p90"])}
    for b, ms in maes.items():
        (a.output / b / "mae.json").write_text(json.dumps(
            {"mae": ms, "shift_vs_control": mae_shift[b]}, indent=2, default=str))

    input_files = [str(pool_path), spec["base"]["candles"],
                   "data/processed/swing_regime_research_v4/config.json",
                   spec["base"]["parent_plan"], spec["base"]["funding_features"],
                   "configs/opencode_v23_fundingfeat.json",
                   "configs/opencode_v73_L2filter.json",
                   "scripts/opencode_r24L2_filter.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "kept_counts": kept_counts, "mae": maes, "mae_shift_vs_control": mae_shift,
              "mae_source": spec["mae"], "control_check": control_check,
              "score_availability": score_avail,
              "filter_records": {k: ({kk: vv for kk, vv in v.items() if kk != "per_signal"}
                                     | {"per_signal_n": len(v["per_signal"])} if "per_signal" in v
                                     else v) for k, v in records.items()},
              "dd_guard_conditional": dd_info, "duration_years": years,
              "gate": spec["gate"],
              "formulas": {"monthly_geometric_net": spec["monthly_formula"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": spec["dd_guard_conditional"]["formula"],
                           "band2": spec["band2"], "t050": spec["t050"],
                           "topdec": spec["topdec"]},
              "config": spec, "independent_test": False, "exploratory": True,
              "live_approved": False, "causality": spec["causality"],
              "smoke": bool(smoke),
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
