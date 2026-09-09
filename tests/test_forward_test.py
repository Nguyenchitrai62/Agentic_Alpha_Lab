"""Tests for scripts/opencode_forward_test.py (promotion machine).

Synthetic summary/trades/signals/paper files only, plus ONE read-only check on
the frozen majority_1x artifacts (known-FAIL branch: must HOLD/REJECT with the
correct reasons, never PROMOTE). No backtests, no training, no live orders.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[1]


def load_forward():
    spec = importlib.util.spec_from_file_location(
        "opencode_forward_test", SCRIPTS / "opencode_forward_test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FT = load_forward()
PROTOCOL = json.loads((ROOT / "configs" / "opencode_forward_protocol.json").read_text())
GC_CONFIG = json.loads((ROOT / "configs" / "opencode_gatecheck.json").read_text())

CUTOFF = "2026-03-23"


def make_trades(path: Path, month_nets: dict, per_month=4) -> Path:
    rows, idx = [], 0
    for month, total in sorted(month_nets.items()):
        for k in range(per_month):
            ts = f"{month}-{2 + k * 4:02d}T12:00:00+00:00"
            share = total / per_month
            rows.append({"signal_index": idx, "direction": 1, "leverage": 1.0,
                         "entry_index": idx, "entry_time": ts,
                         "entry_price": 30000.0, "exit_index": idx + 1,
                         "exit_time": ts, "exit_reason": "tp1",
                         "gross_pnl": share + 0.05, "fees": 0.03,
                         "funding": 0.02, "net_pnl": share,
                         "equity_before": 100.0, "equity_after": 100.0,
                         "holding_bars": 10})
            idx += 1
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def diffuse_months(prefix_year_months, base=10.0):
    return {m: base + (i % 3) for i, m in enumerate(sorted(prefix_year_months))}


def make_summary(path: Path, branch: str, mo: float, dd: float, fills: int,
                 exec_fills: int | None = None) -> Path:
    node = {"normal": {"monthly_geometric_net": mo, "max_drawdown": dd,
                       "trades": fills},
            "fee_stress": {"monthly_geometric_net": mo - 0.001,
                           "max_drawdown": dd - 0.002, "trades": fills},
            "execution_stress": {
                "monthly_geometric_net": mo - 0.005, "max_drawdown": dd,
                "trades": exec_fills if exec_fills is not None else fills}}
    path.write_text(json.dumps({"branches": {branch: node}}))
    return path


def make_signals(path: Path, months, per_month=4) -> Path:
    stamps = []
    for month in sorted(months):
        for k in range(per_month):
            stamps.append(f"{month}-{2 + k * 4:02d}T00:05:00+00:00")
    pd.DataFrame({"bar_index": list(range(len(stamps))),
                  "signal_time": pd.to_datetime(stamps, utc=True)}
                 ).to_parquet(path)
    return path


def make_backtest_config(path: Path, branches) -> Path:
    path.write_text(json.dumps({"experiment": "synthetic-forward-test",
                                "branches": branches}))
    return path


def make_paper(path: Path, *, drill=False, halt_days=None, identity=True,
               one_sided=True, tripped=False, blocked=0, resume=False,
               bad_kill=False) -> Path:
    stats = {"halt_days": halt_days or [],
             "daily_halt_events": [{"day": d} for d in (halt_days or [])],
             "v21_identity": identity and not drill,
             "v21_is_drill": drill,
             "v21_one_sided_checks": "pass" if one_sided else "fail",
             "divergence_tripped": tripped,
             "divergence_blocks": blocked,
             "skipped_divergence": blocked,
             "divergence_trip": ({"kind": "DIVERGENCE_TRIP", "status": "TRIPPED_NOW",
                                  "direction": "UNDER", "divergence": -0.06}
                                 if tripped else None)}
    doc = {"mode": "SIMULATED/PAPER", "exploratory": True,
           "live_orders": False, "bot_version": "paper_trader_v21",
           "is_drill": drill, "stats": stats,
           "halt_trip_params": {"daily_loss_halt_X_pct": 0.09 if bad_kill else 0.03,
                                "max_positions": 1,
                                "divergence_tolerance_Y_pct": 0.05,
                                "one_sided": "UNDER_ONLY"}}
    if resume:
        doc["resume_proof"] = {"intents_identical": True, "equity_match": True,
                               "evidence": "synthetic kill+resume proof"}
    path.write_text(json.dumps(doc))
    return path


IN_MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]
FWD_MONTHS = [f"2026-{m:02d}" for m in range(4, 10)]  # strictly after cutoff


def run_case(tmp_path, *, fwd=True, concentrated_fwd=False,
             paper=True, resume=True, branch="b_green",
             in_mo=0.06, fwd_mo=0.055):
    d = tmp_path
    summ = make_summary(d / "summary.json", branch, in_mo, -0.10, 48)
    trades = make_trades(d / "trades.csv", diffuse_months(IN_MONTHS), 4)
    sig = make_signals(d / "signals.parquet", IN_MONTHS, 4)
    cfg = make_backtest_config(d / "plan.json", [branch])
    papers = []
    if paper:
        papers.append(make_paper(d / "paper_op.json", halt_days=["2024-03-01"],
                                 resume=resume))
        papers.append(make_paper(d / "paper_drill.json", drill=True,
                                 halt_days=["2024-05-01"], identity=False,
                                 tripped=True, blocked=2))
    kw = {}
    if fwd:
        months = ({FWD_MONTHS[2]: 100.0, **{m: 1.0 for m in FWD_MONTHS if m != FWD_MONTHS[2]}}
                  if concentrated_fwd else diffuse_months(FWD_MONTHS))
        kw["forward_summary"] = make_summary(
            d / "fwd_summary.json", branch, fwd_mo, -0.12, 36)
        kw["forward_trades"] = make_trades(d / "fwd_trades.csv", months, 6)
    return FT.run(summ, trades, branch, sig, cfg, papers, PROTOCOL, GC_CONFIG, **kw)


def test_protocol_has_rationale_per_rule_and_handoff():
    for section in ("research_gate", "concentration", "robustness_margins"):
        for rule, node in PROTOCOL[section].items():
            if isinstance(node, dict) and "value" in node:
                assert node.get("rationale"), f"{section}.{rule} lacks rationale"
    assert PROTOCOL["forward_window"]["min_forward_months"]["rationale"]
    assert PROTOCOL["degradation_vs_backtest"][
        "forward_monthly_ge_backtest_ratio_min"]["rationale"]
    for check, node in PROTOCOL["paper_ops"].items():
        if isinstance(node, dict) and "pass_rule" in node:
            assert node.get("rationale"), f"paper_ops.{check} lacks rationale"
    for key in ("replay_parity", "plan_sha_match", "bounded_output_proof",
                "val_export"):
        assert key in PROTOCOL["handoff_checklist"], f"handoff lacks {key}"
        assert PROTOCOL["handoff_checklist"][key]["rationale"]


def test_refuses_forward_start_on_opened_dates(tmp_path):
    run_case(tmp_path, fwd=False)  # builds the frozen input files on disk
    out = tmp_path / "verdict.json"
    summ = tmp_path / "summary.json"
    rc = FT.main(["--summary", str(summ), "--trades", str(tmp_path / "trades.csv"),
                  "--branch", "b_green", "--signals", str(tmp_path / "signals.parquet"),
                  "--backtest-config", str(tmp_path / "plan.json"),
                  "--forward-start", "2025-06-01", "--out", str(out)])
    assert rc == 2
    assert not out.exists()


def test_refuses_overlapping_forward_trades(tmp_path):
    run_case(tmp_path, fwd=False)
    bad_trades = make_trades(tmp_path / "bad_fwd.csv",
                             diffuse_months(["2024-05", "2026-04"]), 20)
    bad_summ = make_summary(tmp_path / "bad_fwd.json", "b_green", 0.055, -0.10, 40)
    out = tmp_path / "verdict.json"
    rc = FT.main(["--summary", str(tmp_path / "summary.json"),
                  "--trades", str(tmp_path / "trades.csv"),
                  "--branch", "b_green",
                  "--signals", str(tmp_path / "signals.parquet"),
                  "--backtest-config", str(tmp_path / "plan.json"),
                  "--forward-summary", str(bad_summ),
                  "--forward-trades", str(bad_trades), "--out", str(out)])
    assert rc == 2
    assert not out.exists()


def test_blocked_without_new_data_never_promotes(tmp_path):
    res = run_case(tmp_path, fwd=False)
    assert res["forward"]["status"] == "FORWARD_BLOCKED"
    assert res["decision"] == "HOLD"  # passing in-sample capped at HOLD
    assert any(r.startswith("FORWARD_BLOCKED") for r in res["decision_reasons"])
    assert res["decision"] != "PROMOTE"


def test_majority_known_fail_hold_never_promote():
    summ = ROOT / "artifacts/research/opencode_v15_mapensemble/summary.json"
    trades = ROOT / "artifacts/research/opencode_v15_mapensemble/majority_1x/normal_trades.csv"
    sig = ROOT / "artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet"
    cfg = ROOT / "configs/opencode_v15_mapensemble.json"
    op = ROOT / "artifacts/research/opencode_paper_v21/paper_v21_intents_x3_summary.json"
    drill = ROOT / "artifacts/research/opencode_paper_v21/paper_v21_intents_drill_x3_summary.json"
    for p in (summ, trades, sig, cfg, op, drill):
        assert p.exists(), f"frozen artifact missing: {p}"
    res = FT.run(summ, trades, "majority_1x", sig, cfg, [op, drill],
                 PROTOCOL, GC_CONFIG)
    assert res["decision"] in ("HOLD", "REJECT")
    assert res["decision"] != "PROMOTE"
    assert "monthly-fail" in res["decision_reasons"]
    assert any(r.startswith("FORWARD_BLOCKED") for r in res["decision_reasons"])
    assert res["forward"]["status"] == "FORWARD_BLOCKED"
    assert res["in_sample"]["decision"] in ("HOLD", "REJECT")
    assert res["paper_rehearsal"]["checks"]["halt_demonstrated"]["status"] == "PASS"
    assert res["paper_rehearsal"]["checks"]["trip_under_blocks"]["status"] == "PASS"


def test_promote_path_all_green(tmp_path):
    res = run_case(tmp_path, fwd=True)
    assert res["forward"]["status"] == "READY"
    assert res["forward"]["months_pass"] is True
    assert res["forward"]["degradation_pass"] is True
    assert res["paper_rehearsal"]["paper_overall"] == "green"
    assert res["decision"] == "PROMOTE"


def test_reject_on_forward_concentration(tmp_path):
    res = run_case(tmp_path, fwd=True, concentrated_fwd=True)
    assert res["forward"]["status"] == "READY"
    assert res["decision"] == "REJECT"
    assert any("concentrated" in r for r in res["decision_reasons"])


def test_missing_resume_blocks_promote(tmp_path):
    res = run_case(tmp_path, fwd=True, resume=False)
    assert res["paper_rehearsal"]["paper_overall"] == "NOT_GREEN"
    assert res["decision"] != "PROMOTE"


def run_forward_only_case(tmp_path, *, fwd_mo=0.02, branch="b_fwdonly",
                           paper=True):
    d = tmp_path
    fwd_summ = make_summary(d / "fwd_summary.json", branch, fwd_mo, -0.10, 36)
    fwd_trades = make_trades(d / "fwd_trades.csv",
                             diffuse_months(FWD_MONTHS), 6)
    papers = []
    if paper:
        papers.append(make_paper(d / "paper_op.json", halt_days=["2026-04-01"]))
        papers.append(make_paper(d / "paper_drill.json", drill=True,
                                 halt_days=["2026-05-01"], identity=False,
                                 tripped=True, blocked=2))
    return FT.run_forward_only(fwd_summ, fwd_trades, branch, papers,
                               PROTOCOL, GC_CONFIG)


def test_forward_only_hold_on_weak_forward(tmp_path):
    res = run_forward_only_case(tmp_path, fwd_mo=0.02)
    assert res["forward"]["status"] == "FORWARD_ONLY"
    assert res["forward"]["in_sample_baseline"] == "NO-IN-SAMPLE-BASELINE"
    assert res["in_sample"]["decision"] == "NO-IN-SAMPLE-BASELINE"
    assert res["decision"] == "HOLD"
    assert res["decision"] != "PROMOTE"
    assert any("monthly-fail" in r for r in res["decision_reasons"])
    assert any("NO-IN-SAMPLE-BASELINE" in r
               for r in res["decision_reasons"])


def test_forward_only_never_promotes_on_strong_forward(tmp_path):
    res = run_forward_only_case(tmp_path, fwd_mo=0.06)
    assert res["forward"]["status"] == "FORWARD_ONLY"
    assert res["forward"]["forward_decision"] == "HOLD"
    assert res["decision"] == "HOLD"
    assert res["decision"] != "PROMOTE"
    assert "PROMOTE" not in res["decision"]
    assert any("forward-only-cap" in r for r in res["decision_reasons"])
    assert any("NO-IN-SAMPLE-BASELINE" in r
               for r in res["decision_reasons"])


def test_out_refuses_overwrite(tmp_path):
    run_case(tmp_path, fwd=False)
    out = tmp_path / "r.json"
    out.write_text("{}")
    rc = FT.main(["--summary", str(tmp_path / "summary.json"),
                  "--trades", str(tmp_path / "trades.csv"),
                  "--branch", "b_green",
                  "--signals", str(tmp_path / "signals.parquet"),
                  "--backtest-config", str(tmp_path / "plan.json"),
                  "--out", str(out)])
    assert rc == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
