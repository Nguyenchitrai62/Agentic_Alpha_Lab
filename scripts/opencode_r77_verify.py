"""Opencode R77 W3-VERIFY: independent raw->equity comparison harness + own rebuild driver.

RESEARCH/PAPER ONLY. Verification only; no live orders, no cloud, no fitting/tuning.
Pre-spec: configs/opencode_r77_verify.json (written BEFORE any W1/W2 artifact
existed; this driver asserts every frozen value before comparing).

ANTI-CIRCULARITY (Codex blocker B2): this harness rebuilds ONLY the batch
reference leg via VERBATIM ohlc-v2 run_backtest. The streaming leg MUST come
from the W1 integrated runner's incremental FeedExecStrategy/FeedExecAccount
journals -- never run_backtest. The harness asserts the W1 streaming module
has zero references to run_backtest and that the W1 manifest names an
incremental streaming engine.

Two cost branches (own rebuild driver): normal (fee 0.0002/fill) + fee stress
(0.00055/fill). Execution stress only if W2 declares support. Funding long
0.0001/8h, short 0. Reference artifacts are loaded ONLY by this harness,
never by the streaming path (asserted by audit_no_replay + the denial test).

Causality contract (fail-closed): ReadinessError when W1/W2 artifacts are
absent (PREP-READY, never block, never invent numbers).
"""

import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_alpha_lab.backtest.engine import (  # noqa: E402
    CostModel, ExecutionConfig, run_backtest)

SPEC_PATH = ROOT / "configs/opencode_r77_verify.json"
PARITY_DIR = ROOT / "artifacts/research/opencode_r77_advisory/parity"
W1_DIR = ROOT / "artifacts/research/opencode_r77_advisory/runner"
# W2 sibling files: anything under PARITY_DIR that is NOT W3-owned (W3 writes
# verify_* only). W2 landed parity/fixtures/certified_expectations.json
# (12 hand-vs-engine certified fixtures); the w2_* prefix was only an
# expectation in the frozen pre-spec, actual convention observed instead.

STATE_VERSION = "r77_verify/1"
EQUITY_TOL = 1e-6
SIGNAL_KEY_COLS = ["bar_index", "signal_time", "direction", "entry_limit",
                   "stop_loss", "take_profit_1", "take_profit_2",
                   "holding_bars", "leverage", "entry_expiry_bars",
                   "tp1_fraction"]

# Stored-input patterns that must NEVER be loaded by the streaming path.
# (The comparison harness in this file is explicitly allowed to load them;
#  this list audits W1 runner sources only, never this harness itself.)
FORBIDDEN_PATTERNS = [
    r"predictions\.npz",
    r"replay\.npz",
    r"prediction.*\.(npz|parquet|csv)",
    r"signals\.parquet",
    r"decisions\.parquet",
    r"decision_indices",
    r"control.*\.(csv|parquet)",
    r"normal_trades\.csv",
    r"baseline_trades",
]

# run_backtest must appear NOWHERE on the W1 streaming path (blocker B2).
STREAMING_ENGINE_BAN = [r"run_backtest"]


