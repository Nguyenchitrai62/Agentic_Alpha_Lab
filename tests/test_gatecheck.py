"""Tests for scripts/opencode_gatecheck.py (synthetic summary + trades only).

No backtests, no training, no live orders. Fast: imports the CLI module once
and calls run() on tmp files.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[1]


def load_gatecheck():
    spec = importlib.util.spec_from_file_location(
        "opencode_gatecheck", SCRIPTS / "opencode_gatecheck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GC = load_gatecheck()
CONFIG = json.loads((ROOT / "configs" / "opencode_gatecheck.json").read_text())


def make_trades(path: Path, month_nets: dict, per_month=4) -> Path:
    """Deterministic trades: month -> net total, split over per_month fills."""
    rows = []
    idx = 0
    for month, total in sorted(month_nets.items()):
        for k in range(per_month):
            share = total / per_month
            day = 3 + k * 6
            ts = f"{month}-{day:02d}T12:00:00+00:00"
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


def diffuse_months(n=12, base=10.0):
    return {f"2024-{m:02d}": base + (m % 3) for m in range(1, n + 1)}


def concentrated_months(n=12):
    d = {f"2024-{m:02d}": 1.0 for m in range(1, n + 1)}
    d["2024-06"] = 100.0
    return d


def make_summary(path: Path, branch: str, mo: float, dd: float, fills: int,
                 nested: bool = False, exec_fills: int | None = None) -> Path:
    scen = {"normal": {"monthly_geometric_net": mo, "max_drawdown": dd,
                       "trades": fills},
            "fee_stress": {"monthly_geometric_net": mo - 0.001,
                           "max_drawdown": dd - 0.002, "trades": fills},
            "execution_stress": {
                "monthly_geometric_net": mo - 0.003, "max_drawdown": dd,
                "trades": exec_fills if exec_fills is not None else fills}}
    node = {"scenarios": scen} if nested else scen
    path.write_text(json.dumps({"branches": {branch: node}}))
    return path


def run_case(tmp_path, branch, mo, dd, fills, months, **kw):
    summ = make_summary(tmp_path / "summary.json", branch, mo, dd, fills, **kw)
    trades = make_trades(tmp_path / "trades.csv", months)
    return GC.run(summ, trades, branch, None, CONFIG)


def test_promote_when_all_pass_diffuse(tmp_path):
    res = run_case(tmp_path, "b_pass", 0.06, -0.10, 40, diffuse_months())
    assert res["gate"]["overall_pass"] is True
    assert res["concentration"]["verdict"] == "diffuse (PASS)"
    assert res["decision"] == "PROMOTE"


def test_hold_on_monthly_fail(tmp_path):
    res = run_case(tmp_path, "b_hold", 0.029, -0.10, 60, diffuse_months())
    assert res["gate"]["overall_pass"] is False
    assert "monthly-fail" in res["gate"]["fail_reasons"]
    assert "fills-exec-fail" not in res["gate"]["fail_reasons"]
    assert res["decision"] == "HOLD"


def test_reject_on_exec_fills_fail(tmp_path):
    res = run_case(tmp_path, "b_rej", 0.024, -0.07, 30, diffuse_months(),
                   exec_fills=28)
    assert "monthly-fail" in res["gate"]["fail_reasons"]
    assert "fills-exec-fail" in res["gate"]["fail_reasons"]
    assert res["decision"] == "REJECT"


def test_reject_on_concentration_fail(tmp_path):
    res = run_case(tmp_path, "b_conc", 0.06, -0.10, 48, concentrated_months())
    assert res["concentration"]["verdict"] == "concentrated (FAIL)"
    assert res["decision"] == "REJECT"


def test_nested_scenarios_schema_parses(tmp_path):
    res = run_case(tmp_path, "b_nest", 0.029, -0.10, 60, diffuse_months(),
                   nested=True)
    assert res["inputs"]["branch"] == "b_nest"
    assert res["gate"]["overall_pass"] is False
    assert "monthly-fail" in res["gate"]["fail_reasons"]
    assert res["decision"] == "HOLD"


def test_robustness_numbers_are_exact_diffs(tmp_path):
    res = run_case(tmp_path, "b_rob", 0.03, -0.10, 40, diffuse_months())
    assert res["robustness"]["exec_drop_pp"] == pytest.approx(0.003)
    assert res["robustness"]["fee_drag_pp"] == pytest.approx(0.001)
    assert res["robustness"]["dd_margin"] == pytest.approx(0.2 - 0.102)


def test_baseline_comparison_deltas(tmp_path):
    summ = make_summary(tmp_path / "summary.json", "b", 0.029, -0.10, 60)
    trades = make_trades(tmp_path / "trades.csv", diffuse_months())
    base = make_trades(tmp_path / "base.csv", diffuse_months())
    res = GC.run(summ, trades, "b", base, CONFIG)
    assert res["baseline_comparison"]["d_total_net_vs_baseline"] == pytest.approx(0.0)
    assert res["baseline_comparison"]["d_top5_share_vs_baseline"] == pytest.approx(0.0)


def test_out_refuses_overwrite(tmp_path):
    summ = make_summary(tmp_path / "summary.json", "b", 0.06, -0.10, 40)
    trades = make_trades(tmp_path / "trades.csv", diffuse_months())
    out = tmp_path / "r.json"
    out.write_text("{}")
    rc = GC.main(["--summary", str(summ), "--trades", str(trades),
                  "--branch", "b", "--out", str(out)])
    assert rc == 2


def losing_months(n=12, base=-10.0):
    """Every month negative => total_net < 0, mean monthly < 0 (gini None)."""
    return {f"2024-{m:02d}": base for m in range(1, n + 1)}


def test_reject_on_losing_book_no_crash(tmp_path):
    """Losing book (total_net <= 0, None shares/gini) -> clean REJECT."""
    summ = make_summary(tmp_path / "summary.json", "b_lose", -0.02, -0.12, 40)
    trades = make_trades(tmp_path / "trades.csv", losing_months())
    res = GC.run(summ, trades, "b_lose", None, CONFIG)  # must not raise
    assert res["concentration"]["total_net"] < 0
    assert res["concentration"]["verdict"] == "concentrated (FAIL)"
    assert "total_net <= 0 (no positive base)" in \
        res["concentration"]["verdict_reasons"]
    assert res["concentration"]["gini_monthly_net"] is None
    assert res["concentration"]["top1_month_share"] is None
    assert res["concentration"]["top3_months_share"] is None
    assert res["concentration"]["top1_trade_share"] is None
    assert res["concentration"]["top5_trades_share"] is None
    assert res["decision"] == "REJECT"
    assert res["decision_line"].startswith("REJECT")
    assert "n/a" in res["decision_line"]


def test_cli_prints_losing_book_no_crash(tmp_path, capsys):
    summ = make_summary(tmp_path / "summary.json", "b_lose", -0.02, -0.12, 40)
    trades = make_trades(tmp_path / "trades.csv", losing_months())
    rc = GC.main(["--summary", str(summ), "--trades", str(trades),
                  "--branch", "b_lose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "REJECT" in out
    assert "n/a" in out


def test_winning_books_have_no_na_placeholders(tmp_path):
    """Winning books keep exact legacy formatting (no 'n/a' placeholders)."""
    res = run_case(tmp_path, "b_pass", 0.06, -0.10, 40, diffuse_months())
    assert res["decision"] == "PROMOTE"
    assert "n/a" not in res["decision_line"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
