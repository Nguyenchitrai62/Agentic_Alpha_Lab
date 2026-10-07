"""Tests for research/tournament/oc_stresshist (pure scoring helpers only)."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).parent.parent / "research" / "tournament" / "oc_stresshist"


def _load():
    spec = importlib.util.spec_from_file_location("oc_stresshist_mod", HERE / "compute_stress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


def _hourly(values, start="2023-09-25 00:00"):
    idx = pd.date_range(start, periods=len(values), freq="1h", tz="UTC")
    es = pd.Series(values, index=idx, dtype=float)
    return es, es.copy()


def test_year_of_anchors():
    assert M.year_of("2021-09-24 01:00") == 0
    assert M.year_of("2022-09-24 00:00") == 0
    assert M.year_of("2022-09-25 00:00") == 1
    assert M.year_of("2026-09-23 00:00") == 4
    with pytest.raises(ValueError):
        M.year_of("2020-01-01")


def test_score_window_hand_checked():
    # flat 1.00 for 100h, linear drop to 0.90 over 24h, linear recovery to 1.00 over 48h
    vals = [1.0] * 100
    vals += [1.0 - 0.10 * i / 24 for i in range(1, 25)]
    vals += [0.90 + 0.10 * i / 48 for i in range(1, 49)]
    vals += [1.0] * 200
    es, ms = _hourly(vals)
    anchor = pd.Timestamp("2023-09-24", tz="UTC")
    w0 = es.index[99]  # last flat bar: start is exactly 1.00
    w1 = w0 + pd.Timedelta(days=7)
    d = M.score_window(es, ms, anchor, w0, w1)
    assert d["start"] == pytest.approx(1.0, abs=1e-9)
    assert d["trough"] == pytest.approx(0.90, abs=1e-9)
    assert d["peak"] == pytest.approx(1.0, abs=1e-9)
    assert d["dd"] == pytest.approx(10.0, abs=1e-6)
    assert d["rec_days"] == pytest.approx(2.0, abs=1e-9)  # trough idx123 -> regain idx171
    assert d["week_ret"] == pytest.approx(0.0, abs=1e-9)  # fully recovered inside the week


def test_score_window_no_recovery_is_null():
    es, ms = _hourly([1.0 + 0.001 * i for i in range(100)] + [1.10 - 0.002 * i for i in range(200)])
    anchor = pd.Timestamp("2023-09-24", tz="UTC")
    w0 = es.index[100]
    d = M.score_window(es, ms, anchor, w0, w0 + pd.Timedelta(days=7))
    assert d["rec_days"] is None


def test_worst_weeks_picks_drop_and_separates():
    base = [1.0] * 400
    for i in range(10, 30):  # sharp permanent drop 1.0 -> 0.8
        base[i] = 1.0 - 0.01 * (i - 9)
    for i in range(30, 400):
        base[i] = 0.8
    es, _ = _hourly(base)
    by_year = {2: es}
    out = M.worst_weeks(by_year, n=2)
    assert len(out) == 2
    assert out[0]["ret7"] < -5
    t0 = pd.Timestamp(out[0]["w0"])
    t1 = pd.Timestamp(out[1]["w0"])
    assert abs((t0 - t1).total_seconds()) >= 7 * 86400


def test_worst_weeks_never_crosses_anchor():
    es, _ = _hourly([1.0 - 0.0005 * i for i in range(300)])  # steady bleed
    by_year = {2: es}
    out = M.worst_weeks(by_year, n=3)
    a0 = pd.Timestamp(M.ANCH[2], tz="UTC")
    for w in out:
        # window END (the 7d lookback target) is never in the first 7d of the year,
        # so the lookback es(t-7d) never crosses the anchor
        assert pd.Timestamp(w["w1"]) >= a0 + pd.Timedelta(days=7)
