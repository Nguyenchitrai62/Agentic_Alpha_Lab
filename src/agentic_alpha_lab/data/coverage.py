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
