"""Forward-validation protocol runner (opencode_forward_test v1.1.0).

Given a FROZEN branch (signals.parquet + backtest config + summary.json +
normal_trades.csv), splits evaluation into IN-SAMPLE (existing opened interval,
reference only) vs FORWARD window (data strictly AFTER the frozen cutoff in
configs/opencode_forward_protocol.json) and folds in the paper-rehearsal
checklist (halts / trips / resume / kill-switch) into ONE verdict file.

First-forward policies (no same-policy frozen leg, e.g. Kronos-mini
zero-shot) use --forward-only: gates the forward window ALONE
(status FORWARD_ONLY, in_sample_baseline NO-IN-SAMPLE-BASELINE, capped at
HOLD max, never PROMOTE). See configs/opencode_forward_protocol.json
forward_only rule for the pre-specified cap.

Current data ends 2026-03-23, so NO forward window exists yet: without
--forward-summary + --forward-trades on genuinely new data the runner reports
forward_status=FORWARD_BLOCKED (never PROMOTE) and explains why. Any attempt
to run forward on already-opened dates (--forward-start on/before the cutoff,
or a forward-trades file overlapping the cutoff) is REFUSED fail-closed with
exit code 2, because per research rule 5 an inspected interval is research
data, never validation.

Analysis/code ONLY. No backtests, no training, no fitting, no live orders.
Gate + concentration + robustness reuse scripts/opencode_gatecheck.py; this
module only adds the cutoff audit, the forward/degradation/paper layers and
the promotion decision. --out refuses to overwrite an existing file.

Usage:
    .venv/Scripts/python.exe scripts/opencode_forward_test.py \
        --summary <summary.json> --trades <normal_trades.csv> \
        --branch <branch> --signals <signals.parquet> \
        --backtest-config <backtest_config.json> \
        --paper-summary <paper_summary.json> [--paper-summary <drill_summary.json>] \
        [--forward-summary <fwd_summary.json> --forward-trades <fwd_trades.csv>] \
        [--forward-start YYYY-MM-DD] \
        [--protocol configs/opencode_forward_protocol.json] \
        [--gatecheck-config configs/opencode_gatecheck.json] \
        --out <verdict.json>
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "configs" / "opencode_forward_protocol.json"
DEFAULT_GATECHECK = ROOT / "configs" / "opencode_gatecheck.json"

_GC_SPEC = importlib.util.spec_from_file_location(
    "opencode_gatecheck", _SCRIPTS_DIR / "opencode_gatecheck.py")
GC = importlib.util.module_from_spec(_GC_SPEC)
_GC_SPEC.loader.exec_module(GC)

PAPER_REQUIRED_CHECKS = (
    "halt_demonstrated",
    "trip_under_blocks",
    "one_sided_verified",
    "same_book_identity",
    "kill_params_prespecified",
    "resume_parity",
)
ALLOWED_HALT_X = (0.02, 0.03)
REQUIRED_TOLERANCE_Y = 0.05


def load_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frozen_cutoff(protocol: dict) -> pd.Timestamp:
    raw = protocol["data_freeze"]["frozen_data_end_exclusive"]
    return pd.Timestamp(raw, tz="UTC")


def audit_frozen_timestamps(signals_path: Path, trades_path: Path,
                            cutoff: pd.Timestamp) -> dict:
    """Prove the frozen artifacts sit fully inside the opened interval.

    Refuses (raises) if any signal/trade timestamp reaches past the cutoff:
    such an artifact is newer than the protocol freeze and the protocol must
    be re-frozen before it can be judged.
    """
    signals_df = pd.read_parquet(signals_path)
    time_col = None
    for cand in ("signal_time", "entry_time", "exit_time", "open_time"):
        if cand in signals_df.columns:
            time_col = cand
            break
    sig_max = None
    if time_col is not None:
        sig_max = pd.to_datetime(signals_df[time_col], utc=True).max()
    trades_df = pd.read_csv(trades_path, usecols=["exit_time"])
    trades_max = pd.to_datetime(trades_df["exit_time"], utc=True).max()
    report = {
        "signals_time_column": time_col,
        "signals_max": str(sig_max) if sig_max is not None else None,
        "trades_max_exit": str(trades_max),
        "cutoff_exclusive": str(cutoff),
    }
    leaks = []
    if sig_max is not None and sig_max >= cutoff:
        leaks.append(f"signals {time_col} max {sig_max} >= cutoff {cutoff}")
    if trades_max >= cutoff:
        leaks.append(f"trades exit max {trades_max} >= cutoff {cutoff}")
    if leaks:
        raise ValueError(
            "REFUSED: frozen artifacts leak past the protocol freeze "
            f"({'; '.join(leaks)}). Re-freeze the protocol first; "
            "this run writes no verdict.")
    report["inside_freeze"] = True
    return report


def forward_month_span(trades_path: Path) -> dict:
    """Calendar-month zero-filled span of a trades file (v61 style)."""
    df = pd.read_csv(trades_path, usecols=["exit_time", "net_pnl"])
    ts = pd.to_datetime(df["exit_time"], utc=True)
    lo, hi = ts.min(), ts.max()
    months = pd.period_range(lo.strftime("%Y-%m"), hi.strftime("%Y-%m"), freq="M")
    return {"min_exit": str(lo), "max_exit": str(hi), "n_months": int(len(months))}


def eval_paper(paper_paths: list, protocol: dict) -> dict:
    """Fold 0..N paper-rehearsal summaries into the six checklist items."""
    checks: dict = {}
    per_file = []
    halt_days_total: set = set()
    operating_ok = drill_ok = one_sided_ok = kill_ok = resume_ok = False
    resume_evidence: list = []
    drill_evidence: list = []
    for raw in paper_paths or []:
        doc = load_json(Path(raw))
        stats = doc.get("stats", {}) if isinstance(doc.get("stats"), dict) else {}
        trip_cfg = doc.get("halt_trip_params", {}) \
            if isinstance(doc.get("halt_trip_params"), dict) else {}
        is_drill = bool(doc.get("is_drill", stats.get("v21_is_drill", False)))
        halt_days = stats.get("halt_days") or []
        if isinstance(halt_days, list):
            halt_days_total.update(str(d) for d in halt_days)
        if stats.get("daily_halt_events"):
            halt_days_total.add(f"{Path(raw).name}:halt_events_present")
        identity = bool(stats.get("v21_identity", False))
        one_sided = stats.get("v21_one_sided_checks") == "pass"
        if one_sided:
            one_sided_ok = True
        mode = str(doc.get("mode", ""))
        live_orders = doc.get("live_orders", None)
        try:
            x = float(trip_cfg.get("daily_loss_halt_X_pct"))
            y = float(trip_cfg.get("divergence_tolerance_Y_pct"))
            mpos = int(trip_cfg.get("max_positions"))
        except (TypeError, ValueError):
            x = y = mpos = None
        kill_this = (x in ALLOWED_HALT_X and y == REQUIRED_TOLERANCE_Y
                     and mpos == 1 and mode.startswith("SIMULATED/PAPER")
                     and live_orders is False)
        if kill_this:
            kill_ok = True
        entry = {"file": str(raw), "is_drill": is_drill,
                 "identity": identity, "one_sided": one_sided,
                 "halt_days": len(halt_days) if isinstance(halt_days, list) else 0,
                 "tripped": bool(stats.get("divergence_tripped", False)),
                 "trip_direction": (stats.get("divergence_trip") or {}).get("direction")
                 if isinstance(stats.get("divergence_trip"), dict) else None,
                 "skipped_divergence": stats.get("skipped_divergence", 0),
                 "kill_params_ok": kill_this}
        per_file.append(entry)
        if not is_drill and identity:
            operating_ok = True
        trip = stats.get("divergence_trip")
        direction = trip.get("direction") if isinstance(trip, dict) else None
        blocked = stats.get("skipped_divergence", 0) or 0
        if is_drill and stats.get("divergence_tripped") is True \
                and direction == "UNDER" and blocked >= 1:
            drill_ok = True
            drill_evidence.append(
                f"{Path(raw).name}: UNDER trip blocks {blocked} later signals")
        rp = doc.get("resume_proof")
        if isinstance(rp, dict) and rp.get("intents_identical") is True \
                and rp.get("equity_match") is True:
            resume_ok = True
            resume_evidence.append(str(raw))
    checks["halt_demonstrated"] = {
        "status": "PASS" if halt_days_total else "MISSING",
        "detail": f"{len(halt_days_total)} halt-day markers across "
                  f"{len(per_file)} summaries",
        "rule": protocol["paper_ops"]["halt_demonstrated"]["pass_rule"],
    }
    checks["trip_under_blocks"] = {
        "status": "PASS" if drill_ok else "MISSING",
        "detail": "; ".join(drill_evidence) or
                  "no drill summary with UNDER trip + >=1 blocked real signal",
        "rule": protocol["paper_ops"]["trip_under_blocks"]["pass_rule"],
    }
    checks["one_sided_verified"] = {
        "status": "PASS" if (per_file and one_sided_ok) else
                  ("MISSING" if not per_file else "FAIL"),
        "detail": "v21_one_sided_checks==pass present" if one_sided_ok else
                  ("no paper summaries provided" if not per_file else
                   "one-sided check missing/failed in provided summaries"),
        "rule": protocol["paper_ops"]["one_sided_verified"]["pass_rule"],
    }
    checks["same_book_identity"] = {
        "status": "PASS" if operating_ok else "MISSING",
        "detail": "operating same-book identity=true present" if operating_ok else
                  "no operating (non-drill) summary with v21_identity=true",
        "rule": protocol["paper_ops"]["same_book_identity"]["pass_rule"],
    }
    checks["kill_params_prespecified"] = {
        "status": "PASS" if kill_ok else ("MISSING" if not per_file else "FAIL"),
        "detail": "X in {2%,3%}, Y=5%, max_positions=1, SIMULATED/PAPER, no live orders"
                  if kill_ok else "no summary carries the pre-specified kill params",
        "rule": protocol["paper_ops"]["kill_params_prespecified"]["pass_rule"],
    }
    checks["resume_parity"] = {
        "status": "PASS" if resume_ok else "MISSING",
        "detail": ("resume_proof attached: " + ", ".join(resume_evidence))
                  if resume_ok else
                  "no resume_proof block (need kill+resume bit-identical intents+equity; "
                  "cf. tests/test_paper_trader_v21.py::"
                  "test_resume_long_trackc_replay_identical)",
        "rule": protocol["paper_ops"]["resume_parity"]["pass_rule"],
    }
    green = all(v["status"] == "PASS" for v in checks.values())
    return {"checks": checks, "per_file": per_file,
            "paper_overall": "green" if green else "NOT_GREEN"}


def eval_forward(fwd_summary: Path, fwd_trades: Path, branch: str | None,
                 backtest_monthly: float | None, protocol: dict,
                 gc_config: dict, cutoff: pd.Timestamp) -> dict:
    """Evaluate a forward window that MUST start strictly after the cutoff."""
    span = forward_month_span(fwd_trades)
    if pd.Timestamp(span["min_exit"]) <= cutoff:
        raise ValueError(
            f"REFUSED: forward window starts {span['min_exit']} which is on/before "
            f"the frozen cutoff {cutoff}. Forward on already-opened dates is "
            "in-sample relabeling (research rule 5), not validation. "
            "This run writes no verdict.")
    gate_res = GC.run(fwd_summary, fwd_trades, branch, None, gc_config)
    rob_cfg = protocol["robustness_margins"]
    rob = gate_res["robustness"]
    margin_checks = {}
    exec_drop = rob.get("exec_drop_pp")
    fee_drag = rob.get("fee_drag_pp")
    dd_margin = rob.get("dd_margin")
    margin_checks["exec_drop_le_limit"] = {
        "value": exec_drop,
        "limit": rob_cfg["max_exec_drop_pp"]["value"],
        "pass": (exec_drop is not None
                 and exec_drop <= rob_cfg["max_exec_drop_pp"]["value"]),
    }
    margin_checks["fee_drag_le_limit"] = {
        "value": fee_drag,
        "limit": rob_cfg["max_fee_drag_pp"]["value"],
        "pass": (fee_drag is not None
                 and fee_drag <= rob_cfg["max_fee_drag_pp"]["value"]),
    }
    margin_checks["dd_margin_ge_limit"] = {
        "value": dd_margin,
        "limit": rob_cfg["min_dd_margin_pp"]["value"],
        "pass": (dd_margin is not None
                 and dd_margin >= rob_cfg["min_dd_margin_pp"]["value"]),
    }
    margins_pass = all(v["pass"] for v in margin_checks.values())
    fwd_mo = (gate_res["robustness"].get("normal_monthly")
              or gate_res["gate"]["per_scenario"].get("normal", {}).get(
                  "monthly_geometric_net"))
    ratio_min = protocol["degradation_vs_backtest"][
        "forward_monthly_ge_backtest_ratio_min"]["value"]
    if backtest_monthly is not None and backtest_monthly > 0 \
            and isinstance(fwd_mo, (int, float)):
        ratio = float(fwd_mo) / float(backtest_monthly)
        degradation_pass = ratio >= ratio_min
    else:
        ratio, degradation_pass = None, False
    months_need = protocol["forward_window"]["min_forward_months"]["value"]
    months_pass = span["n_months"] >= months_need
    gate_pass = bool(gate_res["gate"]["overall_pass"])
    conc_diffuse = gate_res["concentration"]["verdict"].startswith("diffuse")
    total_net = gate_res["concentration"].get("total_net")
    reasons = list(gate_res.get("decision_reasons", []))
    if not months_pass:
        reasons.append(f"forward-months-short({span['n_months']}/{months_need})")
    if not margins_pass:
        bad = sorted(k for k, v in margin_checks.items() if not v["pass"])
        reasons.append("robustness-margin-fail")
        reasons.extend(f"robustness-margin-fail({b})" for b in bad)
    if not degradation_pass:
        reasons.append(
            f"degradation-fail(ratio={ratio:.3f} < {ratio_min})"
            if ratio is not None else "degradation-fail(no positive base)")
    if gate_pass and conc_diffuse and margins_pass and months_pass \
            and degradation_pass and (total_net or 0) > 0:
        decision = "PROMOTE_CANDIDATE"
    elif ("fills-fail" in gate_res["gate"]["fail_reasons"]
          or not conc_diffuse or not ((total_net or 0) > 0)):
        decision = "REJECT"
    else:
        decision = "HOLD"
    return {"status": "READY", "span": span,
            "gatecheck": {"decision": gate_res["decision"],
                          "decision_line": gate_res["decision_line"],
                          "gate": gate_res["gate"],
                          "concentration": gate_res["concentration"],
                          "robustness": gate_res["robustness"]},
            "margin_checks": margin_checks, "margins_pass": margins_pass,
            "backtest_normal_monthly": backtest_monthly,
            "forward_normal_monthly": fwd_mo,
            "degradation_ratio": ratio,
            "degradation_ratio_min": ratio_min,
            "degradation_pass": degradation_pass,
            "months_pass": months_pass,
            "forward_decision": decision, "forward_reasons": reasons}


def _fmt_pct(value) -> str:
    """Crash-safe percent formatting (None -> 'n/a'; losing books have None)."""
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_share(value) -> str:
    """Crash-safe share formatting (None -> 'n/a')."""
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_gini(value) -> str:
    """Crash-safe gini formatting (None on non-positive base -> 'n/a')."""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "n/a"


def eval_forward_only(fwd_summary: Path, fwd_trades: Path,
                      branch: str | None, protocol: dict,
                      gc_config: dict, cutoff: pd.Timestamp) -> dict:
    """Forward-only verdict for first-forward policies (no frozen in-sample leg).

    NEW in v1.1.0: when NO same-policy frozen in-sample leg exists, READY is
    impossible without a second metrics pass, so this path gates the forward
    window ALONE (same research gate + concentration + robustness margins +
    min months as READY) and returns status FORWARD_ONLY with
    in_sample_baseline NO-IN-SAMPLE-BASELINE. Degradation is skipped
    (no ratio). The verdict caps at HOLD max and can NEVER promote:
    a would-be PROMOTE_CANDIDATE is capped to HOLD with an explicit
    forward-only-cap reason. Crash-safe on losing books (safe formatting;
    never calls the winning-book-only decision_line path).
    """
    span = forward_month_span(fwd_trades)
    if pd.Timestamp(span["min_exit"]) <= cutoff:
        raise ValueError(
            f"REFUSED: forward window starts {span['min_exit']} which is on/before "
            f"the frozen cutoff {cutoff}. Forward on already-opened dates is "
            "in-sample relabeling (research rule 5), not validation. "
            "This run writes no verdict.")
    summary = load_json(Path(fwd_summary))
    try:
        n_trades = int(pd.read_csv(fwd_trades, usecols=["net_pnl"]).shape[0])
    except Exception:
        n_trades = None
    branch_name = GC.pick_branch(summary, branch, n_trades)
    scenarios = GC.scenario_dicts(summary["branches"][branch_name])
    per, overall, gate_reasons = GC.check_gate(scenarios, gc_config["gate"])
    conc = GC.analyze_concentration(Path(fwd_trades),
                                    gc_config["concentration_rule"])
    rob = GC.analyze_robustness(scenarios, summary, gc_config["robustness"],
                                gc_config["gate"])
    rob_cfg = protocol["robustness_margins"]
    margin_checks = {}
    exec_drop = rob.get("exec_drop_pp")
    fee_drag = rob.get("fee_drag_pp")
    dd_margin = rob.get("dd_margin")
    margin_checks["exec_drop_le_limit"] = {
        "value": exec_drop,
        "limit": rob_cfg["max_exec_drop_pp"]["value"],
        "pass": (exec_drop is not None
                 and exec_drop <= rob_cfg["max_exec_drop_pp"]["value"]),
    }
    margin_checks["fee_drag_le_limit"] = {
        "value": fee_drag,
        "limit": rob_cfg["max_fee_drag_pp"]["value"],
        "pass": (fee_drag is not None
                 and fee_drag <= rob_cfg["max_fee_drag_pp"]["value"]),
    }
    margin_checks["dd_margin_ge_limit"] = {
        "value": dd_margin,
        "limit": rob_cfg["min_dd_margin_pp"]["value"],
        "pass": (dd_margin is not None
                 and dd_margin >= rob_cfg["min_dd_margin_pp"]["value"]),
    }
    margins_pass = all(v["pass"] for v in margin_checks.values())
    months_need = protocol["forward_window"]["min_forward_months"]["value"]
    months_pass = span["n_months"] >= months_need
    gate_pass = bool(overall)
    conc_diffuse = str(conc.get("verdict", "")).startswith("diffuse")
    total_net = conc.get("total_net")
    fwd_mo = rob.get("normal_monthly")
    if fwd_mo is None:
        fwd_mo = per.get("normal", {}).get("monthly_geometric_net")
    _, gc_reasons = GC.decide(overall, gate_reasons, conc,
                                 gc_config["trade_concentration_notes"],
                                 gc_config.get("decision_rule", {}))
    reasons = list(gc_reasons)
    reasons.append("NO-IN-SAMPLE-BASELINE(degradation skipped: no same-policy "
                   "frozen leg; forward judged alone)")
    if not months_pass:
        reasons.append(f"forward-months-short({span['n_months']}/{months_need})")
    if not margins_pass:
        bad = sorted(k for k, v in margin_checks.items() if not v["pass"])
        reasons.append("robustness-margin-fail")
        reasons.extend(f"robustness-margin-fail({b})" for b in bad)
    if gate_pass and conc_diffuse and margins_pass and months_pass \
            and (total_net or 0) > 0:
        decision = "HOLD"
        reasons.append("forward-only-cap(never PROMOTE without in-sample "
                       "baseline; capped at HOLD max)")
    elif ("fills-fail" in gate_reasons
          or not conc_diffuse or not ((total_net or 0) > 0)):
        decision = "REJECT"
    else:
        decision = "HOLD"
    safe_line = (
        f"{decision} -- {branch_name} [FORWARD_ONLY/NO-IN-SAMPLE-BASELINE]: "
        f"gate {'PASS' if overall else 'FAIL'} [{'; '.join(gate_reasons) or 'clean'}]; "
        f"concentration {conc.get('verdict')} "
        f"(top1mo={_fmt_share(conc.get('top1_month_share'))}, "
        f"top3mo={_fmt_share(conc.get('top3_months_share'))}, "
        f"top5tr={_fmt_share(conc.get('top5_trades_share'))}, "
        f"gini={_fmt_gini(conc.get('gini_monthly_net'))}); "
        f"fwd_mo={_fmt_pct(fwd_mo)}; "
        f"margins={'PASS' if margins_pass else 'FAIL'}; "
        f"months={span['n_months']}/{months_need}; capped at HOLD max.")
    return {"status": "FORWARD_ONLY",
            "in_sample_baseline": "NO-IN-SAMPLE-BASELINE",
            "span": span,
            "branch": branch_name,
            "gatecheck": {"decision": ("REJECT" if decision == "REJECT" else "HOLD"),
                          "decision_line": safe_line,
                          "gate": {"thresholds": gc_config["gate"],
                                   "per_scenario": per,
                                   "overall_pass": overall,
                                   "fail_reasons": gate_reasons},
                          "concentration": conc,
                          "robustness": rob},
            "margin_checks": margin_checks, "margins_pass": margins_pass,
            "backtest_normal_monthly": None,
            "forward_normal_monthly": fwd_mo,
            "degradation_ratio": None,
            "degradation_ratio_min": None,
            "degradation_pass": None,
            "months_pass": months_pass,
            "forward_decision": decision, "forward_reasons": reasons}


def run_forward_only(forward_summary: Path, forward_trades: Path,
                     branch: str | None, paper_paths: list,
                     protocol: dict, gc_config: dict,
                     forward_start: str | None = None) -> dict:
    """Top-level forward-only runner (no frozen leg; never PROMOTE)."""
    cutoff = frozen_cutoff(protocol)
    if forward_start is not None:
        start = pd.Timestamp(forward_start, tz="UTC")
        if start <= cutoff:
            raise ValueError(
                f"REFUSED: --forward-start {start.date()} is on/before the frozen "
                f"cutoff {cutoff.date()}. Those dates are already opened (research "
                "rule 5: once inspected, an interval becomes research data). "
                "Forward validation requires NEW data after "
                f"{cutoff.date()}; this run writes no verdict.")
    if not (forward_summary and forward_trades):
        raise ValueError("forward-only needs BOTH --forward-summary and "
                         "--forward-trades on new data strictly after the cutoff.")
    forward = eval_forward_only(forward_summary, forward_trades, branch,
                                protocol, gc_config, cutoff)
    paper = eval_paper(paper_paths, protocol)
    reasons = list(forward["forward_reasons"])
    if paper["paper_overall"] != "green":
        missing = sorted(k for k, v in paper["checks"].items()
                         if v["status"] != "PASS")
        reasons.append("paper-not-green")
        reasons.extend(f"paper-not-green({m})" for m in missing)
    decision = forward["forward_decision"]
    assert decision in ("HOLD", "REJECT"), \
        "forward-only must never PROMOTE (capped at HOLD max)"
    branch_name = forward["branch"]
    line = (f"{decision} -- {branch_name}: "
            f"in-sample NO-IN-SAMPLE-BASELINE (no same-policy frozen leg; "
            f"forward judged alone, capped at HOLD max); "
            f"forward FORWARD_ONLY -> {forward['forward_decision']} "
            f"[{'; '.join(forward['forward_reasons'])}]"
            f"; paper {paper['paper_overall']}.")
    return {
        "tool": "opencode_forward_test",
        "version": protocol.get("version", "1.0.0"),
        "mode": "FORWARD_ONLY",
        "protocol": str(DEFAULT_PROTOCOL),
        "inputs": {"summary": None, "branch": branch_name,
                   "trades": None, "signals": None,
                   "backtest_config": None,
                   "plan_sha256": None,
                   "plan_declares_branch": None,
                   "paper_summaries": [str(p) for p in (paper_paths or [])],
                   "forward_summary": str(forward_summary),
                   "forward_trades": str(forward_trades),
                   "forward_start": forward_start,
                   "forward_only": True},
        "data_freeze": {"cutoff_exclusive":
                        protocol["data_freeze"]["frozen_data_end_exclusive"],
                        "freeze_audit": "SKIPPED (forward-only: no frozen leg; "
                                        "forward window audited strictly after cutoff)"},
        "in_sample": {"role": "NO-IN-SAMPLE-BASELINE",
                      "decision": "NO-IN-SAMPLE-BASELINE",
                      "note": "No same-policy frozen leg exists; degradation "
                              "skipped; PROMOTE impossible in this mode."},
        "forward": forward,
        "paper_rehearsal": paper,
        "handoff_checklist": protocol["handoff_checklist"],
        "decision": decision,
        "decision_reasons": reasons,
        "decision_line": line,
        "warnings": protocol.get("warnings", []),
    }


def decide(insample: dict, forward: dict, paper: dict) -> tuple[str, list]:
    """Final promotion decision. PROMOTE only via a READY forward + green paper.

    FORWARD_ONLY (no same-policy frozen leg) caps at HOLD max and never
    PROMOTEs; the forward_decision itself is already capped by
    eval_forward_only/run_forward_only.
    """
    if forward["status"] == "FORWARD_ONLY":
        reasons = list(forward.get("forward_reasons", []))
        if paper["paper_overall"] != "green":
            missing = sorted(k for k, v in paper["checks"].items()
                             if v["status"] != "PASS")
            reasons.append("paper-not-green")
            reasons.extend(f"paper-not-green({m})" for m in missing)
        decision = forward.get("forward_decision", "HOLD")
        assert decision in ("HOLD", "REJECT"), \
            "forward-only must never PROMOTE (capped at HOLD max)"
        return decision, reasons
    if forward["status"] == "READY":
        if forward["forward_decision"] == "PROMOTE_CANDIDATE" \
                and paper["paper_overall"] == "green":
            return "PROMOTE", ["forward gate+concentration+robustness PASS",
                               "forward months + degradation PASS",
                               "paper rehearsal green (all six checks)"]
        reasons = list(forward["forward_reasons"])
        if paper["paper_overall"] != "green":
            missing = sorted(k for k, v in paper["checks"].items()
                             if v["status"] != "PASS")
            reasons.append("paper-not-green")
            reasons.extend(f"paper-not-green({m})" for m in missing)
        return forward["forward_decision"], reasons
    blocked_reason = forward.get("blocked_reason", "FORWARD_BLOCKED")
    if insample["decision"] == "REJECT":
        return "REJECT", insample["decision_reasons"] + [blocked_reason]
    return "HOLD", insample["decision_reasons"] + [blocked_reason]


def run(summary_path: Path, trades_path: Path, branch: str | None,
        signals_path: Path, backtest_config_path: Path,
        paper_paths: list, protocol: dict, gc_config: dict,
        forward_summary: Path | None = None,
        forward_trades: Path | None = None,
        forward_start: str | None = None) -> dict:
    cutoff = frozen_cutoff(protocol)
    if forward_start is not None:
        start = pd.Timestamp(forward_start, tz="UTC")
        if start <= cutoff:
            raise ValueError(
                f"REFUSED: --forward-start {start.date()} is on/before the frozen "
                f"cutoff {cutoff.date()}. Those dates are already opened (research "
                "rule 5: once inspected, an interval becomes research data). "
                "Forward validation requires NEW data after "
                f"{cutoff.date()}; this run writes no verdict.")
    if bool(forward_summary) != bool(forward_trades):
        raise ValueError("forward needs BOTH --forward-summary and --forward-trades "
                         "(or neither for a BLOCKED in-sample-only verdict).")
    freeze_audit = audit_frozen_timestamps(signals_path, trades_path, cutoff)
    insample = GC.run(summary_path, trades_path, branch, None, gc_config)
    try:
        backtest_cfg = load_json(backtest_config_path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"backtest config unreadable: {exc}")
    plan_sha = sha256_file(backtest_config_path)
    branches_declared = backtest_cfg.get("branches")
    branch_name = insample["inputs"]["branch"]
    plan_declares_branch = (branch_name in branches_declared
                            if isinstance(branches_declared, list) else None)
    backtest_mo = insample["robustness"].get("normal_monthly")
    if backtest_mo is None:
        backtest_mo = insample["gate"]["per_scenario"].get("normal", {}).get(
            "monthly_geometric_net")
    if forward_summary is not None:
        forward = eval_forward(forward_summary, forward_trades,
                               branch, backtest_mo, protocol, gc_config, cutoff)
    else:
        forward = {
            "status": "FORWARD_BLOCKED",
            "blocked_reason": (
                "FORWARD_BLOCKED(no new data: current data ends "
                f"{protocol['data_freeze']['frozen_data_end_exclusive']}; "
                "forward requires --forward-summary + --forward-trades on "
                "candles strictly after the cutoff)"),
        }
    paper = eval_paper(paper_paths, protocol)
    decision, reasons = decide(insample, forward, paper)
    line = (f"{decision} -- {branch_name}: "
            f"in-sample {insample['decision']} "
            f"[{'; '.join(insample['decision_reasons']) or 'clean'}] (reference only); "
            f"forward {forward['status']}"
            + (f" -> {forward['forward_decision']} "
               f"[{'; '.join(forward['forward_reasons'])}]"
               if forward['status'] == 'READY' else
               f" [{forward['blocked_reason']}]")
            + f"; paper {paper['paper_overall']}.")
    return {
        "tool": "opencode_forward_test",
        "version": protocol.get("version", "1.0.0"),
        "protocol": str(DEFAULT_PROTOCOL),
        "inputs": {"summary": str(summary_path), "branch": branch_name,
                   "trades": str(trades_path), "signals": str(signals_path),
                   "backtest_config": str(backtest_config_path),
                   "plan_sha256": plan_sha,
                   "plan_declares_branch": plan_declares_branch,
                   "paper_summaries": [str(p) for p in (paper_paths or [])],
                   "forward_summary": str(forward_summary)
                   if forward_summary else None,
                   "forward_trades": str(forward_trades)
                   if forward_trades else None,
                   "forward_start": forward_start},
        "data_freeze": {"cutoff_exclusive":
                        protocol["data_freeze"]["frozen_data_end_exclusive"],
                        "freeze_audit": freeze_audit},
        "in_sample": {"role": "reference only",
                      "decision": insample["decision"],
                      "decision_line": insample["decision_line"],
                      "gate": insample["gate"],
                      "concentration": insample["concentration"],
                      "robustness": insample["robustness"]},
        "forward": forward,
        "paper_rehearsal": paper,
        "handoff_checklist": protocol["handoff_checklist"],
        "decision": decision,
        "decision_reasons": reasons,
        "decision_line": line,
        "warnings": protocol.get("warnings", []),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Forward-validation verdict for one frozen branch "
                    "(in-sample reference + forward window + paper checklist). "
                    "Use --forward-only when NO same-policy frozen in-sample leg "
                    "exists: gates the forward window alone (FORWARD_ONLY, "
                    "NO-IN-SAMPLE-BASELINE, capped at HOLD max).")
    parser.add_argument("--summary", type=Path, required=False, default=None)
    parser.add_argument("--trades", type=Path, required=False, default=None)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--signals", type=Path, required=False, default=None)
    parser.add_argument("--backtest-config", type=Path, required=False,
                        default=None)
    parser.add_argument("--paper-summary", action="append", default=[],
                        help="paper rehearsal summary (repeat for drill + resume proof)")
    parser.add_argument("--forward-summary", type=Path, default=None)
    parser.add_argument("--forward-trades", type=Path, default=None)
    parser.add_argument("--forward-start", default=None,
                        help="proposed forward start YYYY-MM-DD (refused if opened)")
    parser.add_argument("--forward-only", action="store_true", default=False,
                        help="forward-only verdict: no frozen in-sample leg; "
                             "gate forward window alone, NO-IN-SAMPLE-BASELINE, "
                             "capped at HOLD max (never PROMOTE)")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--gatecheck-config", type=Path, default=DEFAULT_GATECHECK)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        protocol = load_json(args.protocol)
        gc_config = load_json(args.gatecheck_config)
        if args.forward_only:
            result = run_forward_only(args.forward_summary, args.forward_trades,
                                      args.branch, args.paper_summary, protocol,
                                      gc_config, args.forward_start)
        else:
            missing = [n for n, v in
                       (("--summary", args.summary), ("--trades", args.trades),
                        ("--signals", args.signals),
                        ("--backtest-config", args.backtest_config)) if v is None]
            if missing:
                raise ValueError(
                    "missing required frozen-leg inputs "
                    f"({', '.join(missing)}); pass --forward-only to judge a "
                    "forward window with no same-policy frozen leg.")
            result = run(args.summary, args.trades, args.branch, args.signals,
                         args.backtest_config, args.paper_summary, protocol,
                         gc_config, args.forward_summary, args.forward_trades,
                         args.forward_start)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    ins = result["in_sample"]
    fwd = result["forward"]
    pap = result["paper_rehearsal"]
    plan_sha = result["inputs"].get("plan_sha256")
    plan_decl = result["inputs"].get("plan_declares_branch")
    print(f"branch: {result['inputs']['branch']} "
          f"(plan_sha={(plan_sha[:12] + '..') if plan_sha else 'n/a'}, "
          f"plan_declares_branch={plan_decl})")
    freeze_audit = result["data_freeze"].get("freeze_audit")
    if isinstance(freeze_audit, dict):
        print(f"freeze: cutoff {result['data_freeze']['cutoff_exclusive']} "
              f"(signals_max={freeze_audit.get('signals_max')}, "
              f"trades_max={freeze_audit.get('trades_max_exit')})")
    else:
        print(f"freeze: cutoff {result['data_freeze']['cutoff_exclusive']} "
              f"({freeze_audit})")
    print(f"in-sample (reference): {ins['decision']} [{'; '.join(result['decision_reasons'][:4])}]"
          if result["decision_reasons"] else f"in-sample (reference): {ins['decision']}")
    if fwd["status"] == "READY":
        print(f"forward: {fwd['span']['min_exit']} -> {fwd['span']['max_exit']} "
              f"({fwd['span']['n_months']} months); "
              f"mo_ratio={fwd['degradation_ratio']:.3f} "
              f"(min {fwd['degradation_ratio_min']}); "
              f"margins={'PASS' if fwd['margins_pass'] else 'FAIL'}; "
              f"decision={fwd['forward_decision']}")
    elif fwd["status"] == "FORWARD_ONLY":
        print(f"forward: FORWARD_ONLY {fwd['span']['min_exit']} -> "
              f"{fwd['span']['max_exit']} ({fwd['span']['n_months']} months); "
              f"baseline={fwd['in_sample_baseline']}; "
              f"fwd_mo={(fwd['forward_normal_monthly'] * 100 if isinstance(fwd['forward_normal_monthly'], (int, float)) else float('nan')):.3f}%; "
              f"margins={'PASS' if fwd['margins_pass'] else 'FAIL'}; "
              f"decision={fwd['forward_decision']} (capped at HOLD max)")
    else:
        print(f"forward: {fwd['status']} -- {fwd['blocked_reason']}")
    for name in PAPER_REQUIRED_CHECKS:
        c = pap["checks"][name]
        print(f"paper.{name}: {c['status']} ({c['detail']})")
    print(f"paper_overall: {pap['paper_overall']}")
    print(result["decision_line"])
    if args.out is not None:
        if args.out.exists():
            print(f"ERROR: refusing to overwrite existing {args.out}",
                  file=sys.stderr)
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
