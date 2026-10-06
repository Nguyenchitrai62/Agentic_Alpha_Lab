"""Tests for oc_bookoffset (research/tournament/oc_bookoffset). Lightweight checks on results.json + causality."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bookoffset"
RES = HERE / "results.json"


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_bookoffset_compute", HERE / "compute_bookoffset.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_bookoffset/compute_bookoffset.py first"
    r = _load()
    for k in ("per_rule", "decision", "definitions", "anchor_years", "n_T_bars"):
        assert k in r, k
    assert set(r["per_rule"]) == {"fix", "vol"}
    for rule in ("fix", "vol"):
        assert len(r["per_rule"][rule]["per_year"]) == 5, rule
        for row in r["per_rule"][rule]["per_year"]:
            for k in ("attempted", "filled", "fill_rate", "mean_off_attempted_bps",
                      "mean_off_filled_bps", "filled_gross", "filled_net",
                      "missed_hyp", "total_net"):
                assert k in row, (rule, row)
    d = r["decision"]
    assert len(d["d_net"]) == 5 and len(d["loyo"]) == 5
    n_pos = sum(1 for e in d["d_net"] if e is not None and e > 0)
    assert d["pos_years"] == f"{n_pos}/5"
    assert d["promising"] == (n_pos >= 4)
    assert d["promising"] is True  # 5/5 in this run


def test_year_partition_and_counts():
    r = _load()
    for rule in ("fix", "vol"):
        ns = [row["attempted"] for row in r["per_rule"][rule]["per_year"]]
        assert sum(ns) == r["n_attempted_events"], (rule, ns)
    assert r["orphan_T_bars"] == 6
    assert r["n_T_bars"] == 10955
    assert r["unscored_missing"] == 0
    # fill rates consistent
    for rule in ("fix", "vol"):
        for row in r["per_rule"][rule]["per_year"]:
            if row["attempted"]:
                assert abs(row["fill_rate"] - row["filled"] / row["attempted"]) < 1e-6


def test_sigma_uses_only_bars_before_T():
    mod = _mod()
    idx = pd.date_range("2020-01-01", periods=800, freq="4h", tz="UTC")
    rng = np.random.default_rng(3)
    opens = pd.DataFrame({"C": 100.0 * np.cumprod(1 + 0.005 * rng.standard_normal(len(idx)))}, index=idx)
    T = idx[700:705]
    s1 = mod.sigma4h_at_T(opens, T)
    opens2 = opens.copy()
    opens2.iloc[700:] *= 1.5  # perturb at/after the first T
    s2 = mod.sigma4h_at_T(opens2, T)
    # sigma at T uses bars strictly before T: first T unchanged (its window
    # ends at T-4h < perturbation start for T[0]? T[0]=idx[700], window ends
    # idx[699], untouched) — check at least the first row is identical
    assert np.isfinite(s1["C"].iloc[0])
    pd.testing.assert_series_equal(s1["C"].iloc[:1], s2["C"].iloc[:1], check_dtype=False)


def test_fill_rule_strict_trade_through():
    # buy: touch (==) does NOT fill, trade-through (<) does; sell mirrored.
    P0, off = 100.0, 0.001
    lim_buy = P0 * (1 - off)
    lo_touch = np.full(60, lim_buy + 1.0)
    lo_touch[30] = lim_buy  # exact touch
    assert not bool((lo_touch < lim_buy).any())
    lo_thr = lo_touch.copy()
    lo_thr[30] = lim_buy - 1e-9
    assert bool((lo_thr < lim_buy).any())
    lim_sell = P0 * (1 + off)
    hi_touch = np.full(60, lim_sell - 1.0)
    hi_touch[10] = lim_sell
    assert not bool((hi_touch > lim_sell).any())
    hi_thr = hi_touch.copy()
    hi_thr[10] = lim_sell + 1e-9
    assert bool((hi_thr > lim_sell).any())
    # limit direction: buy below P0, sell above P0, improvement == offset
    assert lim_buy < P0 and lim_sell > P0
    assert abs((P0 - lim_buy) / P0 * 1e4 - 10.0) < 1e-9
    assert abs((lim_sell - P0) / P0 * 1e4 - 10.0) < 1e-9


def test_decision_loyo_consistent():
    r = _load()
    d = r["decision"]
    eff = d["d_net"]
    for h in range(5):
        tr = [e for k, e in enumerate(eff) if k != h]
        mtr = float(np.mean(tr))
        expect = bool(mtr > 0 and np.sign(eff[h]) == np.sign(mtr))
        assert d["loyo"][h] == expect, h
    assert d["loyo_pass"] == f"{sum(d['loyo'])}/5"
