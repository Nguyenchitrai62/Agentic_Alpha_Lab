"""Opencode A2-ARCH (v26c): audit LOCAL cho v26b-cpufix COMPLETE (KHONG train/cloud/live).

Nguon: artifacts/kaggle/a2_v26b_download/multitask-training
  (kernel nguynchtrai/opencode-tracka2-multitask-v26b-cpufix, COMPLETE,
   worker_exit_code 0, CPU-fallback P100->CPU, FULL-34folds).
Plan dong bang: configs/opencode_v26_multitask.json (multitask MLP 44->64->32,
  heads direction+quantile+excursion, policy p10gate/p50gate x {1x,dd_guard}).

(1) Verify: summary state/exit-codes, runtime cpu-fallback, plan JSON-equality +
    plan-SHA vs local, bundle-hashes 52/52 byte-match, input SHAs, predictions
    count/shapes/finite (oos_prob/quantile (4076,3), excursion (4076,2)),
    signals.parquet counts, missing/empty (fee trades CSV empty by-design vi
    driver chi luu metrics fee, khong luu trades; normal/execution co trades).
(2) Replay parity: gen_signals LOCAL tu cloud P/Q (import tu driver dong bang)
    + run_backtest/run_stress LOCAL 4 branches x 3 scenarios
    (normal, fee 0.00055, FillStress(5,5,5,0.00055,False)); so voi cloud
    summary.json; max abs error tren final_equity/monthly/DD (muc tieu ~1e-6).
    Ghi artifacts/research/opencode_v26c_replay/audit.json.
(3) Portfolio: ket qua replay local (da verify parity) + monthly geometric tu
    configs/swing_v15_continuous_folds.json + gate + standing_best.
    Ghi portfolio.json. Dung du bao CLOUD (da verify).

Labels exploratory, causal past-only, development interval only.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
from opencode_r7a2_multitask_train import (  # noqa: E402
    BARS_PER_DAY,
    dd_guard_leverage,
    gen_signals,
)
from train_tcn_kaggle import write_json  # noqa: E402

PLAN_PATH = ROOT / "configs/opencode_v26_multitask.json"
PARENT_PATH = ROOT / "configs/swing_v15_continuous_folds.json"
SOURCE = ROOT / "artifacts/kaggle/a2_v26b_download/multitask-training"
FULL = SOURCE / "full"
OUT_DIR = ROOT / "artifacts/research/opencode_v26c_replay"
BRANCHES = ("mt_p10gate", "mt_p50gate")
SIZINGS = ("1x", "dd_guard")
SCENARIOS = ("normal", "fee_stress", "execution_stress")
METRICS = ("final_equity", "total_return", "max_drawdown", "trades",
           "monthly_geometric_net", "annual_geometric_net", "gross_pnl",
           "fees", "funding", "profit_factor", "win_rate")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    torch.set_num_threads(2)
    if OUT_DIR.exists():
        raise FileExistsError("Khong ghi de audit cu; dung dir moi")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_PATH.read_text(encoding="utf-8"))
    outer = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    runtime = json.loads((SOURCE / "runtime.json").read_text(encoding="utf-8"))
    cloud = json.loads((FULL / "summary.json").read_text(encoding="utf-8"))
    cloud_plan = json.loads((SOURCE / "plan.json").read_text(encoding="utf-8"))

    # --- exit-codes / state ---
    if outer.get("state") != "complete" or outer.get("worker_exit_code") != 0:
        raise ValueError("Outer summary khong complete/exit-0")
    if cloud.get("mode") != "FULL-34folds" or cloud.get("experiment") != "opencode-v26-multitask":
        raise ValueError("Cloud mode/experiment mismatch")
    if runtime.get("compute_mode") != "cpu-fallback":
        raise ValueError("CPU-fallback fix khong kich hoat")
    if "P100" not in json.dumps(runtime.get("gpus", [])):
        raise ValueError("Runtime GPU khong phai P100 nhu ky vong fix")

    # --- plan-SHA / JSON equality ---
    if cloud_plan != plan:
        raise ValueError("Export plan differs from registered plan (JSON)")
    plan_sha_local = sha256(PLAN_PATH)
    plan_sha_cloud = sha256(SOURCE / "plan.json")
    if plan_sha_local != plan_sha_cloud:
        raise ValueError("Plan SHA mismatch")
    if plan_sha_local != "e1c34fb7d83d2b45596fea5fab4ed86f5d27b356101e21208130e182b833ce61":
        raise ValueError("Plan SHA khac manifest luc submit")

    # --- bundle 52/52 ---
    bundle = json.loads((SOURCE / "bundle-hashes.json").read_text(encoding="utf-8"))
    if len(bundle) != 52:
        raise ValueError("Bundle entries khac 52")
    bundle_check = {}
    for name, expected in bundle.items():
        local = ROOT / name
        if sha256(local) != expected:
            raise ValueError(f"Bundle identity mismatch: {name}")
        bundle_check[name] = "byte_match"

    # --- inputs ---
    ds_cfg = json.loads((ROOT / plan["dataset_config"]).read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ROOT / plan["decisions"])
    candles = pd.read_parquet(ROOT / plan["candles"])
    key_to_cfg = {"decisions": "decisions", "candles": "candles",
                  "dataset_config": "dataset_config", "parent_plan": "parent_plan",
                  "examples": "examples"}
    for key in ("decisions", "candles", "dataset_config", "parent_plan", "examples"):
        got = cloud["input_sha256"][key]
        want = sha256(ROOT / plan[key_to_cfg[key]])
        if got != want:
            raise ValueError(f"Input SHA mismatch: {key}")

    # --- predictions count/shapes/finite ---
    P = np.load(FULL / "oos_prob.npy", allow_pickle=False)
    Q = np.load(FULL / "oos_quantile.npy", allow_pickle=False)
    E = np.load(FULL / "oos_excursion.npy", allow_pickle=False)
    if P.shape != (4076, 3) or Q.shape != (4076, 3) or E.shape != (4076, 2):
        raise ValueError(f"Prediction shapes unexpected: {P.shape} {Q.shape} {E.shape}")
    if not (np.isfinite(P).all() and np.isfinite(Q).all() and np.isfinite(E).all()):
        raise ValueError("Predictions non-finite")
    if np.isnan(P).any() or np.isnan(Q).any() or np.isnan(E).any():
        raise ValueError("Predictions contain NaN")
    # prob rows sum ~1
    np.testing.assert_allclose(P.sum(1), np.ones(len(P)), rtol=1e-5, atol=1e-6)
    # quantile crossing: heads doc lap (khong rang buoc) -> do crossing rate, khong fail
    cross_rate = float((((Q[:, 0] > Q[:, 1]) | (Q[:, 1] > Q[:, 2])).mean()))
    if not bool((E >= 0).all()):
        raise ValueError("Excursion negative (softplus violated)")

    # --- missing/empty checks ---
    n_folds = len(cloud["folds"])
    if n_folds != 34:
        raise ValueError("Folds khac 34")
    eval_sum = int(sum(f["eval_decisions"] for f in cloud["folds"]))
    if eval_sum != 4076:
        raise ValueError("Eval decisions sum khac 4076")
    signals_info = {}
    for branch in BRANCHES:
        for sizing in SIZINGS:
            name = f"{branch}_{sizing}"
            sig = pd.read_parquet(FULL / name / "signals.parquet")
            signals_info[name] = int(len(sig))
            if len(sig) == 0:
                raise ValueError(f"Signals empty: {name}")
    # fee trades CSV empty by-design (driver run_branch luu fee items=None)
    for branch in BRANCHES:
        for sizing in SIZINGS:
            name = f"{branch}_{sizing}"
            fee_csv = FULL / name / "fee_stress_trades.csv"
            if fee_csv.stat().st_size != 1:
                raise ValueError(f"Fee CSV unexpected size (expected 1 by-design): {name}")
            for scen in ("normal", "execution_stress"):
                p = FULL / name / f"{scen}_trades.csv"
                if p.stat().st_size == 0:
                    raise ValueError(f"Trades CSV missing/empty: {name}/{scen}")

    # --- replay parity ---
    months = pd.date_range("2023-06-01", "2026-03-01", freq="MS", tz="UTC")
    oos_mask = (decisions.signal_time >= months[0]).to_numpy()
    part = decisions[oos_mask].reset_index(drop=True)
    if len(part) != 4076:
        raise ValueError("OOS partition khac 4076")
    years = ((pd.Timestamp(parent["complete_evaluation_until"])
              - pd.Timestamp(parent["folds"][0][0])).total_seconds() / (365.2425 * 86400))
    costs = CostModel(**ds_cfg["costs"])
    cap = int(max(ds_cfg["holding_days"]) * BARS_PER_DAY)
    OUT_DIR.mkdir(parents=True)
    max_err = 0.0
    replay = {}
    for branch in BRANCHES:
        sig_base = gen_signals(part, P, Q, branch, plan, ds_cfg)
        # signals parity vs cloud (so cot geometry + direction; leverage rieng dd_guard)
        for sizing in SIZINGS:
            name = f"{branch}_{sizing}"
            cloud_sig = pd.read_parquet(FULL / name / "signals.parquet")
            if len(sig_base) != len(cloud_sig):
                raise ValueError(f"Signal count differs {name}: {len(sig_base)} vs {len(cloud_sig)}")
            cols = ["bar_index", "direction", "entry_limit", "stop_loss",
                    "take_profit_1", "take_profit_2", "holding_bars"]
            pd.testing.assert_frame_equal(
                sig_base[cols].reset_index(drop=True),
                cloud_sig[cols].reset_index(drop=True),
                check_exact=False, rtol=1e-6, atol=1e-9)
        ref_trades = []
        for sizing in SIZINGS:
            name = f"{branch}_{sizing}"
            if sizing == "1x":
                sig = sig_base.drop(columns=["leverage"], errors="ignore")
                execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                            max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
            else:
                execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                            max_holding_bars=cap, leverage=0.25, max_leverage=1.0)
                sig = sig_base.copy()
                sig["leverage"] = dd_guard_leverage(sig_base, ref_trades) if len(sig_base) else np.array([], dtype=float)
                cloud_sig = pd.read_parquet(FULL / name / "signals.parquet")
                np.testing.assert_allclose(sig["leverage"].to_numpy(float),
                                           cloud_sig["leverage"].to_numpy(float),
                                           rtol=1e-9, atol=1e-12)
            fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
            normal, trades = run_backtest(candles, sig, 100, costs, execution)
            fee, _ = run_backtest(candles, sig, 100, fee_costs, execution)
            stress, _, _ = run_stress(candles, sig, 100, costs, execution,
                                      FillStress(5, 5, 5, 0.00055, False))
            if sizing == "1x":
                ref_trades = trades
            local = {"normal": normal, "fee_stress": fee, "execution_stress": stress}
            replay[name] = {}
            for scen in SCENARIOS:
                res = local[scen]
                ratio = res.final_equity / 100
                got = {"final_equity": float(res.final_equity),
                       "total_return": float(res.total_return),
                       "max_drawdown": float(res.max_drawdown),
                       "trades": int(res.trades),
                       "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1),
                       "annual_geometric_net": float(ratio ** (1 / years) - 1),
                       "gross_pnl": float(res.gross_pnl),
                       "fees": float(res.fees),
                       "funding": float(res.funding),
                       "profit_factor": float(res.profit_factor),
                       "win_rate": float(res.win_rate)}
                exp = cloud["branches"][name][scen]
                for k in METRICS:
                    e, g = float(exp[k]), float(got[k])
                    err = abs(e - g)
                    if k in ("final_equity", "gross_pnl", "fees", "funding"):
                        err = err / max(1.0, abs(e))
                    max_err = max(max_err, err)
                    if k == "trades" and int(exp[k]) != int(got[k]):
                        raise ValueError(f"Trade count differs {name}/{scen}")
                    if k != "trades" and err > 1e-6:
                        raise ValueError(f"Replay error {err} > 1e-6 {name}/{scen}/{k}: {e} vs {g}")
                replay[name][scen] = got
            print(json.dumps({"branch": name, "parity_ok": True}), flush=True)
            write_json(OUT_DIR / "progress.json",
                       {"completed": name, "max_err_so_far": max_err, "state": "auditing"})

    result = {"state": "passed",
              "kernel": "nguynchtrai/opencode-tracka2-multitask-v26b-cpufix",
              "experiment": "opencode-v26b-cpufix",
              "device": "cpu (local replay i7/GTX1650 host; cloud CPU-fallback P100->CPU threads=2)",
              "predictions": {"oos_prob": list(P.shape), "oos_quantile": list(Q.shape),
                              "oos_excursion": list(E.shape), "n_oos": 4076,
                              "finite_all": True, "nan": 0,
                              "prob_rows_sum_to_1": True,
                              "quantile_crossing_rate": cross_rate,
                              "quantile_note": "heads doc lap khong rang buoc thu tu; crossing la binh thuong, policy chi dung 1 quantile/nhanh",
                              "excursion_nonneg": True},
              "folds": n_folds, "eval_decisions_sum": eval_sum,
              "signals": signals_info,
              "exit_codes": {"outer_state": outer["state"], "worker_exit_code": outer["worker_exit_code"]},
              "compute": {"mode": runtime["compute_mode"], "gpus": runtime["gpus"],
                          "caps": runtime["caps"], "torch": runtime["torch"],
                          "reason": runtime["compute_reason"]},
              "plan_sha256": plan_sha_local,
              "plan_json_equal": True,
              "bundle_identity": {"n": 52, "mismatches": []},
              "missing_empty": {"fee_trades_csv_bytes": 1,
                                "note": "fee_stress_trades.csv size=1 by-design (driver khong luu fee trades, chi metrics); normal/execution trades day du"},
              "max_replay_error": max_err,
              "rtol_atol": "1e-6 abs (relative cho equity/pnl)",
              "source_summary_sha256": digest(SOURCE / "summary.json"),
              "full_summary_sha256": digest(FULL / "summary.json"),
              "all_forecasts_replayed": True,
              "independent_test": False, "exploratory": True, "live_approved": False,
              "prespec_note": "pre-spec = configs/opencode_v26_multitask.json (branches + policy + costs + FillStress)"}
    write_json(OUT_DIR / "audit.json", result)
    print(json.dumps({"state": "passed", "max_replay_error": max_err}))


if __name__ == "__main__":
    main()
