"""Tests for oc_carrycombo (frozen rows, causality, fees, cm agreement, REPORT)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carrycombo"
CC = ROOT / "research/tournament/oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_f0_reproduces_frozen_rows():
    out = _res()
    v421 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())
    g2 = out["rows"]["G2_f0.0"]
    exp = v421["rows"]["R2B1D17BFG2"]
    assert g2["R"] == exp["R"] and g2["W"] == exp["W"] and g2["DD"] == exp["DD"]
    assert [tuple(x) for x in g2["years"]] == [tuple(x) for x in exp["years"]]
    assert g2["full_path_dd"]["full"] == exp["full_path_dd"]
    man = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())["rows"]["M5_human"]
    m = out["rows"]["MAN_f0.0"]
    assert m["R"] == man["R5"] and m["W"] == man["W"] and m["DD"] == man["maxDD"]
    assert [r for r, _ in m["years"]] == man["years_R"]
    assert [d for _, d in m["years"]] == man["years_DD"]
    assert m["full_path_dd"]["full"] == man["fullDD"]


def test_carry_lifts_wealth_not_rate_and_trims_dd():
    out = _res()
    for base, brow in (("G2", "G2_f0.0"), ("MAN", "MAN_f0.0")):
        b = out["rows"][brow]
        for f in ("0.25", "0.5"):
            c = out["rows"][f"{base}_f{f}"]
            assert c["losing"] == 0
            assert abs(c["R"] - b["R"]) < 0.05, (base, f, c["R"], b["R"])
            assert c["full_path_dd"]["full"] <= b["full_path_dd"]["full"] + 1e-9
            assert c["DD"] <= b["DD"] + 1e-9
            assert c["W"] >= b["W"] - 0.05
    # effect scales with f (linear sleeve): f=0.5 moves about 2x f=0.25
    g0 = out["rows"]["G2_f0.0"]["R"]
    d1 = out["rows"]["G2_f0.25"]["R"] - g0
    d2 = out["rows"]["G2_f0.5"]["R"] - g0
    assert abs(d2 - 2 * d1) < 0.01, (d1, d2)


def test_entries_frozen_and_fee_math():
    out = _res()
    ccres = json.loads((CC / "results.json").read_text())
    assert out["meta"]["pregrid_excluded"] == 4
    assert out["meta"]["spanning_at_start"] == 4
    frozen = sorted((t["coin"], t["delivery"]) for t in ccres["trades"])
    assert len(frozen) == 33
    for t in ccres["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9, t
        assert t["ret_alloc"] > 0  # every entered pair net positive


def test_hourly_marks_causal_on_local_data():
    """Value at grid hour H uses only 1h bars with open_time < H (local file)."""
    q = pd.read_parquet(ROOT / "data/raw/qbasis_20261003/um_BTCUSDT_241227_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    qn = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    H = pd.Timestamp("2024-12-27 07:00", tz="UTC").value
    idx = int(np.searchsorted(qn, H, side="left") - 1)
    assert qn[idx] < H  # only bars with 1h open_time < H are visible at H
    # the 07:00 grid hour sees the 06:00 bar close (96650.0), not the flatlined 07:00+ prints
    assert abs(float(q["close"].iloc[idx]) - 96650.0) < 1e-9
    src = (HERE / "analyze_carrycombo.py").read_text()
    assert 'side="left"' in src
    for bad in ("intraday_20260924", "intraday_20260930", "klines_1m", "aggflow",
                "_1m.parquet", "Pool(", "heavy_slot"):
        assert bad not in src, bad


def test_cm_vs_um_agreement():
    out = _res()
    c = out["cm_vs_um"]
    av = [x for x in c["entered"] if x.get("cm_available")]
    assert len(av) == 33
    assert sum(1 for x in av if x["um_enter"] == x["cm_enter"]) >= 32
    assert abs(float(np.mean([x["diff_bps"] for x in av]))) < 100
    sk = c["skipped_with_cm"]
    assert len(sk) == 15  # 13 skipped + 2 incomplete
    assert sum(1 for x in sk if x["um_enter"] == x["cm_enter"]) >= 12


def test_bybit_block_and_assumptions_marked():
    out = _res()
    b = out["bybit"]
    assert b["fetched"].startswith("2026-10-06")
    assert "BTCUSDT-25DEC26" in b["linear_quarterlies"] and "ETHUSDT-26MAR27" in b["linear_quarterlies"]
    assert b["linear_settle"] == "USDT" and b["linear_delivery_fee"] == "0"
    assert b["inverse_settle"] == "BTC/ETH (coin)"
    assert b["fees_vip0"]["futures_taker"] == 0.00055
    assert "ASSUMPTION" in b["uta_collateral"]["tier_note"] and "ASSUMPTION" in b["gaps"]
    assert "funded" in out["meta"]["funded_capital_note"]
    assert isinstance(out["meta"]["spot_hourly_ok"], bool)


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    for needle in ("5.413", "16.34", "5.418", "15.86", "3.746", "17.19",
                   "3.765", "16.61", "32/33", "13/15", "BTCUSDT-25DEC26",
                   "BTCUSDZ26", "KHUYEN NGHI", "95 %", "ASSUMPTION"):
        assert needle in rep, needle
    for y, r in zip(("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"),
                    out["rows"]["G2_f0.25"]["years"]):
        assert y in rep and str(r[0]) in rep
