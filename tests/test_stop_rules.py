"""Tests for scripts/stop_rules.py. Synthetic equity paths only, no network."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "stop_rules", Path(__file__).resolve().parents[1] / "scripts" / "stop_rules.py")
sr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sr)

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _iso(t):
    return t.isoformat()


def write_runner(root: Path, name: str, eq_pts, actions=(), ledger=None, links=None):
    d = root / "artifacts" / "bot" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "exchange.json").write_text(json.dumps({
        "cash": 5000.0, "equity0": 5000.0, "orders": {}, "pos": {},
        "execs": [], "funding_paid": 0.0, "fees": 0.0,
        "equity_curve": [[_iso(t), v] for t, v in eq_pts]}), encoding="utf-8")
    (d / "state.json").write_text(
        json.dumps({"ledger": ledger or {}, "links": links or {}}), encoding="utf-8")
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in actions:
            f.write(json.dumps(r) + "\n")
    return d


def daily_points(n_days, start_eq=5000.0, ret_per_day=0.0, t0=T0):
    pts, eq = [], start_eq
    for i in range(n_days):
        pts.append((t0 + timedelta(days=i), eq))
        eq *= (1.0 + ret_per_day)
    return pts


# --- pure status functions ---

def test_dd_21pct_is_stop():
    dd = sr.running_dd([100.0, 110.0, 86.9])  # (110-86.9)/110 = 21%
    assert dd == pytest.approx(0.21, abs=1e-9)
    assert sr.stop_dd_status(dd) == "STOP"


def test_dd_boundaries():
    assert sr.stop_dd_status(0.0) == "OK"
    assert sr.stop_dd_status(0.16) == "WATCH"  # vuot 15% go-live, chua toi 20%
    assert sr.stop_dd_status(0.2001) == "STOP"
    assert sr.stop_dd_status(None) == "WATCH"  # chua du du lieu -> khong STOP


def test_month_minus_11pct_is_stop():
    pts = [(datetime(2026, 9, 30, 23, tzinfo=timezone.utc), 10000.0),
           (datetime(2026, 10, 31, 23, tzinfo=timezone.utc), 8900.0)]
    label, mret = sr.current_month_return(pts, 10000.0)
    assert label == "2026-10"
    assert mret == pytest.approx(-11.0, abs=1e-9)
    assert sr.stop_month_status(mret) == "STOP"


def test_month_boundaries():
    assert sr.stop_month_status(1.5) == "OK"
    assert sr.stop_month_status(-5.0) == "WATCH"
    assert sr.stop_month_status(-10.0) == "STOP"
    assert sr.stop_month_status(None) == "WATCH"


def test_percentile_stop_only_with_enough_weeks():
    assert sr.stop_percentile_status(3.0, 9.0) == "STOP"    # <5 sau >=8 tuan
    assert sr.stop_percentile_status(3.0, 2.0) == "WATCH"  # thieu tuan -> khong STOP
    assert sr.stop_percentile_status(3.0, None) == "WATCH"
    assert sr.stop_percentile_status(None, 9.0) == "WATCH"
    assert sr.stop_percentile_status(10.0, 9.0) == "WATCH"  # <20: chua dat go-live
    assert sr.stop_percentile_status(25.0, 9.0) == "OK"


def test_weeks_and_live_return_need_two_points():
    assert sr.weeks_of_evidence([]) is None
    assert sr.live_return([(T0, 5000.0)]) is None
    pts = daily_points(15)
    assert sr.weeks_of_evidence(pts) == pytest.approx(14 / 7.0, abs=1e-9)


def test_long_cycle_error_span():
    assert sr.long_cycle_error(Path("nope/actions.jsonl"))[0] is False
    t1, t2 = T0, T0 + timedelta(hours=2)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "actions.jsonl"
        p.write_text("\n".join(json.dumps({"t": _iso(t), "op": "cycle_error"})
                               for t in (t1, t2)) + "\n", encoding="utf-8")
        bad, _note = sr.long_cycle_error(p)
        assert bad is True
        p.write_text("\n".join(json.dumps({"t": _iso(t), "op": "cycle_error"})
                               for t in (t1, t1 + timedelta(minutes=10))) + "\n",
                     encoding="utf-8")
        ok, _note2 = sr.long_cycle_error(p)
        assert ok is False


def test_open_without_stop(tmp_path):
    pid = "b1BTCx"
    piece = {"symbol": "BTCUSDT", "side": 1, "qty": 0.01}
    links_ok = {pid + "S": {"order": {"piece": pid, "kind": "stop",
                                      "symbol": "BTCUSDT", "meta": {"kind": "book"}},
                            "rest": {"symbol": "BTCUSDT", "qty": 0.01}}}
    assert sr.open_without_stop({"ledger": {pid: piece}, "links": links_ok}, {}) == []
    missing = sr.open_without_stop({"ledger": {pid: piece}, "links": {}}, {})
    assert len(missing) == 1 and "no-stop" in missing[0]


# --- runner summaries on synthetic dirs ---

def test_summarize_dd_21pct_stops(tmp_path):
    pts = [(T0, 5000.0), (T0 + timedelta(days=5), 5500.0),
           (T0 + timedelta(days=10), 5500.0 * 0.79)]  # DD 21%
    write_runner(tmp_path, "paper_d17bfg2", pts)
    r = sr.summarize_runner(tmp_path, "paper_d17bfg2")
    assert r["exists"] is True
    assert r["dd"] == pytest.approx(0.21, abs=1e-9)
    assert r["stops"]["dd"] == "STOP"
    assert r["severity"] == "critical"
    assert r["gates"]["b"] == "CHUA DAT"
    assert any("=> STOP" in line for line in r["lines"])
    assert any("go-live: chua du" in line for line in r["lines"])


def test_summarize_month_minus_11pct_halves(tmp_path):
    pts = [(datetime(2026, 9, 30, 23, tzinfo=timezone.utc), 10000.0),
           (datetime(2026, 10, 31, 23, tzinfo=timezone.utc), 8900.0)]
    write_runner(tmp_path, "paper_d17bfg2", pts)
    r = sr.summarize_runner(tmp_path, "paper_d17bfg2")
    assert r["stops"]["month"] == "STOP"
    assert r["severity"] == "critical"
    assert any("giam mot nua von" in line for line in r["lines"])


def test_summarize_too_little_data_never_stops(tmp_path):
    write_runner(tmp_path, "paper_d17bfg2", [(T0, 5000.0)])  # 1 diem duy nhat
    r = sr.summarize_runner(tmp_path, "paper_d17bfg2")
    assert r["exists"] is True
    assert r["dd"] is None and r["weeks"] is None and r["percentile"] is None
    assert "STOP" not in r["stops"].values()
    assert r["severity"] != "critical"
    assert any("go-live: chua du" in line for line in r["lines"])


def test_summarize_fresh_runner_ok_with_chua_du_golive(tmp_path):
    pts = daily_points(2)  # ~1 ngay: du 2 diem nhung chua du 8 tuan
    write_runner(tmp_path, "paper_d17bfg2", pts)
    r = sr.summarize_runner(tmp_path, "paper_d17bfg2")
    assert r["stops"] == {"dd": "OK", "month": "OK", "percentile": "WATCH"}
    assert r["severity"] == "ok"  # WATCH chua-du-8-tuan khong day verdict
    assert r["golive"] is False
    assert r["gates"]["a"] == "CHUA DU"


def test_missing_dir_skipped(tmp_path):
    r = sr.summarize_runner(tmp_path, "paper_d17bfg2")
    assert r["exists"] is False and r["severity"] == "ok"


def test_cli_exit_codes(tmp_path):
    pts = [(T0, 5000.0), (T0 + timedelta(days=5), 5500.0),
           (T0 + timedelta(days=10), 5500.0 * 0.79)]
    write_runner(tmp_path, "paper_d17bfg2", pts)
    assert sr.main(["--root", str(tmp_path), "paper_d17bfg2"]) == 2
    write_runner(tmp_path, "paper_d17bfg2c", daily_points(2))
    assert sr.main(["--root", str(tmp_path), "paper_d17bfg2c"]) == 0
