"""scripts/forward_trade_phase.py (R2-4P sub-book plans, registry v376).

Fast (no network, no data): the shifted-grid builder, the settlement flags, the book forward-fill and the opens helpers.
Slow (marked, skipped when the local 1m archive / research tables are missing): the research-books replay mode of the paper script must
reproduce the v376 research harness (research/diagnostics/phase_offset_full prep_idx + pipe_setup, phase_agents agent tables, engine_user)
on the same shifted grid and window - same events, same equity.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ftp = _load("forward_trade_phase_test", ROOT / "scripts/forward_trade_phase.py")
UTC = "UTC"


# ------------------------------------------------------------------ fast
@pytest.mark.parametrize("s", [0, 1, 2, 3])
def test_shifted_grid_on_phase_lattice(s):
    start = ftp.PHASE_START[s]
    assert start == pd.Timestamp("2026-10-04T04:00Z") + pd.Timedelta(hours=s)
    assert ftp.on_phase(start, s)
    now = start + pd.Timedelta(days=3, hours=2, minutes=7)
    cur = ftp.phase_floor(now, s)
    assert cur <= now < cur + pd.Timedelta(hours=4) and (cur.hour - s) % 4 == 0 and cur.minute == 0
    g = ftp.shifted_grid(start, cur - pd.Timedelta(hours=4), s)
    assert (np.diff(g.asi8) == 4 * 3600 * 10**9).all()
    assert all((t.hour - s) % 4 == 0 for t in g)
    assert g[-1] == cur - pd.Timedelta(hours=4) and g[0] == start - ftp.WARMUP
    assert start - pd.Timedelta(hours=4) in g  # the decision row of the first traded bar


def test_phase_floor_examples():
    t = pd.Timestamp("2026-10-04T06:59Z")
    assert ftp.phase_floor(t, 0) == pd.Timestamp("2026-10-04T04:00Z")
    assert ftp.phase_floor(t, 1) == pd.Timestamp("2026-10-04T05:00Z")
    assert ftp.phase_floor(t, 2) == pd.Timestamp("2026-10-04T06:00Z")
    assert ftp.phase_floor(t, 3) == pd.Timestamp("2026-10-04T03:00Z")
    assert not ftp.on_phase(pd.Timestamp("2026-10-04T05:00Z"), 0)
    with pytest.raises(ValueError):
        ftp.build(0, pd.Timestamp("2026-10-04T05:00Z"), pd.Timestamp("2026-10-05T00:00Z"))


def test_settle_flags_match_research_and_standard_rule():
    pof = _load("pof_settle_test", ROOT / "research/diagnostics/phase_offset_full/phase_offset_full.py")
    for s in range(4):
        idx = pd.date_range(pd.Timestamp("2026-01-01", tz=UTC) + pd.Timedelta(hours=s), periods=60, freq="4h")
        f = ftp.settle_flags(idx)
        assert np.array_equal(f, pof.settle_flags(idx))
        # every settlement 00/08/16 lies in exactly one holding bar (T, T + 4h]
        hold0, hold1 = idx + pd.Timedelta(hours=4), idx + pd.Timedelta(hours=8)
        for st in pd.date_range(hold0[0] + pd.Timedelta(hours=8), hold1[-10], freq="8h").floor("8h").unique():
            assert int(((hold0 < st) & (st <= hold1) & f).sum()) == 1
    idx0 = pd.date_range("2026-01-01", periods=30, freq="4h", tz=UTC)  # s = 0: forward_v205.build_prep's rule
    assert np.array_equal(ftp.settle_flags(idx0), np.isin((idx0 + pd.Timedelta(hours=8)).hour, (0, 8, 16)))


def test_books_forward_fill_no_lookahead():
    std = pd.date_range("2026-09-01", periods=40, freq="4h", tz=UTC)
    books = pd.DataFrame({s: np.arange(len(std), dtype=float) + j / 10 for j, s in enumerate(ftp.SYMS)}, index=std)
    books = books.drop(std[10])  # a missing standard row is forward-filled on the standard grid first (as forward_trade)
    for s in range(4):
        grid = pd.date_range(std[2] + pd.Timedelta(hours=s), std[-1] + pd.Timedelta(hours=s), freq="4h")
        b = ftp.books_on_grid(books, grid)
        assert list(b.columns) == ftp.SYMS and b.index.equals(grid)
        for t in grid:
            r = t.floor("4h")  # latest standard row <= t_s
            want = books.loc[books.index <= r].iloc[-1]
            assert np.allclose(b.loc[t].to_numpy(), want.to_numpy())
            assert r + pd.Timedelta(hours=5) <= t + pd.Timedelta(hours=4) or s == 0  # published (r + 4h + minutes) before it is used
    grid0 = std[2:]
    assert np.allclose(ftp.books_on_grid(books, grid0).to_numpy(), books.reindex(grid0).ffill().to_numpy())


def test_opens_helpers():
    t = pd.date_range("2026-10-01", periods=24 * 60, freq="1min", tz=UTC)
    k1 = {s: pd.DataFrame({"open": np.arange(len(t), dtype=float) + j, "close": 0.0}, index=t) for j, s in enumerate(ftp.SYMS)}
    k1h = {s: k1[s].resample("1h").first() for s in ftp.SYMS}
    for s in range(4):
        om = ftp.opens_from_minutes(k1, s)
        oh = ftp.opens_from_hours(k1h, s)
        assert all((x.hour - s) % 4 == 0 and x.minute == 0 for x in om.index)
        assert om.index.equals(oh.index)
        merged, chk = ftp.merge_opens(oh, om)
        assert chk["max_rel_diff_1h_vs_1m"] == 0.0 and merged.equals(om)


# ------------------------------------------------------------------ slow: replay parity with the v376 research harness
W0, W1 = pd.Timestamp("2025-07-01", tz=UTC), pd.Timestamp("2025-09-20", tz=UTC)
ARCH = ROOT / "data/raw/majors_intraday_20260924/BNBUSDT_1m_2025.parquet"
TABLES = ROOT / "research/diagnostics/phase_agents/tables"
slow = pytest.mark.skipif(not (ARCH.exists() and TABLES.exists() and (ROOT / "artifacts/research/engine_real").exists())
                          or os.environ.get("SKIP_SLOW") == "1", reason="local 1m archive / research tables missing")


def research_replay(s, start, now, table):
    """The v376 harness (phase_agents/replay_agents.py setup) on the same shifted grid and window as the paper script's replay."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    pof = _load(f"pof_par_{s}", ROOT / "research/diagnostics/phase_offset_full/phase_offset_full.py")
    hist = _load(f"hist_par_{s}", ROOT / "backend/history_tm.py")
    v221 = _load(f"v221_par_{s}", RD / "v221/v221_grid_hysteresis.py")
    fw = _load(f"fw_par_{s}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), stats=stats) or {}
    sh = pd.Timedelta(hours=s)
    cur_bar = ftp.phase_floor(now, s)
    last_t = cur_bar - pd.Timedelta(hours=4)
    grid = ftp.shifted_grid(start, last_t, s)
    books154, _ = eu.er.v154_books()
    std_idx = books154.index[(books154.index >= grid[0] - sh) & (books154.index <= last_t - sh + pd.Timedelta(hours=8))]
    idx_in = std_idx + sh
    assert idx_in[:len(grid)].equals(grid)
    M = {}
    for sym in ftp.SYMS:  # minutes of the whole grid (warm-up included) for prep_idx
        d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
        f = d / ("klines_1m_2025.parquet" if sym == "BTCUSDT" else f"{sym}_1m_2025.parquet")
        m = pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        M[sym] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    opens, prep = pof.prep_idx(M, idx_in, s, list(books154.columns))
    idx, cols = prep["idx"], list(prep["cols"])
    assert cols == ftp.SYMS
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols].reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = table
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    eu.v110.START, eu.v110.END = start - pd.Timedelta(hours=4), last_t
    events = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
    return cap, events, cur_bar


