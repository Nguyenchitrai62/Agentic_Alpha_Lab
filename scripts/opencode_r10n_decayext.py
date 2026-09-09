"""Opencode v40 (R10-N): alpha-decay EXTENSION on FROZEN v15 majority_1x signals.

TIEP NOI v37 (N-decay, edge song toi d6): TAI SU DUNG TRUC TIEP latency driver tu
  scripts/opencode_r8n_latency.py — import run_latency_backtest
  (co che first_entry_bar = signal_index + delay, giu expiry length 12 bars,
  holding dem tu entry thuc te). File nay KHONG copy-paste logic engine;
  chi tham so hoa entry_delay theo ma tran decayext va viet summary/gate/sha256.
  Xem latency_driver_source.py trong output (luu kem ca file nay + file v33 duoc import).

Frozen input (never refit):
  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
Pre-specified matrix (fixed in configs/opencode_v40_decayext.json BEFORE running):
  branches {majority_d1 (control, delay=1), majority_d12, majority_d24,
            majority_d48} x scenario_plan:
    d1,d24 -> {normal}; d12,d48 -> {normal, fee_stress 0.00055} = 6 scenario-cells.
  Fixed 1x baseline. Monthly geometric theo
  configs/swing_v15_continuous_folds.json.
Control gate: majority_d1 normal must reproduce published majority_1x
  (+165.17829563633% total_return, -20.09% max_drawdown, 63 trades) or STOP.
Edge-death definition (normal): Ret<0 OR PF<1 OR fills<30.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import agentic_alpha_lab.backtest.engine as eng
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.data.training import sha256

# ---- REUSE v33 latency driver (ghi ro nguon) ----
_SCRIPT_DIR = Path(__file__).resolve().parent
_R8N_PATH = _SCRIPT_DIR / "opencode_r8n_latency.py"
_spec = importlib.util.spec_from_file_location("opencode_r8n_latency", _R8N_PATH)
_r8n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_r8n)
run_latency_backtest = _r8n.run_latency_backtest
TRADE_COLUMNS = list(_r8n.TRADE_COLUMNS)

EXPECTED_BRANCHES = ["majority_d1", "majority_d12", "majority_d24",
                     "majority_d48"]
EXPECTED_DELAYS = {"majority_d1": 1, "majority_d12": 12,
                   "majority_d24": 24, "majority_d48": 48}
EXPECTED_PLAN = {"majority_d1": ["normal"],
                 "majority_d12": ["normal", "fee_stress"],
                 "majority_d24": ["normal"],
                 "majority_d48": ["normal", "fee_stress"]}


def edge_death_flags(normal_dict):
    """Edge chet neu Ret<0 HOAC PF<1 HOAC fills<30 (tren normal)."""
    ret = normal_dict.get("total_return")
    pf = normal_dict.get("profit_factor")
    fills = normal_dict.get("trades")
    ret_dead = bool(ret is not None and ret < 0)
    pf_dead = bool(pf is not None and pf < 1.0)
    fills_dead = bool(fills is not None and fills < 30)
    return {"ret_lt_0": ret_dead, "pf_lt_1": pf_dead, "fills_lt_30": fills_dead,
            "edge_dead_any": bool(ret_dead or pf_dead or fills_dead)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    assert list(cfg["branches"]) == EXPECTED_BRANCHES, "branches must be pre-specified 4-delay matrix"
    for b, k in EXPECTED_DELAYS.items():
        assert cfg["branch_specs"][b] == {"base": "majority_1x", "entry_delay": k}, f"spec mismatch {b}"
    assert list(cfg["scenarios"]) == ["normal", "fee_stress"]
    for b, plan in EXPECTED_PLAN.items():
        assert cfg["scenario_plan"][b] == plan, f"plan mismatch {b}"
    assert int(cfg["scenario_cells"]) == 6, "must be 6 scenario-cells"
    root = Path(__file__).resolve().parents[1]
    eng_src = (root / "src/agentic_alpha_lab/backtest/engine.py").read_text()
    for needle in ("def run_backtest", "def _entry_fill", "stop_first",
                   "float(signal.stop_loss)", "float(signal.take_profit_1)"):
        assert needle in eng_src, f"engine insertion check failed: {needle}"
    r8n_src = _R8N_PATH.read_text()
    for needle in ("def run_latency_backtest",
                   "first_entry_bar = signal_index + int(entry_delay)",
                   "last_entry_bar = min(signal_index + execution.entry_expiry_bars"):
        assert needle in r8n_src, f"v33 driver insertion check failed: {needle}"
    candles = pd.read_parquet(root / cfg["candles"]).sort_values("open_time").reset_index(drop=True)
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
    (a.output / "latency_driver_source.py").write_text(r8n_src)

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

    # ---- CONTROL: majority_d1 must reproduce published majority_1x ----
    sig0 = base_sigs["majority_1x"]
    res_n0, tr_n0 = run_latency_backtest(candles, sig0, 1, 100.0, costs, execution)
    eng_res, _ = eng.run_backtest(candles, sig0, 100.0, costs, execution)
    ref = cfg["control_reference"]
    match = bool(abs(res_n0.total_return - ref["total_return"]) < 1e-9
                 and abs(res_n0.max_drawdown - ref["max_drawdown"]) < 1e-9
                 and res_n0.trades == ref["trades"])
    identical = bool(abs(res_n0.total_return - eng_res.total_return) < 1e-12
                     and abs(res_n0.max_drawdown - eng_res.max_drawdown) < 1e-12
                     and res_n0.trades == eng_res.trades)
    print(json.dumps({"control_check": {
        "reproduced": {"total_return": res_n0.total_return,
                       "max_drawdown": res_n0.max_drawdown, "trades": res_n0.trades},
        "engine_crosscheck": {"total_return": eng_res.total_return,
                              "max_drawdown": eng_res.max_drawdown, "trades": eng_res.trades,
                              "bit_identical": identical},
        "reference": ref, "match": match}}), flush=True)
    if not (match and identical):
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"reproduced": asdict(res_n0), "engine": asdict(eng_res),
             "reference": ref}, indent=2, default=str))
        print("CONTROL MISMATCH: STOP; majority_d1 != +165.18%/-20.09%/63", flush=True)
        sys.exit(1)

    results = {}
    for branch in cfg["branches"]:
        spec = cfg["branch_specs"][branch]
        sig = base_sigs[spec["base"]]
        delay = int(spec["entry_delay"])
        plan = list(cfg["scenario_plan"][branch])
        bdir = a.output / branch
        bdir.mkdir()
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = {}
        cache = {}
        if "normal" in plan:
            cache["normal"] = run_latency_backtest(candles, sig, delay, 100.0, costs, execution)
        if "fee_stress" in plan:
            cache["fee_stress"] = run_latency_backtest(candles, sig, delay, 100.0, fee_costs, execution)
        for label in plan:
            res, trs = cache[label][0], cache[label][1]
            d = with_geo(res)
            d["gate"] = gate_flags(d)
            scenarios[label] = d
            rows = [asdict(t) for t in trs]
            pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
                bdir / f"{label}_trades.csv", index=False)
        results[branch] = {"base": spec["base"], "entry_delay": delay,
                           "n_signals": int(len(sig)), "scenarios_run": plan,
                           "scenarios": scenarios}
        print(json.dumps({"branch": branch, "base": spec["base"], "entry_delay": delay,
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in plan},
                          "gate": {s: scenarios[s]["gate"] for s in plan}},
                         default=str), flush=True)

    # decay curve: normal Ret/Mo vs delay 1->48 + fee at d12/d48 + death flags
    decay_normal = {}
    for branch in cfg["branches"]:
        s = results[branch]["scenarios"]["normal"]
        decay_normal[branch] = {
            "entry_delay": results[branch]["entry_delay"],
            "total_return": s["total_return"], "monthly_geometric_net": s["monthly_geometric_net"],
            "max_drawdown": s["max_drawdown"], "trades": s["trades"],
            "profit_factor": s["profit_factor"], "win_rate": s["win_rate"],
            "gross_pnl": s["gross_pnl"], "fees": s["fees"], "funding": s["funding"],
            "gate": s["gate"], "edge_death": edge_death_flags(s)}
    fee_table = {}
    for branch in ("majority_d12", "majority_d48"):
        fee_table[branch] = {s: {k: results[branch]["scenarios"][s][k] for k in
                            ["total_return", "monthly_geometric_net", "max_drawdown",
                             "trades", "profit_factor", "win_rate"]}
                        for s in ("normal", "fee_stress")}
        fee_table[branch]["gate"] = {s: results[branch]["scenarios"][s]["gate"] for s in
                                ("normal", "fee_stress")}

    report = {"branches": results, "config": cfg,
              "decay_normal": decay_normal, "fee_d12_d48": fee_table,
              "control_check": {"reference": ref,
                                "reproduced": {"total_return": res_n0.total_return,
                                               "max_drawdown": res_n0.max_drawdown,
                                               "trades": res_n0.trades},
                                "engine_bit_identical": identical, "match": True},
              "formulas": {"entry_window": cfg["entry_window"],
                           "monthly_geometric_net": cfg["monthly_formula"],
                           "engine": cfg["engine_note"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "edge_death": "Ret<0 OR PF<1 OR fills<30 on normal"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened 2023-2026 development interval only. "
                          "Entry delay is a subjective latency stress assumption, NOT measured "
                          "live latency. Drawdown is trade-candle-close sampled, not true "
                          "mark-price/intrabar drawdown. Stop/timeout exits are market-like at "
                          "the scenario fee, not guaranteed maker fills. Do not promote any "
                          "branch or claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["dataset_config"], cfg["parent_plan"],
                                cfg["bases"]["majority_1x"],
                                "configs/opencode_v40_decayext.json",
                                "scripts/opencode_r8n_latency.py",
                                "scripts/opencode_r10n_decayext.py")},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
