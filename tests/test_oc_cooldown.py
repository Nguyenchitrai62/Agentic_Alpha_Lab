"""oc_cooldown tests: 24h per-coin cooldown logic on synthetic bars + ledger checks."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_cooldown"))
from run_cooldown import COOLDOWN, R2_DEPTHS, apply_cooldown, daily_stats, year_of


def _mk(rows):
    df = pd.DataFrame(rows)
    for c in ("bar_start", "exit_t"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def _rung(sym, bar, ext="rung_tp", ret=0.01, w=0.1, depth=2.5, fill="2022-01-01 00:00+00:00"):
    return {"symbol": sym, "depth": depth, "exit": ext, "ret": ret, "weight": w,
            "loss": w * ret, "bar_start": bar, "exit_t": bar, "fill_t": fill}


def test_strictly_after_stop():
    s = "2022-03-01 12:00+00:00"
    df = _mk([_rung("BTCUSDT", s, "rung_sl", -0.07),  # the stop itself: bar open == s
              _rung("BTCUSDT", s)])  # same-bar rung kept (resting order rule)
    out = apply_cooldown(df, COOLDOWN)
    assert not out.iloc[0] and not out.iloc[1]


def test_window_boundaries():
    s = pd.Timestamp("2022-03-01 12:00", tz="UTC")
    df = _mk([_rung("BTCUSDT", s, "rung_sl", -0.07),
              _rung("BTCUSDT", s + pd.Timedelta(hours=24)),  # inclusive end -> cooled
              _rung("BTCUSDT", s + pd.Timedelta(hours=24, minutes=1))])  # outside -> kept
    out = apply_cooldown(df, COOLDOWN)
    assert not out.iloc[0] and out.iloc[1] and not out.iloc[2]


def test_other_coin_unaffected_and_tp_no_trigger():
    s = "2022-03-01 12:00+00:00"
    df = _mk([_rung("BTCUSDT", s, "rung_tp", 0.02),  # TP is not a trigger
              _rung("ETHUSDT", "2022-03-01 16:00+00:00"),  # other coin kept
              _rung("BTCUSDT", "2022-03-01 16:00+00:00")])  # same coin kept (no stop)
    assert not apply_cooldown(df, COOLDOWN).any()


def test_multiple_stops_extend_union():
    df = _mk([_rung("XRPUSDT", "2022-03-01 00:00+00:00", "rung_sl", -0.08),
              _rung("XRPUSDT", "2022-03-01 20:00+00:00", "rung_sl", -0.06),
              _rung("XRPUSDT", "2022-03-02 18:00+00:00"),  # in 2nd window -> cooled
              _rung("XRPUSDT", "2022-03-02 21:00+00:00")])  # after both -> kept
    out = apply_cooldown(df, COOLDOWN)
    # [1] itself sits 20h after the first stop -> cooled (triggers are all stops)
    assert not out.iloc[0] and out.iloc[1] and out.iloc[2] and not out.iloc[3]


def test_daily_stats_maxdd():
    losses = pd.Series([1.0, -3.0, 1.0])
    dates = pd.Series(pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03"], utc=True))
    st = daily_stats(losses, dates)
    assert st["worst_day"] == -3.0
    assert abs(st["max_dd"] - -3.0) < 1e-12  # peak 1.0 -> trough -2.0
    st0 = daily_stats(pd.Series([], dtype=float), pd.Series([], dtype="datetime64[ns, UTC]"))
    assert st0 == {"worst_day": 0.0, "max_dd": 0.0, "ndays": 0}


def test_ledger_has_stop_exits_and_r2_depths():
    r = pd.read_parquet(ROOT / "research/tournament/oc_ddanat17/rungs_s0.parquet")
    assert (r["exit"] == "rung_sl").sum() >= 100
    assert set(R2_DEPTHS) <= set(r["depth"].unique())
    assert (pd.to_datetime(r["exit_t"], utc=True) > pd.to_datetime(r["bar_start"], utc=True)).all()


def test_year_of_edges():
    assert year_of(pd.Timestamp("2021-09-24", tz="UTC")) == 0
    assert year_of(pd.Timestamp("2022-09-23 23:59", tz="UTC")) == 0
    assert year_of(pd.Timestamp("2026-09-23", tz="UTC")) == 4
    assert year_of(pd.Timestamp("2026-09-24", tz="UTC")) is None