def _key(e):
    return (str(pd.Timestamp(e["t"])), e["symbol"], e["kind"], e.get("side"))


@slow
@pytest.mark.parametrize("s", [0, 1, 2, 3])
def test_research_replay_parity(s):
    start = W0 + pd.Timedelta(hours=s)
    now = W1 + pd.Timedelta(hours=s, minutes=1)  # the bar starting at W1 + s is in progress (minute 0 only)
    table = TABLES / f"r2_table_s{s}.parquet"
    plan = ftp.build(s, start, now, research=True, minutes="archive", table=table)
    mine = plan["_internal"]
    cap, ev_r, cur_bar = research_replay(s, start, now, table)
    # events of every complete holding bar
    ea = [e for e in mine["events"] if pd.Timestamp(e["t"]) < cur_bar]
    eb = [e for e in ev_r if start <= pd.Timestamp(e["t"]) < cur_bar]
    a, b = [_key(e) for e in ea], [_key(e) for e in eb]
    assert len(a) > 50 and a == b  # same events: time, coin, kind, side
    # prices / weights equal up to the research cube's float32 storage (prep_idx) vs the paper script's float64 cube (build_prep)
    assert max(abs(x["price"] / y["price"] - 1) for x, y in zip(ea, eb)) < 1e-6
    assert max(abs(x.get("weight", 0.0) - y.get("weight", 0.0)) for x, y in zip(ea, eb)) < 1e-6
    # equity after every complete holding bar (rows up to cur_bar - 8h)
    g = mine["grid"]
    rows = (g >= start - pd.Timedelta(hours=4)) & (g <= cur_bar - pd.Timedelta(hours=8))
    er = pd.Series(cap["eq"], index=cap["idx"]).reindex(g[rows]).to_numpy()
    em = mine["eq"][rows]
    assert np.max(np.abs(em / er - 1)) < 1e-6
    print(f"phase {s}: {len(a)} events identical, equity equal (1e-6) over {int(rows.sum())} bars, final {em[-1]:.6f}")
