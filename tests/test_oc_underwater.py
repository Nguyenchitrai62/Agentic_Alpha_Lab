"""Tests for oc_underwater: episode logic + mix-convention integrity (no simulation)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_underwater"
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
sys.path.insert(0, str(W))
import compute_underwater as C


def _res():
    return json.loads((W / "results.json").read_text())


def _syn(e_vals, m_vals, start="2022-01-01"):
    idx = pd.date_range(start, periods=len(e_vals), freq="1h", tz="UTC")
    return pd.Series(e_vals, index=idx, dtype=float), pd.Series(m_vals, index=idx, dtype=float)


def test_files_present_and_plan_first():
    for f in ("PLAN.md", "compute_underwater.py", "results.json", "REPORT.md"):
        assert (W / f).exists(), f
    assert (W / "PLAN.md").stat().st_mtime <= (W / "results.json").stat().st_mtime


def test_no_1m_data_in_script():
    src = (W / "compute_underwater.py").read_text()
    for bad in ("intraday", "minutes()", "bar_open_ext", "fills_U_ext", "alts2020"):
        assert bad not in src


def test_hand_single_episode():
    e, m = _syn([1.0, 1.1, 1.0, 0.9, 1.0, 1.15], [1.0, 1.1, 0.99, 0.9, 0.99, 1.15])
    exc = C.find_excursions(e, m)
    assert len(exc) == 1
    x = exc[0]
    assert (x["ipos_peak"], x["ipos_trough"], x["ipos_rec"]) == (1, 3, 5)
    assert x["depth"] == pytest.approx(1 - 0.9 / 1.1)
    assert x["censored"] is False


def test_nested_crossings_do_not_split_and_ties_first():
    # peak 2.0 at i=1; dd crosses 5% twice but never recovers until i=6 -> one episode
    e, m = _syn([1.0, 2.0, 1.96, 1.90, 1.97, 1.91, 2.0],
                [1.0, 2.0, 1.90, 1.80, 1.97, 1.80, 2.0])
    exc = C.find_excursions(e, m)
    assert len(exc) == 1
    assert exc[0]["ipos_peak"] == 1 and exc[0]["ipos_rec"] == 6
    assert exc[0]["ipos_trough"] == 3  # first of the tied maxima
    assert exc[0]["depth"] == pytest.approx(1 - 1.8 / 2.0)


def test_censored_and_shallow_ignored():
    e, m = _syn([1.0, 1.2, 1.0, 0.9], [1.0, 1.2, 1.0, 0.9])
    exc = C.find_excursions(e, m)
    assert len(exc) == 1 and exc[0]["censored"] is True and exc[0]["ipos_rec"] is None
    e2, m2 = _syn([1.0, 1.05, 1.03, 1.06], [1.0, 1.05, 1.02, 1.06])
    assert all(x["depth"] <= 0.05 for x in C.find_excursions(e2, m2))


def test_mix_conventions_and_official_dd():
    import importlib.util
    spec = importlib.util.spec_from_file_location("v388_t", RD / "v388" / "v388_bot_stop_distance.py")
    v388 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v388)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    r = _res()
    got = {d["row"]: d for d in r["rows_data"]}
    assert set(got) == {"R2B1D17BFG2", "R2B1D13BF"}
    for label, vdir, pkl, row in C.SPECS:
        runs = pickle.loads((RD / vdir / pkl).read_bytes())
        assert set(runs) == {0, 1, 2, 3}
        e_full, mn_full = v388.mix(runs, row, g1)
        seg = e_full.index > C.ANCHOR0
        e, mn = e_full[seg], mn_full[seg]
        assert bool((mn.to_numpy() <= e.to_numpy() + 1e-12).all())
        peak = np.maximum.accumulate(e.to_numpy(float))
        dd = 1.0 - mn.to_numpy(float) / peak
        d = got[label]
        assert d["window"]["n_hours"] == len(e) == 43809
        assert d["full_path_dd"] == pytest.approx(float(np.max(dd)) * 100.0, abs=0.011)
        official = json.loads((RD / vdir / f"{vdir}_result.json").read_text())["rows"][row]
        assert d["official_full_path_dd"] == pytest.approx(official["full_path_dd"])
        assert d["full_path_match"] is True
        # episode max == full-path DD; sorted desc; shares recompute
        depths = [ep["depth_pct"] for ep in d["episodes_gt5"]]
        assert depths == sorted(depths, reverse=True)
        assert max(depths) == pytest.approx(d["full_path_dd"], abs=0.011)
        assert np.mean(dd > 0.05) == pytest.approx(d["share"]["gt5_frac"], abs=1e-6)
        assert np.mean(dd > 0.10) == pytest.approx(d["share"]["gt10_frac"], abs=1e-6)
        durs = np.array([ep["days_underwater"] for ep in d["episodes_gt5"]])
        assert d["underwater_dist_gt5"]["n"] == len(durs) == len(depths)
        assert d["underwater_dist_gt5"]["median_days"] == pytest.approx(float(np.median(durs)), abs=0.011)
        assert d["underwater_dist_gt5"]["p90_days"] == pytest.approx(float(np.percentile(durs, 90)), abs=0.011)
        assert d["underwater_dist_gt5"]["max_days"] == pytest.approx(float(np.max(durs)), abs=0.011)
        for ep in d["episodes_gt5"]:
            assert ep["depth_pct"] > 5.0
            assert pd.Timestamp(ep["peak_date"]) < pd.Timestamp(ep["trough_date"]) or ep["days_to_trough"] == 0.0
            assert ep["days_underwater"] >= ep["days_to_trough"]
            if not ep["censored"]:
                assert ep["recovery_date"] is not None
    rep = (W / "REPORT.md").read_text()
    assert "R2B1D17BFG2" in rep and "R2B1D13BF" in rep and "Tom tat tieng Viet" in rep
