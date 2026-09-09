"""Opencode v44 (R12-B): 1m-refined entry limits on frozen majority_1x.

Frozen inputs (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  decisions (close/atr5 for offset recovery) + candles 5m + 1m audit dir.
Pre-specified matrix (configs/opencode_v44_1mentry.json BEFORE running):
  control_full (94, frozen 5m entry; reproduction gate) +
  {control, m1close, m1extreme, m1vwap} on the KEPT subset (1x) +
  one dd_guard branch on the best refined variant by normal monthly
  (tie-break: normal total_return, then normal trades; rule frozen in config).
Refined entries use ONLY the 5x1m sub-bars of the SIGNAL candle
(close_time <= 5m signal close: strictly causal, asserted at runtime).
Stop/TP/holding kept IDENTICAL to frozen (isolate entry effect; disclosed).
Scenarios: normal / fee .00055 / run_stress FillStress(5,5,5,.00055,False).
Monthly geometric from configs/swing_v15_continuous_folds.json duration.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
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

# B4 published majority_1x normal reference (control gate, exact).
PUBLISHED = {"total_return": 1.6517829563633004,
             "max_drawdown": -0.20086073993367803, "trades": 63}

FROZEN_COLS = ["stop_loss", "take_profit_1", "take_profit_2", "holding_bars",
               "entry_expiry_bars", "tp1_fraction", "direction", "bar_index",
               "signal_time"]


def entry_fill(bar, direction, limit):
    """Mirror of engine._entry_fill (ohlc-v2) for the touch-conversion diagnostic."""
    if direction == 1:
        if float(bar["low"]) > limit:
            return None
        return min(float(bar["open"]), limit) if float(bar["open"]) <= limit else limit
    if float(bar["high"]) < limit:
        return None
    return max(float(bar["open"]), limit) if float(bar["open"]) >= limit else limit


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from reference (control-kept) equity, evaluated at given signal times."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: eq for ts, eq in equity_at})
    out = []
    for ts in signal_times:
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
        pd.DataFrame([asdict(t) for t in items]).to_csv(out_dir / f"{label}_trades.csv", index=False)
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
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == ["control_full", "control", "m1close",
                                     "m1extreme", "m1vwap"], "branches must be pre-specified"
    assert list(cfg["sizings"]) == ["1x"]
    root = Path(__file__).resolve().parents[1]

    candles = pd.read_parquet(root / cfg["base"]["candles_5m"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    decisions = pd.read_parquet(root / cfg["base"]["decisions"])
    frozen = pd.read_parquet(root / cfg["base"]["signals"])
    assert len(frozen) == cfg["base"]["n_signals_frozen"] == 94, "frozen majority count changed"
    m1dir = root / cfg["base"]["m1dir"]
    files_1m = sorted(m1dir.glob("klines_*_1m_*.parquet"))
    m1 = pd.concat([pd.read_parquet(f) for f in files_1m], ignore_index=True)
    m1 = m1.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    m1["close_time"] = pd.to_datetime(m1["close_time"], utc=True)
    m1_idx = {t: i for i, t in enumerate(m1["open_time"])}
    dec_map = {int(r.bar_index): (float(r.close), float(r.atr5)) for r in decisions.itertuples()}

    # ---- coverage: 5 sub-bars of the SIGNAL candle, causal (close_time <= 5m close) ----
    kept_rows, dropped = [], []
    for pos, r in enumerate(frozen.itertuples()):
        bar = candles.iloc[int(r.bar_index)]
        t0 = pd.Timestamp(bar["open_time"])
        sig_close = pd.Timestamp(bar["close_time"])
        assert pd.Timestamp(r.signal_time) == sig_close, "signal_time != candle close"
        subs = [t0 + pd.Timedelta(minutes=k) for k in range(5)]
        found = [s for s in subs if s in m1_idx]
        causal = all(m1.iloc[m1_idx[s]]["close_time"] <= sig_close for s in found)
        assert causal, f"non-causal 1m bar used at {t0}"
        if len(found) == 5 and list(subs) == found:
            rows = [m1.iloc[m1_idx[s]] for s in subs]
            kept_rows.append({"pos": pos, "bar_index": int(r.bar_index),
                              "closes": [float(x["close"]) for x in rows],
                              "lows": [float(x["low"]) for x in rows],
                              "highs": [float(x["high"]) for x in rows]})
        else:
            dropped.append({"pos": pos, "bar_index": int(r.bar_index),
                            "signal_time": str(sig_close), "n_1m_found": len(found)})
    kept_pos = {k["pos"] for k in kept_rows}
    print(json.dumps({"coverage": {"n_frozen": len(frozen), "kept": len(kept_rows),
                                   "dropped": len(dropped),
                                   "dropped_bar_indices": [d["bar_index"] for d in dropped]}}),
          flush=True)

    # ---- offset recovery + refined limits (signal-candle 1m only) ----
    variants = {}
    shift_bp = {}
    sanity_rel = []
    for k in kept_rows:
        r = frozen.iloc[k["pos"]]
        close5, atr5 = dec_map[k["bar_index"]]
        d = int(r.direction)
        off = (close5 - float(r.entry_limit)) / atr5 if d == 1 else (
            float(r.entry_limit) - close5) / atr5
        assert abs(off - round(off * 2) / 2) < 1e-9 and round(off * 2) / 2 in (0.5, 1.5), off
        off = round(off * 2) / 2
        last_c = k["closes"][-1]
        mean_c = float(np.mean(k["closes"]))
        ext = min(k["lows"]) if d == 1 else max(k["highs"])
        if d == 1:
            lims = {"control": float(r.entry_limit), "m1close": last_c - off * atr5,
                    "m1extreme": ext - off * atr5, "m1vwap": mean_c - off * atr5}
        else:
            lims = {"control": float(r.entry_limit), "m1close": last_c + off * atr5,
                    "m1extreme": ext + off * atr5, "m1vwap": mean_c + off * atr5}
        assert all(np.isfinite(v) and v > 0 for v in lims.values()), lims
        variants[k["pos"]] = {"offset": off, "atr5": atr5, "close5": close5,
                              "last1m": last_c, "mean1m": mean_c, "extreme": ext, **lims}
        sanity_rel.append(abs(last_c - close5) / close5)
        for v in ("m1close", "m1extreme", "m1vwap"):
            shift_bp.setdefault(v, []).append(d * (lims[v] - lims["control"]) / close5 * 1e4)
    print(json.dumps({"sanity_last1m_vs_5m_close": {
        "median_rel": float(np.median(sanity_rel)), "max_rel": float(np.max(sanity_rel)),
        "limit_shift_bps_signed": {v: {"mean": float(np.mean(x)), "median": float(np.median(x))}
                                   for v, x in shift_bp.items()}}}), flush=True)

    def build(variant, positions):
        rows = []
        for pos in positions:
            r = frozen.iloc[pos].to_dict()
            if variant != "control_full" and variant != "control":
                r["entry_limit"] = variants[pos][variant]
                r["base_entry_limit"] = float(frozen.iloc[pos]["entry_limit"])
            else:
                r["base_entry_limit"] = float(frozen.iloc[pos]["entry_limit"])
            r["entry_variant"] = variant
            if variant not in ("control_full", "control"):
                v = variants[pos]
                r["entry_offset_atr5"] = v["offset"]
                r["m1_last_close"] = v["last1m"]
                r["m1_mean_close"] = v["mean1m"]
                r["m1_extreme"] = v["extreme"]
            rows.append(r)
        df = pd.DataFrame(rows)
        if "leverage" in df.columns:
            df = df.drop(columns=["leverage"])
        return df.reset_index(drop=True)

    ds_cfg = json.loads((root / cfg["base"]["dataset_config"]).read_text())
    parent = json.loads((root / cfg["base"]["parent_plan"]).read_text())
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
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                   tp1_fraction=0.5, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=0.5, leverage=LEV_MIN, max_leverage=LEV_MAX)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    results, n_sigs = {}, {}
    kept_positions = sorted(kept_pos)

    # ---- control_full first (reproduction gate on 94) ----
    cdir = a.output / "control_full"
    cdir.mkdir()
    full_sig = build("control_full", list(range(len(frozen))))
    full_sig.to_parquet(cdir / "signals.parquet", index=False)
    full_scen, full_trades = run_branch(candles, full_sig, costs, fee_costs,
                                        exec_for("1x"), stress, duration, cdir)
    n = full_scen["normal"]
    ok = (abs(n["total_return"] - PUBLISHED["total_return"]) < 1e-6
          and abs(n["max_drawdown"] - PUBLISHED["max_drawdown"]) < 1e-6
          and n["trades"] == PUBLISHED["trades"])
    print(json.dumps({"branch": "control_full", "n_signals": len(full_sig),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL",
                      "published": PUBLISHED}), flush=True)
    if not ok:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"published": PUBLISHED,
             "reproduced": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    results["control_full"] = {"scenarios": full_scen, "variant": "control_full", "sizing": "1x"}
    n_sigs["control_full"] = len(full_sig)

    # ---- 1x comparison branches on kept subset ----
    control_trades_kept = None
    for variant in ("control", "m1close", "m1extreme", "m1vwap"):
        bdir = a.output / variant
        bdir.mkdir()
        sig = build(variant, kept_positions)
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, trades = run_branch(candles, sig, costs, fee_costs,
                                       exec_for("1x"), stress, duration, bdir)
        results[variant] = {"scenarios": scenarios, "variant": variant, "sizing": "1x"}
        n_sigs[variant] = len(sig)
        if variant == "control":
            control_trades_kept = trades
        print(json.dumps({"branch": variant, "n_signals": len(sig),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades",
                                            "rejected_or_unfilled_signals"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
              flush=True)

    # ---- touch-conversion diagnostic: would refined limits fill where control did not? ----
    expiry = int(ds_cfg["entry_expiry_bars"])
    conv = {}
    for v in ("m1close", "m1extreme", "m1vwap"):
        c2r = r2c = both_out = both_in = 0
        for pos in kept_positions:
            d = int(frozen.iloc[pos]["direction"])
            bi = int(frozen.iloc[pos]["bar_index"])
            last = min(bi + expiry, len(candles) - 1)
            win = [candles.iloc[i] for i in range(bi + 1, last + 1)]
            f_c = any(entry_fill(b, d, variants[pos]["control"]) is not None for b in win)
            f_r = any(entry_fill(b, d, variants[pos][v]) is not None for b in win)
            if f_c and f_r:
                both_in += 1
            elif not f_c and not f_r:
                both_out += 1
            elif f_r:
                c2r += 1
            else:
                r2c += 1
        conv[v] = {"control_no_fill_refined_fills": c2r, "control_fills_refined_no_fill": r2c,
                   "both_fill": both_in, "neither_fills": both_out, "n": len(kept_positions)}

    # ---- dd_guard on best refined (rule frozen in config) ----
    dd_info = {"applied": False}
    order = sorted(("m1close", "m1extreme", "m1vwap"),
                   key=lambda v: (results[v]["scenarios"]["normal"]["monthly_geometric_net"],
                                  results[v]["scenarios"]["normal"]["total_return"],
                                  results[v]["scenarios"]["normal"]["trades"]), reverse=True)
    best = order[0]
    try:
        bdir = a.output / f"{best}_dd_guard"
        bdir.mkdir()
        probe = build(best, kept_positions)
        guard_vec = dd_guard_leverage_at(pd.to_datetime(probe["signal_time"], utc=True),
                                         control_trades_kept)
        sig = probe.copy()
        sig["leverage"] = guard_vec
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, fee_costs,
                                  exec_for("dd_guard"), stress, duration, bdir)
        results[f"{best}_dd_guard"] = {"scenarios": scenarios, "variant": best, "sizing": "dd_guard"}
        n_sigs[f"{best}_dd_guard"] = len(sig)
        dd_info = {"applied": True, "branch": f"{best}_dd_guard", "base_variant": best,
                   "selection_order": order, "guard_reference": "control (kept-subset, 1x) this-run equity",
                   "guard_frac_low": float((guard_vec == DD_GUARD_LEV).mean())}
        print(json.dumps({"branch": f"{best}_dd_guard", "n_signals": len(sig),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
              flush=True)
    except Exception as e:  # cheap-or-skip policy from config
        dd_info = {"applied": False, "reason": f"skipped: {type(e).__name__}: {e}",
                   "selection_order": order, "would_have_been": best}

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": n_sigs[b], "variant": v["variant"], "sizing": v["sizing"],
                   "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "control_check": {"published": PUBLISHED,
                                "reproduced": {k: n[k] for k in
                                               ("total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net")},
                                "match": True},
              "coverage": {"n_frozen": len(frozen), "kept": len(kept_rows),
                           "dropped": len(dropped), "dropped_rows": dropped,
                           "note": ("15 signal candles lack 1m data (0/5 sub-bars each, all-or-nothing); "
                                    "dropped without extrapolation. control_full runs on 94; all comparison "
                                    "branches (control/m1close/m1extreme/m1vwap[/dd_guard]) run on the same "
                                    "kept 79.")},
              "diagnostics": {
                  "fill_rate_note": "fill_rate = trades / n_signals (same 79 rows for all comparison branches).",
                  "touch_conversion_entry_window": conv,
                  "limit_shift_bps_signed": {v: {"mean": float(np.mean(x)), "median": float(np.median(x)),
                                                 "note": "+ means limit moved closer to price (more aggressive)"}
                                             for v, x in shift_bp.items()},
                  "sanity_last1m_vs_5m_close": {"median_rel": float(np.median(sanity_rel)),
                                                "max_rel": float(np.max(sanity_rel))}},
              "dd_guard": dd_info,
              "formulas": cfg["entry_formulas"],
              "isolation": ("stop_loss/take_profit_1/take_profit_2/holding_bars/entry_expiry_bars/tp1_fraction "
                            "IDENTICAL to frozen in every branch; only entry_limit varies. Entry-to-stop risk "
                            "distance changes as a disclosed side effect."),
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("EXPLORATORY ONLY: opened 2023-2026 development interval. Dropped-signal subset (79/94) "
                          "is a disclosed auxiliary-data limitation, not a trade filter. Drawdown is "
                          "trade-candle-close sampled, not true mark-price/intrabar drawdown. Stop/timeout exits "
                          "are market-like at the scenario fee, not guaranteed maker fills."),
              "input_sha256": {"base_majority": sha256(root / cfg["base"]["signals"]),
                               **{str(q): sha256(root / q) for q in
                                  (cfg["base"]["candles_5m"], cfg["base"]["decisions"],
                                   cfg["base"]["dataset_config"], cfg["base"]["parent_plan"],
                                   "configs/opencode_v44_1mentry.json")},
                               "manifest_1m": sha256(m1dir / "manifest.json"),
                               "n_1m_files": len(files_1m), "n_1m_rows": int(len(m1))},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
