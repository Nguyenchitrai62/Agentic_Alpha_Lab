"""Opencode R38-E (v109): forward-pipeline shakedown with FROZEN Kronos-mini zero-shot.

B-path FIRST-EVER forward evaluation: validate MACHINERY on sealed forward window
2026-03-23 -> 2026-09-08 with a KNOWN-WEAK model (Kronos-mini zero-shot failed
historically: Phase-A 4h locked test -0.26%, PF 0.95). Metrics computed EXACTLY
ONCE. Expect WEAK numbers; success = machinery validated, NOT profit.

Frozen policy (verbatim scripts/run_kronos_backtest.py defaults +
scripts/generate_dashboard_data.py TIMEFRAMES["5m"], threshold 12bps dashboard
default; prespecified in configs/opencode_v109_fwdshakedown.json BEFORE running):
  mini / lookback 512 / horizon 12 / greedy top_k=1 / temp 0.6 / top_p 1.0 /
  1 sample / thr 12bps / atr14 / offset 0 / stop 1.25 / tp1 1.0 / tp2 2.0 /
  expiry 1 / holding 12 / tp1f 0.5 / lev 1x.
NO fitting, NO thresholds on forward, NO labels/outcomes beyond scoring
(no per-signal actual_return/direction_correct columns), NO plots.

Modes:
  --dry-run : plumbing ONLY on 20 OPENED pre-cutoff research bars
              (signals-only, no backtest, no metrics, writes nothing).
  full pass : ONE pass over the 679-decision forward lattice (clock authority =
              E-fwfeatures decisions_forward.parquet), then 3 ohlc-v2 backtests
              (normal / fee_stress .00055 / execution_stress FillStress(5,5,5,
              .00055,False)), monthly geometric over the forward span.

Outputs (new dir only): artifacts/research/opencode_v109_fwdshakedown/
"""
import torch  # noqa: F401  (torch truoc pandas: tranh loi DLL tren host nay)
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

from agentic_alpha_lab.backtest.engine import (  # noqa: E402
    CostModel,
    ExecutionConfig,
    run_backtest,
)
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.kronos_adapter import KronosAdapter  # noqa: E402
from agentic_alpha_lab.signals.forecast_signal import (  # noqa: E402
    forecast_to_signal,
    signal_dict,
)

BRANCH = "kronos_mini_zs12_1x"
CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z")
STRIDE = 72
N_RESEARCH = 444096
N_FORWARD = 48819
LOOKBACK = 512
HORIZON = 12
N_DEC = 679
BATCH = 8
DEVICE = "cuda:0"

FWD = ROOT / "data/processed/opencode_forward_20260323"
FEAT = FWD / "features"
RESEARCH = ROOT / "data/processed/swing_regime_research_v4"
KRONOS_REPO = ROOT.parent / "Kronos"
MODEL_ROOT = ROOT / "artifacts/models"

