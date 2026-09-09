"""Opencode v79 (R26-L2 VERIFY): independent rebuild of L3 v75 combo numbers.

Rebuilds from FROZEN inputs only:
  signals = artifacts/research/opencode_v73_L2filter/s0004_1x/signals.parquet (210)
  candles/costs = data/processed/swing_regime_research_v4/
  constants read from configs/opencode_v79_verify.json (pre-spec, values mirror L3 v75).

Own implementation (no import of L3 driver scripts/opencode_r24L3_risk.py):
  - guard: explicit loop over sorted reference exits, strictly-past cutoff
    (signal_ts - 1 microsecond), 100.0 seed, lev 0.5 iff level/peak < 1-trigger.
  - tp075: via ExecutionConfig.tp1_fraction (signal tp1_fraction column is
    provenance only, mirroring L3 convention).
  - sizing: 1x -> ExecutionConfig(leverage=1,max=1) + drop leverage column;
    dd_guard -> ExecutionConfig(leverage=LEV_MIN,max=LEV_MAX) + per-signal
    leverage column (0.5/1.0) kept so the engine reads it (keep-column rule).

Scope: normal (fee 0.0002 from dataset costs) + fee_stress (0.00055).
No execution_stress, no MAE-stop, no new hypotheses. Exploratory labels only.
"""
import torch  # noqa: F401  (torch before pandas: DLL load-order on this host)
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.training import sha256

MICROSECOND = pd.Timedelta(microseconds=1)
SEED_EQUITY = 100.0


def own_guard_leverage(signal_times_utc, ref_exit_times_utc, ref_equities, trigger, low_lev):
    """Independent guard: loop-based, strictly-past reference equity.

    signal_times_utc: iterable of Timestamps (tz-aware UTC).
    ref_exit_times_utc / ref_equities: parallel arrays of the 1x reference
      book's exits (any datetime-like array); sorted internally, stable.
    Returns np.array of 1.0 / low_lev, one per signal, in input order.
    """
    exits_all = list(pd.to_datetime(ref_exit_times_utc, utc=True))
    eqs_all = [float(v) for v in ref_equities]
    paired = sorted(zip(exits_all, eqs_all), key=lambda p: p[0])
    exits = [p[0] for p in paired]
    eqs = [p[1] for p in paired]
    out = np.ones(len(signal_times_utc), dtype=float)
    for k, ts in enumerate(signal_times_utc):
        cutoff = ts - MICROSECOND
        # binary search: last exit <= cutoff
        lo, hi, pos = 0, len(exits) - 1, -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if exits[mid] <= cutoff:
                pos = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if pos < 0:
            out[k] = 1.0
            continue
        level = eqs[pos]
        peak = SEED_EQUITY
        for j in range(pos + 1):
            if eqs[j] > peak:
                peak = eqs[j]
        out[k] = low_lev if (level / peak) < (1.0 - trigger) else 1.0
    return out


