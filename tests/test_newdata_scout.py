"""Scout parsing helpers + tests (tag `scout`).

Scope per OPENCODE_NEWDATA_SCOUT.md: this file may ONLY test small parsing
helpers for the availability scan. No network, no bulk data, no repo imports.
"""

import math


# ---------------------------------------------------------------- helpers
def parse_wiki_pageviews(payload):
    """Wikimedia pageviews per-article payload -> [(date 'YYYY-MM-DD', views)]."""
    out = []
    for it in payload.get("items", []):
        ts = it.get("timestamp", "")
        if len(ts) < 8 or not ts[:8].isdigit():
            continue
        out.append(("%s-%s-%s" % (ts[0:4], ts[4:6], ts[6:8]), int(it.get("views", 0))))
    return out


def parse_okx_funding_page(payload):
    """OKX funding-rate-history page -> [(fundingTime_ms, rate)]. Skips bad rows."""
    out = []
    for row in payload.get("data", []):
        try:
            out.append((int(row["fundingTime"]), float(row["fundingRate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_bybit_funding_list(payload):
    """Bybit v5 funding/history result -> [(fundingRateTimestamp_ms, rate)]."""
    out = []
    for row in payload.get("result", {}).get("list", []):
        try:
            out.append((int(row["fundingRateTimestamp"]), float(row["fundingRate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_hl_funding(payload):
    """Hyperliquid fundingHistory list -> [(time_ms, fundingRate)]."""
    out = []
    for row in payload or []:
        try:
            out.append((int(row["time"]), float(row["fundingRate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_deribit_dvol(payload):
    """Deribit get_volatility_index_data -> [(ts_ms, o, h, l, c)]."""
    out = []
    for row in payload.get("result", {}).get("data", []):
        try:
            ts, o, h, l, c = row
            out.append((int(ts), float(o), float(h), float(l), float(c)))
        except (TypeError, ValueError):
            continue
    return out


def parse_binance_metrics_row(row):
    """One Binance metrics-ZIP CSV row -> {field: float} (create_time kept raw)."""
    numeric = (
        "sum_open_interest",
        "sum_open_interest_value",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    )
    return {"create_time": row.get("create_time"), **{k: float(row[k]) for k in numeric}}


def usable_for_bar(bar_close_ms, avail_ms, lag_ms):
    """Bar-t as-of guard: snapshot usable iff avail + lag <= bar close."""
    return avail_ms + lag_ms <= bar_close_ms


def usable_for_fill(fill_minute_ms, avail_ms):
    """Fill-t strict guard: availability must be strictly before fill minute."""
    return avail_ms < fill_minute_ms


def asof_series(records, query_ms, lag_ms=0):
    """Last record with avail+lag <= query (merge_asof backward); None if none."""
    best = None
    for avail_ms, value in records:
        if avail_ms + lag_ms <= query_ms:
            best = (avail_ms, value)
    return best


# ---------------------------------------------------------------- tests
def test_wiki_basic_and_bad_timestamp():
    p = {"items": [
        {"timestamp": "2021010100", "views": 10},
        {"timestamp": "bad", "views": 5},
        {"timestamp": "2021010200", "views": 7},
    ]}
    assert parse_wiki_pageviews(p) == [("2021-01-01", 10), ("2021-01-02", 7)]


def test_okx_funding_parses_and_skips_bad():
    p = {"data": [
        {"fundingTime": "1788220800000", "fundingRate": "0.0000279"},
        {"fundingTime": "oops", "fundingRate": "0.1"},
        {"nope": 1},
    ]}
    rows = parse_okx_funding_page(p)
    assert rows == [(1788220800000, 0.0000279)]
    assert rows[0][0] > 10**12  # ms, not seconds


def test_bybit_funding_parses():
    p = {"result": {"list": [
        {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingRateTimestamp": "1609459200000"},
        {"symbol": "BTCUSDT", "fundingRate": "bad", "fundingRateTimestamp": "1609462800000"},
    ]}}
    assert parse_bybit_funding_list(p) == [(1609459200000, 0.0001)]


def test_hl_funding_empty_and_basic():
    assert parse_hl_funding([]) == []
    assert parse_hl_funding([{"coin": "BTC", "fundingRate": "0.0001",
                              "time": 1684108800374}]) == [(1684108800374, 0.0001)]


def test_deribit_dvol_parses_and_skips():
    p = {"result": {"data": [[1625097600000, 103.8, 105.94, 101.96, 102.38], [], "x"]}}
    assert parse_deribit_dvol(p) == [(1625097600000, 103.8, 105.94, 101.96, 102.38)]
    assert parse_deribit_dvol({"result": {"data": []}}) == []


def test_binance_metrics_row_floats():
    row = {"create_time": "2024-01-01 00:00:00", "symbol": "BTCUSDT",
           "sum_open_interest": "74006.266", "sum_open_interest_value": "3.1e9",
           "count_toptrader_long_short_ratio": "1.368203",
           "sum_toptrader_long_short_ratio": "1.253668",
           "count_long_short_ratio": "1.507109",
           "sum_taker_long_short_vol_ratio": "1.311745"}
    d = parse_binance_metrics_row(row)
    assert d["create_time"] == "2024-01-01 00:00:00"
    assert math.isclose(d["sum_toptrader_long_short_ratio"], 1.253668)


def test_asof_guards_boundaries():
    assert usable_for_bar(100, 90, 10) is True
    assert usable_for_bar(100, 91, 10) is False  # lagged availability after close
    assert usable_for_fill(100, 99) is True
    assert usable_for_fill(100, 100) is False  # equality is leakage for fills


def test_asof_series_backward_and_none():
    recs = [(10, 1.0), (20, 2.0), (30, 3.0)]
    assert asof_series(recs, 25) == (20, 2.0)
    assert asof_series(recs, 5) is None
    assert asof_series(recs, 25, lag_ms=10) == (10, 1.0)


def test_causality_truncation_equals_full():
    """Features at T from data truncated at T equal full-data features at T."""
    full = [(10, 1.0), (20, 2.0), (30, 3.0), (40, 4.0)]
    for t in (10, 25, 40, 100):
        trunc = [(a, v) for a, v in full if a <= t]
        assert asof_series(full, t) == asof_series(trunc, t)
