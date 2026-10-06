"""Tests for scripts/weekly_report.py. Synthetic runner folders only, no network."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "weekly_report", Path(__file__).resolve().parents[1] / "scripts" / "weekly_report.py")
wr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wr)

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _iso(t):
    return t.isoformat()


def write_runner(root: Path, name: str, eq_pts, execs=(), ledger=None, links=None, actions=()):
    d = root / "artifacts" / "bot" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "exchange.json").write_text(json.dumps({
        "cash": 5000.0, "equity0": 5000.0, "orders": {}, "pos": {},
        "execs": list(execs), "funding_paid": 0.0, "fees": 0.1,
        "equity_curve": [[_iso(t), v] for t, v in eq_pts]}), encoding="utf-8")
    (d / "state.json").write_text(
        json.dumps({"ledger": ledger or {}, "links": links or {}}), encoding="utf-8")
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in actions:
            f.write(json.dumps(r) + "\n")
    return d


def write_plan(root: Path, eq_pts):
    p = root / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "equity_curve": [[_iso(t), v] for t, v in eq_pts], "events": []}), encoding="utf-8")
    return p


def write_carry(root: Path, open_pos=True, with_history=True):
    p = root / "artifacts" / "bot" / "paper_carry" / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    pos = {}
    if open_pos:
        pos = {"BTC": {"coin": "BTC", "symbol": "BTCUSDT-25DEC26", "category": "linear",
                       "spot_symbol": "BTCUSDT", "status": "open",
                       "entry_time": _iso(T0 + timedelta(days=19)),
                       "delivery_ms": 1798185600000, "S_entry": 85000.0, "F_entry": 86000.0,
                       "ann_basis": 0.05, "dte_days": 80.0, "equity_entry": 5000.0, "f": 0.5,
                       "entry_fees": 3.875, "unrealised": -3.0}}
    hist = []
    if with_history:
        hist = [{"coin": "BTC", "symbol": "BTCUSDT-25SEP26", "status": "delivered",
                 "settled_at": _iso(T0 + timedelta(days=18)),
                 "realised_pnl": 12.5, "realised_ret_alloc": 0.005}]
    p.write_text(json.dumps({
        "tag": "carry", "equity_arg": 5000.0, "f": 0.5, "rule": {},
        "created_at": _iso(T0), "updated_at": _iso(T0 + timedelta(days=20)),
        "positions": pos, "history": hist, "entered_symbols": ["BTC:BTCUSDT-25DEC26"],
        "totals": {"n_entered": 1, "n_skipped": 0,
                   "realised_pnl": 12.5 if with_history else 0.0, "fees_paid": 0.0}}),
        encoding="utf-8")
    return p


def _ms(t):
    return str(int(t.timestamp() * 1000))


def sample_execs(t):
    return [
        {"orderLinkId": "b0ETHxE", "execQty": "0.02", "execPrice": "100",
         "execTime": _ms(t)},
        {"orderLinkId": "b0ETHxT", "execQty": "0.02", "execPrice": "110",
         "execTime": _ms(t + timedelta(hours=1))},
        {"orderLinkId": "d0BTCxE", "execQty": "0.01", "execPrice": "100",
         "execTime": _ms(t)},
        {"orderLinkId": "d0BTCxT", "execQty": "0.01", "execPrice": "90",
         "execTime": _ms(t + timedelta(hours=2))},
    ]


def sample_ledger_links():
    ledger = {"b0ETHx": {"symbol": "ETHUSDT", "side": 1, "qty": 0},
              "d0BTCx": {"symbol": "BTCUSDT", "side": 1, "qty": 0}}
    links = {
        "b0ETHxE": {"order": {"kind": "entry", "piece": "b0ETHx", "symbol": "ETHUSDT",
                              "meta": {"kind": "book"}}},
        "b0ETHxT": {"order": {"kind": "tp", "piece": "b0ETHx", "symbol": "ETHUSDT",
                              "meta": {"kind": "book"}}},
        "d0BTCxE": {"order": {"kind": "entry", "piece": "d0BTCx", "symbol": "BTCUSDT",
                              "meta": {"kind": "dip"}}},
        "d0BTCxT": {"order": {"kind": "tp", "piece": "d0BTCx", "symbol": "BTCUSDT",
                              "meta": {"kind": "dip"}}},
    }
    return ledger, links


def test_full_report_sections_and_numbers(tmp_path):
    t_exit = T0 + timedelta(days=19, hours=1)
    eq = [(T0 + timedelta(days=i), 5000.0 + 10.0 * i) for i in range(21)]
    ledger, links = sample_ledger_links()
    write_runner(tmp_path, "paper_d17bfg2", eq, sample_execs(t_exit), ledger, links)
    write_runner(tmp_path, "paper_d17bfg2c", eq[:3])
    write_plan(tmp_path, [(T0 - timedelta(days=1), 1.0),
                          (T0 + timedelta(days=20), 1.0)])
    write_carry(tmp_path)
    rep = wr.build_report(tmp_path)
    assert rep["iso_week"].startswith("2026-W")
    r = rep["runners"][0]
    assert r["exists"] is True
    assert r["days"] == 20.0
    assert r["ret_all"] == (5200.0 / 5000.0 - 1.0) * 100.0
    assert r["dd_all"] == 0.0
    assert r["ret_week"] is not None  # anchor ffill tai week_start
    assert r["n_book"] == 1 and r["n_dip"] == 1
    assert r["wr_book"] == "100.0% (1/1)" and r["wr_dip"] == "0.0% (0/1)"
    assert r["wr_all"] == "50.0% (1/2)"
    assert r["biggest_win"] > 0 and r["biggest_loss"] < 0
    assert r["divergence"]["verdict"] in ("PASS", "FAIL", "too early")
    assert "worst" in r["edge"] and "severity" in r["stops"]
    c = rep["carry"]
    assert c["exists"] is True and c["realised"] == 12.5
    assert c["wr"] == "100.0% (1/1)" and c["biggest_win"] == 12.5
    text = wr.format_markdown(rep)
    for needle in ("paper_d17bfg2", "paper_d17bfg2c", "Carry", "Divergence",
                   "Edge", "Stop/go-live", "56 ngay", "Tom tat 3 dong",
                   "book", "dip", "carry"):
        assert needle in text
    assert len(wr.plain_summary(rep)) == 3


def test_week_slice_uses_ffill_anchor():
    pts = [(T0, 5000.0), (T0 + timedelta(days=10), 5100.0),
           (T0 + timedelta(days=12), 5200.0)]
    now = T0 + timedelta(days=12)
    ws = now - timedelta(days=7)  # T0+5d: anchor ffill la diem cuoi <= ws
    wpts = wr.week_slice(pts, ws)
    assert [v for _, v in wpts] == [5000.0, 5100.0, 5200.0]
    assert wr.pct_return(wpts) == (5200.0 / 5000.0 - 1.0) * 100.0


def test_missing_data_never_crashes(tmp_path):
    rep = wr.build_report(tmp_path)  # cay rong: khong runner, khong carry, khong plan
    assert all(r["exists"] is False for r in rep["runners"])
    assert rep["carry"]["exists"] is False
    text = wr.format_markdown(rep)
    assert "n/a" in text and "chua co ledger" in text
    assert len(wr.plain_summary(rep)) == 3
    assert wr.main(["--root", str(tmp_path),
                    "--out", str(tmp_path / "o.md")]) == 0
    assert (tmp_path / "o.md").exists()


def test_default_out_path_uses_iso_week(tmp_path):
    write_runner(tmp_path, "paper_d17bfg2",
                 [(T0, 5000.0), (T0 + timedelta(days=1), 5010.0)])
    assert wr.main(["--root", str(tmp_path)]) == 0
    files = list((tmp_path / "artifacts" / "reports").glob("weekly_*.md"))
    assert len(files) == 1 and files[0].read_text(encoding="utf-8").startswith("# Bao cao tuan")


def test_missing_exchange_graceful(tmp_path):
    d = tmp_path / "artifacts" / "bot" / "paper_d17bfg2"
    d.mkdir(parents=True, exist_ok=True)  # thu muc co nhung khong co file
    rep = wr.build_report(tmp_path)
    r = rep["runners"][0]
    assert r["exists"] is True and r["ret_all"] is None
    assert "n/a" in wr.format_markdown(rep)