def monthly_net(final_equity, years):
    ratio = float(final_equity) / 100.0
    return float(ratio ** (1.0 / (12.0 * years)) - 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    cfg = json.loads(Path(a.config).read_text())
    root = Path(__file__).resolve().parents[1]

    fc = cfg["frozen_constants"]
    TRG = float(fc["dd_trigger"])
    GLV = float(fc["dd_guard_lev"])
    LMIN = float(fc["lev_min"])
    LMAX = float(fc["lev_max"])
    TP_C = float(fc["tp1_control"])
    TP_75 = float(fc["tp1_tp075"])
    FEE_S = float(fc["fee_stress_rate"])
    TOL = float(cfg["pass_criterion"]["tolerance_abs"])
    assert 0 < TP_C < 1 and 0 < TP_75 < 1 and 0 < TRG < 1

    sig_path = root / cfg["frozen_inputs"]["signals"]
    base = pd.read_parquet(sig_path)
    assert len(base) == int(cfg["frozen_inputs"]["signals_n_expected"]), (
        f"frozen signals count changed: {len(base)}")
    for col in ("bar_index", "signal_time", "direction", "entry_limit",
                "stop_loss", "take_profit_1", "take_profit_2"):
        assert col in base.columns, f"missing executable column {col}"

    # Deterministic order: stable sort by (bar_index, signal_time); record
    # whether the frozen input was already sorted (floating-order diagnostic).
    sig_time = pd.to_datetime(base["signal_time"], utc=True)
    already_sorted = bool((base["bar_index"].to_numpy()[:-1]
                           <= base["bar_index"].to_numpy()[1:]).all())
    work = base.copy()
    work["__st"] = sig_time.to_numpy()
    work = work.sort_values(["bar_index", "__st"], kind="mergesort").reset_index(drop=True)
    work = work.drop(columns=["__st"])

    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    ds_cfg = json.loads((root / cfg["frozen_inputs"]["dataset_config"]).read_text())
    parent = json.loads((root / cfg["frozen_inputs"]["parent_plan"]).read_text())
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**ds_cfg["costs"])
    assert abs(costs.fee_rate_per_fill - float(cfg["frozen_constants"]["fee_normal"])) < 1e-12
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": FEE_S})
    cap = int(max(ds_cfg["holding_days"]) * 288)
    exp_bars = int(ds_cfg["entry_expiry_bars"])
    assert exp_bars == 12 and cap == 2016, "dataset execution horizon changed"

    def exec_1x(tp1):
        return ExecutionConfig(entry_expiry_bars=exp_bars, max_holding_bars=cap,
                               tp1_fraction=tp1, leverage=1.0, max_leverage=1.0)

    def exec_guard(tp1):
        return ExecutionConfig(entry_expiry_bars=exp_bars, max_holding_bars=cap,
                               tp1_fraction=tp1, leverage=LMIN, max_leverage=LMAX)

    def frame_1x(tp1):
        f = work.copy()
        f["tp1_fraction"] = tp1  # provenance only; engine reads ExecutionConfig
        if "leverage" in f.columns:
            f = f.drop(columns=["leverage"])
        return f.reset_index(drop=True)

    def run_two(frame, execution):
        res_n, tr_n = run_backtest(candles, frame, 100, costs, execution)
        res_f, tr_f = run_backtest(candles, frame, 100, fee_costs, execution)
        return (res_n, tr_n), (res_f, tr_f)

    def metrics_pair(res_n, res_f):
        d = {}
        for label, r in (("normal", res_n), ("fee_stress", res_f)):
            dd = asdict(r)
            dd["monthly_geometric_net"] = monthly_net(r.final_equity, years)
            dd["annual_geometric_net"] = float((r.final_equity / 100.0) ** (1.0 / years) - 1.0)
            d[label] = dd
        return d

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    store = {}

    # --- control_1x (tp0.5, 1x) ---
    f_control = frame_1x(TP_C)
    (cn, tn), (cf, tf) = run_two(f_control, exec_1x(TP_C))
    store["control_1x"] = {"frame": f_control, "normal": (cn, tn), "fee": (cf, tf)}

    # --- tp075_1x (tp0.75, 1x): own-book guard reference ---
    f_75 = frame_1x(TP_75)
    (s75n, t75n), (s75f, t75f) = run_two(f_75, exec_1x(TP_75))
    store["tp075_1x"] = {"frame": f_75, "normal": (s75n, t75n), "fee": (s75f, t75f)}

    # --- guard vector from own-book tp075_1x NORMAL exits ---
    ref_times = pd.to_datetime([t.exit_time for t in t75n], utc=True)
    ref_eq = np.array([float(t.equity_after) for t in t75n], dtype=float)
    sig_times = pd.to_datetime(store["tp075_1x"]["frame"]["signal_time"], utc=True)
    guard_vec = own_guard_leverage(list(sig_times), np.array(ref_times),
                                   ref_eq, TRG, GLV)
    guard_low_frac = float((guard_vec == GLV).mean())
    guard_n = int((guard_vec == GLV).sum())

    # --- dd_guard_tp075 (tp0.75 + guard) ---
    f_combo = work.copy()
    f_combo["tp1_fraction"] = TP_75
    if "leverage" in f_combo.columns:
        f_combo = f_combo.drop(columns=["leverage"])
    f_combo["leverage"] = guard_vec
    f_combo = f_combo.reset_index(drop=True)
    (cbn, tbn), (cbf, tbf) = run_two(f_combo, exec_guard(TP_75))
    store["dd_guard_tp075"] = {"frame": f_combo, "normal": (cbn, tbn), "fee": (cbf, tbf)}

    # --- persist branches ---
    for branch in ("control_1x", "tp075_1x", "dd_guard_tp075"):
        bdir = a.output / branch
        bdir.mkdir()
        store[branch]["frame"].to_parquet(bdir / "signals.parquet", index=False)
        for label, key in (("normal", "normal"), ("fee_stress", "fee")):
            res, trs = store[branch][key]
            rows = [asdict(t) for t in trs]
            pd.DataFrame(rows).to_csv(bdir / f"{label}_trades.csv", index=False)
            m = metrics_pair(store[branch]["normal"][0], store[branch]["fee"][0])[label]
            (bdir / f"{label}_metrics.json").write_text(json.dumps(m, indent=2, default=str))
    pd.DataFrame({"signal_time": sig_times.astype(str),
                  "guard_leverage": guard_vec}).to_csv(
        a.output / "dd_guard_tp075" / "guard_vector.csv", index=False)

    # --- compare vs L3 published (exact) ---
    pub = cfg["l3_published_exact"]
    rep, deltas, verdicts = {}, {}, {}
    for branch in ("control_1x", "tp075_1x", "dd_guard_tp075"):
        rep[branch] = metrics_pair(store[branch]["normal"][0], store[branch]["fee"][0])
        deltas[branch] = {}
        verdicts[branch] = {}
        for scen in ("normal", "fee_stress"):
            r = rep[branch][scen]
            p = pub[branch][scen]
            d = {k: float(r[k] - p[k]) for k in
                 ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity")}
            d["trades"] = int(r["trades"] - p["trades"])
            ok = (all(abs(d[k]) <= TOL for k in
                      ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"))
                  and d["trades"] == 0)
            deltas[branch][scen] = d
            verdicts[branch][scen] = "PASS" if ok else "FAIL"

    overall = all(v == "PASS" for b in verdicts for v in verdicts[b].values())

    # --- mismatch triage (only fills if FAIL; never adjusts numbers) ---
    triage = {"status": "no mismatch" if overall else "mismatch under investigation",
              "checks": {}}
    if not overall:
        triage["checks"]["input_sorted"] = already_sorted
        triage["checks"]["guard_low_frac_repro"] = guard_low_frac
        triage["checks"]["guard_low_frac_published"] = pub["dd_guard_tp075"]["meta"]["guard_low_frac"]
        triage["checks"]["guard_n_low"] = guard_n
        triage["checks"]["tp075_effect_repro"] = float(
            rep["tp075_1x"]["normal"]["total_return"] - rep["control_1x"]["normal"]["total_return"])
        triage["checks"]["note"] = ("Candidate causes in order: (1) guard-ref difference "
                                    "(own-book tp075 vs shared control), (2) tp1 handling "
                                    "(ExecutionConfig vs signal column), (3) floating signal order, "
                                    "(4) fee/years formula drift. See per-branch deltas.")

    summary = {
        "experiment": "opencode-v79-verify",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "frozen_inputs": cfg["frozen_inputs"],
        "input_sorted_by_bar_index": already_sorted,
        "duration_years": years,
        "tolerance_abs": TOL,
        "l3_published_exact": pub,
        "reproduced": rep,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "guard": {"ref": "own-book tp075_1x normal (this run)",
                  "n_signals": int(len(f_combo)),
                  "n_guarded_low": guard_n,
                  "guard_low_frac": guard_low_frac},
        "triage": triage,
        "artifacts": {"control_1x": "control_1x/{signals.parquet,normal_trades.csv,fee_stress_trades.csv,*_metrics.json}",
                      "tp075_1x": "tp075_1x/{...}",
                      "dd_guard_tp075": "dd_guard_tp075/{...+guard_vector.csv}"},
        "causal_notes": cfg["causal_notes"],
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
        "warning": ("Exploratory verification on the opened development interval only "
                    "(2023-2026). Not an independent test. No live approval. "
                    "Drawdown is trade-candle-close sampled; stops/timeouts market-like."),
        "input_sha256": {q: sha256(root / q) for q in
                         (cfg["frozen_inputs"]["signals"], cfg["frozen_inputs"]["candles"],
                          cfg["frozen_inputs"]["dataset_config"], cfg["frozen_inputs"]["parent_plan"],
                          "configs/opencode_v79_verify.json", "scripts/opencode_r26L2_verify.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({"control_normal": {k: rep["control_1x"]["normal"][k] for k in
                                         ("total_return", "max_drawdown", "trades",
                                          "monthly_geometric_net", "final_equity")},
                      "combo_normal": {k: rep["dd_guard_tp075"]["normal"][k] for k in
                                       ("total_return", "max_drawdown", "trades",
                                        "monthly_geometric_net", "final_equity")},
                      "verdicts": verdicts, "overall": summary["overall_verdict"],
                      "guard_low_frac": guard_low_frac, "guard_n": guard_n,
                      "input_sorted": already_sorted}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
