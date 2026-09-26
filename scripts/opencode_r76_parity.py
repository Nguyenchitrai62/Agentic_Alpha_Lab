"""Opencode R76 W3-VERIFY: independent raw->equity comparison harness + own rebuild driver.

RESEARCH/PAPER ONLY. Verification only; no live orders, no cloud, no fitting/tuning.
Pre-spec: configs/opencode_r76_parity.json (written BEFORE any W1/W2 artifact
existed; this driver asserts every frozen value before comparing).

Two cost branches (own rebuild driver): normal (fee 0.0002/fill) + fee stress
(0.00055/fill), both via VERBATIM ohlc-v2 run_backtest. Funding long 0.0001/8h,
short 0. Reference artifacts are loaded ONLY by this harness, never by the
streaming path (asserted by audit_no_replay + the denial test).

Causality contract (fail-closed): ReadinessError when W1/W2 artifacts are absent
(PREP-READY, never block, never invent numbers).
"""

import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_alpha_lab.backtest.engine import (  # noqa: E402
    CostModel, ExecutionConfig, run_backtest)

SPEC_PATH = ROOT / "configs/opencode_r76_parity.json"
PARITY_DIR = ROOT / "artifacts/research/opencode_r76_real_inference/parity"
W1_DIR = ROOT / "artifacts/research/opencode_r76_real_inference/manifest"
W2_DIR = ROOT / "artifacts/research/opencode_r76_real_inference/feedexec"

STATE_VERSION = "r76_parity/1"
EQUITY_TOL = 1e-6
SIGNAL_KEY_COLS = ["bar_index", "signal_time", "direction", "entry_limit",
                   "stop_loss", "take_profit_1", "take_profit_2",
                   "holding_bars", "leverage", "entry_expiry_bars",
                   "tp1_fraction"]

# Stored-input patterns that must NEVER be loaded by the streaming path.
# (The comparison harness in this file is explicitly allowed to load them;
#  this list audits W1/W2 sources only, never this harness itself.)
FORBIDDEN_PATTERNS = [
    r"predictions\.npz",
    r"replay\.npz",
    r"signals\.parquet",
    r"decisions\.parquet",
    r"decision_indices",
    r"control.*\.(csv|parquet)",
    r"normal_trades\.csv",
    r"baseline_trades",
]


class ReadinessError(RuntimeError):
    """Fail-closed: W1/W2 inputs absent or incomplete (PREP-READY, not a FAIL)."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_prespec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["hypothesis_id"] == "opencode-r76-real-inference-parity"
    assert spec["frozen_reference_policy"]["branch"] == "confirmed_dd_guard"
    assert spec["frozen_reference_policy"]["checkpoints"]["fold_used"] == 10
    assert spec["frozen_reference_policy"]["checkpoints"]["seeds"] == [1729, 1730, 1731]
    assert spec["costs"]["normal"]["fee_rate_per_fill"] == 0.0002
    assert spec["costs"]["fee_stress"]["fee_rate_per_fill"] == 0.00055
    assert spec["execution_core"]["entry_expiry_bars"] == 12
    assert spec["execution_core"]["max_holding_bars"] == 2016
    assert spec["execution_core"]["tp1_fraction"] == 0.5
    assert spec["execution_core"]["intrabar_policy"] == "stop_first"
    return spec


def w1w2_status() -> dict:
    """Poll the sibling W1/W2 drop zones. Absent files => PREP-READY."""
    w1_files = sorted(p.relative_to(ROOT).as_posix()
                      for p in W1_DIR.rglob("*") if p.is_file()) if W1_DIR.exists() else []
    w2_files = sorted(p.relative_to(ROOT).as_posix()
                      for p in W2_DIR.rglob("*") if p.is_file()) if W2_DIR.exists() else []
    expected_manifest = W1_DIR / "manifest.json"
    expected_adapter = list(W1_DIR.glob("adapter_config*.json"))
    ready = (expected_manifest.is_file() and len(expected_adapter) > 0
             and len(w2_files) > 0)
    return {"w1_files": w1_files, "w2_files": w2_files,
            "manifest_present": expected_manifest.is_file(),
            "adapter_config_present": len(expected_adapter) > 0,
            "ready": ready}


def audit_no_replay(source_paths: list) -> dict:
    """Static leg of the no-replay audit: scan streaming-path SOURCES for
    forbidden stored-input loads. Returns violations per file. Method recorded
    in summary.json (pass rule: zero violations on the W1/W2 streaming path).

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