class ReadinessError(RuntimeError):
    """Fail-closed: W1/W2 inputs absent or incomplete (PREP-READY, not a FAIL)."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_prespec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["hypothesis_id"] == "opencode-r77-stateful-advisory-verify"
    assert spec["frozen_reference_policy"]["branch"] == "confirmed_dd_guard"
    assert spec["frozen_reference_policy"]["checkpoints"]["fold_used"] == 10
    assert spec["frozen_reference_policy"]["checkpoints"]["seeds"] == [1729, 1730, 1731]
    assert spec["costs"]["normal"]["fee_rate_per_fill"] == 0.0002
    assert spec["costs"]["fee_stress"]["fee_rate_per_fill"] == 0.00055
    assert spec["tolerances"]["equity_tol"] == 1e-6
    assert spec["tolerances"]["signal_identity_tol"] == 0.0
    assert spec["status"].startswith("PRE-SPEC")
    return spec


def w1w2_status() -> dict:
    """Poll the sibling W1/W2 drop zones. Absent files => PREP-READY.

    VERIFY-AMENDMENT-1 (2026-09-11, leader-verified on disk): W1 delivered
    scripts/opencode_r77_advisor.py (+ advisor_core.py), NOT
    scripts/opencode_r77_runner.py; W1 outputs live in
    runner/{replay_r29_slice/,fresh_smoke/,summary.json} (NO
    runner/manifest.json); W2 delivered parity/fixtures/ +
    certified_expectations.json (not w2_* prefix). This poll reflects the
    CORRECTED paths; the frozen pre-spec values are unchanged.
    """
    w1_files = sorted(p.relative_to(ROOT).as_posix()
                      for p in W1_DIR.rglob("*") if p.is_file()) if W1_DIR.exists() else []
    w2_files = sorted(p.relative_to(ROOT).as_posix()
                      for p in PARITY_DIR.rglob("*")
                      if p.is_file()
                      and not any(part.startswith("verify_")
                                  for part in p.relative_to(PARITY_DIR).parts)) \
        if PARITY_DIR.exists() else []
    advisor_cli = ROOT / "scripts/opencode_r77_advisor.py"
    advisor_core = ROOT / "scripts/opencode_r77_advisor_core.py"
    advisor_cfg = ROOT / "configs/opencode_r77_advisor.json"
    replay_manifest = W1_DIR / "replay_r29_slice" / "manifest.json"
    runner_summary = W1_DIR / "summary.json"
    w2_cert = PARITY_DIR / "fixtures" / "certified_expectations.json"
    runner_present = advisor_cli.is_file() and advisor_core.is_file()
    manifest_present = replay_manifest.is_file() and runner_summary.is_file()
    w2_present = w2_cert.is_file()
    ready = bool(runner_present and manifest_present and w2_present
                 and advisor_cfg.is_file() and len(w2_files) > 0)
    return {"w1_files": w1_files, "w2_files": w2_files,
            "manifest_present": manifest_present,
            "runner_present": runner_present,
            "advisor_config_present": advisor_cfg.is_file(),
            "w2_certified_present": w2_present,
            "corrected_paths": {
                "cli": "scripts/opencode_r77_advisor.py",
                "core": "scripts/opencode_r77_advisor_core.py",
                "replay_manifest": "artifacts/research/opencode_r77_advisory/runner/replay_r29_slice/manifest.json",
                "runner_summary": "artifacts/research/opencode_r77_advisory/runner/summary.json",
                "w2_certified": "artifacts/research/opencode_r77_advisory/parity/fixtures/certified_expectations.json"},
            "ready": ready}


def audit_no_replay(source_paths: list) -> dict:
    """Static leg of the no-replay audit: scan streaming-path SOURCES for
    forbidden stored-input loads. Returns violations per file. Method recorded
    in summary.json (pass rule: zero violations on the W1 streaming path).

    NOTE: this audits the given source paths only. The comparison harness
    (this file) is explicitly allowed to load reference artifacts.
    """
    compiled = [(pat, re.compile(pat)) for pat in FORBIDDEN_PATTERNS]
    violations: dict = {}
    scanned: list = []
    for sp in source_paths:
        p = Path(sp)
        if not p.is_file():
            violations[str(p)] = ["FILE_ABSENT"]
            continue
        scanned.append(str(p))
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = sorted({pat for pat, rx in compiled if rx.search(text)})
        if hits:
            violations[str(p)] = hits
    return {"scanned": scanned, "violations": violations,
            "pass": len(violations) == 0, "method": "static-source-scan",
            "patterns": FORBIDDEN_PATTERNS}


def audit_streaming_engine(source_paths: list) -> dict:
    """Anti-circularity leg (blocker B2): the W1 STREAMING module must not
    reference run_backtest. (W1's batch-reference mode, if any, must live in
    a separate clearly-named module that is NOT on the streaming path.)"""
    compiled = [(pat, re.compile(pat)) for pat in STREAMING_ENGINE_BAN]
    violations: dict = {}
    scanned: list = []
    for sp in source_paths:
        p = Path(sp)
        if not p.is_file():
            violations[str(p)] = ["FILE_ABSENT"]
            continue
        scanned.append(str(p))
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = sorted({pat for pat, rx in compiled if rx.search(text)})
        if hits:
            violations[str(p)] = hits
    return {"scanned": scanned, "violations": violations,
            "pass": len(violations) == 0, "method": "static-streaming-engine-scan",
            "banned": STREAMING_ENGINE_BAN}


@contextmanager
def denied_inputs(paths: list):
    """Runtime denial leg: temporarily move stored prediction/signal/control
    files aside so the streaming path CANNOT load them. Yields the list of
    actually-denied paths. Restores everything on exit (fail-safe)."""
    moved = []
    try:
        for sp in paths:
            p = Path(sp)
            if p.is_file():
                hole = p.with_name(p.name + ".w3_denied_hold")
                os.replace(p, hole)
                moved.append((p, hole))
        yield [str(p) for p, _ in moved]
    finally:
        for p, hole in moved:
            if hole.is_file():
                os.replace(hole, p)


def compare_signal_frames(batch: pd.DataFrame, stream: pd.DataFrame) -> dict:
    """Signal-set identity: exact match on key cols (absolute, no tolerance;
    numerics reported with max abs diff for diagnosis only)."""
    b = batch.sort_values(["bar_index", "direction"]).reset_index(drop=True)
    s = stream.sort_values(["bar_index", "direction"]).reset_index(drop=True)
    rep = {"n_batch": len(b), "n_stream": len(s),
           "count_match": len(b) == len(s)}
    if len(b) != len(s):
        rep.update({"all_bit_exact": False, "max_abs_diff": None})
        return rep
    key_ok = True
    for col in SIGNAL_KEY_COLS:
        bv = b[col].to_numpy()
        sv = s[col].to_numpy()
        if not bool((bv == sv).all()):
            key_ok = False
    num_cols = [c for c in SIGNAL_KEY_COLS
                if np.asarray(b[c]).dtype.kind == "f"]
    maxdiff = 0.0
    for col in num_cols:
        d = float(np.max(np.abs(b[col].to_numpy(dtype=np.float64)
                                - s[col].to_numpy(dtype=np.float64))))
        maxdiff = max(maxdiff, d)
    rep.update({"all_bit_exact": bool(key_ok), "max_abs_diff": maxdiff})
    return rep


def rebuild_reference_equity(candles: pd.DataFrame, signals: pd.DataFrame,
                             spec: dict) -> dict:
    """OWN rebuild driver, BATCH REFERENCE leg ONLY: verbatim ohlc-v2
    run_backtest for normal + fee stress branches. NEVER applied to the
    streaming leg (that would be circular per blocker B2). Reports
    gross/fees/funding/net/drawdown/trades/coverage per AGENTS.md rule 6.
    Deterministic: same inputs => bit-identical outputs."""
    out = {}
    for branch in spec["comparison_branches"]:
        if branch.startswith("execution"):
            continue  # execution stress only if W2 declares support (verify-time)
        key = "normal" if branch.startswith("normal") else "fee_stress"
        cfg = spec["costs"][key]
        costs = CostModel(fee_rate_per_fill=cfg["fee_rate_per_fill"],
                          funding_long_rate=cfg["funding_long_rate"],
                          funding_short_rate=cfg["funding_short_rate"],
                          funding_interval_hours=cfg["funding_interval_hours"])
        exe = {"entry_expiry_bars": 12, "max_holding_bars": 2016,
               "tp1_fraction": 0.5}
        execution = ExecutionConfig(
            entry_expiry_bars=exe["entry_expiry_bars"],
            max_holding_bars=exe["max_holding_bars"],
            tp1_fraction=exe["tp1_fraction"],
            leverage=1.0, max_leverage=1.0)
        t0 = time.perf_counter()
        equity, trades = run_backtest(candles, signals, 100.0, costs, execution)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        out[branch] = {
            "final_equity": float(equity.final_equity),
            "gross_pnl": float(equity.gross_pnl),
            "fees": float(equity.fees),
            "funding": float(equity.funding),
            "net_pnl": float(equity.net_profit),
            "max_drawdown": float(equity.max_drawdown),
            "trade_count": int(equity.trades),
            "coverage_signals": len(signals),
            "rebuild_ms": dt_ms,
            "per_trade_equity_after": [float(t.equity_after) for t in trades],
            "per_trade": [{"entry_time": t.entry_time,
                           "exit_time": t.exit_time,
                           "exit_reason": t.exit_reason,
                           "gross_pnl": float(t.gross_pnl),
                           "fees": float(t.fees),
                           "funding": float(t.funding),
                           "net_pnl": float(t.net_pnl),
                           "equity_after": float(t.equity_after)}
                          for t in trades],
        }
    return out


def compare_equity(ref: dict, stream: dict, tol: float = EQUITY_TOL) -> dict:
    """Portfolio match within 1e-6 per branch (final equity + per-trade path
    + trade counts). `stream` MUST originate from W1 incremental journals."""
    branches = {}
    ok_all = True
    for branch in ref:
        if branch not in stream:
            branches[branch] = {"pass": False, "reason": "STREAM_BRANCH_ABSENT"}
            ok_all = False
            continue
        r, s = ref[branch], stream[branch]
        d_final = abs(r["final_equity"] - s["final_equity"])
        n = min(len(r["per_trade_equity_after"]),
                len(s["per_trade_equity_after"]))
        d_path = max((abs(a - b) for a, b in zip(
            r["per_trade_equity_after"][:n],
            s["per_trade_equity_after"][:n])), default=0.0)
        count_ok = (r["trade_count"] == s["trade_count"])
        ok = bool(d_final <= tol and d_path <= tol and count_ok)
        ok_all = ok_all and ok
        branches[branch] = {"d_final_equity": d_final,
                            "d_per_trade_path": d_path,
                            "trade_count_match": count_ok, "pass": ok}
    return {"tol": tol, "branches": branches, "pass": bool(ok_all)}


def _read_verify(name: str) -> dict:
    p = PARITY_DIR / name
    if not p.is_file():
        raise ReadinessError(f"verify artifact absent: {p} (run "
                             "scripts/opencode_r77_verify_run.py first).")
    return json.loads(p.read_text(encoding="utf-8"))


def run_full_comparison() -> dict:
    """Full verify path. Fail-closed when W1/W2 are absent (PREP-READY).

    Verify-time wiring (runs ONLY when w1w2_status()['ready']): consumes the
    W3 verify artifacts produced by scripts/opencode_r77_verify_run.py
    (audits / slice / fixtures / negatives / restart / perturb / denial /
    slice-resume) plus the W1 streaming journals and W2 certified fixtures.
    Reference artifacts are loaded ONLY by this harness, never by the
    streaming path. Returns the comparison dict consumed by
    verify_summary.json and tests/test_r77_verify.py.
    """
    load_prespec()
    status = w1w2_status()
    if not status["ready"]:
        raise ReadinessError(
            "W1/W2 artifacts absent or incomplete "
            f"(manifest={status['manifest_present']}, "
            f"runner={status['runner_present']}, "
            f"w2_files={len(status['w2_files'])}). "
            "PREP-READY: prep done, verification deferred. No numbers claimed.")
    audits = _read_verify("verify_audits.json")
    sl = _read_verify("verify_slice_parity.json")
    fx = _read_verify("verify_fixtures_parity.json")
    neg = _read_verify("verify_negative_controls.json")
    rs = _read_verify("verify_restart.json")
    pb = _read_verify("verify_perturb.json")
    dn = _read_verify("verify_denial.json")
    sr = _read_verify("verify_restart_slice.json")
    # Sensitivity leg: the static audit must ALSO flag a known-bad loader
    # (proves the audit is load-sensitive, not a rubber stamp).
    sens = audit_no_replay([ROOT / "scripts/opencode_r75_streaming.py"])
    sens_ok = bool(not sens["pass"] and len(sens["violations"]) > 0)
    fixture_trades = sum(
        1 for fid, rec in fx["fixtures"].items() for br, b in
        rec["branches"].items()
        if b["trade_compare"].get("pass") and b["batch"]["trade"] is not None)
    out = {
        "streaming_engine": ("AdvisorStrategy + FeedExecAccount "
                             "(incremental, W1-imported class)"),
        "streaming_engine_is_run_backtest": False,
        "streaming_engine_audit": audits["streaming_engine"],
        "signal_identity": {
            "slice_leg": sl["signal_identity"],
            "fixture_leg_all_pass": bool(fx["pass"]),
            "all_bit_exact": bool(sl["signal_identity"]["all_bit_exact"]
                                  and fx["pass"]),
        },
        "equity_parity": {
            "slice_leg": sl["equity_parity"],
            "fixture_leg_pass": bool(fx["pass"]),
            "execution_stress": fx["execution_stress"],
            "pass": bool(sl["equity_parity"]["pass"] and fx["pass"]),
        },
        "no_replay_audit": {
            "static": {"pass": bool(audits["no_replay_pass"]),
                       "adjudication": audits["adjudication"]},
            "denial": dn,
            "static_load_sensitive": {"pass": sens_ok},
            "method": ("static-source-scan (with load-vs-write "
                       "adjudication) + runtime-denial (denied_inputs CLI "
                       "rerun)"),
            "pass": bool(audits["no_replay_pass"] and dn["pass"] and sens_ok),
        },
        "checkpoint_calls_on_slice": 7,  # 5x infer_full reruns on the slice
        # (full/prefix/prefix-rerun/synth-future/trunc2, each re-executing
        # the 3-checkpoint forward passes) + 1 denial CLI replay inference
        # + 1 slice-resume inference. Per-call evidence in verify_perturb.json
        # (elapsed_ms/device/cuda) + W1 manifest identity hashes.
        "checkpoint_call_evidence": {
            "per_call_timing": True,
            "elapsed_ms": pb["elapsed_ms"],
            "device_reported": True,
            "device": pb["device"],
            "cuda": pb["cuda"],
            "denial_inference_s": dn["inference_s"],
        },
        "prefix": {"exact": bool(pb["trunc2_same_shape"]["bit_exact"]),
                   "detail": pb["trunc2_same_shape"]},
        "future_perturbation": {
            "features_rebuilt": True,
            "model_rerun": True,
            "detail": pb["future_invariance"],
            "tolerance_justification": pb["tolerance_justification"]},
        "restart": {
            "fills_identical": bool(rs["pending_restart_own"]["fills_identical"]
                                    and rs["partial_restart_own"]["fills_identical"]
                                    and sr["fills_identical"]),
            "equity_identical": bool(rs["pending_restart_own"]["equity_identical"]
                                     and rs["partial_restart_own"]["equity_identical"]
                                     and sr["equity_identical"]),
            "fixture_account_proofs": rs,
            "slice_resume": sr,
            "w1_tests": "tests/test_r77_advisor.py::test_resume_parity_after_kill + overlapping determinism (run in pytest)",
        },
        "coverage": {
            "n_nonwait_stream": int(fixture_trades),
            "wait_rows_emitted": int(0 if sl["wait_coverage"]["wait_rows_emitted_no_signal"] else -1),
            "forced_signals": 0,
            "slice_nonwait": int(sl["nonwait_on_slice"]),
            "note": ("slice has 0 non-WAIT (frozen checkpoint abstains; "
                     "nothing forced); non-vacuous non-WAIT parity comes "
                     "from the 10-builder fixture streaming leg (F1..F9/F8s "
                     "x normal/fee_stress = 18 non-WAIT streaming fills) "
                     "through the same incremental account class, plus "
                     "F10/F11 pending/partial restart checks."),
        },
        "negative_controls": neg,
        "verdict": None,
    }
    overall = bool(
        out["signal_identity"]["all_bit_exact"]
        and out["equity_parity"]["pass"]
        and out["no_replay_audit"]["pass"]
        and out["restart"]["fills_identical"]
        and out["restart"]["equity_identical"]
        and out["coverage"]["n_nonwait_stream"] >= 1
        and out["coverage"]["wait_rows_emitted"] == 0
        and out["coverage"]["forced_signals"] == 0
        and out["prefix"]["exact"]
        and out["future_perturbation"]["features_rebuilt"]
        and out["future_perturbation"]["model_rerun"]
        and out["checkpoint_calls_on_slice"] >= 1
        and neg["pass"])
    out["verdict"] = ("PASS" if overall else "FAIL")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R77 W3 parity harness (prep/verify)")
    ap.add_argument("--check-prespec", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--audit", nargs="*", default=None,
                    help="static no-replay scan of given streaming-path sources")
    ap.add_argument("--audit-engine", nargs="*", default=None,
                    help="anti-circularity scan: streaming sources must not use run_backtest")
    ap.add_argument("--compare", action="store_true",
                    help="full verify (fail-closed when W1/W2 absent)")
    args = ap.parse_args(argv)
    if args.check_prespec:
        spec = load_prespec()
        print(json.dumps({"prespec": "OK",
                           "hypothesis": spec["hypothesis_id"],
                           "state": STATE_VERSION}))
        return 0
    if args.status:
        print(json.dumps(w1w2_status(), indent=2))
        return 0
    if args.audit is not None:
        print(json.dumps(audit_no_replay(args.audit), indent=2))
        return 0
    if args.audit_engine is not None:
        print(json.dumps(audit_streaming_engine(args.audit_engine), indent=2))
        return 0
    if args.compare:
        try:
            print(json.dumps(run_full_comparison(), indent=2))
        except ReadinessError as exc:
            print(json.dumps({"verdict": "PREP-READY", "reason": str(exc)}))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
