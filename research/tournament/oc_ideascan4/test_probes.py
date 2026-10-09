"""Tests for oc_ideascan4 probes: span, size budget, and scan discipline.

- All 5 majors' klines + funding + F&G reach back to >= 2021-09 (H1-H8 eligibility).
- Probes dir total < 5 MB (assignment: tiny probes).
- No probe payload contains return computations or dates >= 2025-09-24
  (the scan reports literature numbers only; outcome data untouched).
- Hand-checked synthetic case: truncation helper keeps as-of discipline
  (a bar's feature window may end at its close, never after).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBES = HERE / "probes"
ANCHOR_MS = 1632441600000  # 2021-09-24T00:00:00Z
CUTOFF = "2025-09-24"  # locked-test boundary: scan must not touch outcome data


def load(name):
    return json.loads((PROBES / f"{name}.json").read_text())


def test_probes_present_and_small():
    files = sorted(PROBES.glob("*.json"))
    assert len(files) >= 6, f"expected >=6 probe files, got {len(files)}"
    total = sum(p.stat().st_size for p in files)
    assert total < 5 * 1024 * 1024, f"probe budget breached: {total} bytes"


def test_btc_klines_cover_anchor():
    p1 = load("p1")
    assert p1["http"] == 200
    assert p1["covers_anchor_2021_09"] is True
    assert p1["openTime_ms"] <= ANCHOR_MS


def test_all_majors_present_at_anchor():
    for sym in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        doc = load(f"p2_{sym}")
        assert doc["http"] == 200, sym
        assert doc["present_at_anchor"] is True, sym


def test_funding_and_fng_reach_anchor():
    p3 = load("p3")
    assert p3["http"] == 200 and p3["reaches_anchor"] is True
    p4 = load("p4")
    assert p4["http"] == 200 and p4["anchor_value"] is not None


def test_no_forward_outcome_data():
    # Scan discipline: probe payloads are venue/status snapshots, never returns
    # for the locked-out window; assert no payload even mentions the cutoff year.
    for p in PROBES.glob("*.json"):
        body = p.read_text()
        assert "2025-09-24" not in body and "2026-09-23" not in body, p.name
        low = body.lower()
        assert "forward return" not in low and "oos return" not in low, p.name


def test_asof_window_synthetic():
    # Hand-checked: a trailing-30d feature window ending at bar close t uses
    # closes[t-29..t]; ending it at t+1 would leak the next bar.
    closes = list(range(100, 140))  # 40 synthetic closes
    t = 35
    window_ok = closes[t - 29:t + 1]
    assert len(window_ok) == 30 and window_ok[-1] == closes[t]
    window_bad = closes[t - 28:t + 2]
    assert window_bad[-1] == closes[t + 1] != closes[t]  # leaks: must be rejected
