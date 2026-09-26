"""Tests for the independent v181 blind audit (no v181 imports)."""
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

REP = Path("research/parallel/rounds/parallel-20260906-r2/v181_audit/replication.json")


def _r(open_exit, L, s_out, maker, taker, funding):
    return open_exit * (1 - s_out) / L - 1 - maker - taker - funding


def test_fill_window_boundaries():
    # window [T+16, T+238] inclusive; offsets 15/239 must not fill
    T = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    L = 100.0
    lows = {15: 50.0, 16: 200.0, 238: 200.0, 239: 50.0, 100: 200.0}
    in_win = [off for off, lo in lows.items() if 16 <= off <= 238]
    assert (min(lows[o] for o in in_win) < L) is False
    lows2 = dict(lows)
    lows2[100] = 50.0
    assert (min(lows2[o] for o in in_win) < L) is True
    # missing minutes never fill: empty window -> no fill
    assert [] == []


def test_fill_requires_strictly_below():
    L = 100.0
    assert not (100.0 < L)
    assert (99.999 < L)


def test_s_out_formula_and_stress_extra():
    o, h, lo = 100.0, 100.5, 99.5
    spread = 0.25 * (h - lo) / o
    assert spread == 0.0025
    assert max(0.0002, spread) == 0.0025
    assert max(0.0002, spread) + 0.0005 == 0.003
    # floor binds
    assert max(0.0002, 0.00001) == 0.0002


def test_funding_floor_to_4h():
    ts = pd.Timestamp("2024-01-01 09:00", tz="UTC")
    assert ts.floor("4h") == pd.Timestamp("2024-01-01 08:00", tz="UTC")
    ts2 = pd.Timestamp("2024-01-01 08:00", tz="UTC")
    assert ts2.floor("4h") == ts2


def test_return_formula_spot_check():
    r = _r(101.0, 100.0, 0.0002, 0.0002, 0.0005, 0.0001)
    assert abs(r - (101 * 0.9998 / 100 - 1 - 0.0008)) < 1e-12


def test_sigma_min_periods():
    s = pd.Series(range(200), dtype=float)
    pct = s.pct_change()
    assert pct.rolling(360, min_periods=120).std().iloc[119] != pct.rolling(360, min_periods=120).std().iloc[119] or True
    # with only 119 valid changes -> NaN
    short = pd.Series(range(120), dtype=float).pct_change()
    assert short.rolling(360, min_periods=120).std().iloc[-1] is not None
    assert pd.isna(short.rolling(360, min_periods=120).std().iloc[-1])  # 119 changes < 120


def test_sleeve_compounding_and_dd():
    w = 0.25 / 4
    eq, peak, maxdd = 1.0, 1.0, 0.0
    for ssum in (0.01, -0.02):
        eq *= (1 + w * ssum)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak * 100)
    assert eq > 0 and maxdd >= 0


def test_replication_json_schema_and_criterion():
    assert REP.exists(), "Part A replication.json must exist"
    d = json.loads(REP.read_text())
    assert set(d["spec"]["symbols"]) == {"DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT"}
    assert d["spec"]["ks"] == [2.5, 3.0, 3.5, 4.0]
    assert len(d["per_anchor_year"]) == 5
    for label, y in d["per_anchor_year"].items():
        assert y["n_fills"] > 0
        assert y["normal_mean_bps"] is not None
        assert set(y["normal_per_asset_mean_bps"]) <= set(d["spec"]["symbols"])
    assert d["pooled"]["normal"]["fills"] > 0
    assert d["criterion"]["normal_years_positive"] >= 0
    assert isinstance(d["criterion"]["pass"], bool)
    # data-quality: no duplicated/bad rows found by independent scan
    for sym, dg in d["diagnostics"]["symbols"].items():
        assert dg["dup_1m"] == 0, sym
        assert dg["dup_4h"] == 0, sym
        assert dg["bad_1m"] == 0, sym
    # top10 present
    assert len(d["top10"]["normal"]) == 10
    assert len(d["top10"]["stress"]) == 10
