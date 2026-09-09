"""Opencode v36 (R9-N): capital scale-up on FROZEN v15 majority_1x signals.

Tiep noi N-volcap v32 (mien nhiem o indexed-100). Cau hoi: bot von lon co sao khong?
TAI DUNG truc tiep logic volcap tu scripts/opencode_r8n_volcap.py:
  from opencode_r8n_volcap import run_volcap_backtest, TRADE_COLUMNS
  (khong duplicate/sua logic entry-search; chi driver vong von + monthly theo initial).
Pre-specified matrix (fixed in configs/opencode_v36_volscale.json BEFORE running):
  initial_equity {100, 10_000, 1_000_000} x k {0.05, 0.01} = 6 nh matches volscale
  + control cap100_k100 (von 100, k=1.0 bypass) = 7 branches x 2 scenarios
  (normal, fee_stress 0.00055) = 14 evaluations. NO exec-stress (volcap IS the stress).
Fixed 1x baseline; engine compounding theo von (notional=equity*1x) — day chinh la thu can do.
Monthly geometric theo parent_plan swing_v15_continuous_folds.json, ratio=final/initial_cua_branch.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
k subjective stress, NOT measured liquidity/queue. Full-bar volume mild intrabar look-ahead.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opencode_r8n_volcap import run_volcap_backtest, TRADE_COLUMNS  # noqa: E402  (verbatim reuse v32)

import agentic_alpha_lab.backtest.engine as eng
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.data.training import sha256


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == ["cap100_k100", "cap100_k05", "cap100_k01",
                                     "cap10k_k05", "cap10k_k01",
                                     "cap1M_k05", "cap1M_k01"], "branches must be pre-specified 7-branch volscale matrix"
    assert list(cfg["k_levels"]) == [1.0, 0.05, 0.01]
    assert list(cfg["capitals"]) == [100, 10000, 1000000]
    assert cfg["branch_specs"]["cap100_k100"] == {"base": "majority_1x", "initial_equity": 100, "k": 1.0}
    assert cfg["branch_specs"]["cap100_k05"] == {"base": "majority_1x", "initial_equity": 100, "k": 0.05}
    assert cfg["branch_specs"]["cap100_k01"] == {"base": "majority_1x", "initial_equity": 100, "k": 0.01}
    assert cfg["branch_specs"]["cap10k_k05"] == {"base": "majority_1x", "initial_equity": 10000, "k": 0.05}
    assert cfg["branch_specs"]["cap10k_k01"] == {"base": "majority_1x", "initial_equity": 10000, "k": 0.01}
    assert cfg["branch_specs"]["cap1M_k05"] == {"base": "majority_1x", "initial_equity": 1000000, "k": 0.05}
    assert cfg["branch_specs"]["cap1M_k01"] == {"base": "majority_1x", "initial_equity": 1000000, "k": 0.01}
    assert list(cfg["scenarios"]) == ["normal", "fee_stress"]
    assert cfg["seed_base"] == 1729
    assert cfg["volume_column"] == "volume"
    assert abs(float(cfg["fee_stress_rate"]) - 0.00055) < 1e-12
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    r8n_src = (root / "scripts/opencode_r8n_volcap.py").read_text()
    for needle in ("def run_volcap_backtest", "cap = float(k) * vol", "qty <= cap"):
        assert needle in r8n_src, f"volcap reuse check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
    assert cfg["volume_column"] in candles.columns, "volume column missing in candles"
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    base_sigs = {}
    for base, rel in cfg["bases"].items():
        df = pd.read_parquet(root / rel).sort_values("bar_index").reset_index(drop=True)
        assert len(df) == 94, f"frozen {base} count changed: {len(df)}"
        for col in ("bar_index", "direction", "entry_limit", "stop_loss",
                    "take_profit_1", "take_profit_2", "holding_bars"):
            assert col in df.columns, f"{base} missing {col}"
        base_sigs[base] = df
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": float(cfg["fee_stress_rate"])})
    cap = int(max(ds_cfg["holding_days"]) * 288)
    execution = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                                max_holding_bars=cap, leverage=1.0, max_leverage=1.0,
                                tp1_fraction=0.5)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def with_geo(result, initial):
        d = asdict(result)
        ratio = result.final_equity / float(initial)
        d["annual_geometric_net"] = float(ratio ** (1 / duration) - 1)
        d["monthly_geometric_net"] = float(ratio ** (1 / (12 * duration)) - 1)
        return d

    # ---- CONTROL: cap100_k100 must reproduce published majority_1x ----
    sig0 = base_sigs["majority_1x"]
    res_n0, tr_n0, _, stats0 = run_volcap_backtest(
        candles, sig0, 1.0, cfg["volume_column"], 100.0, costs, execution)
    ref = cfg["control_reference"]
    match = bool(abs(res_n0.total_return - ref["total_return"]) < 1e-9
                 and abs(res_n0.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_n0.trades == ref["trades"])
    print(json.dumps({"control_check": {"reproduced": {"total_return": res_n0.total_return,
                                                       "max_drawdown": res_n0.max_drawdown,
                                                       "trades": res_n0.trades},
                                        "reference": ref, "match": match,
                                        "volcap_stats": stats0}}), flush=True)
    if not match:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_n0), "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; cap100_k100 != +165.18%/-20.09%/63", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        base = spec["base"]
        k = float(spec["k"])
        initial = float(spec["initial_equity"])
        sig = base_sigs[base]
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = {}
        diag_by_scenario = {}
        for label, cm in (("normal", costs), ("fee_stress", fee_costs)):
            res, trs, diag, stats = run_volcap_backtest(
                candles, sig, k, cfg["volume_column"], initial, cm, execution)
            d = with_geo(res, initial)
            try:
                m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
                dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
                f_ok = bool(d["trades"] >= gate["fills_min"])
            except (KeyError, TypeError):
                m_ok = dd_ok = f_ok = False
            d["gate"] = {"monthly_geometric_net_ge_5pct": m_ok,
                         "drawdown_within_20pct": dd_ok, "fills_ge_30": f_ok,
                         "pass_all": bool(m_ok and dd_ok and f_ok)}
            d["volcap"] = {"k": k, "initial_equity": initial,
                           "volume_column": cfg["volume_column"], **stats}
            scenarios[label] = d
            rows = [asdict(t) for t in trs]
            if rows:
                pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            else:
                pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
            diag.to_csv(bdir / f"{label}_volcap_diag.csv", index=False)
            diag_by_scenario[label] = stats
        results[branch] = {"base": base, "k": k, "initial_equity": initial,
                           "n_signals": int(len(sig)), "scenarios": scenarios,
                           "seeds": {"seed_base": int(cfg["seed_base"]),
                                     "rng": "none (deterministic volcap; seed recorded for ordering reproducibility)"},
                           "volcap_stats": diag_by_scenario}
        print(json.dumps({"branch": branch, "base": base, "k": k, "initial_equity": initial,
                          "volcap_stats": diag_by_scenario,
                          "metrics": {s: {kk: scenarios[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress")},
                          "gate": {s: scenarios[s]["gate"] for s in ("normal", "fee_stress")}},
                         default=str), flush=True)
    report = {"branches": results, "config": cfg,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_n0.total_return,
                                               "max_drawdown": res_n0.max_drawdown,
                                               "trades": res_n0.trades},
                                "match": True},
              "formulas": {"volcap": cfg["volcap_formula"],
                           "reuse": cfg["reuse_note"],
                           "rng_scheme": cfg["rng_scheme"],
                           "monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "scenarios": "normal + fee_stress only (no exec-stress; volcap IS the stress)"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "k is a subjective stress assumption, NOT measured liquidity or queue position from OHLC. "
                          "Full-bar volume is known only after bar close (mild intrabar look-ahead), applied uniformly. "
                          "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
                          "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
                          "Compounding from current equity: capital scale is exactly what is measured; "
                          "do NOT extrapolate beyond tested capitals/k. "
                          "Do not promote any branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["majority_1x"],
                                "configs/opencode_v36_volscale.json",
                                "scripts/opencode_r9n_volscale.py",
                                "scripts/opencode_r8n_volcap.py")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
