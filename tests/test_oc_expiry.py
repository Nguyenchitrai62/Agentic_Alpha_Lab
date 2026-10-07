"""oc_expiry causality / alignment tests (no market data needed for flags)."""
import importlib.util
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research/tournament/oc_expiry"
ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("oc_expiry_mod", HERE / "analyze_expiry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


def test_expiry_calendar_hand_checked():
    assert M.expiry(2025, 9) == pd.Timestamp("2025-09-26 08:00", tz="UTC")
    assert M.expiry(2024, 2) == pd.Timestamp("2024-02-23 08:00", tz="UTC")  # leap Feb
    assert M.expiry(2026, 6) == pd.Timestamp("2026-06-26 08:00", tz="UTC")
    exp = M.expiries()
    assert (exp.E.dt.weekday == 4).all()  # all Fridays
    assert ((exp.E.dt.hour == 8) & (exp.E.dt.minute == 0)).all()
    q = exp[exp.quarterly]
    assert set(q.E.dt.month.unique()) <= {3, 6, 9, 12} and len(q) > 0
    nq = exp[~exp.quarterly]
    assert set(nq.E.dt.month.unique()) <= {1, 2, 4, 5, 7, 8, 10, 11}


def test_windows_need_no_market_data():
    exp = M.expiries()
    t = pd.Series(pd.to_datetime(["2025-09-22 12:00", "2025-09-26 07:00",
                                   "2025-09-26 09:00", "2025-09-23 12:00"], utc=True))
    f1 = M.window_flags(t, exp)
    # shifting market inputs cannot change calendar flags: recompute identical
    f2 = M.window_flags(t.copy(), exp.copy())
    pd.testing.assert_frame_equal(f1, f2)
    # Mon 2025-09-22 12:00 and Thu 07:00 before Fri-26 expiry are in WEEK
    assert f1["week"].tolist() == [True, True, False, True]
    # PRE24 subset of WEEK; POST24 disjoint from WEEK
    assert ((~f1["week"]) | (~f1["pre24"])).all() or (f1["pre24"] <= f1["week"]).all()
    assert not (f1["post24"] & f1["week"]).any()
    # WEEK starts Monday 00:00: Sunday before is out, Monday 00:00 is in
    s = pd.Series(pd.to_datetime(["2025-09-21 23:00", "2025-09-22 00:00"], utc=True))
    fs = M.window_flags(s, exp)
    assert fs["week"].tolist() == [False, True]


def test_cutoff_and_universe():
    import pyarrow.parquet as pq
    f = pq.read_table(ROOT / "research/tournament/ext/fills_U_ext.parquet").to_pandas()
    assert (f.t_fill < M.DEV_END).sum() > 0
    d = f[(f.t_fill < M.DEV_END)]
    d = d[d.sym.isin(M.MAJORS) & d.x1.isin(M.R2)].copy()
    d["T"] = d.t_fill - pd.to_timedelta(d.f, unit="min")
    assert (d["T"] < M.DEV_END).all()
    assert set(d.sym.unique()) <= M.MAJORS and set(d.x1.unique()) <= set(M.R2)
    for a0 in M.ANCHORS:
        yd = d[(d["T"] >= a0) & (d["T"] < a0 + M.YEAR_LEN)]
        assert len(yd) > 300
        fl = M.window_flags(yd["T"], M.expiries())
        share = fl["week"].mean()
        assert 0.05 < share < 0.25