SIGNAL_KEYS = {"bar_index", "signal_time", "direction", "label", "current_close",
               "predicted_close", "predicted_return", "threshold", "atr",
               "entry_limit", "stop_loss", "take_profit_1", "take_profit_2"}


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_concat() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Verify sealed SHAs (structural) + build causal concat frame. No outcomes."""
    plan = json.loads((ROOT / "configs/opencode_v109_fwdshakedown.json").read_text(
        encoding="utf-8"))
    assert plan["experiment"] == "opencode-r38e-fwdshakedown"
    assert list(plan["branches"]) == [BRANCH], "branches phai la {1x} only"
    pol = plan["policy_frozen_ref"]
    assert pol["threshold_bps"] == 12.0 and pol["lookback_bars"] == 512
    assert pol["horizon_bars"] == 12 and pol["top_k"] == 1
    assert pol["variant"] == "mini"

    fz = json.loads((FWD / "manifest.json").read_text(encoding="utf-8"))
    for key, name in (("candles", "candles.parquet"), ("funding", "funding.parquet"),
                      ("macro", "macro.parquet")):
        if sha(FWD / name) != fz[key]["sha256"]:
            raise ValueError(f"Sealed hash mismatch: {name}")
    fw = pd.read_parquet(FWD / "candles.parquet")
    if len(fw) != N_FORWARD != fz["candles"]["rows"]:
        raise ValueError("Forward candle row mismatch")
    sums: dict[str, str] = {}
    for line in (FEAT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1]] = parts[0]
    if sums.get("decisions_forward.parquet") != sha(FEAT / "decisions_forward.parquet"):
        raise ValueError("E-fwfeatures decisions SHA mismatch")
    decisions = pd.read_parquet(FEAT / "decisions_forward.parquet")
    if len(decisions) != N_DEC:
        raise ValueError(f"Forward decisions != {N_DEC}")

    rs_meta = json.loads((RESEARCH / "manifest.json").read_text(encoding="utf-8"))
    if sha(RESEARCH / "candles.parquet") != rs_meta["files"]["candles.parquet"]:
        raise ValueError("Research candles changed")
    rs = pd.read_parquet(RESEARCH / "candles.parquet")
    if len(rs) != N_RESEARCH:
        raise ValueError("Research candle row mismatch")
    keep = [c for c in rs.columns if c in fw.columns]
    candles = pd.concat([rs[keep], fw[keep]], ignore_index=True)
    candles = validate_source(candles)  # structural contiguity incl. boundary
    if len(candles) != N_RESEARCH + N_FORWARD:
        raise ValueError("Concat candle length mismatch")

    grid = np.arange(N_RESEARCH, len(candles), STRIDE, dtype=np.int64)[:N_DEC]
    if len(grid) != N_DEC:
        raise ValueError("Forward lattice != 679")
    if (grid != decisions["bar_index_concat"].to_numpy()).any():
        raise ValueError("Lattice != E-fwfeatures clock")
    sig_times = pd.DatetimeIndex(pd.to_datetime(
        candles["close_time"].iloc[grid])).tz_convert("UTC")
    if (sig_times != pd.DatetimeIndex(
            pd.to_datetime(decisions["signal_time"], utc=True))).any():
        raise ValueError("Signal times != E-fwfeatures clock")
    return plan, candles, decisions, grid


def check_local_weights() -> None:
    """Fail-closed: frozen weights must resolve LOCAL (no download, no train)."""
    if not (KRONOS_REPO / "model" / "kronos.py").exists():
        raise FileNotFoundError(f"Kronos repo missing: {KRONOS_REPO}")
    for sub in ("Kronos-mini", "Kronos-Tokenizer-2k"):
        if not (MODEL_ROOT / sub / "config.json").exists():
            raise FileNotFoundError(
                f"STOP: frozen checkpoint missing: {MODEL_ROOT / sub}. "
                "No training allowed; audit precisely and stop.")


def future_grid(fw_opens: pd.Series, last_open: pd.Timestamp,
                pos: int, horizon: int) -> pd.Series:
    out = []
    n = len(fw_opens)
    for j in range(1, horizon + 1):
        if pos + j < n:
            out.append(fw_opens.iloc[pos + j])
        else:
            out.append(last_open + pd.Timedelta(minutes=5 * (pos + j - n + 1)))
    return pd.Series(pd.to_datetime(out, utc=True))


def to_signals(adapter: KronosAdapter, candles: pd.DataFrame,
               grid: np.ndarray, fw_pos: np.ndarray,
               fw_opens: pd.Series, last_open: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict] = []
    t0 = time.perf_counter()
    for s in range(0, len(grid), BATCH):
        sl = slice(s, s + BATCH)
        ctx = [candles.iloc[g - LOOKBACK + 1: g + 1].copy() for g in grid[sl]]
        fts = [future_grid(fw_opens, last_open, int(p), HORIZON) for p in fw_pos[sl]]
        preds = adapter.forecast_batch(ctx, fts, temperature=0.6, top_k=1,
                                       top_p=1.0, sample_count=1)
        for g, pred in zip(grid[sl], preds):
            sig = forecast_to_signal(candles, int(g), pred, threshold_bps=12.0,
                                     atr_window=14, entry_limit_offset_bps=0.0,
                                     stop_atr=1.25, tp1_atr=1.0, tp2_atr=2.0)
            row = signal_dict(sig)
            assert set(row) == SIGNAL_KEYS, f"signal schema drift: {sorted(set(row))}"
            for k in ("current_close", "predicted_close", "predicted_return",
                      "threshold", "atr", "entry_limit", "stop_loss",
                      "take_profit_1", "take_profit_2"):
                if not np.isfinite(row[k]):
                    raise ValueError(f"non-finite signal field {k}")
            assert row["direction"] in (-1, 0, 1)
            rows.append(row)
    secs = time.perf_counter() - t0
    return pd.DataFrame(rows), secs


def dry_run() -> None:
    """Plumbing on 20 OPENED pre-cutoff bars. Signals ONLY. Writes nothing."""
    _, candles, _, _ = load_concat()
    check_local_weights()
    grid = np.array([N_RESEARCH - STRIDE * j for j in range(1, 21)][::-1],
                    dtype=np.int64)
    assert (pd.to_datetime(candles["close_time"].iloc[grid], utc=True).max()
            < CUTOFF), "dry-run phai pre-cutoff"
    opens = pd.to_datetime(candles["open_time"], utc=True).reset_index(drop=True)
    adapter = KronosAdapter("mini", KRONOS_REPO, DEVICE, MODEL_ROOT)
    ctx = [candles.iloc[g - LOOKBACK + 1: g + 1].copy() for g in grid]
    fts = [opens.iloc[g + 1: g + 1 + HORIZON].reset_index(drop=True) for g in grid]
    preds = adapter.forecast_batch(ctx, fts, temperature=0.6, top_k=1,
                                   top_p=1.0, sample_count=1)
    n = 0
    for g, pred in zip(grid, preds):
        row = signal_dict(forecast_to_signal(candles, int(g), pred,
                                             threshold_bps=12.0))
        assert set(row) == SIGNAL_KEYS
        n += 1
    print(json.dumps({"dry_run_plumbing": "OK", "n_windows": n,
                      "pre_cutoff_only": True, "writes": "none",
                      "metrics": "none (signals-only, no backtest)"}))


def full_pass(out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"Khong ghi de: {out} da ton tai")
    plan, candles, decisions, grid = load_concat()
    check_local_weights()
    fw_pos = decisions["bar_index_forward"].to_numpy(dtype=np.int64)
    fw_opens = pd.to_datetime(
        pd.read_parquet(FWD / "candles.parquet")["open_time"],
        utc=True).reset_index(drop=True)
    last_open = fw_opens.iloc[-1]

    adapter = KronosAdapter("mini", KRONOS_REPO, DEVICE, MODEL_ROOT)
    signals, infer_s = to_signals(adapter, candles, grid, fw_pos, fw_opens,
                                  last_open)
    del adapter
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    costs = CostModel(**plan["backtest"]["costs_normal"])
    costs_fee = CostModel(**plan["backtest"]["costs_fee_stress"])
    exe = ExecutionConfig(**{k: v for k, v in
                             plan["backtest"]["execution"].items()})
    stress = FillStress(5, 5, 5, 0.00055, False)

    first_open = pd.to_datetime(fw_opens.iloc[0], utc=True)
    last_close = pd.to_datetime(
        pd.read_parquet(FWD / "candles.parquet")["close_time"],
        utc=True).max()
    years = (last_close - first_open).total_seconds() / (365.2425 * 86400)

    res_n, tr_n = run_backtest(candles, signals, 100.0, costs, exe)
    res_f, tr_f = run_backtest(candles, signals, 100.0, costs_fee, exe)
    res_x, tr_x, diag_x = run_stress(candles, signals, 100.0, costs, exe,
                                     stress)
    scenarios = {}
    for name, res, trs in (("normal", res_n, tr_n), ("fee_stress", res_f, tr_f),
                           ("execution_stress", res_x, tr_x)):
        ratio = res.final_equity / 100.0
        scenarios[name] = {**asdict(res),
                           "annual_geometric_net": ratio ** (1 / years) - 1,
                           "monthly_geometric_net": ratio ** (1 / (12 * years)) - 1}
        assert scenarios[name]["trades"] == len(trs)

    gate = json.loads((ROOT / "configs/opencode_gatecheck.json").read_text(
        encoding="utf-8"))["gate"]
    flags = {}
    for name, m in scenarios.items():
        flags[name] = {
            "monthly_pass": bool(m["monthly_geometric_net"] >= gate["monthly_min"]),
            "dd_pass": bool(m["max_drawdown"] >= -gate["dd_max"]),
            "fills_pass": bool(m["trades"] >= gate["fills_min"])}
        flags[name]["scenario_pass"] = all(flags[name].values())
    flags["overall_pass"] = all(flags[s]["scenario_pass"] for s in scenarios)

    bdir = out / BRANCH
    bdir.mkdir(parents=True)
    signals.to_parquet(bdir / "signals.parquet", index=False)
    for name, trs in (("normal", tr_n), ("fee_stress", tr_f),
                      ("execution_stress", tr_x)):
        pd.DataFrame([asdict(t) for t in trs]).to_csv(
            bdir / f"{name}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diag_x

    exits = pd.to_datetime(pd.DataFrame(
        [asdict(t) for t in tr_n])["exit_time"], utc=True) \
        if tr_n else pd.DatetimeIndex([], tz="UTC")
    summary = {
        "experiment": "opencode-r38e-fwdshakedown",
        "prespec": "configs/opencode_v109_fwdshakedown.json",
        "branch": BRANCH,
        "seal": {"cutoff_exclusive": "2026-03-23T00:00:00+00:00",
                 "state": "PRISTINE per SEAL.json + ledger forward_window rule"},
        "policy_frozen": plan["policy_frozen_ref"],
        "checkpoint": plan["checkpoint_audit"],
        "clock": {"n_decisions": len(signals), "stride_bars": STRIDE,
                  "first_signal": str(pd.to_datetime(
                      signals["signal_time"].iloc[0], utc=True)),
                  "last_signal": str(pd.to_datetime(
                      signals["signal_time"].iloc[-1], utc=True)),
                  "matches_E_fwfeatures": True},
        "signals_composition": {
            "n_signals": int(len(signals)),
            "n_actionable": int((signals["direction"] != 0).sum()),
            "n_long": int((signals["direction"] == 1).sum()),
            "n_short": int((signals["direction"] == -1).sum()),
            "n_wait": int((signals["direction"] == 0).sum())},
        "span": {"forward_first_open": str(first_open),
                 "forward_last_close": str(last_close),
                 "years": years,
                 "exit_span_normal": [str(exits.min()), str(exits.max())]
                 if len(exits) else [None, None],
                 "n_calendar_months_exit_span":
                     int(len(pd.period_range(exits.min().strftime("%Y-%m"),
                                             exits.max().strftime("%Y-%m"),
                                             freq="M"))) if len(exits) else 0},
        "scenarios": scenarios,
        "gate_flags": {"thresholds": gate, "per_scenario": flags},
        "inference": {"device": DEVICE, "batch": BATCH,
                      "inference_seconds": infer_s,
                      "seconds_per_window": infer_s / max(len(signals), 1)},
        "machine_verdict": None,
        "seal_affirmation": {
            "frozen_policy": True,
            "metrics_computed_once": True,
            "no_tuning": True,
            "no_threshold_selection_on_forward": True,
            "no_labels_outcomes_beyond_scoring": True,
            "no_plots": True,
            "no_training_or_fitting": True,
            "sealed_files_unmodified": True,
            "evidence": "threshold 12bps + all params prespecified in v109 before "
                        "running; dry-run was signals-only on 20 pre-cutoff bars "
                        "(no backtest); single full pass; no actual_return / "
                        "direction_correct columns; sealed SHAs re-verified"},
        "input_sha256": {
            "sealed_candles": sha(FWD / "candles.parquet"),
            "sealed_funding": sha(FWD / "funding.parquet"),
            "sealed_macro": sha(FWD / "macro.parquet"),
            "decisions_forward": sha(FEAT / "decisions_forward.parquet"),
            "research_candles_warmup": sha(RESEARCH / "candles.parquet"),
            "prespec": sha(ROOT / "configs/opencode_v109_fwdshakedown.json")},
    }
    (out / "config.json").write_text(json.dumps(plan, indent=2,
                                                ensure_ascii=False),
                                     encoding="utf-8")
    (out / "driver_source.py").write_text(Path(__file__).read_text(
        encoding="utf-8"), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2,
                                                 ensure_ascii=False,
                                                 default=str),
                                      encoding="utf-8")
    sums = [f"{sha(p)}  {p.name}" for p in
            (bdir / "signals.parquet", bdir / "normal_trades.csv",
             bdir / "fee_stress_trades.csv",
             bdir / "execution_stress_trades.csv", out / "summary.json",
             out / "config.json", out / "driver_source.py")]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                        encoding="utf-8")
    mo = scenarios["normal"]["monthly_geometric_net"]
    print(json.dumps({"one_pass_complete": True, "branch": BRANCH,
                      "n_signals": len(signals),
                      "actionable": int((signals["direction"] != 0).sum()),
                      "normal": {k: scenarios["normal"][k] for k in
                                 ("total_return", "monthly_geometric_net",
                                  "max_drawdown", "trades", "profit_factor",
                                  "win_rate")},
                      "fee_stress_monthly": scenarios["fee_stress"][
                          "monthly_geometric_net"],
                      "exec_monthly": scenarios["execution_stress"][
                          "monthly_geometric_net"],
                      "exec_trades": scenarios["execution_stress"]["trades"],
                      "gate_overall": flags["overall_pass"],
                      "out": str(out)}, ensure_ascii=False, default=str),
          flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_v109_fwdshakedown"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run()
    else:
        full_pass(args.output)
