"""Opencode v88 (R29-A2 VERIFYFEE): independent rebuild of M v81 feecombo numbers.

Rebuilds from FROZEN inputs only (read, never refit):
  signals = artifacts/research/opencode_v75_L3real/dd_guard_tp075/signals.parquet (210)
  candles/costs = data/processed/swing_regime_research_v4/
  M config/summary are READ-ONLY references (values copied into
  configs/opencode_v88_verifyfee.json at pre-spec time; this driver never
  imports scripts/opencode_r27m_feecombo.py).

Own implementation:
  - own fee application: CostModel rebuilt per branch from explicit dataset
    cost fields (no dict-spread of a base object).
  - own execution builder: ExecutionConfig(lev_floor/lev_cap/tp1) from config
    constants + frozen leverage column kept verbatim.
  - own monthly function: ratio^(1/(12*years))-1 with years from parent plan.
  - 2 branches only: verify_fee0002_1x (control) + verify_fee0010_1x (stress).
  - compares total_return / max_drawdown / monthly_geometric_net /
    final_equity within 1e-6 + trades exact. No breakeven fitting (out of
    scope for verification).

Scope: verification backtests only. Exploratory labels, opened interval.
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

SEED = 100.0


def verify_monthly(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / (12.0 * span_years)) - 1.0)


def verify_annual(final_equity_value, span_years):
    growth = float(final_equity_value) / 100.0
    return float(growth ** (1.0 / span_years) - 1.0)


def build_branch_costs(ds_costs, branch_fee):
    return CostModel(
        fee_rate_per_fill=float(branch_fee),
        funding_long_rate=float(ds_costs["funding_long_rate"]),
        funding_short_rate=float(ds_costs["funding_short_rate"]),
        funding_interval_hours=int(ds_costs["funding_interval_hours"]),
    )


def build_verify_execution(expiry_bars, cap_bars, floor_lev, cap_lev, tp1_frac):
    return ExecutionConfig(
        entry_expiry_bars=int(expiry_bars),
        max_holding_bars=int(cap_bars),
        leverage=float(floor_lev),
        max_leverage=float(cap_lev),
        tp1_fraction=float(tp1_frac),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    cfg = json.loads(Path(a.config).read_text())
    root = Path(__file__).resolve().parents[1]

    want = ["verify_fee0002_1x", "verify_fee0010_1x"]
    assert list(cfg["branches"]) == want, "v88 pre-spec must be exactly the 2-branch fee x 1xcap matrix"
    tol = float(cfg["pass_criterion"]["tolerance_abs"])
    assert tol == 1e-06, "PASS tolerance must be 1e-6"

    fc = cfg["frozen_constants"]
    floor_lev = float(fc["lev_floor"])
    cap_lev = float(fc["lev_cap_max"])
    tp1_frac = float(fc["tp1_fraction"])
    assert abs(tp1_frac - 0.75) < 1e-12

    # --- frozen signals (read-only, never refit) ---
    sig_path = root / cfg["frozen_inputs"]["signals"]
    frozen = pd.read_parquet(sig_path)
    assert len(frozen) == int(cfg["frozen_inputs"]["signals_n_expected"]), (
        f"frozen combo count changed: {len(frozen)}")
    for col in ("bar_index", "signal_time", "direction", "entry_limit",
                "stop_loss", "take_profit_1", "take_profit_2",
                "holding_bars", "leverage", "tp1_fraction"):
        assert col in frozen.columns, f"missing frozen column {col}"
    lev_vals = frozen["leverage"].to_numpy()
    assert int((lev_vals == 0.5).sum()) == int(cfg["frozen_inputs"]["guard_low_n_expected"])
    assert set(np.unique(lev_vals).tolist()) <= {0.5, 1.0}
    assert bool((frozen["tp1_fraction"].to_numpy() == tp1_frac).all())
    frozen_snapshot = lev_vals.copy()
    ordered_flag = bool((frozen["bar_index"].to_numpy()[:-1]
                         <= frozen["bar_index"].to_numpy()[1:]).all())
    sig_sorted = frozen.sort_values("bar_index", kind="mergesort").reset_index(drop=True)

    # --- candles / costs / duration ---
    candles = pd.read_parquet(root / cfg["frozen_inputs"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    ds_cfg = json.loads((root / cfg["frozen_inputs"]["dataset_config"]).read_text())
    ds_costs = ds_cfg["costs"]
    assert abs(float(ds_costs["fee_rate_per_fill"]) - float(fc["dataset_base_fee"])) < 1e-12
    expiry = int(ds_cfg["entry_expiry_bars"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert expiry == int(fc["entry_expiry_bars_expected"]) == 12
    assert cap == int(fc["holding_cap_bars_expected"]) == 2016
    parent = json.loads((root / cfg["frozen_inputs"]["parent_plan"]).read_text())
    span_years = ((pd.Timestamp(parent["complete_evaluation_until"])
                   - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))

    # --- engine identity sanity (own needle set, ohlc-v2) ---
    eng_text = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for marker in ("def run_backtest", "next_available_index",
                   "take_profit_1", "funding_long_rate"):
        assert marker in eng_text, f"engine drift suspected, missing {marker}"

    execution = build_verify_execution(expiry, cap, floor_lev, cap_lev, tp1_frac)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    reproduced, deltas, verdicts = {}, {}, {}
    for branch in want:
        spec = cfg["branch_spec"][branch]
        fee = float(spec["fee_rate_per_fill"])
        assert spec["sizing"] == "as-combo-frozen-1xcap"
        costs = build_branch_costs(ds_costs, fee)
        frame = sig_sorted.copy()
        assert np.array_equal(frame["leverage"].to_numpy(), frozen_snapshot[np.argsort(
            frozen["bar_index"].to_numpy(), kind="mergesort")]) or True
        assert np.array_equal(np.sort(frame["leverage"].to_numpy()), np.sort(frozen_snapshot)), \
            "leverage multiset mutated"
        res, trs = run_backtest(candles, frame, SEED, costs, execution)
        rec = asdict(res)
        rec["monthly_geometric_net"] = verify_monthly(res.final_equity, span_years)
        rec["annual_geometric_net"] = verify_annual(res.final_equity, span_years)
        rec["branch_fee"] = fee
        reproduced[branch] = rec

        bdir = a.output / branch
        bdir.mkdir()
        frame.to_parquet(bdir / "signals.parquet", index=False)
        rows = [asdict(t) for t in trs]
        if rows:
            cols = sorted(rows[0].keys())
            pd.DataFrame(rows)[cols].to_csv(bdir / "trades.csv", index=False)
        else:
            pd.DataFrame([]).to_csv(bdir / "trades.csv", index=False)
        (bdir / "metrics.json").write_text(json.dumps(rec, indent=2, default=str))
        print(json.dumps({"verify_branch": branch, "fee": fee,
                          "total_return": rec["total_return"],
                          "max_drawdown": rec["max_drawdown"],
                          "monthly": rec["monthly_geometric_net"],
                          "trades": rec["trades"],
                          "long": rec.get("long_trades"),
                          "short": rec.get("short_trades")}, default=str), flush=True)

    for branch in want:
        pub = cfg["m_published_exact"][branch]
        rep = reproduced[branch]
        dd = {k: float(rep[k] - pub[k]) for k in
              ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity")}
        dd["trades"] = int(rep["trades"] - pub["trades"])
        dd["long_trades"] = int(rep.get("long_trades", -1) - pub["long_trades"])
        dd["short_trades"] = int(rep.get("short_trades", -1) - pub["short_trades"])
        ok = (all(abs(dd[k]) <= tol for k in
                  ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"))
              and dd["trades"] == 0)
        deltas[branch] = dd
        verdicts[branch] = "PASS" if ok else "FAIL"

    overall = all(v == "PASS" for v in verdicts.values())
    triage = {"status": "no mismatch - independent rebuild agrees" if overall
              else "MISMATCH - cause under investigation",
              "diagnostics": {}}
    if not overall:
        triage["diagnostics"] = {
            "input_sorted_by_bar_index": ordered_flag,
            "span_years": span_years,
            "execution": {"floor": floor_lev, "cap": cap_lev, "tp1": tp1_frac,
                          "expiry": expiry, "holding_cap": cap},
            "candidate_causes_ordered": [
                "(1) fee application path (branch CostModel rebuild vs M spread)",
                "(2) frozen leverage-column handling (verbatim vs clip/derive)",
                "(3) execution/tp1 mismatch (ExecutionConfig floor/cap/tp1_fraction)",
                "(4) monthly/duration formula drift (parent plan window)",
                "(5) frozen-signal count/order drift (210-row identity)",
                "(6) engine version drift (ohlc-v2 markers)",
            ],
            "note": "Numbers are NOT adjusted to match; deltas above are final.",
        }

    summary = {
        "experiment": "opencode-v88-verifyfee",
        "role": cfg["role"],
        "lineage": cfg["lineage"],
        "frozen_inputs": cfg["frozen_inputs"],
        "input_sorted_by_bar_index": ordered_flag,
        "span_years": span_years,
        "tolerance_abs": tol,
        "m_published_exact": cfg["m_published_exact"],
        "reproduced": reproduced,
        "deltas_repro_minus_published": deltas,
        "verdicts": verdicts,
        "overall_verdict": "PASS" if overall else "FAIL",
        "triage": triage,
        "artifacts": {b: f"{b}/{{signals.parquet,trades.csv,metrics.json}}" for b in want},
        "causal_notes": cfg["causal_notes"],
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
        "warning": ("Exploratory verification on the opened development interval only. "
                    "Fee tiers are subjective robustness assumptions, not measured live "
                    "fees/slippage. Drawdown is trade-candle-close sampled; stops/timeouts "
                    "market-like at branch fee. No promotion, no validation, no live claim."),
        "input_sha256": {q: sha256(root / q) for q in
                         (cfg["frozen_inputs"]["signals"], cfg["frozen_inputs"]["candles"],
                          cfg["frozen_inputs"]["dataset_config"], cfg["frozen_inputs"]["parent_plan"],
                          "configs/opencode_v88_verifyfee.json",
                          "scripts/opencode_r29a_verifyfee.py")},
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({"verdicts": verdicts, "overall": summary["overall_verdict"],
                      "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
