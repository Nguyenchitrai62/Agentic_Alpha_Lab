"""oc_lit_calendar tests (PLAN-fixed calendars + side-conditional gates).

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_lit_calendar.py -q
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TCAL = ROOT / "research/tournament/oc_lit_calendar"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mp = _load("litcal_panel", TCAL / "make_panel.py")
re_ = _load("litcal_engine", TCAL / "run_engine.py")

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _syn_sb(dates, vals):
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])
    data = np.tile(np.asarray(vals, dtype=float)[:, None], (1, len(SYMS)))
    return pd.DataFrame(data, index=idx, columns=SYMS)


def test_panel_exists_and_schema():
    p = pd.read_parquet(TCAL / "panel.parquet")
    assert {"T", "sym", "tom_in", "on_in", "onwide_in", "halv_in", "halv525_in", "D"}.issubset(p.columns)
    assert (pd.to_datetime(p["T"], utc=True) >= pd.Timestamp("2021-09-24", tz="UTC")).all()
    assert (pd.to_datetime(p["T"], utc=True) < pd.Timestamp("2026-09-24", tz="UTC")).all()
    assert set(p["sym"].unique()) == set(SYMS)
    # 5 syms per T
    nT = p["T"].nunique()
    assert len(p) == 5 * nT


def test_tom_hand_checked():
    # Sep 2021: L=30 -> TOM {29,30,10-01,10-02,10-03}; Oct 4 is OUT
    assert _dt.date(2021, 9, 29) in mp.build_tom_set(_dt.date(2021, 9, 1), _dt.date(2021, 10, 5))
    assert _dt.date(2021, 9, 30) in mp.build_tom_set(_dt.date(2021, 9, 1), _dt.date(2021, 10, 5))
    assert _dt.date(2021, 10, 3) in mp.build_tom_set(_dt.date(2021, 9, 1), _dt.date(2021, 10, 5))
    assert _dt.date(2021, 10, 4) not in mp.build_tom_set(_dt.date(2021, 9, 1), _dt.date(2021, 10, 5))
    # Feb 2024 leap: L=29 -> {28,29,03-01,03-02,03-03}; Feb 27 OUT
    s = mp.build_tom_set(_dt.date(2024, 2, 1), _dt.date(2024, 3, 5))
    assert _dt.date(2024, 2, 28) in s and _dt.date(2024, 2, 29) in s
    assert _dt.date(2024, 2, 27) not in s and _dt.date(2024, 3, 4) not in s
    # grid-level: 2021-10-01 00:00 bar is TOM-IN, 2021-10-04 00:00 is OUT
    g = pd.DatetimeIndex([pd.Timestamp("2021-10-01", tz="UTC"), pd.Timestamp("2021-10-04", tz="UTC")])
    fl = mp.flags_for_grid(g)
    assert fl["tom_in"].tolist() == [True, False]


def test_overnight_overlap_hand_checked():
    g = pd.DatetimeIndex([pd.Timestamp(f"2022-03-15 {h:02d}:00", tz="UTC") for h in (0, 4, 8, 12, 16, 20)])
    fl = mp.flags_for_grid(g)
    assert fl["on_in"].tolist() == [False, False, False, False, False, True]
    assert fl["onwide_in"].tolist() == [True, False, False, False, False, True]


def test_halving_D_hand_checked():
    assert mp.days_since_halving(_dt.date(2024, 4, 19)) == 0
    assert mp.days_since_halving(_dt.date(2024, 4, 20)) == 1
    assert mp.days_since_halving(_dt.date(2021, 9, 24)) == 501  # 365 + 136, in [400,900]
    g = pd.DatetimeIndex([pd.Timestamp("2021-09-24", tz="UTC"),
                          pd.Timestamp("2024-04-19", tz="UTC"),
                          pd.Timestamp("2026-09-23", tz="UTC")])
    fl = mp.flags_for_grid(g)
    assert fl["halv_in"].tolist() == [True, False, True]  # 2026-09-23: D=887 in [400,900]
    assert fl["halv525_in"].tolist() == [False, False, True]  # 2021-09-24: D=501 < 525
    assert fl["D"].tolist() == [501, 0, (g[2].date() - _dt.date(2024, 4, 19)).days]
    # engine copy matches panel copy on the same grid
    assert (re_.halv_in_for(g) == fl["halv_in"].to_numpy()).all()
    assert abs(re_.DIP_SCALE - 0.20 / 0.26) < 1e-12


def test_truncation_rows_before_2021_never_gated():
    sb = _syn_sb(["2021-09-20 20:00", "2021-09-21 00:00"], [0.4, -0.3])
    books, _ = re_.gate_books(sb)
    for k in ("V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"):
        assert np.allclose(books[k].to_numpy(), sb.to_numpy()), k
        assert np.allclose(books[re_.CTRL_OF[k]].to_numpy(), sb.to_numpy()), k


def test_side_conditional_synthetic():
    # 2021-10-04 20:00 UTC: NOT TOM (Oct 4 OUT), on_in True (hour 20)
    sb = _syn_sb(["2021-10-04 20:00"], [0.4])  # long 0.4 all syms
    books, _ = re_.gate_books(sb)
    assert np.allclose(books["S1"].to_numpy(), 0.4 * 1.0)  # IN -> 1.0
    assert np.allclose(books["V1"].to_numpy(), 0.4 * 0.85)  # OUT -> 0.85
    sb2 = _syn_sb(["2021-10-04 20:00"], [-0.3])  # short: S1 untouched, V1 scaled
    books2, _ = re_.gate_books(sb2)
    assert np.allclose(books2["S1"].to_numpy(), -0.3)
    assert np.allclose(books2["V1"].to_numpy(), -0.3 * 0.85)
    # S2 longs flat outside window: 2021-10-04 08:00 (OUT) long -> 0
    sb3 = _syn_sb(["2021-10-04 08:00"], [0.5])
    books3, _ = re_.gate_books(sb3)
    assert np.allclose(books3["S2"].to_numpy(), 0.0)
    assert np.allclose(books3["S1"].to_numpy(), 0.5 * 0.75)
    # V3: OUT longs 0.85 / shorts 0.50; IN (2021-10-01 20:00: TOM + overnight) 1.0
    sb4 = _syn_sb(["2021-10-04 08:00"], [0.5])
    b4, _ = re_.gate_books(sb4)
    assert np.allclose(b4["V3"].to_numpy(), 0.5 * 0.85)
    sb5 = _syn_sb(["2021-10-04 08:00"], [-0.5])
    b5, _ = re_.gate_books(sb5)
    assert np.allclose(b5["V3"].to_numpy(), -0.5 * 0.50)
    sb6 = _syn_sb(["2021-10-01 20:00"], [0.5])
    b6, _ = re_.gate_books(sb6)
    assert np.allclose(b6["V3"].to_numpy(), 0.5 * 1.0)
    sb7 = _syn_sb(["2021-10-01 20:00"], [-0.5])
    b7, _ = re_.gate_books(sb7)
    assert np.allclose(b7["V3"].to_numpy(), -0.5 * 1.0)


def test_bug_replicas_are_sb():
    # Disclosed first-run behaviour (kept originals): the no-op C_V3/C_S*
    # books are bit-identical to the bear-filtered base.
    sb = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [0.4, -0.3])
    books, _ = re_.gate_books(sb)
    for k in ("C_V3", "C_S1", "C_S2", "C_S3"):
        assert np.array_equal(books[k].to_numpy(), sb.to_numpy()), k


def test_fix_controls_hand_checked():
    # Same-year bars: 2021-10-01 20:00 (TOM-IN, on-IN) + 2021-10-04 08:00 (OUT/OUT).
    sb = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [0.4, 0.4])
    books, info = re_.gate_books(sb)
    e = info["per_year"]["S1"][0]
    assert e["cL"] == round((1.0 + 0.75) / 2, 6)
    assert np.allclose(books["C_S1_FIX"].to_numpy(), sb.to_numpy() * e["cL"])
    e3 = info["per_year"]["V3"][0]
    assert e3["cL"] == round((1.0 + 0.85) / 2, 6)
    assert e3["cS"] == 1.0  # no short cells in this sb -> default 1.0
    sbL = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [0.4, 0.4])
    bL, _ = re_.gate_books(sbL)
    assert np.allclose(bL["C_V3_FIX"].to_numpy(), sbL.to_numpy() * e3["cL"])
    sbS = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [-0.4, -0.4])
    bS, iS = re_.gate_books(sbS)
    eS = iS["per_year"]["V3"][0]
    assert eS["cS"] == round((1.0 + 0.50) / 2, 6)
    assert np.allclose(bS["C_V3_FIX"].to_numpy(), sbS.to_numpy() * eS["cS"])


def test_control_constants_match_realised_means():
    # two bars same year: one TOM-IN (2021-10-01 20:00), one OUT (2021-10-04 08:00)
    sb = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [0.4, 0.4])
    books, info = re_.gate_books(sb)
    e = info["per_year"]["V1"][0]
    assert e["mean_mult"] == round((1.0 + 0.85) / 2, 6)
    assert np.allclose(books["C_V1"].to_numpy(), sb.to_numpy() * e["c"])
    # S1 control touches longs only
    e1 = info["per_year"]["S1"][0]
    assert e1["cS"] == 1.0
    sbS = _syn_sb(["2021-10-01 20:00", "2021-10-04 08:00"], [-0.4, -0.4])
    bS, _ = re_.gate_books(sbS)
    assert np.allclose(bS["C_S1"].to_numpy(), sbS.to_numpy())
