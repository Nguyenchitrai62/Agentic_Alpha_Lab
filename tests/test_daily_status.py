import importlib.util
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "daily_status", Path(__file__).resolve().parents[1] / "scripts" / "daily_status.py")
ds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ds)

NOW = datetime(2026, 10, 6, 3, 0, 0, tzinfo=timezone.utc)
pq = pytest.importorskip("pyarrow.parquet")


def write_bot(root: Path, name: str, age_s: float = 10.0, plan_age_h: float = 1.0):
    d = root / "artifacts" / "bot" / name
    d.mkdir(parents=True, exist_ok=True)
    t = (NOW - timedelta(seconds=age_s)).isoformat()
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"t": t, "mode": "paper", "op": "place"}) + "\n")
    (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {}}), encoding="utf-8")
    (d / "exchange.json").write_text(json.dumps({
        "cash": 5000.0, "equity0": 5000.0, "orders": {}, "pos": {}, "execs": [],
        "funding_paid": 0.0, "fees": 0.0,
        "equity_curve": [[(NOW - timedelta(hours=2)).isoformat(), 5000.0],
                         [NOW.isoformat(), 5010.0]]}), encoding="utf-8")
    return d


def write_plan(root: Path, age_h: float = 1.0):
    p = root / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    gen = (NOW - timedelta(hours=age_h)).isoformat()
    p.write_text(json.dumps({"generated_at": gen, "equity_curve": []}), encoding="utf-8")


def write_collectors(root: Path, gap: bool = False, stale_s: float = 30.0):
    import pyarrow as pa
    now_ms = int(NOW.timestamp() * 1000)
    for venue in ("binance", "bybit"):
        cov = root / "data" / "raw" / "liquidations_live" / "_coverage" / venue
        cov.mkdir(parents=True, exist_ok=True)
        end = now_ms - int(stale_s * 1000)
        start = end - 24 * 3600 * 1000
        ivs = []
        if gap:  # 1 gap 10 phut cach day 1h
            mid = end - 3600 * 1000
            ivs = [(start, mid - 600 * 1000), (mid, end)]
        else:
            ivs = [(start, end)]
        pq.write_table(pa.table({
            "venue": [venue] * len(ivs),
            "start_ms": [s for s, _ in ivs], "end_ms": [e for _, e in ivs]}),
            str(cov / "2026-10-06.parquet"))
        for sym in ("BTCUSDT",):
            ld = root / "data" / "raw" / "liquidations_live" / venue / sym
            ld.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.table({
                "venue": [venue], "symbol": [sym], "side": ["long"], "raw_side": ["Sell"],
                "price": [85000.0], "qty": [0.01], "notional_usd": [850.0],
                "event_time": [end - 600 * 1000], "recv_time": [end - 600 * 1000]}),
                str(ld / "2026-10-06.parquet"))
            tb = root / "data" / "raw" / "topbook_live" / venue / sym
            tb.mkdir(parents=True, exist_ok=True)
            step, rows = 10_000, []
            m = end - 24 * 3600 * 1000
            if gap:
                m = end - 3600 * 1000  # chi giu 1h gan nhat + 1 gap 10p o giua
                while m < end:
                    if abs(m - (end - 1800 * 1000)) > 300 * 1000:
                        rows.append(m)
                    m += step
            else:
                while m < end:
                    rows.append(m)
                    m += step
                rows = rows[-2000:]
            n = len(rows)
            pq.write_table(pa.table({
                "venue": [venue] * n, "symbol": [sym] * n,
                "sample_time": rows, "quote_time": rows,
                "bid": [85000.0] * n, "bid_qty": [1.0] * n,
                "ask": [85001.0] * n, "ask_qty": [1.0] * n,
                "recv_time": rows}), str(tb / "2026-10-06.parquet"))


def make_root(tmp_path: Path, **kw) -> Path:
    write_plan(tmp_path, kw.get("plan_age_h", 1.0))
    write_bot(tmp_path, "paper_x", age_s=kw.get("bot_age_s", 10.0))
    write_collectors(tmp_path, gap=kw.get("gap", False), stale_s=kw.get("stale_s", 30.0))
    return tmp_path


class FakeResp:
    def __init__(self, body=b'{"status":"ok"}', status=200):
        self.status, self._b = status, body

    def read(self, n=-1):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def mock_ok(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())


def test_ok_exit_0(tmp_path, monkeypatch, capsys):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path), NOW)
    assert (st["verdict"], st["exit"]) == ("ok", 0)
    assert "KET LUAN: OK" in ds.format_text(st)


def test_backend_down_is_critical(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise ConnectionRefusedError("down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    st = ds.build_status(make_root(tmp_path), NOW)  # plan tuoi 1.0h van CRITICAL vi backend tat
    assert st["plan"]["severity"] == "ok"
    assert st["verdict"] == "critical" and st["exit"] == 2
    assert "backend tắt: plan sẽ cũ" in ds.format_text(st)


def test_stale_plan_warns_early(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path, plan_age_h=2.0), NOW)
    assert st["plan"]["severity"] == "warning" and st["exit"] == 1


def test_stale_plan_is_critical(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path, plan_age_h=5.0), NOW)
    assert st["plan"]["severity"] == "critical" and st["exit"] == 2


def test_stale_bot_is_critical(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path, bot_age_s=3600.0), NOW)
    assert st["bots"][0]["severity"] == "critical" and st["exit"] == 2


def test_collector_gap_warns_and_stale_is_critical(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path, gap=True), NOW)
    assert st["verdict"] == "warning" and st["exit"] == 1
    st2 = ds.build_status(make_root(tmp_path, stale_s=3600.0), NOW)
    assert st2["verdict"] == "critical" and st2["exit"] == 2


def test_cli_md_and_reuse(tmp_path, monkeypatch, capsys):
    mock_ok(monkeypatch)
    monkeypatch.setattr(ds, "utcnow", lambda: NOW)
    assert ds.bot_health.check_dir and ds.paper_report.summarize_dir and ds.liq_mod.coverage_gaps
    md = tmp_path / "r.md"
    rc = ds.main(["--root", str(make_root(tmp_path)), "--md", str(md)])
    assert rc == 0 and md.read_text(encoding="utf-8").startswith("# Trang thai")
    assert "KET LUAN" in capsys.readouterr().out


def test_tong_line_and_order(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    st = ds.build_status(make_root(tmp_path), NOW)
    txt = ds.format_text(st)
    assert "TONG: OK" in txt
    idx = [txt.index("TONG:"),
           txt.index("1) Stop rules + bao ve"),
           txt.index("2) Runner health"),
           txt.index("3) Backend & plan"),
           txt.index("4) Carry:"),
           txt.index("7) Collector")]
    assert idx == sorted(idx)
    assert "tong thoi gian:" in txt
    assert st["protection"]["severity"] == "ok"  # runner sach: co stop? khong vi the mo -> OK


def test_fast_no_network(tmp_path, monkeypatch, capsys):
    def _boom(*a, **k):
        raise AssertionError("khong duoc goi network o --fast")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(ds, "utcnow", lambda: NOW)
    rc = ds.main(["--root", str(make_root(tmp_path)), "--fast"])
    assert rc == 0
    assert "TONG: OK" in capsys.readouterr().out


def test_failing_section_one_loi_line(tmp_path, monkeypatch):
    mock_ok(monkeypatch)
    monkeypatch.setattr(ds, "check_collectors", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    st = ds.build_status(make_root(tmp_path), NOW)
    txt = ds.format_text(st)
    assert txt.count("loi: collectors") == 1
    assert "KET LUAN" in txt
