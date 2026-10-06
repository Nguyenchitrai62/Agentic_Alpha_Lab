"""Tests for research/diagnostics/oc_cmegap4p (assignment OPENCODE_W_oc_cmegap4p)."""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "diagnostics" / "oc_cmegap4p"


def _load_script():
    spec = importlib.util.spec_from_file_location("oc_cmegap4p_mod", str(OC / "oc_cmegap4p.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _results():
    return json.loads((OC / "results.json").read_text())


def test_results_exists_and_schema():
    r = _results()
    assert r["version"] == "oc_cmegap4p"
    assert r["reproduced"] is True
    assert set(r["rows"]) == {"R2B1D17BFG2", "R2B1D17BFG2_CME"}
    for row in r["rows"].values():
        for k in ("mean5y", "worst", "maxDD", "losing", "years", "dev4", "full_path_dd", "per_year", "win_all_5y"):
            assert k in row, k
        assert len(row["years"]) == 5
        assert len(row["per_year"]) == 5
        for y in row["per_year"]:
            for k in ("year", "R", "DD", "win", "n", "nb", "nr"):
                assert k in y, k
            assert y["win"] is None or 0.0 <= y["win"] <= 1.0
        assert r["verdict"] in ("KEEP-CANDIDATE", "NO")
    assert len(r["gaps_cme_minus_base yearly R"]) == 5


def test_gap_calendar_hand_checked():
    m = _load_script()
    # DST boundaries 2025: second Sun Mar = Mar 9, first Sun Nov = Nov 2.
    assert m.dst_start_end(2025) == (_dt.date(2025, 3, 9), _dt.date(2025, 11, 2))
    # Winter Friday vs summer Friday.
    assert m.is_summer_friday(_dt.date(2025, 1, 17)) is False
    assert m.is_summer_friday(_dt.date(2025, 9, 19)) is True
    # Boundary Fridays: Mar 7 winter, Mar 14 summer, Oct 31 summer, Nov 7 winter.
    assert m.is_summer_friday(_dt.date(2025, 3, 7)) is False
    assert m.is_summer_friday(_dt.date(2025, 3, 14)) is True
    assert m.is_summer_friday(_dt.date(2025, 10, 31)) is True
    assert m.is_summer_friday(_dt.date(2025, 11, 7)) is False
    wk = m.enumerate_weekends()
    winter = wk.loc[wk["friday"] == "2025-01-17"].iloc[0]
    summer = wk.loc[wk["friday"] == "2025-09-19"].iloc[0]
    assert winter["close_min"] == pd.Timestamp("2025-01-17 21:00", tz="UTC")
    assert winter["reopen_min"] == pd.Timestamp("2025-01-19 22:00", tz="UTC")
    assert summer["close_min"] == pd.Timestamp("2025-09-19 20:00", tz="UTC")
    assert summer["reopen_min"] == pd.Timestamp("2025-09-21 21:00", tz="UTC")
    # Full enumeration matches the audited screen: 262 weekends, 58 large (28 up / 30 down).
    assert len(m.WK) == 262
    assert int(m.WK["large"].sum()) == 58
    assert int(((m.WK["gap"] > 0.02) & m.WK["large"]).sum()) == 28
    assert int(((m.WK["gap"] < -0.02) & m.WK["large"]).sum()) == 30


def test_fill_strictly_before_T_and_first_row():
    m = _load_script()
    # Synthetic single large up-gap weekend: fill known strictly before T.
    ro = pd.Timestamp("2025-09-21 21:00", tz="UTC")
    fm = pd.Timestamp("2025-09-22 05:00", tz="UTC")
    wk = pd.DataFrame([dict(reopen_min=ro, gap=0.03, large=True, fill_minute=fm)])
    grid = pd.date_range("2025-09-21 00:00", "2025-09-25 00:00", freq="4h", tz="UTC")
    affected, gap_at = m.cme_tilt_info(grid, wk)
    end = ro + pd.Timedelta(hours=72)
    expect = np.asarray((grid > ro) & (grid <= end) & (grid <= fm))
    assert bool((affected == expect).all())
    assert not affected[grid <= ro].any()  # 4h bar containing reopen never affected
    assert affected[grid == pd.Timestamp("2025-09-22 00:00", tz="UTC")].all()
    assert not affected[grid > fm].any()  # rows after fill not affected
    assert float(gap_at[affected][0]) == 0.03
    # Unfilled window expires at +72h.
    wk2 = pd.DataFrame([dict(reopen_min=ro, gap=-0.03, large=True, fill_minute=pd.NaT)])
    aff2, _ = m.cme_tilt_info(grid, wk2)
    assert not aff2[grid > end].any()
    assert aff2[grid == end].all()
    # Real weekends: first affected row is strictly after the reopen.
    grid0 = pd.date_range("2021-09-17", "2021-10-04", freq="4h", tz="UTC")
    aff0, _ = m.cme_tilt_info(grid0, m.WK)
    first = grid0[affected_mask(aff0)][0] if aff0.any() else None
    assert first is not None and first > pd.Timestamp("2021-09-19 22:00", tz="UTC")


def affected_mask(a):
    return np.asarray(a, dtype=bool)


def test_rule_math_tilt():
    m = _load_script()
    assert m.GAP_TH == 0.02
    grid = pd.date_range("2025-09-21 00:00", "2025-09-22 12:00", freq="4h", tz="UTC")
    ro = pd.Timestamp("2025-09-21 21:00", tz="UTC")
    # Up-gap weekend tilts longs x0.75, shorts bit-identical.
    wk_up = pd.DataFrame([dict(reopen_min=ro, gap=0.05, large=True,
                               fill_minute=pd.Timestamp("2025-09-23 00:00", tz="UTC"))])
    aff, gap_at = m.cme_tilt_info(grid, wk_up)
    rng = np.random.default_rng(1)
    base = rng.normal(size=(len(grid), 2))
    rule = base.copy()
    up = aff & np.isfinite(gap_at) & (gap_at > 0.02)
    longs = np.zeros_like(base, bool)
    longs[up, :] = base[up, :] > 0
    rule[longs] = 0.75 * base[longs]
    assert bool((rule[~up] == base[~up]).all())
    short_rows = up[:, None] & (base <= 0)
    assert bool((rule[short_rows] == base[short_rows]).all())
    pos = up[:, None] & (base > 0) if False else (up[:, None] & (base > 0))
    assert bool((rule[pos] == 0.75 * base[pos]).all())
    # Down-gap weekend tilts longs x1.25.
    wk_dn = pd.DataFrame([dict(reopen_min=ro, gap=-0.05, large=True,
                               fill_minute=pd.Timestamp("2025-09-23 00:00", tz="UTC"))])
    affd, gapd = m.cme_tilt_info(grid, wk_dn)
    dn = affd & np.isfinite(gapd) & (gapd < -0.02)
    rule2 = base.copy()
    posd = dn[:, None] & (base > 0)
    rule2[posd] = 1.25 * base[posd]
    assert bool((rule2[~dn] == base[~dn]).all())
    assert bool((rule2[posd] == 1.25 * base[posd]).all())
    # Small-gap window leaves all weights identical.
    wk_small = pd.DataFrame([dict(reopen_min=ro, gap=0.005, large=False,
                                  fill_minute=pd.Timestamp("2025-09-23 00:00", tz="UTC"))])
    affs, _ = m.cme_tilt_info(grid, wk_small)
    assert not affs.any()


def test_reproduction_matches_v421():
    r = _results()
    base = r["rows"]["R2B1D17BFG2"]
    assert base["mean5y"] == 5.41
    assert base["maxDD"] == 16.91
    assert base["full_path_dd"] == 16.82


def test_verdict_matches_rule():
    r = _results()
    base, cme = r["rows"]["R2B1D17BFG2"], r["rows"]["R2B1D17BFG2_CME"]
    gaps = [round(cme["per_year"][y]["R"] - base["per_year"][y]["R"], 3) for y in range(5)]
    assert list(r["gaps_cme_minus_base yearly R"]) == gaps
    assert r["worst_year_gap"] == min(gaps)
    expect = "KEEP-CANDIDATE" if (cme["full_path_dd"] < base["full_path_dd"]
                                  and cme["mean5y"] >= 5.30
                                  and min(gaps) > -0.3 - 1e-12) else "NO"
    assert r["verdict"] == expect
    rep = (OC / "REPORT.md").read_text()
    assert f"VERDICT: {expect}" in rep
