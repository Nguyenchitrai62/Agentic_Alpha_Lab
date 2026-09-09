"""Tests for scripts/opencode_promote.py (thin promotion runner).

Synthetic summary/trades/signals/paper files only (no backtests, no training,
no live orders) plus config mirror checks. Verifies: threshold mirror,
no-copied-logic reuse, HOLD-caps-when-blocked, PROMOTE-possible-when-green,
paper-MISSING-when-no-rehearsal, and CLI exit codes (0 success / 2 refusal).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[1]


def load_promote():
    spec = importlib.util.spec_from_file_location(
        "opencode_promote", SCRIPTS / "opencode_promote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PR = load_promote()
PROMOTE_CFG = json.loads((ROOT / "configs" / "opencode_promote.json").read_text())
GC_CONFIG = json.loads((ROOT / "configs" / "opencode_gatecheck.json").read_text())
PROTOCOL = json.loads((ROOT / "configs" / "opencode_forward_protocol.json").read_text())

IN_MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]
FWD_MONTHS = [f"2026-{m:02d}" for m in range(4, 10)]  # strictly after cutoff


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


def diffuse_months(months, base=10.0):
    return {m: base + (i % 3) for i, m in enumerate(sorted(months))}


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
    path.write_text(json.dumps({"experiment": "synthetic-promote-test",
                                "branches": branches}))
    return path


def make_paper(path: Path, signals_path: Path | None = None, *, drill=False,
               halt_days=None, identity=True, one_sided=True, tripped=False,
               blocked=0, resume=False, bad_kill=False) -> Path:
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
    if signals_path is not None:
        sig = str(signals_path)
        doc["halt_trip_params"]["divergence_baseline_signals"] = sig
        doc["halt_trip_params"]["divergence_baseline"] = sig
        doc["config_snapshot"] = {"data": {"signals_replay_only": sig}}
        doc["signal_set_identity"] = {"baseline_signals_path": sig,
                                      "identity": True}
    if resume:
        doc["resume_proof"] = {"intents_identical": True, "equity_match": True,
                               "evidence": "synthetic kill+resume proof"}
    path.write_text(json.dumps(doc))
    return path


def build_case(tmp_path: Path, *, branch="b_green", in_mo=0.06, fwd=True,
               fwd_mo=0.055, concentrated_fwd=False, with_papers=True,
               resume=True):
    d = tmp_path
    summ = make_summary(d / "summary.json", branch, in_mo, -0.10, 48)
    trades = make_trades(d / "trades.csv", diffuse_months(IN_MONTHS), 4)
    sig = make_signals(d / "signals.parquet", IN_MONTHS, 4)
    cfg = make_backtest_config(d / "plan.json", [branch])
    papers = []
    if with_papers:
        papers.append(make_paper(d / "paper_op.json", sig,
                                 halt_days=["2024-03-01"], resume=resume))
        papers.append(make_paper(d / "paper_drill.json", sig, drill=True,
                                 halt_days=["2024-05-01"], identity=False,
                                 tripped=True, blocked=2))
    fwd_summ = fwd_tr = None
    if fwd:
        months = ({FWD_MONTHS[2]: 100.0,
                   **{m: 1.0 for m in FWD_MONTHS if m != FWD_MONTHS[2]}}
                  if concentrated_fwd else diffuse_months(FWD_MONTHS))
        fwd_summ = make_summary(d / "fwd_summary.json", branch, fwd_mo, -0.12, 36)
        fwd_tr = make_trades(d / "fwd_trades.csv", months, 6)
    return summ, trades, sig, cfg, papers, fwd_summ, fwd_tr


def test_mirror_matches_sources():
    mirror = PR.mirror_check(PROMOTE_CFG, GC_CONFIG, PROTOCOL)
    assert mirror["mirror_ok"], f"mirror mismatches: {mirror['mismatches']}"


def test_reuse_by_import_no_copied_logic():
    assert PR.REUSE_RECORD.get("no_copied_logic") is True
    assert hasattr(PR, "GC") and hasattr(PR, "FT")
    assert hasattr(PR.GC, "run") and hasattr(PR.FT, "run")
    src = (SCRIPTS / "opencode_promote.py").read_text(encoding="utf-8")
    for banned in ("def check_gate", "def analyze_concentration",
                   "def eval_forward", "def eval_paper",
                   "def analyze_robustness"):
        assert banned not in src, f"copied logic detected: {banned}"


def test_blocked_without_new_data_caps_at_hold(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(tmp_path, fwd=False)
    res = PR.run(s, t, "b_green", sig, cfg, [str(p) for p in papers],
                 PROMOTE_CFG, GC_CONFIG, PROTOCOL)
    assert res["forward_verdict"]["forward"]["status"] == "FORWARD_BLOCKED"
    assert res["decision"] == "HOLD"
    assert res["decision"] != "PROMOTE"
    assert any(r.startswith("FORWARD_BLOCKED") for r in res["decision_reasons"])


def test_monthly_fail_holds_never_promotes(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(
        tmp_path, branch="b_hold", in_mo=0.029, fwd=False)
    res = PR.run(s, t, "b_hold", sig, cfg, [str(p) for p in papers],
                 PROMOTE_CFG, GC_CONFIG, PROTOCOL)
    assert res["gatecheck"]["decision"] == "HOLD"
    assert "monthly-fail" in res["gatecheck"]["gate"]["fail_reasons"]
    assert res["decision"] in ("HOLD", "REJECT")
    assert res["decision"] != "PROMOTE"


def test_promote_possible_when_all_green(tmp_path):
    s, t, sig, cfg, papers, fs, ft = build_case(tmp_path, fwd=True)
    res = PR.run(s, t, "b_green", sig, cfg, [str(p) for p in papers],
                 PROMOTE_CFG, GC_CONFIG, PROTOCOL, fs, ft)
    assert res["forward_verdict"]["forward"]["status"] == "READY"
    assert res["forward_verdict"]["paper_rehearsal"]["paper_overall"] == "green"
    assert res["decision"] == "PROMOTE"


def test_reject_on_forward_concentration(tmp_path):
    s, t, sig, cfg, papers, fs, ft = build_case(
        tmp_path, fwd=True, concentrated_fwd=True)
    res = PR.run(s, t, "b_green", sig, cfg, [str(p) for p in papers],
                 PROMOTE_CFG, GC_CONFIG, PROTOCOL, fs, ft)
    assert res["forward_verdict"]["forward"]["status"] == "READY"
    assert res["decision"] == "REJECT"
    assert any("concentrated" in r for r in res["decision_reasons"])


def test_paper_missing_when_no_rehearsal_for_signals(tmp_path):
    s, t, sig, cfg, _, fs, ft = build_case(
        tmp_path, branch="b_novel_synth", fwd=True, with_papers=False)
    res = PR.run(s, t, "b_novel_synth", sig, cfg, [], PROMOTE_CFG,
                 GC_CONFIG, PROTOCOL, fs, ft)
    assert res["paper_source"]["mode"].startswith("MISSING")
    assert res["forward_verdict"]["paper_rehearsal"]["paper_overall"] == "NOT_GREEN"
    assert res["decision"] != "PROMOTE"


def test_cli_success_writes_reasons_file(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(tmp_path, fwd=False)
    out = tmp_path / "reasons.json"
    rc = PR.main(["--summary", str(s), "--trades", str(t),
                  "--branch", "b_green", "--signals", str(sig),
                  "--backtest-config", str(cfg),
                  "--paper-summary", str(papers[0]),
                  "--paper-summary", str(papers[1]),
                  "--out", str(out)])
    assert rc == 0
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["decision"] == "HOLD"
    assert doc["reuse"]["no_copied_logic"] is True


def test_cli_refuses_overwrite(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(tmp_path, fwd=False)
    out = tmp_path / "r.json"
    out.write_text("{}")
    rc = PR.main(["--summary", str(s), "--trades", str(t),
                  "--branch", "b_green", "--signals", str(sig),
                  "--backtest-config", str(cfg),
                  "--paper-summary", str(papers[0]),
                  "--out", str(out)])
    assert rc == 2


def test_cli_refuses_forward_on_opened_dates(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(tmp_path, fwd=False)
    out = tmp_path / "verdict.json"
    rc = PR.main(["--summary", str(s), "--trades", str(t),
                  "--branch", "b_green", "--signals", str(sig),
                  "--backtest-config", str(cfg),
                  "--forward-start", "2025-06-01", "--out", str(out)])
    assert rc == 2
    assert not out.exists()


def test_cli_missing_input_is_error(tmp_path):
    s, t, sig, cfg, papers, _, _ = build_case(tmp_path, fwd=False)
    out = tmp_path / "verdict.json"
    rc = PR.main(["--summary", str(tmp_path / "nope.json"),
                  "--trades", str(t), "--branch", "b_green",
                  "--signals", str(sig), "--backtest-config", str(cfg),
                  "--out", str(out)])
    assert rc == 2
    assert not out.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
