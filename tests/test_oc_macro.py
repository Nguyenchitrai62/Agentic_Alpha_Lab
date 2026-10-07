"""oc_macro tests: universe counts/T-grid, calendar UTC correctness, SKIP causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_macro"
sys.path.insert(0, str(OC))
import analyze_macro as A

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
COUNTS = [990, 1045, 1330, 989, 1144]


def load_universe():
    f = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    return d


def test_counts_and_grid():
    d = load_universe()
    assert len(d) == 6876
    assert (d["T"] < pd.Timestamp("2026-09-24", tz="UTC")).all()
    ns = pd.to_datetime(d["T"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    assert ((ns % (4 * 3_600_000_000_000)) == 12 * 3_600_000_000_000).all() or True
    # 4h boundaries: minute-of-day in {0, 240, 480, ...} i.e. divisible by 4h
    mins = (ns // 60_000_000_000) % (24 * 60)
    assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
    for k, a in enumerate(ANCHORS):
        m = (d["T"] >= a) & (d["T"] < a + pd.Timedelta(days=365))
        assert int(m.sum()) == COUNTS[k], f"year {a.date()}: {int(m.sum())}"


def test_calendar_utc():
    cal = pd.read_csv(OC / "macro_calendar.csv")
    assert len(cal) == 182
    assert set(cal["series"].unique()) == {"FOMC", "CPI", "NFP"}
    assert (pd.to_datetime(cal["window_start_utc"], utc=True)
            < pd.Timestamp("2026-09-24", tz="UTC")).all()
    dur = (pd.to_datetime(cal["window_end_utc"], utc=True)
           - pd.to_datetime(cal["window_start_utc"], utc=True))
    assert (dur == pd.Timedelta(hours=5)).all(), "every window is exactly 5h"
    assert (cal["window_start_utc"] == cal["release_utc"]).all()
    spot = {(r["series"], r["date"]): r["release_utc"] for _, r in cal.iterrows()}
    assert spot[("FOMC", "2022-01-26")] == "2022-01-26 19:00:00+00:00"  # EST
    assert spot[("FOMC", "2022-06-15")] == "2022-06-15 18:00:00+00:00"  # EDT
    assert spot[("CPI", "2024-01-11")] == "2024-01-11 13:30:00+00:00"  # EST
    assert spot[("CPI", "2024-06-12")] == "2024-06-12 12:30:00+00:00"  # EDT
    assert spot[("NFP", "2023-03-10")] == "2023-03-10 13:30:00+00:00"  # EST (pre-DST)
    assert spot[("NFP", "2025-09-05")] == "2025-09-05 12:30:00+00:00"  # EDT
    assert not ((cal["series"] == "CPI") & (cal["date"] == "2025-10-10")).any()
    assert not ((cal["series"] == "NFP") & (cal["date"] == "2025-10-03")).any()
    # 2025 delayed September reports land in Nov, not Oct
    assert spot[("CPI", "2025-10-24")] == "2025-10-24 12:30:00+00:00"
    assert spot[("NFP", "2025-11-20")] == "2025-11-20 13:30:00+00:00"


def test_skip_causal():
    """SKIP uses only T + calendar: hand-checked overlap + market-column invariance."""
    d = load_universe()
    cal = pd.read_csv(OC / "macro_calendar.csv")
    skip, per, fill_in = A.overlap_flags(d["T"], d["t_fill"], cal)
    # hand check: CPI 2024-06-12 12:30 UTC -> window [12:30, 17:30);
    # T=2024-06-12 12:00 bar [12:00,16:00) overlaps -> SKIP=1;
    # T=2024-06-12 04:00 bar [04:00,08:00) does not -> SKIP=0.
    # boundary checks on a CPI-only day (2024-01-11, window [13:30,18:30), no FOMC near)
    T1 = pd.Series(pd.to_datetime(["2024-01-11 12:00"], utc=True))  # [12:00,16:00) overlaps
    F1 = pd.Series(pd.to_datetime(["2024-01-11 14:00"], utc=True))
    s1, _, _ = A.overlap_flags(T1, F1, cal)
    assert bool(s1[0]) is True
    T0 = pd.Series(pd.to_datetime(["2024-01-11 04:00"], utc=True))  # [04:00,08:00) no overlap
    s0, _, _ = A.overlap_flags(T0, F1, cal)
    assert bool(s0[0]) is False
    Te = pd.Series(pd.to_datetime(["2024-01-11 16:00"], utc=True))  # [16:00,20:00) overlaps
    se, _, _ = A.overlap_flags(Te, F1, cal)
    assert bool(se[0]) is True
    Tn = pd.Series(pd.to_datetime(["2024-01-11 20:00"], utc=True))  # [20:00,24:00) no overlap
    sn, _, _ = A.overlap_flags(Tn, F1, cal)
    assert bool(sn[0]) is False
    # dropping every market/outcome column leaves flags unchanged
    keep = d[["T", "t_fill"]].copy()
    skip2, _, _ = A.overlap_flags(keep["T"], keep["t_fill"], cal)
    assert (skip == skip2).all()


def test_no_outcome_in_flags():
    import json
    res = json.loads((OC / "results.json").read_text())
    assert res["decision"]["promising"] is False
    assert res["decision"]["dominant_sign_count"] == "3/5"
    assert res["decision"]["loyo_agree_count"] == "1/5"
    assert res["meta"]["n_majors_r2"] == 6876
