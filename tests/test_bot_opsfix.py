"""bot_opsfix: shared kline cache (hit/miss/expiry) + skipped_below_minimum dedupe. No network, no keys."""
import pandas as pd

from bot.bybit_v5 import KLINE_CACHE_TTL, cached_1m_rows, cached_call
from bot.run import Runner

T0 = pd.Timestamp("2026-10-05 04:00", tz="UTC")


def _fetcherbox(val, counter):
    def _fetch():
        counter[0] += 1
        return val
    return _fetch


def test_cache_miss_then_hit(tmp_path):
    n = [0]
    v1, hit1 = cached_call("BTCUSDT", "close_1m", _fetcherbox(50000.0, n),
                           cache_dir=tmp_path, ttl=KLINE_CACHE_TTL, now=1000.0)
    assert (v1, hit1, n[0]) == (50000.0, False, 1)  # miss fetches
    v2, hit2 = cached_call("BTCUSDT", "close_1m", _fetcherbox(50000.0, n),
                           cache_dir=tmp_path, ttl=KLINE_CACHE_TTL, now=1005.0)
    assert (v2, hit2, n[0]) == (50000.0, True, 1)  # second runner hits: ~1 request per TTL


def test_cache_expiry(tmp_path):
    n = [0]
    cached_call("BTCUSDT", "close_1m", _fetcherbox(1.0, n),
                cache_dir=tmp_path, ttl=20.0, now=1000.0)
    assert n[0] == 1
    v, hit = cached_call("BTCUSDT", "close_1m", _fetcherbox(2.0, n),
                         cache_dir=tmp_path, ttl=20.0, now=1019.9)
    assert (v, hit, n[0]) == (1.0, True, 1)  # inside TTL: stale value reused, no refetch
    v, hit = cached_call("BTCUSDT", "close_1m", _fetcherbox(2.0, n),
                         cache_dir=tmp_path, ttl=20.0, now=1020.0)
    assert (v, hit, n[0]) == (2.0, False, 2)  # TTL expired: refetch


def test_cached_1m_rows_shared(tmp_path):
    calls = [0]

    def _fetch(s, e):
        calls[0] += 1
        return [[str(e - 60_000), "1", "2", "0.5", "1.5", "0", "0"],
                [str(s), "1", "2", "0.5", "1.4", "0", "0"]]

    s, e = 1_700_000_000_000, 1_700_000_000_000 + 120_000
    r1, h1 = cached_1m_rows("ETHUSDT", s, e, _fetch, cache_dir=tmp_path, now=2000.0)
    assert h1 is False and calls[0] == 1
    r2, h2 = cached_1m_rows("ETHUSDT", s, e, _fetch, cache_dir=tmp_path, now=2005.0)
    assert h2 is True and calls[0] == 1  # second runner: no extra request
    assert sorted(int(r[0]) for r in r2) == sorted(int(r[0]) for r in r1)
    r3, h3 = cached_1m_rows("ETHUSDT", s, e, _fetch, cache_dir=tmp_path, now=2025.0)
    assert h3 is False and calls[0] == 2  # past TTL: refetch


def _mk_runner_min():
    r = Runner.__new__(Runner)
    r._skip_logged = {}
    r.logs = []
    r.log = lambda rec: r.logs.append(rec)
    return r


def test_skipped_dedupe_per_link_bar():
    r = _mk_runner_min()
    r._log_skipped(["d3BTC40hrvicE", "d3BTC50hrvicE"], T0, 5000.0)
    assert len([l for l in r.logs if l.get("op") == "skipped_below_minimum"]) == 1
    r._log_skipped(["d3BTC40hrvicE", "d3BTC50hrvicE"], T0 + pd.Timedelta(minutes=20), 5000.0)
    assert len([l for l in r.logs if l.get("op") == "skipped_below_minimum"]) == 1  # same bar: silent
    r._log_skipped(["d3BTC40hrvicE", "d3BTC50hrvicE", "d0BTC35hrvdcE"],
                   T0 + pd.Timedelta(minutes=20), 5000.0)
    last = [l for l in r.logs if l.get("op") == "skipped_below_minimum"][-1]
    assert last["links"] == ["d0BTC35hrvdcE"]  # same bar: only the new link logs
    r._log_skipped(["d3BTC40hrvicE"], T0 + pd.Timedelta(hours=5), 5000.0)
    assert len([l for l in r.logs if l.get("op") == "skipped_below_minimum"]) == 3  # new 4h bar: log again


def test_last_close_1m_shared_across_runners(tmp_path):
    class FakePub:
        def __init__(self):
            self.calls = 0

        def klines(self, s, interval="1", limit=2):
            self.calls += 1
            return [["2", "1", "1", "1", "50000", "0", "0"],
                    ["1", "1", "1", "1", "49999", "0", "0"]]

    def _runner():
        r = Runner.__new__(Runner)
        r.mode = "dry"
        r.ex = FakePub()
        r._kline_cache_dir_override = tmp_path
        return r

    r1, r2 = _runner(), _runner()
    assert r1.last_close_1m()["BTCUSDT"] == 49999.0 and r1.ex.calls == 5
    assert r2.last_close_1m()["BTCUSDT"] == 49999.0 and r2.ex.calls == 0  # all 5 symbols hit
