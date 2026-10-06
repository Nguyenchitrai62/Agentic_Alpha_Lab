"""Causality + accounting tests for oc_b1btc (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_b1btc"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_b1btc as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def test_btc_det_matches_v399_definition():
    """Hand-computed BTC-leg detection: exact-2.5-sigma counts, NaN/zero skipped, BTC own = 0."""
    O, C, sg = 100.0, 100.0 * (1 - 2.5 * 0.01), 0.01  # exactly at threshold
    assert A.btc_det_row(O, C, sg, False) == 1
    assert A.btc_det_row(O, C + 1e-6, sg, False) == 0  # just above: no flush
    assert A.btc_det_row(O, 50.0, np.nan, False) == 0  # NaN sig skipped
    assert A.btc_det_row(O, 50.0, 0.0, False) == 0  # zero sig skipped
    assert A.btc_det_row(np.nan, 50.0, sg, False) == 0  # NaN open skipped
    assert A.btc_det_row(O, np.nan, sg, False) == 0  # NaN close skipped
    assert A.btc_det_row(O, 10.0, sg, True) == 0  # BTC own fills always 0
    assert A.maxdd_of_cumsum(np.array([1.0, 1.0])) == pytest.approx(0.0)
    assert A.maxdd_of_cumsum(np.array([1.0, -2.0, 1.0])) == pytest.approx(3.0)


def test_n_reuse_join():
    """Every TEST row joins exactly one stored n; ranges and BTC-own rule hold."""
    g = pd.read_parquet(OC / "n_btc_per_fill.parquet")
    assert len(g) == 5498
    assert bool(g["n"].between(0, 4).all())
    assert bool(g["n_btc"].between(0, 5).all())
    assert bool((g.loc[g["sym"] == "BTCUSDT", "btc_det"] == 0).all())
    assert bool((g.loc[g["sym"] == "BTCUSDT", "n_btc"] == g.loc[g["sym"] == "BTCUSDT", "n"]).all())
    nb = g["sym"].to_numpy() != "BTCUSDT"
    assert bool(((g.loc[nb, "n_btc"] - g.loc[nb, "n"]) == g.loc[nb, "btc_det"].to_numpy()).all())
    assert bool(g["btc_det"].isin([0, 1]).all())
    # exact consistency: BTC counted in n, so btc_det=1 implies n>=1
    assert int(((g["sym"] != "BTCUSDT") & (g["btc_det"] == 1) & (g["n"] == 0)).sum()) == 0
    # join keys unique and match harness TEST universe
    assert g.set_index(["sym", "x1", "T", "t_fill", "f"]).index.is_unique
    r = _results()
    assert [int((((g["T"] >= a) & (g["T"] < a + pd.Timedelta(days=365)))).sum())
            for a in ANCHORS] == [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]


def test_renorm_equal_exposure():
    """Per-year mean(s) == mean(size_dep) for both arms (independently recomputed)."""
    g = pd.read_parquet(OC / "n_btc_per_fill.parquet")
    g["T"] = pd.to_datetime(g["T"], utc=True)
    for a in ANCHORS:
        te = ((g["T"] >= a) & (g["T"] < a + pd.Timedelta(days=365))).to_numpy()
        sd = g["size_dep"].to_numpy()[te]
        ra = sd / (1.0 + g["n"].to_numpy(float)[te])
        rb = sd / (1.0 + g["n_btc"].to_numpy(float)[te])
        sa = ra * sd.mean() / ra.mean()
        sb = rb * sd.mean() / rb.mean()
        assert sa.mean() == pytest.approx(sd.mean(), rel=1e-9)
        assert sb.mean() == pytest.approx(sd.mean(), rel=1e-9)
        # stored sums match an independent recomputation
        yd = g["y_dep"].to_numpy()[te]
        r = _results()
        k = ANCHORS.index(a)
        assert float((sa * yd).sum()) == pytest.approx(r["years"][k]["S_a"], abs=5e-4)
        assert float((sb * yd).sum()) == pytest.approx(r["years"][k]["S_b"], abs=5e-4)


def test_decision_counts_match():
    r = _results()
    n_gain = sum(1 for y in r["years"] if y["gain_pass"])
    n_dd = sum(1 for y in r["years"] if y["dd_pass"])
    n_loyo = sum(1 for L in r["loyo"] if L["pass"])
    for y in r["years"]:
        assert y["gain_pass"] == bool(y["gain"] > 0)
        assert y["dd_pass"] == bool(y["DD_b"] <= y["DD_a"])
    gains = [y["gain"] for y in r["years"]]
    for h, L in enumerate(r["loyo"]):
        expect = float(np.mean([g for k, g in enumerate(gains) if k != h]))
        assert L["loyo_gain"] == pytest.approx(expect, abs=5e-4)
        assert L["pass"] == bool(expect > 0)
    assert r["decision"]["gain"] == f"{n_gain}/5" == "3/5"
    assert r["decision"]["loyo_gain"] == f"{n_loyo}/5" == "2/5"
    assert r["decision"]["dd_not_worse"] == f"{n_dd}/5" == "2/5"
    assert r["decision"]["promising"] is False


def test_T_and_bounds():
    g = pd.read_parquet(OC / "n_btc_per_fill.parquet")
    T = pd.to_datetime(g["T"], utc=True)
    assert bool((T < DEV_END).all())
    calc = pd.to_datetime(g["t_fill"], utc=True) - pd.to_timedelta(g["f"], unit="min")
    assert bool((calc == T).all())
    f = pd.read_parquet(ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet",
                        columns=["t_fill", "f"])
    Tall = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    assert bool((Tall < DEV_END).all())
    # only BTC 1m files are read by this assignment's script
    assert "MAJ_DIR" not in dir(A)
    assert sorted(p.name for p in A.BTC_DIR.glob("klines_1m_20*.parquet"))
    assert all("klines_1m" in p.name for p in A.BTC_DIR.glob("klines_1m_20*.parquet"))


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert r["meta"]["test_rows"] == 5498
    d = H5.load()
    assert int(sum(te.sum() for _, _, _, te in H5.folds(d))) == 5498
