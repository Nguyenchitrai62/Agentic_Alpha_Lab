"""R82 shadow-log causality test: targets at bar t ignore later bars."""
import importlib.util
from datetime import datetime, timedelta, timezone

RESEARCH_SHADOW = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "research"
    / "opencode_r82_ma_replication"
    / "shadow_log.py"
)

spec = importlib.util.spec_from_file_location("r82_shadow_log", RESEARCH_SHADOW)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _bars(n, start=100.0, step=0.7):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    daily, four_h = [], []
    px = start
    for i in range(n):
        px = px + step * (1 if i % 7 else -2)
        daily.append(
            {
                "open_time": base + timedelta(days=i),
                "close": px,
                "close_time": base + timedelta(days=i, hours=23, minutes=59, seconds=59),
            }
        )
    hpx = start
    for i in range(n * 6):
        hpx = hpx + 0.11 * (1 if i % 5 else -1.5)
        four_h.append(
            {
                "open_time": base + timedelta(hours=4 * i),
                "close": hpx,
                "close_time": base + timedelta(hours=4 * i + 3, minutes=59),
            }
        )
    return daily, four_h


def test_targets_at_t_unchanged_when_later_bars_appended():
    daily, four_h = _bars(260)
    full = mod.build_lines(daily, four_h)
    k = 210  # beyond SMA200 warm-up so targets are non-trivial
    prefix = mod.build_lines(daily[:k], [b for b in four_h if b["close_time"] <= daily[k - 1]["close_time"]])
    assert len(prefix) == k
    for i in range(k):
        assert full[i]["h4_target"] == prefix[i]["h4_target"], i
        assert full[i]["sel_4h_ema20_200_ribbon_long"] == prefix[i]["sel_4h_ema20_200_ribbon_long"], i
        assert full[i]["data_hash"] == prefix[i]["data_hash"], i
