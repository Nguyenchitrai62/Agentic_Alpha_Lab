"""Tests for oc_carrycompound (compounding overlay; f=0 exact; causality)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carrycompound"
CC = ROOT / "research/tournament/oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_f0_reproduces_g2_to_digit():
    out = _res()
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0 = out["rows"]["G2_f0.0"]
    assert g0["R"] == exp["R"] and g0["W"] == exp["W"] and g0["DD"] == exp["DD"]
    assert [yy["R"] for yy in g0["years"]] == [r for r, _ in exp["years"]]
    assert [yy["DD"] for yy in g0["years"]] == [d for _, d in exp["years"]]
    assert g0["full_path_dd"]["full"] == exp["full_path_dd"]
    assert g0["losing"] == 0


def test_compound_headline_numbers():
    out = _res()
    g1 = out["rows"]["G2_f0.25"]
    assert g1["R"] == 5.634 and g1["W"] == 2.778 and g1["DD"] == 16.75
    assert g1["full_path_dd"]["full"] == 16.66
    assert g1["losing"] == 0
    assert out["carry_add_pp_per_month"] == 0.224
    assert round(g1["R"] - out["rows"]["G2_f0.0"]["R"], 3) == 0.224
    # compounding exceeds both book-keeping overlays
    assert g1["R"] > 5.533 > 5.413


def test_aggregates_consistent():
    out = _res()
    for key in ("G2_f0.0", "G2_f0.25"):
        r = out["rows"][key]
        assert len(r["years"]) == 5
        assert min(y["R"] for y in r["years"]) == r["W"]
        assert max(y["DD"] for y in r["years"]) == r["DD"]
        assert r["losing"] == sum(y["R"] < 0 for y in r["years"])
        fac = 1.0
        for y in r["years"]:
            fac *= 1 + y["R"] / 100
        assert abs(fac ** (1 / 5) - 1 - r["R"] / 100) < 5e-5
        for y in r["years"]:
            m2 = (y["end"]) ** (1 / 12) - 1
            assert abs(m2 * 100 - y["R"]) < 1e-2
    # carry lifts return and trims DD, no new losing year
    b, c = out["rows"]["G2_f0.0"], out["rows"]["G2_f0.25"]
    assert c["R"] > b["R"] and c["W"] > b["W"]
    assert c["DD"] <= b["DD"] and c["full_path_dd"]["full"] <= b["full_path_dd"]["full"]
    assert c["losing"] == b["losing"] == 0


def test_frozen_trades_and_fee_math():
    cc = json.loads((CC / "results.json").read_text())
    assert len(cc["trades"]) == 33
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9
        assert t["ret_alloc"] > 0


def test_causal_marking_and_no_heavy():
    src = (HERE / "analyze_carrycompound.py").read_text()
    assert 'side="left"' in src
    assert "last CLOSED hourly bar strictly" in src
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "phase_offset_full", "heavy_slot", "Pool("):
        assert bad not in src, bad
    # assumption stated: r_bot on WHOLE equity (UTA)
    meta = _res()["meta"]["assumption"]
    assert "WHOLE" in meta or "TOTAL" in meta
    assert "UTA" in meta
    # spot-check causal helper on a local quarterly file
    q = pd.read_parquet(ROOT / "data/raw/qbasis_20261003/um_BTCUSDT_241227_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    qn = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    H = pd.Timestamp("2024-12-27 07:00", tz="UTC").value
    idx = int(np.searchsorted(qn, H, side="left") - 1)
    assert qn[idx] < H
    assert abs(float(q["close"].iloc[idx]) - 96650.0) < 1e-9


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("5.634", "2.778", "16.75", "16.66", "+0.224", "UTA",
                   "f=0 reproduces", "5.413", "5.533"):
        assert needle in rep, needle