def compare_signal_frames(batch: pd.DataFrame, stream: pd.DataFrame) -> dict:
    """Signal-set identity: exact match on key cols (no tolerance on identity;
    numerics reported with max abs diff for diagnosis)."""
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
        if bv.dtype.kind in "iub" or col in ("bar_index", "direction",
                                             "holding_bars",
                                             "entry_expiry_bars"):
            if not bool((bv == sv).all()):
                key_ok = False
        else:
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


def rebuild_equity(candles: pd.DataFrame, signals: pd.DataFrame,
                   spec: dict) -> dict:
    """OWN rebuild driver: verbatim ohlc-v2 run_backtest for normal + fee
    stress branches. Reports gross/fees/funding/net/drawdown/trades/coverage
    per AGENTS.md rule 6. Deterministic: same inputs => bit-identical outputs.
    """
    out = {}
    for branch in spec["comparison_branches"]:
        key = "normal" if branch.startswith("normal") else "fee_stress"
        cfg = spec["costs"][key]
        costs = CostModel(fee_rate_per_fill=cfg["fee_rate_per_fill"],
                          funding_long_rate=cfg["funding_long_rate"],
                          funding_short_rate=cfg["funding_short_rate"],
                          funding_interval_hours=cfg["funding_interval_hours"])
        exe = spec["execution_core"]
        execution = ExecutionConfig(
            entry_expiry_bars=exe["entry_expiry_bars"],
            max_holding_bars=exe["max_holding_bars"],
            tp1_fraction=exe["tp1_fraction"],
            leverage=1.0, max_leverage=1.0)
        equity, trades = run_backtest(candles, signals, 100.0, costs, execution)
        out[branch] = {
            "final_equity": float(equity.final_equity),
            "gross_pnl": float(equity.gross_pnl),
            "fees": float(equity.fees),
            "funding": float(equity.funding),
            "net_pnl": float(equity.net_profit),
            "max_drawdown": float(equity.max_drawdown),
            "trade_count": int(equity.trades),
            "coverage_signals": len(signals),
            "per_trade_equity_after": [float(t.equity_after) for t in trades],
        }
    return out


def compare_equity(ref: dict, stream: dict, tol: float = EQUITY_TOL) -> dict:
    """Portfolio match within 1e-6 per branch (final equity + per-trade path)."""
    branches = {}
    ok_all = True
    for branch in ref:
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


def run_full_comparison() -> dict:
    """Full verify path. Fail-closed when W1/W2 are absent (PREP-READY)."""
    spec = load_prespec()
    try:
        import opencode_r76_parity_verify as V
    except Exception:
        V = None
    if V is not None:
        try:
            pres = V.verify_inputs_present()
        except Exception:
            pres = {"ready": False}
        if pres.get("ready"):
            return V.run_full_comparison()
    status = w1w2_status()
    if not status["ready"]:
        raise ReadinessError(
            "W1/W2 artifacts absent or incomplete "
            f"(manifest={status['manifest_present']}, "
            f"adapter_cfg={status['adapter_config_present']}, "
            f"feedexec_files={len(status['w2_files'])}). "
            "PREP-READY: prep done, verification deferred. No numbers claimed.")
    raise ReadinessError(
        "W1/W2 present but full-compare wiring runs at verify time only "
        "(streaming signals + harness reference load + denial test). "
        "Pre-spec skeleton reached the compare gate intact.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R76 W3 parity harness (prep/verify)")
    ap.add_argument("--check-prespec", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--audit", nargs="*", default=None,
                    help="static no-replay scan of given streaming-path sources")
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
