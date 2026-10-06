"""Unit tests for scripts/latency_report.py (pure helpers + tiny fixtures, no bot I/O)."""
from datetime import datetime, timezone

from scripts import latency_report as lr


def test_f36_roundtrip():
    dt = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
    # mirror.t36-compatible encoding of the same minute
    n = int(dt.timestamp() // 60)
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
    assert lr.f36(s) == dt


def test_parse_link_book_and_dip():
    b = lr.parse_link("b0ETHhrvdcE")
    assert b["kind"] == "book" and b["phase"] == 0 and b["sym"] == "ETH"
    assert b["entry"] is True
    assert b["bar"] == datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc)
    d = lr.parse_link("d0BNB25hrv6oE")
    assert d["kind"] == "dip" and d["phase"] == 0 and d["rung"] == 2.5
    assert d["bar"] == datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
    assert lr.parse_link("cETHhrvxtS") is None  # carry link: not book/dip
    assert lr.parse_link("bogus") is None


def test_summarize_percentiles():
    s = lr.summarize([5.0, 5.2, 5.4, 5.3])
    assert s["n"] == 4 and s["min"] == 5.0 and s["max"] == 5.4
    assert abs(s["median"] - 5.25) < 1e-9
    assert lr.summarize([])["n"] == 0


def test_protection_latency_seconds():
    recs = [
        {"t": "2026-10-05 23:50:20.053459+00:00", "op": "fill",
         "link": "b2ETHhrvgoE"},
        {"t": "2026-10-05 23:50:20.339663+00:00", "op": "place",
         "payload": {"orderLinkId": "b2ETHhrvgoS"}},
        {"t": "2026-10-05 23:50:20.339663+00:00", "op": "place",
         "payload": {"orderLinkId": "b2ETHhrvgoT"}},
    ]
    lat = lr.protection_latencies(recs)
    assert len(lat) == 1
    assert 0.0 < lat[0] < 0.05  # ~0.29 s next-cycle protection


def test_first_placements_ignores_protection_and_carry():
    recs = [
        {"t": "2026-10-06 00:16:14.195382+00:00", "op": "place",
         "payload": {"orderLinkId": "d0BNB25hrvk0E"}},
        {"t": "2026-10-06 00:16:15.000000+00:00", "op": "place",
         "payload": {"orderLinkId": "d0BNB25hrvk0T"}},
        {"t": "2026-10-06 00:16:16.000000+00:00", "op": "place",
         "payload": {"orderLinkId": "cETHhrvxtS"}},
    ]
    first = lr.first_placements(recs)
    assert set(first) == {"d0BNB25hrvk0E"}


def test_friction_verdict_is_base():
    v = lr.friction_verdict(5.3, 16.16)
    assert v == {"book": "base(5)", "dip": "base/S2(16)"}
    v2 = lr.friction_verdict(15.1, 31.0)
    assert v2["book"] == "S2(15)" and v2["dip"] == "S3(31)"
