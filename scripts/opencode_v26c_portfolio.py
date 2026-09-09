"""Opencode A2-ARCH (v26c): portfolio LOCAL tu cloud v26b (da verify parity 3.4e-15).

Doc audit.json (phai passed) + cloud full/summary.json + signals.parquet cloud.
Ghi artifacts/research/opencode_v26c_replay/portfolio.json (moi, khong ghi de).
Monthly geometric tu configs/swing_v15_continuous_folds.json (duration 2.809y).
Gate: 5%/mo, DD 20%, 30 fills. Standing best: majority_1x 2.935%,
confirmed_dd_guard 2.79% DD-safe.
"""
import torch  # noqa: F401
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from train_tcn_kaggle import write_json  # noqa: E402

PLAN_PATH = ROOT / "configs/opencode_v26_multitask.json"
PARENT_PATH = ROOT / "configs/swing_v15_continuous_folds.json"
SOURCE = ROOT / "artifacts/kaggle/a2_v26b_download/multitask-training"
FULL = SOURCE / "full"
OUT_DIR = ROOT / "artifacts/research/opencode_v26c_replay"


def main():
    audit = json.loads((OUT_DIR / "audit.json").read_text(encoding="utf-8"))
    if audit.get("state") != "passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Replay audit chua PASS: chan portfolio")
    if audit.get("source_summary_sha256") != sha256(SOURCE / "summary.json"):
        raise ValueError("Audit thuoc ve training export khac")
    out_file = OUT_DIR / "portfolio.json"
    if out_file.exists():
        raise FileExistsError("Khong ghi de portfolio cu")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    cloud = json.loads((FULL / "summary.json").read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ROOT / plan["decisions"])
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    if abs(years - float(cloud["duration_years"])) > 1e-9:
        raise ValueError("Duration years khac cloud")
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30,
            "scenarios": ["normal", "fee_stress", "execution_stress"]}
    part = decisions[(decisions.signal_time >= pd.Timestamp("2023-06-01T00:00:00Z"))]
    months = pd.period_range(part.signal_time.iloc[0].tz_localize(None),
                             part.signal_time.iloc[-1].tz_localize(None), freq="M")
    branches = {}
    for name in ("mt_p10gate_1x", "mt_p10gate_dd_guard",
                 "mt_p50gate_1x", "mt_p50gate_dd_guard"):
        scen = cloud["branches"][name]
        sig = pd.read_parquet(FULL / name / "signals.parquet")
        if len(sig) != audit["signals"][name]:
            raise ValueError(f"Portfolio signals khac audit parity: {name}")
        counts = sig.signal_time.dt.strftime("%Y-%m").value_counts() if len(sig) else {}
        branches[name] = {
            "scenarios": scen,
            "n_signals": int(len(sig)),
            "n_decisions": 4076,
            "coverage": float(len(sig) / 4076),
            "signals_by_month": {str(m): int(counts.get(str(m), 0)) for m in months},
            "passes_gate_all_scenarios": bool(all(
                scen[s]["monthly_geometric_net"] >= gate["monthly_min"]
                and scen[s]["max_drawdown"] >= -gate["dd_max"]
                and scen[s]["trades"] >= gate["fills_min"]
                for s in gate["scenarios"])),
            "dd_safe_all_scenarios": bool(all(
                scen[s]["max_drawdown"] >= -gate["dd_max"] for s in gate["scenarios"])),
        }
        print(json.dumps({"branch": name,
                          "gate": branches[name]["passes_gate_all_scenarios"],
                          "metrics": {s: {k: scen[s][k] for k in
                                          ("total_return", "max_drawdown", "trades",
                                           "monthly_geometric_net", "gross_pnl",
                                           "fees", "funding", "profit_factor", "win_rate")}
                                      for s in gate["scenarios"]}}), flush=True)
    report = {"experiment": "opencode-v26b-cpufix-audit",
              "prespec_note": "pre-spec = configs/opencode_v26_multitask.json (branches mt_p10gate/mt_p50gate x {1x,dd_guard}; policy + costs + FillStress)",
              "policy_spec": {"mt_p10gate": plan["policy_branches"]["mt_p10gate"],
                              "mt_p50gate": plan["policy_branches"]["mt_p50gate"],
                              "frequency": "cooldown 5d + max 4/thang (dataset cfg, giong driver)",
                              "geometry": plan["backtest"]["geometry"],
                              "execution": plan["backtest"]["execution"]},
              "branches": branches,
              "duration_years": years,
              "gate": gate,
              "standing_best": {"majority_1x": "2.935%/mo (DD breach)",
                                "confirmed_dd_guard": "2.79/2.67/2.06 DD-safe all scenarios"},
              "comparison": ("So truc tiep voi standing_best va gate: "
                             "KHONG nhanh nao pass gate; p50gate_dd_guard gan nhat ve return "
                             "nhung DD breach; p10gate DD-safe nhung fills rot + am."),
              "diagnostic": {"facing_OOS_mean": cloud["facing_OOS_mean"],
                             "note": "dir_acc 37.5% (~chance 3-class), pinball 0.0081; p10gate chi 4 signals/3 fills WR 0% (cong chat cat het); p50gate 111 signals/88 fills WR 36% PF~1.05-1.13 (edge yeu, DD breach)."},
              "formulas": {"fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": "own-branch 1x equity, trigger 10%, lev 0.5/1.0 past-only + execution lev 0.25/1.0 (driver v26)",
                           "monthly_geometric": "tu configs/swing_v15_continuous_folds.json (2023-06-01..2026-03-23)",
                           "frequency": "cooldown 5d + monthly cap 4, giong driver dong bang"},
              "replay": {"max_replay_error": audit["max_replay_error"],
                         "parity": "local signals+backtest identical cloud (error 3.4e-15)",
                         "source": "du bao CLOUD (oos_prob/quantile), khong refit"},
              "audit_sha256": sha256(OUT_DIR / "audit.json"),
              "training_summary_sha256": sha256(SOURCE / "summary.json"),
              "full_summary_sha256": sha256(FULL / "summary.json"),
              "plan_sha256": sha256(PLAN_PATH),
              "independent_test": False, "exploratory": True, "live_approved": False,
              "warning": ("Opened development interval only (2023-2026). Drawdown close-sampled; "
                          "stop/timeout market-like. KHONG live approval. "
                          "fee_stress_trades.csv empty by-design (driver chi luu metrics fee).")}
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(out_file))


if __name__ == "__main__":
    main()
