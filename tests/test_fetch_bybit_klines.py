"""Tests for scripts/fetch_bybit_klines.py (no network: mocked responses only)."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_bybit_klines", ROOT / "scripts/fetch_bybit_klines.py")
fb = importlib.util.module_from_spec(spec)
sys.modules["fetch_bybit_klines"] = fb
spec.loader.exec_module(fb)

M = 60_000
T0 = 1622505600000  # 2021-06-01 00:00 UTC


def mock_list_newest_first(n, start_ms=T0):
    """Fake Bybit result.list: n minute rows starting at start_ms, NEWEST FIRST."""
    rows = []
    for i in range(n):
        t = start_ms + i * M
        rows.append([str(t), "100.0", "101.0", "99.0", "100.5", "1.5", "150.0"])
    return rows[::-1]


def test_parse_newest_first_order():
    df = fb.parse_kline_list(mock_list_newest_first(5))
    assert df["open_time"].tolist() == [T0 + i * M for i in range(5)]
    assert df["open"].tolist() == [100.0] * 5
    assert str(df["open_time"].dtype) == "int64"
    assert str(df["close"].dtype) == "float64"
    assert list(df.columns) == ["open_time", "open", "high", "low", "close", "volume", "turnover"]


def test_parse_empty():
    df = fb.parse_kline_list([])
    assert len(df) == 0
    assert list(df.columns) == ["open_time", "open", "high", "low", "close", "volume", "turnover"]


def test_dedup_merge():
    a = fb.parse_kline_list(mock_list_newest_first(5, T0))
    b = fb.parse_kline_list(mock_list_newest_first(5, T0 + 3 * M))  # overlaps 2 rows
    out = fb.merge_klines(a, b)
    assert len(out) == 8
    assert out["open_time"].is_unique
    assert out["open_time"].tolist() == sorted(out["open_time"].tolist())


def test_resume_skips_complete_chunks():
    have = {T0 + i * M for i in range(2000)}  # two full chunks present
    todo = fb.chunks_to_fetch(have, T0, T0 + 2999 * M)
    assert (T0, T0 + 999 * M) not in todo
    assert (T0 + 1000 * M, T0 + 1999 * M) not in todo
    assert (T0 + 2000 * M, T0 + 2999 * M) in todo  # partial chunk refetched


def test_resume_refetches_partial_chunk_only():
    have = {T0 + i * M for i in range(1000)} | {T0 + 1000 * M}  # 1 full + 1 partial
    todo = fb.chunks_to_fetch(have, T0, T0 + 1999 * M)
    assert todo == [(T0 + 1000 * M, T0 + 1999 * M)]


def test_resume_skips_prelisting_with_manifest_first():
    first = T0 + 2000 * M  # listing starts later (e.g. SOL/BNB)
    todo = fb.chunks_to_fetch(set(), T0, T0 + 2999 * M, known_first_ms=first)
    assert all(ce >= first for _, ce in todo)
    assert todo[0][0] >= first - 999 * M  # straddling chunk kept, earlier ones skipped


def test_missing_ranges():
    have = [T0 + i * M for i in range(10) if i not in (3, 4, 7)]
    gaps = fb.find_missing_ranges(have, T0, T0 + 9 * M)
    assert gaps == [[T0 + 3 * M, T0 + 4 * M], [T0 + 7 * M, T0 + 7 * M]]


def test_missing_ranges_none():
    have = [T0 + i * M for i in range(10)]
    assert fb.find_missing_ranges(have, T0, T0 + 9 * M) == []


def test_chunk_ranges_cover_exactly():
    chunks = fb.chunk_ranges(T0, T0 + 2500 * M)
    assert chunks[0] == (T0, T0 + 999 * M)
    assert chunks[-1] == (T0 + 2000 * M, T0 + 2500 * M)
    covered = sum((ce - cs) // M + 1 for cs, ce in chunks)
    assert covered == 2501


def test_last_closed_minute():
    now_ms = T0 + 123 * M + 45_000
    assert fb.last_closed_minute_ms(now_ms) == T0 + 122 * M
