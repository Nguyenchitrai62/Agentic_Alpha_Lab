import pandas as pd
import pytest

from agentic_alpha_lab.data.coverage import require_closed_coverage_after_refetch


def _frame(times):
    return pd.DataFrame({"open_time": pd.to_datetime(times, utc=True)})


def test_interior_exchange_gap_is_tolerated_and_reported():
    t = pd.date_range("2026-05-08 00:00", "2026-05-08 09:00", freq="h", tz="UTC")
    kept = [x for x in t if not (2 <= x.hour <= 6)]
    gaps = require_closed_coverage_after_refetch(_frame(kept), t[0], t[-1] + pd.Timedelta("1h"), "1h")
    assert gaps == [(int(t[2].value // 1_000_000), int(t[6].value // 1_000_000))]


def test_missing_latest_closed_candle_still_raises():
    t = pd.date_range("2026-05-08 00:00", "2026-05-08 09:00", freq="h", tz="UTC")
    with pytest.raises(RuntimeError, match="Missing closed 1h candles at the tail"):
        require_closed_coverage_after_refetch(_frame(t[:-1]), t[0], t[-1] + pd.Timedelta("1h"), "1h")
