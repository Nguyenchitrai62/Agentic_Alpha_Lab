"""oc_usdtdepeg tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd
import pytest

from research.tournament.oc_usdtdepeg import backtest as B

MAKER, TAKER = 0.0002, 0.00055
ROOT = Path(__file__).resolve().parents[1]


def _rows(ohlc: list[tuple[float, float, float, float]],
          day: str = "2022-05-12"):
    t0 = pd.Timestamp(f"{day} 00:00", tz="UTC")
    out = []
    for k, (o, h, l, c) in enumerate(ohlc):
        out.append({"t": t0 + pd.Timedelta(hours=k),
                    "open": o, "high": h, "low": l, "close": c})
    return out


def test_strict_trade_through_entry():
    # E1: signal bar0 close 0.9970 -> L = 0.9969. bar1 low == L (touch only)
    # must NOT fill; bar2 trades through -> fill at L; bar3 hits TP.
    rows = _rows([
        (0.9980, 0.9981, 0.9969, 0.9970),
        (0.9970, 0.9972, 0.9969, 0.9971),
        (0.9971, 0.9972, 0.9968, 0.9970),
        (0.9970, 0.9996, 0.9970, 0.9994),
    ])
    ev, inc = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert inc == [] and len(ev) == 1
    e = ev[0]
    assert (e["signal_i"], e["fill_i"], e["exit_i"]) == (0, 2, 3)
    assert e["exit"] == "tp" and e["exit_px"] == pytest.approx(0.9995)
    assert e["limit"] == pytest.approx(0.9969)
    assert e["net"] == pytest.approx((0.9995 - 0.9969) / 0.9969 - 0.0004)


def test_touch_only_never_fills():
    # Only bar0 signals (later closes sit above the trigger); lows touch L
    # exactly inside the window -> strict trade-through never fires.
    rows = _rows([
        (0.9980, 0.9981, 0.9969, 0.9970),
        (0.9976, 0.9978, 0.9969, 0.9977),
        (0.9977, 0.9979, 0.9969, 0.9978),
        (0.9978, 0.9980, 0.9969, 0.9979),
        (0.9979, 0.9981, 0.9970, 0.9980),
    ])
    ev, inc = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert ev == [] and inc == []


def test_stop_first_same_bar():
    # E2: signal close 0.9940 -> L = 0.9939. Fill bar also touches stop
    # (low 0.984 <= 0.985) and TP (high 1.0 > 0.999) -> STOP wins.
    rows = _rows([
        (0.9960, 0.9961, 0.9939, 0.9940),
        (0.9939, 1.0000, 0.9840, 0.9990),
    ])
    ev, inc = B.simulate(rows, 0.995, 0.999, 0.985, MAKER, TAKER)
    assert len(ev) == 1
    e = ev[0]
    assert (e["fill_i"], e["exit_i"]) == (1, 1)
    assert e["exit"] == "stop" and e["exit_px"] == pytest.approx(0.985)
    assert e["net"] == pytest.approx((0.985 - 0.9939) / 0.9939 - 0.00075)


def test_cap_exit_exact():
    # E1: fill at bar1, flat bars after -> cap exit at fill+72 close, taker.
    # Flat closes sit above the trigger so no trailing signals fire.
    flat = [(0.9980, 0.9981, 0.9979, 0.9980)] * 80
    rows = _rows([
        (0.9980, 0.9981, 0.9960, 0.9970),
        (0.9970, 0.9971, 0.9958, 0.9960),
        *flat,
    ])
    rows[1 + 72 + 1 - 1] = dict(rows[1 + 72],
                                close=0.9990)  # cap bar close (index 73)
    ev, inc = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert inc == [] and len(ev) == 1
    e = ev[0]
    assert e["fill_i"] == 1 and e["exit"] == "cap" and e["exit_i"] == 73
    assert e["exit_px"] == pytest.approx(0.9990)
    assert e["net"] == pytest.approx((0.9990 - 0.9969) / 0.9969 - 0.00075)


def test_one_position_blocks_overlap():
    # Second signal (bar2) fires while IN_POSITION -> ignored; one event.
    rows = _rows([
        (0.9980, 0.9981, 0.9960, 0.9970),
        (0.9970, 0.9971, 0.9958, 0.9960),
        (0.9960, 0.9962, 0.9940, 0.9945),  # would-be second signal
        (0.9945, 0.9996, 0.9945, 0.9994),  # TP for the first position
    ])
    ev, inc = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert len(ev) == 1 and ev[0]["signal_i"] == 0 and ev[0]["exit"] == "tp"


def test_retail_fees_erase_edge():
    rows = _rows([
        (0.9980, 0.9981, 0.9969, 0.9970),
        (0.9970, 0.9972, 0.9968, 0.9970),
        (0.9970, 0.9996, 0.9970, 0.9994),
    ])
    ev, _ = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert len(ev) == 1 and ev[0]["net"] > 0
    rn = B.renet(ev, 0.004, 0.006)
    assert rn[0] == pytest.approx(ev[0]["net"] - (0.004 - MAKER) * 2)
    assert rn[0] < 0


def test_causality_truncation_real_data():
    df = pd.read_parquet(
        ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    rows = [{"t": df["open_time"].iloc[k], "open": float(df["open"].iloc[k]),
             "high": float(df["high"].iloc[k]), "low": float(df["low"].iloc[k]),
             "close": float(df["close"].iloc[k])} for k in range(len(df))]
    ev_full, _ = B.simulate(rows, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert len(ev_full) >= 10  # five-year testability floor input
    cut = ev_full[-1]["exit_i"] + 10
    ev_tr, _ = B.simulate(rows[:cut], 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    key = lambda e: (e["signal_t"], e["fill_t"], e["exit_t"], e["exit"],
                     round(e["net"], 12))
    assert [key(e) for e in ev_tr] == [key(e) for e in ev_full
                                       if e["exit_i"] < cut]
    # signal uses the close only: a far-later close perturbation changes nothing
    rows2 = [dict(r) for r in rows[:cut]]
    rows2[-1]["close"] = 0.5
    ev2, _ = B.simulate(rows2, 0.9975, 0.9995, 0.9900, MAKER, TAKER)
    assert [key(e) for e in ev2] == [key(e) for e in ev_tr]


def test_g2_baseline_spot_check():
    import importlib.util
    p = (ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    spec = importlib.util.spec_from_file_location("rm_depeg", p)
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    runs = pickle.loads(
        (ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/"
         "v421_runs.pkl").read_bytes())
    assert rm.year_reset(runs, "R2B1D17BFG2", 0) == {"R": 2.588, "DD": 10.86}
    assert rm.year_reset(runs, "R2B1D17BFG2", 4) == {"R": 4.648, "DD": 12.9}
