"""Tests for oc_rungquality (IDEAS5 #9 dip-rung quality filter).

Causality/truncation + hand-checked synthetic cases. Run:
  .venv/Scripts/python.exe -m pytest tests/test_oc_rungquality.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_rungquality"))

from quality import (  # noqa: E402
    ANCH5,
    DEPTHS,
    MAJORS,
    MIN_N,
    N_BAR_WINDOW,
    fill_minute,
    pair_shift,
    skip_sets,
    trailing_stats,
    with_T,
)


def _ev(rows):
    return pd.DataFrame(rows)


def test_fill_minute_hand_and_grid():
    # 2021-10-15 09:05 UTC: 545 min since midnight.
    t = pd.Timestamp("2021-10-15 09:05", tz="UTC")
    assert fill_minute(t, 0) == 545 % 240  # 65
    assert fill_minute(t, 1) == (545 - 60) % 240  # 5
    assert fill_minute(t, 2) == (545 - 120) % 240
    # bar open maps to 0 on its own shift grid
    assert fill_minute(pd.Timestamp("2021-10-15 08:00", tz="UTC"), 0) == 0
    assert fill_minute(pd.Timestamp("2021-10-15 09:00", tz="UTC"), 1) == 0
    # all shifts stay in 0..239
    for s in range(4):
        assert 0 <= fill_minute(t, s) <= 239


def test_pair_fifo_hand():
    ev = _ev([
        {"t": pd.Timestamp("2022-01-01 01:00", tz="UTC"), "symbol": "BTCUSDT",
         "kind": "rung_fill", "rung": 2.5, "weight": 1.0, "ret": np.nan},
        {"t": pd.Timestamp("2022-01-01 01:10", tz="UTC"), "symbol": "BTCUSDT",
         "kind": "rung_fill", "rung": 3.0, "weight": 0.5, "ret": np.nan},
        {"t": pd.Timestamp("2022-01-01 01:12", tz="UTC"), "symbol": "BTCUSDT",
         "kind": "rung_sl", "rung": np.nan, "weight": 0.0, "ret": -0.02},
        {"t": pd.Timestamp("2022-01-01 01:20", tz="UTC"), "symbol": "BTCUSDT",
         "kind": "rung_tp", "rung": np.nan, "weight": 0.0, "ret": 0.01},
    ]).sort_values("t").reset_index(drop=True)
    rungs, unpaired, left = pair_shift(ev, 0)
    assert unpaired == 0 and left == 0 and len(rungs) == 2
    # FIFO: first fill (2.5) pairs the stop, second (3.0) pairs the TP
    assert rungs[0]["depth"] == 2.5 and rungs[0]["exit"] == "rung_sl"
    assert rungs[1]["depth"] == 3.0 and rungs[1]["exit"] == "rung_tp"
    # cross-symbol isolation
    ev2 = _ev([
        {"t": pd.Timestamp("2022-01-01 01:00", tz="UTC"), "symbol": "ETHUSDT",
         "kind": "rung_tp", "rung": np.nan, "weight": 0.0, "ret": 0.01},
    ])
    _, unpaired2, _ = pair_shift(ev2, 0)
    assert unpaired2 == 1


def _synthetic_pairs():
    """Two cells with contrasting quality inside W(2022-09-24).

    Cell A (BTC,2.5): 12 fills, 9 stops -> stop_rate 0.75.
    Cell B (ETH,5.0): 12 fills, 1 stop  -> stop_rate 1/12.
    All other cells: 0 fills. T = 2022-06-01 00:00 (inside [2022-06-20? ...]).
    W(2022-09-24) = [2022-06-19, 2022-09-17). Use T = 2022-07-01 00:00 shift 0.
    """
    rows = []
    base = pd.Timestamp("2022-07-01 00:00", tz="UTC")
    for i in range(12):
        ft = base + pd.Timedelta(minutes=16 + i)
        xt = ft + pd.Timedelta(minutes=10)
        rows.append({"symbol": "BTCUSDT", "depth": 2.5, "shift": 0,
                     "fill_t": ft, "exit_t": xt,
                     "exit": "rung_sl" if i < 9 else "rung_tp", "weight": 1.0, "ret": 0.0})
    for i in range(12):
        ft = base + pd.Timedelta(minutes=60 + i)
        xt = ft + pd.Timedelta(minutes=10)
        rows.append({"symbol": "ETHUSDT", "depth": 5.0, "shift": 1,
                     "fill_t": ft, "exit_t": xt,
                     "exit": "rung_sl" if i < 1 else "rung_tp", "weight": 1.0, "ret": 0.0})
    df = pd.DataFrame(rows)
    df["fill_t"] = pd.to_datetime(df["fill_t"], utc=True)
    df["exit_t"] = pd.to_datetime(df["exit_t"], utc=True)
    return with_T(df)


def test_stop_rate_hand_and_skip_direction():
    pairs = _synthetic_pairs()
    st = trailing_stats(pairs, "2022-09-24")
    a = st[(st["sym"] == "BTCUSDT") & (st["depth"] == 2.5)].iloc[0]
    b = st[(st["sym"] == "ETHUSDT") & (st["depth"] == 5.0)].iloc[0]
    assert a["n_fill"] == 12 and a["n_stop"] == 9
    assert abs(a["stop_rate"] - 0.75) < 1e-12
    assert abs(b["stop_rate"] - 1 / 12) < 1e-12
    assert abs(a["fill_rate"] - 12 / N_BAR_WINDOW) < 1e-12
    sk = skip_sets(st)
    # F1 skips the high-stop cell only (p80 over 2 finite cells = 0.75*0.2+...; check membership)
    assert ["BTCUSDT", 2.5] in sk["f1"]
    assert ["ETHUSDT", 5.0] not in sk["f1"]
    # F2 superset of F1. Here p20 == 0.0 (23/25 cells have fill_rate exactly 0) so the
    # frozen strict-inequality tie rule (ties keep) adds nothing: F2 == F1.
    assert set(map(tuple, sk["f1"])).issubset(set(map(tuple, sk["f2"])))
    assert sk["p20"] == 0.0 and sk["f2"] == sk["f1"]


def _count_fixture(counts):
    """Fabricate pairs with n_fill per cell = counts[(sym, depth)] (TP exits)."""
    rows = []
    base = pd.Timestamp("2022-07-01 00:00", tz="UTC")
    k = 0
    for (sym, depth), c in counts.items():
        for i in range(c):
            ft = base + pd.Timedelta(minutes=(k % 200) + 16)
            rows.append({"symbol": sym, "depth": depth, "shift": 0, "fill_t": ft,
                         "exit_t": ft + pd.Timedelta(minutes=10), "exit": "rung_tp",
                         "weight": 1.0, "ret": 0.0})
            k += 1
    df = pd.DataFrame(rows)
    df["fill_t"] = pd.to_datetime(df["fill_t"], utc=True)
    df["exit_t"] = pd.to_datetime(df["exit_t"], utc=True)
    return with_T(df)


def test_f2_adds_chronic_nonfillers_when_p20_above_zero():
    counts = {(s, d): i for i, (s, d)
              in enumerate([(s, d) for s in MAJORS for d in DEPTHS])}
    # counts 0..24: p20 position 0.2*24 = 4.8 -> p20 = 4 + 0.8 = 4.8 fills
    pairs = _count_fixture(counts)
    st = trailing_stats(pairs, "2022-09-24")
    sk = skip_sets(st)
    assert abs(sk["p20"] * N_BAR_WINDOW - 4.8) < 1e-9
    skipped = set(map(tuple, sk["f2"]))
    # cells with n_fill in {0,1,2,3,4} skipped; cell with 5 kept (strict <)
    assert len([c for c in skipped if counts[c] < 5]) == 5
    assert all(counts[c] < 5 for c in skipped)


def test_ties_keep_and_min_n_never_skipped():
    pairs = _synthetic_pairs()
    st = trailing_stats(pairs, "2022-09-24")
    sk = skip_sets(st)
    # a cell exactly AT p80 must be kept (strict >)
    sr = st["stop_rate"].dropna().to_numpy(float)
    p80 = float(np.quantile(sr, 0.80))
    at = st[np.isclose(st["stop_rate"], p80)]
    for r in at.itertuples():
        assert [str(r.sym), float(r.depth)] not in sk["f1"]
    # cells with < MIN_N fills are never F1-skipped: inject a 100%-stop tiny cell
    tiny = pd.DataFrame([{"symbol": "SOLUSDT", "depth": 3.0, "shift": 0,
                           "fill_t": pd.Timestamp("2022-07-02 00:16", tz="UTC"),
                           "exit_t": pd.Timestamp("2022-07-02 00:26", tz="UTC"),
                           "exit": "rung_sl", "weight": 1.0, "ret": 0.0,
                           "T": pd.Timestamp("2022-07-02 00:00", tz="UTC")}])
    big = pd.concat([pairs, tiny], ignore_index=True)
    st2 = trailing_stats(big, "2022-09-24")
    row = st2[(st2["sym"] == "SOLUSDT") & (st2["depth"] == 3.0)].iloc[0]
    assert row["n_fill"] == 1 and not np.isfinite(row["stop_rate"])
    sk2 = skip_sets(st2)
    assert ["SOLUSDT", 3.0] not in sk2["f1"]


def test_trailing_truncation_causal():
    pairs = _synthetic_pairs()
    full = trailing_stats(pairs, "2022-09-24")
    # dropping everything after the window end leaves stats unchanged
    cut = pairs[pairs["fill_t"] < pd.Timestamp("2022-09-17", tz="UTC")]
    assert len(cut) == len(pairs)  # nothing after the cut in this fixture
    assert trailing_stats(cut, "2022-09-24")["n_fill"].sum() == full["n_fill"].sum()
    # a fill placed after the embargo is excluded even if its T is inside
    late = pairs.copy()
    late.loc[late.index[0], "exit_t"] = pd.Timestamp("2022-09-20", tz="UTC")
    st_late = trailing_stats(late, "2022-09-24")
    assert st_late["n_fill"].sum() == full["n_fill"].sum() - 1
    # shifting post-cutoff data cannot change the kept prefix
    assert full["n_stop"].sum() == 10


def test_empty_window_gives_empty_skip():
    empty = pd.DataFrame(columns=["symbol", "depth", "shift", "fill_t", "exit_t",
                                  "exit", "weight", "ret", "T"])
    st = trailing_stats(empty, "2021-09-24")
    assert (st["n_fill"] == 0).all()
    sk = skip_sets(st)
    assert sk["f1"] == [] and sk["f2"] == []
    assert not np.isfinite(sk["p80"])


def test_with_T_on_shift_grid():
    df = pd.DataFrame([{"fill_t": pd.Timestamp("2021-10-15 09:05", tz="UTC"), "shift": 0}])
    out = with_T(df)
    assert out["T"].iloc[0] == pd.Timestamp("2021-10-15 08:00", tz="UTC")
    # T is always on the shift's 4h grid: (T - shift hours) % 4h == 0
    df2 = pd.DataFrame([{"fill_t": pd.Timestamp("2021-10-16 12:52", tz="UTC"), "shift": 1}])
    t2 = with_T(df2)["T"].iloc[0]
    assert (t2 - pd.Timestamp("2021-10-16 01:00", tz="UTC")).total_seconds() % 14400 == 0


def test_cell_universe_is_25():
    pairs = _synthetic_pairs()
    st = trailing_stats(pairs, "2022-09-24")
    assert len(st) == 25
    assert set(st["sym"]) == set(MAJORS)
    assert sorted(st["depth"].unique().tolist()) == [2.5, 3.0, 3.5, 4.0, 5.0]
    assert N_BAR_WINDOW == 2160
    assert MIN_N == 10


def test_run_variant_k_matches_skipped_and_sums():
    """Hand-checked replica math on a tiny ledger + k_skipped regression test.

    Guards the loop-variable shadowing bug (block loop reusing `k` made the
    stored k_skipped == n_y - 1 while the permutations used the true count).
    """
    sys.path.insert(0, str(ROOT / "research/tournament/oc_rungquality"))
    import compute_replica_gate as g  # noqa: E402
    # toy-ledger base 4-phase-mean sum5y = 1.0 + 1.0 = 2.0; relax the module gate
    g.BASE_GATE = 2.0
    # 8 fills: year 0 (phase 0, coin 0, rung 0, y=+1 x2) and year 1 (y=-1 x2 + y=+3 x2)
    n = 8
    ph = np.array([0, 0, 0, 0, 0, 0, 0, 0])
    yr = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    co = np.zeros(n, dtype=int)
    ru = np.zeros(n, dtype=int)
    w = np.ones(n)
    yv = np.array([1.0, 1.0, 1.0, 1.0, -1.0, -1.0, 3.0, 3.0])
    bt = np.array([pd.Timestamp("2021-10-01", tz="UTC")] * 4
                  + [pd.Timestamp("2022-10-01", tz="UTC")] * 4)
    skip = [{(0, 0)}, set(), set(), set(), set()]  # skip all year-0 fills (F1-style)
    years, placebo, dsum, sum_ge, base_y, filt_y = g.run_variant(
        "F1", skip, ph, yr, co, ru, w, yv, bt, n)
    # base year0 = mean over phases of phase-0 sum = 4.0/4 = 1.0; filt year0 = 0
    assert base_y[0] == 1.0 and filt_y[0] == 0.0
    assert base_y[1] == 1.0 and filt_y[1] == 1.0  # untouched year
    assert dsum == -1.0
    for row, pl in zip(years, placebo):
        assert pl["k_skipped"] == row["n_skipped"], (pl, row)
    assert years[0]["n_skipped"] == 4 and placebo[0]["k_skipped"] == 4
    assert years[1]["n_skipped"] == 0 and placebo[1]["k_skipped"] == 0
    g.BASE_GATE = 7.718304
