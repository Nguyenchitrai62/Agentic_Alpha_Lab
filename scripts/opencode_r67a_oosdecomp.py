"""Opencode R67a (v156): OOS fill-loss decomposition, majority chain.

Prespec: configs/opencode_v156_oosdecomp.json (written BEFORE this script ran).
Read-only analysis. NO backtests (never imports run_backtest/run_stress),
NO training/fitting/refitting, NO new thresholds, NO threshold tuning on
forward, NO live orders, NO registry/ledger writes, NO overwrites.

Frozen inputs only:
  in-sample  = artifacts/research/opencode_v15_mapensemble (majority_1x)
  forward    = artifacts/research/opencode_v154_fwdmaj (majority_1x)
  research predictions = opencode_v02_reproduce_v30 isotonic_*/predictions.npz
  forward predictions  = opencode_v154_fwdmaj/forward_predictions.npz
Score claims are descriptive only: frozen pass-rate counts at the frozen
thresholds (0.3 expected / 0.25 fill) + calibrated-ch0 quantile tables.
Rejected decomposition uses frozen signals<->trades linkage only
(overlap vs truncated-window vs residual expiry-no-fill); the engine is
never re-simulated.

Outputs (new dir only): artifacts/research/opencode_v156_oosdecomp/
Exploratory: in-sample is opened development data, NOT an independent test.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SPEC_PATH = ROOT / "configs/opencode_v156_oosdecomp.json"
IS_SUMMARY = ROOT / "artifacts/research/opencode_v15_mapensemble/summary.json"
FW_SUMMARY = ROOT / "artifacts/research/opencode_v154_fwdmaj/summary.json"
IS_SIGNALS = ROOT / "artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet"
FW_SIGNALS = ROOT / "artifacts/research/opencode_v154_fwdmaj/majority_1x/signals.parquet"
IS_TRADES = ROOT / "artifacts/research/opencode_v15_mapensemble/majority_1x/normal_trades.csv"
FW_TRADES = ROOT / "artifacts/research/opencode_v154_fwdmaj/majority_1x/normal_trades.csv"
IS_PRED = {
    "iso2": ROOT / "artifacts/research/opencode_v02_reproduce_v30/isotonic_2/predictions.npz",
    "iso4": ROOT / "artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz",
    "isoall": ROOT / "artifacts/research/opencode_v02_reproduce_v30/isotonic_all/predictions.npz",
}
FW_PRED = ROOT / "artifacts/research/opencode_v154_fwdmaj/forward_predictions.npz"

QS_MAIN = [0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0]
QS_TAIL = [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]


def qtable(arr: np.ndarray, qs) -> dict:
    q = np.quantile(arr.ravel().astype(np.float64), qs)
    return {str(x): float(v) for x, v in zip(qs, q)}


def decompose_rejected(signals: pd.DataFrame, trades: pd.DataFrame,
                       data_len: int, expiry: int) -> dict:
    """Frozen-linkage split of signals-minus-fills.

    overlap: unfilled signal with bar_index < next_available, where
      next_available advances only on frozen fills (exit_index + 1),
      mirroring the single-position engine's displacement rule.
    truncated: signal whose holding window cannot fit even at the
      earliest/latest possible entry (signal+1+holding or
      signal+expiry+holding >= data_len), using the signal's OWN
      frozen holding_bars.
    residual: remainder, labelled expiry-no-fill candidate
      (touch-no-cross within 12 bars, INFERRED, never re-simulated).
    """
    s = signals.sort_values("bar_index").reset_index(drop=True)
    t = trades.sort_values("signal_index").reset_index(drop=True)
    filled = set(int(x) for x in t["signal_index"].tolist())
    exit_by = {int(r.signal_index): int(r.exit_index) for r in t.itertuples()}
    hold_by = {int(r.bar_index): int(r.holding_bars) for r in s.itertuples()}
    next_avail = 0
    overlap, non_overlap = [], []
    for r in s.itertuples():
        bi = int(r.bar_index)
        if bi in filled:
            next_avail = exit_by[bi] + 1
        elif bi < next_avail:
            overlap.append(bi)
        else:
            non_overlap.append(bi)
    trunc = [bi for bi in non_overlap
             if bi + 1 + hold_by[bi] >= data_len or bi + expiry + hold_by[bi] >= data_len]
    residual = [bi for bi in non_overlap if bi not in set(trunc)]
    return {
        "n_signals": int(len(s)),
        "n_fills": int(len(t)),
        "n_rejected": int(len(s) - len(t)),
        "n_overlap_displaced": int(len(overlap)),
        "n_truncated_window": int(len(trunc)),
        "n_residual_expiry_no_fill": int(len(residual)),
        "overlap_bar_index": [int(x) for x in overlap],
        "truncated_bar_index": [int(x) for x in trunc],
        "residual_bar_index": [int(x) for x in residual],
        "data_len": int(data_len),
        "method": ("frozen linkage only (signals bar_index vs frozen trades "
                   "signal_index/exit_index + own holding_bars vs data_len); "
                   "engine never re-simulated; residual is inferred, not proven"),
    }


def main(out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"Khong ghi de: {out} da ton tai")
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert list(spec["stages"].keys()) == [
        "S0_decisions", "S1_gate_hits", "S2_selected", "S3_signals", "S4_fills"], \
        "stage definitions changed after prespec"
    policy = spec["policy_frozen_ref"]
    anchors = spec["parity_anchors"]

    is_sum = json.loads(IS_SUMMARY.read_text(encoding="utf-8"))
    fw_sum = json.loads(FW_SUMMARY.read_text(encoding="utf-8"))

    # ---- Frozen stage counts (no recomputation of gates/backtests) ----
    is_agr = is_sum["agreement_row_level"]
    fw_vote = fw_sum["vote_outcome"]
    is_nsig = is_sum["n_signals_per_filter"]["majority"]
    fw_nsig = fw_sum["signals_composition"]["majority_1x"]["n_signals"]
    is_norm = is_sum["branches"]["majority_1x"]["normal"]
    fw_norm = fw_sum["branches"]["majority_1x"]["normal"]

    s_is = [int(is_agr["n_rows"]), int(is_agr["pass_majority"]),
            int(is_nsig), int(is_nsig), int(is_norm["trades"])]
    s_fw = [int(fw_vote["n_rows"]), int(fw_vote["pass_majority"]),
            int(fw_nsig), int(fw_nsig), int(fw_norm["trades"])]
    assert s_is[0] == anchors["in_sample"]["decisions"] == 4076
    assert s_is[1] == anchors["in_sample"]["gate_hits_majority"] == 1304
    assert s_is[2] == anchors["in_sample"]["signals"] == 94
    assert s_is[4] == anchors["in_sample"]["fills_normal"] == 63
    assert int(is_norm["rejected_or_unfilled_signals"]) == anchors["in_sample"]["rejected_normal"] == 31
    assert s_fw[0] == anchors["forward"]["decisions"] == 679
    assert s_fw[1] == anchors["forward"]["gate_hits_majority"] == 158
    assert s_fw[2] == anchors["forward"]["signals"] == 18
    assert s_fw[4] == anchors["forward"]["fills_normal"] == 11
    assert int(fw_norm["rejected_or_unfilled_signals"]) == anchors["forward"]["rejected_normal"] == 7

    # Cross-check signals.parquet row counts match the frozen summaries.
    is_sig = pd.read_parquet(IS_SIGNALS)
    fw_sig = pd.read_parquet(FW_SIGNALS)
    assert len(is_sig) == s_is[2] and len(fw_sig) == s_fw[2]
    is_tr = pd.read_csv(IS_TRADES)
    fw_tr = pd.read_csv(FW_TRADES)
    assert len(is_tr) == s_is[4] and len(fw_tr) == s_fw[4]

    names = ["S0_decisions", "S1_gate_hits", "S2_selected", "S3_signals", "S4_fills"]
    funnel = []
    for i, name in enumerate(names):
        a, b = float(s_is[i]), float(s_fw[i])
        per_is, per_fw = a / s_is[0], b / s_fw[0]
        rel = (per_fw - per_is) / per_is if per_is else None
        funnel.append({"stage": name, "is_abs": int(a), "fw_abs": int(b),
                       "abs_ratio_is_over_fw": float(a / b) if b else None,
                       "is_per_decision": per_is, "fw_per_decision": per_fw,
                       "pp_change": float(per_fw - per_is),
                       "rel_change": float(rel) if rel is not None else None})

    def tr(num_is, den_is, num_fw, den_fw):
        r_is = num_is / den_is if den_is else 0.0
        r_fw = num_fw / den_fw if den_fw else 0.0
        rel = (r_fw - r_is) / r_is if r_is else None
        return {"is": float(r_is), "fw": float(r_fw),
                "pp_change": float(r_fw - r_is),
                "rel_change": float(rel) if rel is not None else None}

    transitions = {
        "T01_gate_S1_over_S0": tr(s_is[1], s_is[0], s_fw[1], s_fw[0]),
        "T12_frequency_S2_over_S1": tr(s_is[2], s_is[1], s_fw[2], s_fw[1]),
        "T23_geometry_S3_over_S2": tr(s_is[3], s_is[2], s_fw[3], s_fw[2]),
        "T34_fill_S4_over_S3": tr(s_is[4], s_is[3], s_fw[4], s_fw[3]),
        "overall_S4_over_S0": tr(s_is[4], s_is[0], s_fw[4], s_fw[0]),
    }

    # ---- Time normalization (frozen durations, never recomputed) ----
    is_years = float(is_sum["duration_years"])
    fw_years = float(fw_sum["span"]["years"])
    is_months, fw_months = is_years * 12.0, fw_years * 12.0
    per_month = {
        "is_months": is_months, "fw_months": fw_months,
        "is_signals_per_month": s_is[2] / is_months,
        "fw_signals_per_month": s_fw[2] / fw_months,
        "is_fills_per_month": s_is[4] / is_months,
        "fw_fills_per_month": s_fw[4] / fw_months,
        "is_decisions_per_month": s_is[0] / is_months,
        "fw_decisions_per_month": s_fw[0] / fw_months,
    }
    for df, tag in ((is_sig, "is"), (fw_sig, "fw")):
        ym = pd.to_datetime(df["signal_time"], utc=True).dt.strftime("%Y-%m")
        vc = ym.value_counts()
        per_month[f"{tag}_calendar_months_with_signals"] = int(vc.shape[0])
        per_month[f"{tag}_months_at_cap4"] = int((vc >= 4).sum())
        per_month[f"{tag}_max_signals_in_month"] = int(vc.max())

    # ---- Frozen score descriptives (counts at frozen thresholds + quantiles) ----
    scores = {
        "frozen_thresholds": {
            "minimum_expected_net_percent": policy["minimum_expected_net_percent"],
            "minimum_fill_score": policy["minimum_fill_score"],
            "note": ("thresholds quoted from the frozen policy only; "
                     "no threshold was applied or tuned in this script"),
        },
        "pass_rates_frozen_counts": {
            "is": {"n": int(is_agr["n_rows"]),
                   "nonwait_iso2": int(is_agr["nonwait_iso2"]),
                   "nonwait_iso4": int(is_agr["nonwait_iso4"]),
                   "nonwait_isoall": int(is_agr["nonwait_isoall"]),
                   "pass_majority": int(is_agr["pass_majority"]),
                   "agree_majority_given_iso4": float(is_agr["agree_majority_given_iso4"])},
            "fw": {"n": int(fw_vote["n_rows"]),
                   "nonwait_iso2": int(fw_vote["nonwait_iso2"]),
                   "nonwait_iso4": int(fw_vote["nonwait_iso4"]),
                   "nonwait_isoall": int(fw_vote["nonwait_isoall"]),
                   "pass_majority": int(fw_vote["pass_majority"]),
                   "agree_majority_given_iso4": float(fw_vote["agree_majority_given_iso4"])},
        },
        "calibrated_ch0_quantiles": {},
        "forward_only_ensemble_details": {},
    }
    with np.load(IS_PRED["iso4"]) as z:
        r_iso4 = np.asarray(z["prediction"][..., 0], dtype=np.float64)
    with np.load(IS_PRED["iso2"]) as z:
        r_iso2 = np.asarray(z["prediction"][..., 0], dtype=np.float64)
    with np.load(IS_PRED["isoall"]) as z:
        r_isoall = np.asarray(z["prediction"][..., 0], dtype=np.float64)
    with np.load(FW_PRED) as z:
        f_iso4 = np.asarray(z["calibrated_iso4"][..., 0], dtype=np.float64)
        f_iso2 = np.asarray(z["calibrated_iso2"][..., 0], dtype=np.float64)
        f_isoall = np.asarray(z["calibrated_isoall"][..., 0], dtype=np.float64)
        f_sel = np.asarray(z["selection_score_percent"], dtype=np.float64)
        f_fill = np.asarray(z["mean_fill_score"], dtype=np.float64)
    scores["calibrated_ch0_quantiles"] = {
        "iso4": {"is": qtable(r_iso4, QS_MAIN), "fw": qtable(f_iso4, QS_MAIN)},
        "iso2": {"is": qtable(r_iso2, QS_TAIL), "fw": qtable(f_iso2, QS_TAIL)},
        "isoall": {"is": qtable(r_isoall, QS_TAIL), "fw": qtable(f_isoall, QS_TAIL)},
        "note": ("descriptive quantiles of frozen calibrated ch0 arrays; "
                 "research = isotonic_*/predictions.npz, forward = "
                 "forward_predictions.npz calibrated_*; no thresholds applied here"),
    }
    scores["forward_only_ensemble_details"] = {
        "selection_score_percent_quantiles": qtable(f_sel, QS_TAIL),
        "mean_fill_score_quantiles": qtable(f_fill, QS_TAIL),
        "note": "forward-only (no in-sample counterpart stored); fill gate 0.25 never binds forward (min 0.356)",
    }

    # ---- Rejected decomposition (frozen linkage only) ----
    rej = {
        "in_sample": decompose_rejected(
            is_sig, is_tr, int(spec["frozen_sources"]["research_candles_len"]),
            int(policy["entry_expiry_bars"])),
        "forward": decompose_rejected(
            fw_sig, fw_tr, 444096 + 48819, int(policy["entry_expiry_bars"])),
        "engine_rejected_frozen": {
            "is": int(is_norm["rejected_or_unfilled_signals"]),
            "fw": int(fw_norm["rejected_or_unfilled_signals"]),
        },
    }
    assert rej["in_sample"]["n_rejected"] == rej["engine_rejected_frozen"]["is"] == 31
    assert rej["forward"]["n_rejected"] == rej["engine_rejected_frozen"]["fw"] == 7

    # ---- Verdict: biggest per-decision transition drop ----
    cands = {k: v["rel_change"] for k, v in transitions.items()
             if k in ("T01_gate_S1_over_S0", "T12_frequency_S2_over_S1", "T34_fill_S4_over_S3")}
    biggest = min(cands, key=lambda k: cands[k])
    verdict = {
        "biggest_relative_drop": {"transition": biggest, **transitions[biggest]},
        "all_transitions_rel_change": {k: v["rel_change"] for k, v in transitions.items()},
        "overall_fills_per_decision_rel_change": transitions["overall_S4_over_S0"]["rel_change"],
        "reading": ("absolute fills collapse with window length; per-decision "
                    "fill conversion is flat (see overall_S4_over_S0)"),
    }

    summary = {
        "experiment": "opencode-r67a-oosdecomp",
        "prespec": "configs/opencode_v156_oosdecomp.json",
        "branch": "majority_1x",
        "exploratory": True,
        "in_sample_note": ("opened 2023-2026 development data (v15), NOT an independent test; "
                           "numbers reused verbatim from the frozen summary, never recomputed"),
        "forward_note": ("single pristine pass (v154, 679 decisions, span 0.464y); "
                         "metrics reused verbatim, never recomputed; no tuning"),
        "funnel": funnel,
        "transitions": transitions,
        "per_month": per_month,
        "scores": scores,
        "rejected_decomposition": rej,
        "verdict": verdict,
        "seal_affirmation": {
            "no_backtest": True, "no_training_or_fitting": True,
            "no_threshold_selection_on_forward": True, "no_live_orders": True,
            "sealed_files_unmodified": True,
            "evidence": ("counts reused from frozen summaries; signals/trades/predictions "
                         "read read-only; engine never called"),
        },
    }

    out.mkdir(parents=True)
    (out / "config.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                      encoding="utf-8")
    pd.DataFrame(funnel).to_csv(out / "funnel.csv", index=False)
    print(json.dumps({"wrote": str(out), "funnel": funnel,
                      "transitions": transitions, "verdict": verdict},
                     ensure_ascii=False, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_v156_oosdecomp"))
    args = ap.parse_args()
    if Path(args.output).as_posix() != "artifacts/research/opencode_v156_oosdecomp":
        raise ValueError("Output is fixed to artifacts/research/opencode_v156_oosdecomp (no overwrites)")
    main(Path(args.output))
    sys.exit(0)
