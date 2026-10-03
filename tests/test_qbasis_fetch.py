"""Tests for scripts/fetch_quarterly_basis.py (synthetic only, no network).

Covers: expiry/roll rule, annualised-basis formula, causality (a feature at
a 4h close never uses an hourly bar closing after it; shuffling future rows
does not change past values), NaN handling, UM-over-CM priority, and 4h
aggregation taking the last hourly value inside the bar.
"""

import importlib.util
import io
import math
import zipfile
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_mod():
    spec = importlib.util.spec_from_file_location(
        "fetch_quarterly_basis", SCRIPTS / "fetch_quarterly_basis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load_mod()
TS = pd.Timestamp


def synth_grid(start: str, hours: int, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"close_time": idx,
                         "perp_close": [price + 0.01 * i for i in range(hours)]})


def synth_contract(idx, price: float = 101.0, step: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame({"close_time": list(idx),
                         "close": [price + step * i for i in range(len(idx))]})


# ------------------------------------------------------------- expiry/roll

def test_expiry_parsing():
    assert M.expiry_from_contract("BTCUSDT_210326") == TS("2021-03-26 08:00", tz="UTC")
    assert M.expiry_from_contract("BTCUSD_201225") == TS("2020-12-25 08:00", tz="UTC")
    assert M.expiry_from_contract("SOLUSD_250328") == TS("2025-03-28 08:00", tz="UTC")
    with pytest.raises(ValueError):
        M.expiry_from_contract("BTCUSDT_PERP")


def test_roll_rule_boundary():
    e1, e2, e3 = (TS("2021-03-26 08:00", tz="UTC"), TS("2021-06-25 08:00", tz="UTC"),
                  TS("2021-09-24 08:00", tz="UTC"))
    exps = [e1, e2, e3]
    # more than 7 days before e1 -> e1 is front
    assert M.select_front_next(exps, e1 - pd.Timedelta(days=8)) == (e1, e2)
    # exactly 7 days before -> e1 no longer > 7d away -> rolled to e2
    assert M.select_front_next(exps, e1 - pd.Timedelta(days=7)) == (e2, e3)
    assert M.select_front_next(exps, e1 - pd.Timedelta(days=6)) == (e2, e3)
    # after e1 expiry the chain advances
    assert M.select_front_next(exps, e1 + pd.Timedelta(hours=1)) == (e2, e3)
    # past the last roll window -> no front
    assert M.select_front_next(exps, e3 - pd.Timedelta(days=1)) == (None, None)


def test_annualised_basis_formula():
    c = TS("2021-01-01 00:00", tz="UTC")
    e = TS("2021-04-02 08:00", tz="UTC")  # 91d8h -> 91.333...d
    dte = (e - c).total_seconds() / 86400.0
    assert M.annualised_basis(110.0, 100.0, c, e) == pytest.approx(
        math.log(1.1) * 365.0 / dte)
    assert math.isnan(M.annualised_basis(0.0, 100.0, c, e))
    assert math.isnan(M.annualised_basis(110.0, -1.0, c, e))
    assert math.isnan(M.annualised_basis(110.0, 100.0, e, e))  # dte = 0


# ------------------------------------------------------------- causality

def test_future_shuffle_does_not_change_past():
    perp = synth_grid("2021-01-01 00:00", 96)
    e1, e2 = TS("2021-06-25 08:00", tz="UTC"), TS("2021-09-24 08:00", tz="UTC")
    closes = {e1: synth_contract(perp["close_time"], 101.0, 0.001),
              e2: synth_contract(perp["close_time"], 102.0, 0.001)}
    base = M.build_hourly_features(perp, closes, [e1, e2])
    b4 = M.aggregate_to_4h(base)

    # perturb + reorder every delivery row closing after hour 48
    cut = perp["close_time"].iloc[48]
    changed = {}
    for e, d in closes.items():
        dd = d.copy()
        mask = dd["close_time"] > cut
        dd.loc[mask, "close"] = dd.loc[mask, "close"] * 2.0
        changed[e] = dd.iloc[::-1].reset_index(drop=True)  # shuffled order
    alt = M.build_hourly_features(perp, changed, [e1, e2])
    a4 = M.aggregate_to_4h(alt)

    past = base["close_time"] <= cut
    assert past.sum() > 0
    pd.testing.assert_frame_equal(base[past].reset_index(drop=True),
                                  alt[past].reset_index(drop=True))
    past4 = b4["close_time"] <= cut
    assert past4.sum() > 0
    pd.testing.assert_frame_equal(b4[past4].reset_index(drop=True),
                                  a4[past4].reset_index(drop=True))
    # ... while the future really did change
    assert (base.loc[~past, "qb_front"] != alt.loc[~past, "qb_front"]).all()


def test_4h_value_is_last_hourly_inside_bar():
    perp = synth_grid("2021-01-01 00:00", 48)
    e1, e2 = TS("2021-06-25 08:00", tz="UTC"), TS("2021-09-24 08:00", tz="UTC")
    closes = {e1: synth_contract(perp["close_time"], 101.0, 0.01),
              e2: synth_contract(perp["close_time"], 102.0, 0.01)}
    h = M.build_hourly_features(perp, closes, [e1, e2])
    b4 = M.aggregate_to_4h(h)
    by_close = h.set_index("close_time")
    for _, r in b4.iterrows():
        assert r["qb_front"] == pytest.approx(by_close.loc[r["close_time"], "qb_front"])
    # hourly bars are 00-aligned; 4h closes sit on 00/04/08/12/16/20 UTC
    assert set(b4["close_time"].dt.hour.unique()) <= {0, 4, 8, 12, 16, 20}


# ------------------------------------------------------------- NaN / venues

def test_nan_when_no_contract():
    perp = synth_grid("2021-01-01 00:00", 48)
    h = M.build_hourly_features(perp, {}, [])
    assert h["qb_front"].isna().all()
    assert h["qb_slope"].isna().all()
    assert h["qb_chg24"].isna().all()
    c = M.combine_venues(None, h)
    assert (c["source"] == "none").all()
    b4 = M.aggregate_to_4h(c)
    assert b4["qb_front"].isna().all()


def test_single_expiry_slope_nan_front_valid():
    perp = synth_grid("2021-01-01 00:00", 72)
    e1 = TS("2021-06-25 08:00", tz="UTC")
    h = M.build_hourly_features(perp, {e1: synth_contract(perp["close_time"])}, [e1])
    assert h["qb_front"].notna().all()
    assert h["qb_slope"].isna().all()  # no NEXT leg
    assert h["qb_chg24"].iloc[:24].isna().all()  # needs C-24h
    assert h["qb_chg24"].iloc[24:].notna().all()


def test_combine_prefers_um_else_cm():
    perp = synth_grid("2021-01-01 00:00", 48)
    e1, e2 = TS("2021-06-25 08:00", tz="UTC"), TS("2021-09-24 08:00", tz="UTC")
    um = M.build_hourly_features(perp, {e1: synth_contract(perp["close_time"], 101.0),
                                        e2: synth_contract(perp["close_time"], 102.0)},
                                 [e1, e2])
    cm = M.build_hourly_features(perp, {e1: synth_contract(perp["close_time"], 99.0),
                                        e2: synth_contract(perp["close_time"], 98.0)},
                                 [e1, e2])
    both = M.combine_venues(um, cm)
    assert (both["source"] == "um").all()
    assert both["qb_front"].iloc[0] == pytest.approx(um["qb_front"].iloc[0])
    # wipe the UM front leg -> falls back to CM row, same venue for slope
    um_blank = um.copy()
    um_blank["qb_front"] = float("nan")
    fb = M.combine_venues(um_blank, cm)
    assert (fb["source"] == "cm").all()
    assert fb["qb_front"].iloc[0] == pytest.approx(cm["qb_front"].iloc[0])


def test_parse_kline_zip_columns():
    rows = "\n".join(
        f"{1577836800000 + 3600000 * i},{100 + i},101,99,{100.5 + i},10,"
        f"{1577836799999 + 3600000 * i},1000,10,5,500,0" for i in range(3))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("X-1h-2021-01.csv", rows)
    d = M.parse_kline_zip(buf.getvalue())
    assert d.columns.tolist() == ["open_time", "open", "high", "low", "close", "volume"]
    assert len(d) == 3
    assert str(d["open_time"].iloc[0]) == "2020-01-01 00:00:00+00:00"
