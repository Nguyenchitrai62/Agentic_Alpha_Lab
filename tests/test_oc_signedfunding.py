"""oc_signedfunding tests: actual-funding side row (no selection).

Light (no engine): funding-source equivalence, settlement->bar mapping,
sign conventions, reconstruction on synthetic engine hooks.
Heavy (needs research/diagnostics/oc_signedfunding/results.json): gate
bit-for-bit reproduction of v421 rows, schema + no-selection labelling.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/diagnostics/oc_signedfunding"
V421 = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"
import sys
sys.path.insert(0, str(OC))
import funding_rates as FR


def test_funding_sources_match_on_overlap():
    a = FR.load_funding_rates("premium")
    b = FR.load_funding_rates("xs")
    assert list(a.columns) == FR.SYMS and list(b.columns) == FR.SYMS
    common = a.index.intersection(b.index)
    assert len(common) > 7000
    assert float((a.loc[common] - b.loc[common]).abs().max().max()) == 0.0


def test_funding_covers_walk_forward():
    b = FR.load_funding_rates("xs")
    assert b.index.min() <= pd.Timestamp("2021-09-24", tz="UTC")
    assert b.index.max() >= pd.Timestamp("2026-09-23", tz="UTC")
    a = FR.load_funding_rates("premium")
    # mirror ends early: document why xs is the replay source
    assert a.index.max() < pd.Timestamp("2026-09-23", tz="UTC")


def test_settlement_mapping_holds_through():
    # settlements at 00/08/16 UTC; holding bar (T, T+4h], T = idx + 4h.
    idx = pd.date_range("2021-09-24 00:00", periods=6, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    fr = pd.DataFrame({"BTCUSDT": [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007]},
                      index=pd.DatetimeIndex([
                          "2021-09-24 04:00", "2021-09-24 08:00", "2021-09-24 12:00",
                          "2021-09-24 16:00", "2021-09-24 20:00", "2021-09-25 00:00",
                          "2021-09-25 04:00"], tz="UTC"))
    m = FR.map_funding_to_bars(fr, idx, cols)
    # bar i covers (idx[i]+4h, idx[i]+8h]: i=0 gets 08:00 only (04:00 is the left edge)
    assert m[0, 0] == pytest.approx(0.002)
    assert m[1, 0] == pytest.approx(0.003)
    # a decision at t filled during t+1 pays the t+2-open settlement, never t+1's
    assert m[0, 0] != pytest.approx(0.001)


def test_reconstruct_signs_synthetic():
    # one bar, settle=True: long pays / short receives signed; gate: long pays, short zero.
    idx = pd.DatetimeIndex(["2021-09-24 00:00+00:00"])
    cols = ["BTCUSDT", "ETHUSDT"]
    o2 = np.array([[100.0, 50.0]])
    settle = np.array([True])
    t = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    bars = [dict(t=t, qty=[0.5, -0.4])]  # long BTC, short ETH (fractions of equity)
    fr_bar = np.array([[0.001, -0.0005]])
    r = FR.reconstruct_funding([], bars, idx, cols, o2, settle, fr_bar)
    assert r["book_total"] == pytest.approx(0.5 * 0.001 * 100 + (-0.4) * (-0.0005) * 50)
    g = FR.reconstruct_funding([], bars, idx, cols, o2, settle, None)
    assert g["book_total"] == pytest.approx(0.0001 * 0.5 * 100)  # short pays nothing
    # dip timeout rung pays its bar's rate on its notional
    ev = [dict(t=t + pd.Timedelta(minutes=30), symbol="BTCUSDT", kind="rung_fill", weight=0.1),
          dict(t=t + pd.Timedelta(minutes=240), symbol="BTCUSDT", kind="rung_timeout")]
    r2 = FR.reconstruct_funding(ev, bars, idx, cols, o2, settle, fr_bar)
    assert r2["dip_total"] == pytest.approx(0.1 * 0.001)
    # TP/SL exits inside the bar never span a settlement: no funding
    ev3 = [dict(t=t + pd.Timedelta(minutes=30), symbol="BTCUSDT", kind="rung_fill", weight=0.1),
           dict(t=t + pd.Timedelta(minutes=100), symbol="BTCUSDT", kind="rung_tp")]
    r3 = FR.reconstruct_funding(ev3, bars, idx, cols, o2, settle, fr_bar)
    assert r3["dip_total"] == pytest.approx(0.0)


RESULTS = OC / "results.json"


@pytest.mark.skipif(not RESULTS.exists(), reason="heavy replay not finished")
def test_results_schema_and_labelling():
    import json
    res = json.loads(RESULTS.read_text())
    assert "SIDE ROW ONLY" in res["note"] and "official" in res["note"]
    for row in ("R2B1D17BF", "R2B1D17BFG2"):
        r = res["rows"][row]
        for mode in ("gate", "signed"):
            m = r[mode]
            assert set(("R", "W", "DD", "losing", "years", "full_path_dd")) <= set(m)
            assert len(m["years"]) == 5
        assert len(r["funding_pct_of_year_start_equity"]["gate"]) == 5
        assert len(r["funding_pct_of_year_start_equity"]["signed"]) == 5
    assert res["gate_reproduction_exact"] is True


@pytest.mark.skipif(not RESULTS.exists(), reason="heavy replay not finished")
def test_gate_reproduces_v421_exactly():
    import json
    res = json.loads(RESULTS.read_text())
    v421 = json.loads(V421.read_text())
    for row in ("R2B1D17BF", "R2B1D17BFG2"):
        g, v = res["rows"][row]["gate"], v421["rows"][row]
        for k in ("R", "W", "DD", "losing", "full_path_dd"):
            assert g[k] == v[k], (row, k, g[k], v[k])
        assert g["years"] == [list(x) for x in v["years"]]
