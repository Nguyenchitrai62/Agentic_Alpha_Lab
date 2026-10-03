"""Closed-candle coverage checks; future/forming bars never count as missing."""

import pandas as pd


def missing_ranges(opens, first: int, last: int, step: int) -> list[tuple[int, int]]:
    """Inclusive UTC opening-time ranges, including interior holes and missing tails."""
    if first > last:
        return []
    cursor, gaps = first, []
    for t in sorted(set(int(t) for t in opens if first <= int(t) <= last)):
        if (t - first) % step:
            raise ValueError("Candle opening time is off the expected grid")
        if t > cursor:
            gaps.append((cursor, t - step))
        cursor = t + step
    if cursor <= last:
        gaps.append((cursor, last))
    return gaps


def require_closed_coverage(frame, start, now, interval: str) -> None:
    step = pd.Timedelta(interval)
    first = pd.Timestamp(start).floor(interval)
    last = pd.Timestamp(now).floor(interval) - step
    gaps = missing_ranges((int(t.value // 1_000_000) for t in pd.to_datetime(frame["open_time"], utc=True)),
                          int(first.value // 1_000_000), int(last.value // 1_000_000), int(step.value // 1_000_000))
    if gaps:
        raise RuntimeError(f"Missing closed {interval} candles: {len(gaps)} ranges, first {gaps[0]}")


def require_closed_coverage_after_refetch(frame, start, now, interval: str) -> list[tuple[int, int]]:
    """Coverage check for a frame whose every missing range was just re-requested from the exchange.

    Interior ranges that are still missing were confirmed empty by the exchange (a venue outage, e.g. Coinbase
    2026-05-08 02:00-05:00 UTC) and are returned instead of raising; a missing tail (the latest closed candle) is
    never tolerated, so stale data still fails loudly.
    """
    step = pd.Timedelta(interval)
    first = pd.Timestamp(start).floor(interval)
    last = int((pd.Timestamp(now).floor(interval) - step).value // 1_000_000)
    gaps = missing_ranges((int(t.value // 1_000_000) for t in pd.to_datetime(frame["open_time"], utc=True)),
                          int(first.value // 1_000_000), last, int(step.value // 1_000_000))
    if gaps and gaps[-1][1] == last:
        raise RuntimeError(f"Missing closed {interval} candles at the tail (latest closed bar): {gaps[-1]}")
    return gaps
