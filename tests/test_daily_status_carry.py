import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "daily_status_carry", Path(__file__).resolve().parents[1] / "scripts" / "daily_status.py")
ds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ds)

NOW = datetime(2026, 10, 6, 7, 0, 0, tzinfo=timezone.utc)


def write_carry(root: Path, age_s: float = 600.0, settled: bool = False):
    d = root / "artifacts" / "bot" / "paper_carry"
    d.mkdir(parents=True, exist_ok=True)
    dlv_ms = int((NOW + timedelta(days=80)).timestamp() * 1000)
    st = {
        "tag": "carry", "equity_arg": 5000.0, "f": 0.5,
        "updated_at": (NOW - timedelta(seconds=age_s)).isoformat(),
        "positions": {"BTC": {
            "coin": "BTC", "symbol": "BTCUSDT-25DEC26", "category": "linear",
            "spot_symbol": "BTCUSDT", "status": "open",
            "delivery_ms": dlv_ms, "ann_basis": 0.054242, "mtm_alloc": -0.001473,
            "entry_fees": 3.875}},
        "history": ([{"coin": "ETH", "symbol": "E", "realised_pnl": 12.5}] if settled else []),
        "entered_symbols": ["BTC:BTCUSDT-25DEC26"],
        "totals": {"n_entered": 1, "n_skipped": 2,
                   "realised_pnl": 12.5 if settled else 0.0, "fees_paid": 1.0},
    }
    (d / "state.json").write_text(json.dumps(st), encoding="utf-8")
    ts = (NOW - timedelta(seconds=age_s)).timestamp()
    os.utime(d / "state.json", (ts, ts))
    (d / "actions.jsonl").write_text("", encoding="utf-8")
    return d


def write_runner(root: Path, name: str, age_s: float = 10.0, cycle_ms=None):
    d = root / "artifacts" / "bot" / name
    d.mkdir(parents=True, exist_ok=True)
    st = {"ledger": {}, "links": {}}
    if cycle_ms is not None:
        st["last_cycle_ms"] = cycle_ms
        st["last_cycle_stages_ms"] = {"plan_ms": 5.0, "kline_ms": cycle_ms - 10.0,
                                      "sync_ms": 1.0, "decide_ms": 2.0,
                                      "order_ms": 1.0, "state_ms": 1.0}
    (d / "state.json").write_text(json.dumps(st), encoding="utf-8")
    ts = (NOW - timedelta(seconds=age_s)).timestamp()
    os.utime(d / "state.json", (ts, ts))
    return d


def test_carry_open_ok(tmp_path):
    write_carry(tmp_path)
    c = ds.check_carry(tmp_path, NOW)
    assert c["severity"] == "ok"
    assert "BTC BTCUSDT-25DEC26" in c["lines"][0]
    assert "+5.42%/nam" in c["lines"][0]
    assert "80.0 ngay" in c["lines"][0]
    assert "MtM -0.15%" in c["lines"][0]
    assert any("roll tiep theo: 2026-12-25" in x for x in c["lines"])


def test_carry_settled_pnl(tmp_path):
    write_carry(tmp_path, settled=True)
    c = ds.check_carry(tmp_path, NOW)
    assert any("1 cap" in x and "+12.50" in x for x in c["lines"])


def test_carry_stale_warns(tmp_path):
    write_carry(tmp_path, age_s=3 * 3600)
    c = ds.check_carry(tmp_path, NOW)
    assert c["severity"] == "warning" and ">2h" in c["lines"][-2]


def test_carry_missing_is_ok(tmp_path):
    c = ds.check_carry(tmp_path, NOW)
    assert c["severity"] == "ok" and "chua co ledger" in c["line"]


def test_cycles_ok_and_warnings(tmp_path):
    write_runner(tmp_path, "paper_a", age_s=10.0, cycle_ms=1000.0)
    rs = ds.check_cycles(tmp_path, NOW)
    assert rs[0]["severity"] == "ok" and "kline_ms=1.0s" in rs[0]["line"]
    write_runner(tmp_path, "paper_b", age_s=10.0, cycle_ms=61_000.0)
    rs = ds.check_cycles(tmp_path, NOW)
    b = [r for r in rs if r["name"] == "paper_b"][0]
    assert b["severity"] == "warning" and "cycle >60s" in b["line"]
    write_runner(tmp_path, "paper_c", age_s=300.0, cycle_ms=1000.0)
    rs = ds.check_cycles(tmp_path, NOW)
    cc = [r for r in rs if r["name"] == "paper_c"][0]
    assert cc["severity"] == "warning" and "state >2p" in cc["line"]


def test_status_includes_new_sections(tmp_path):
    write_carry(tmp_path)
    write_runner(tmp_path, "paper_a", age_s=10.0, cycle_ms=1000.0)
    st = ds.build_status(tmp_path, NOW,
                         health_url="http://127.0.0.1:1/health")  # backend chet nhung chi ktra section
    txt = ds.format_text(st)
    assert "4) Carry:" in txt and "5) Chu ky runner" in txt
    md = ds.format_markdown(st)
    assert "Carry:" in md and "runner" in md
