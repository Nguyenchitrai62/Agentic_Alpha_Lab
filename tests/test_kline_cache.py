"""Binance kline fetch: transient-error retry and the on-disk store of closed klines (fetch_klines_cached)."""

from datetime import datetime, timezone

import pandas as pd
import pytest
import requests

from agentic_alpha_lab.data import binance_usdm as bu

STEP = 60_000
T0 = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)


class Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload, headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeExchange:
    """1m klines from T0 to the server time; optional queue of error statuses served first."""

    def __init__(self, server_ms, errors=()):
        self.server_ms, self.errors, self.kline_calls = server_ms, list(errors), 0

    def get(self, url, params=None, timeout=None):
        if self.errors:
            return Resp(self.errors.pop(0), headers={"Retry-After": "1"})
        if url.endswith("/time"):
            return Resp(200, {"serverTime": self.server_ms})
        self.kline_calls += 1
        a = max(params["startTime"], T0)
        a = -(-a // STEP) * STEP
        b = min(params["endTime"], self.server_ms)
        rows = []
        for t in range(a, b + 1, STEP):
            if len(rows) == params["limit"]:
                break
            p = 100 + (t - T0) / STEP
            rows.append([t, p, p + 1, p - 1, p + 0.5, 10, t + STEP - 1, 1000, 5, 4, 400, "0"])
        return Resp(200, rows)


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(bu.time, "sleep", lambda s: None)


def test_transient_statuses_are_retried():
    ex = FakeExchange(T0 + 100 * STEP, errors=[429, 503])
    f = bu.fetch_klines("BTCUSDT", "1m", ts(T0), ts(T0 + 50 * STEP), session=ex)
    assert len(f) == 51


def test_persistent_error_still_raises():
    ex = FakeExchange(T0 + 100 * STEP, errors=[429] * bu.RETRY_ATTEMPTS)
    with pytest.raises(requests.HTTPError):
        bu.fetch_klines("BTCUSDT", "1m", ts(T0), ts(T0 + 50 * STEP), session=ex)


def test_client_errors_are_not_retried():
    ex = FakeExchange(T0 + 100 * STEP, errors=[400, 200])
    with pytest.raises(requests.HTTPError):
        bu.fetch_klines("BTCUSDT", "1m", ts(T0), ts(T0 + 50 * STEP), session=ex)


def test_cached_fetch_equals_direct_fetch_and_only_downloads_new_candles(tmp_path):
    ex = FakeExchange(T0 + 3000 * STEP + 30_000)  # mid-candle: the forming candle is never returned or stored
    ref = bu.fetch_klines("BTCUSDT", "1m", ts(T0 + 1000 * STEP), ts(T0 + 3000 * STEP), session=ex)
    seed = bu.fetch_klines_cached("BTCUSDT", "1m", ts(T0 + 2000 * STEP), ts(T0 + 2500 * STEP), session=ex, cache_dir=tmp_path)
    assert len(seed) == 501
    got = bu.fetch_klines_cached("BTCUSDT", "1m", ts(T0 + 1000 * STEP), ts(T0 + 3000 * STEP), session=ex, cache_dir=tmp_path)
    pd.testing.assert_frame_equal(got, ref)
    calls = ex.kline_calls
    again = bu.fetch_klines_cached("BTCUSDT", "1m", ts(T0 + 1000 * STEP), ts(T0 + 2999 * STEP), session=ex, cache_dir=tmp_path)
    assert ex.kline_calls == calls  # fully stored: no request at all
    pd.testing.assert_frame_equal(again, ref)  # the candle at +3000 was still forming: ref ends at +2999
    ex.server_ms += 10 * STEP  # ten new closed candles: one small tail request
    newer = bu.fetch_klines_cached("BTCUSDT", "1m", ts(T0 + 1000 * STEP), None, session=ex, cache_dir=tmp_path)
    assert ex.kline_calls == calls + 1 and len(newer) == len(ref) + 10
    assert newer["close_time"].max() < pd.Timestamp(ex.server_ms, unit="ms", tz="UTC")


def test_damaged_cache_is_rebuilt(tmp_path):
    ex = FakeExchange(T0 + 200 * STEP)
    (tmp_path / "BTCUSDT_1m.parquet").write_bytes(b"not parquet")
    got = bu.fetch_klines_cached("BTCUSDT", "1m", ts(T0), ts(T0 + 100 * STEP), session=ex, cache_dir=tmp_path)
    assert len(got) == 101
