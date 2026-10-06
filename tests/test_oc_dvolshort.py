"""oc_dvolshort tests: as-of causality, cut-off causality, book rebuild, grid bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dvolshort"
OC_BOOKIC = ROOT / "research/tournament/oc_bookic"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(OC_BOOKIC))
import compute_dvolshort as S
import compute_bookic as B

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


@pytest.fixture(scope="module")
def res():
    return json.loads((OC / "results.json").read_text())


@pytest.fixture(scope="module")
def panel():
    p = pd.read_parquet(OC / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p


@pytest.fixture(scope="module")
def dvol():
    return S.load_dvol()


def test_asof_usable_at_or_before_T(dvol, panel):
    """z recomputed from DVOL truncated to end <= T matches saved rows."""
    idx = [0, 5000, 20000, 40000, len(panel) - 1]
    sub = panel.iloc[idx].reset_index(drop=True)
    Tns = sub["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ref = sub["z"].to_numpy(float)
    for i in range(len(sub)):
        T = int(Tns[i])
        for c, (e, _) in dvol.items():
            assert (e[e <= T] <= T).all()
        dvol_t = {c: (e[e <= T], v[e <= T]) for c, (e, v) in dvol.items()}
        got = S.z90_for_times(np.array([T]), dvol_t)[S.COINMAP[sub["sym"].iloc[i]]][0]
        assert (np.isnan(got) and np.isnan(ref[i])) or abs(got - ref[i]) < 1e-9, \
            f"row {idx[i]} T={sub['T'].iloc[i]} got={got} ref={ref[i]}"
    got_full = S.z90_for_times(Tns, dvol)
    for i in range(len(sub)):
        cur = S.COINMAP[sub["sym"].iloc[i]]
        g = got_full[cur][i]
        assert (np.isnan(g) and np.isnan(ref[i])) or abs(g - ref[i]) < 1e-9


def test_cutoffs_causal(panel, res):
    """results.json q67 must equal previous-data-only pool quantiles."""
    opens_full = pd.read_parquet(S.CACHE / "opens_v154.parquet")
    pre = opens_full.index[(opens_full.index >= S.FEAT_START) & (opens_full.index < S.ANCHORS[0])].sort_values()
    T_all = pre.union(pd.DatetimeIndex(panel["T"].unique())).sort_values()
    Tns = T_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    zfeat = S.z90_for_times(Tns, S.load_dvol())
    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({"T": T_all, "z": zfeat[S.COINMAP[s]]}))
    pool = pd.concat(rows, ignore_index=True)
    pool["T"] = pd.to_datetime(pool["T"], utc=True)
    for k in (0, 2):  # first year (pre-anchor pool) + one later year
        a0 = S.ANCHORS[k]
        pm = (pool["T"] >= S.FEAT_START) & (pool["T"] < a0) & pool["z"].notna()
        assert int(pm.sum()) >= 100
        assert pool["T"][pm].max() < a0
        q67 = float(np.quantile(pool["z"][pm].to_numpy(float), 2 / 3))
        assert res["years"][k]["q67"] == pytest.approx(q67, abs=1e-6)
    # NaN-z rows are never gated; gated rows strictly exceed their year's q67
    z = panel["z"].to_numpy(float)
    assert not panel["gated"][~np.isfinite(z)].any()
    for k, a0 in enumerate(S.ANCHORS):
        q = res["years"][k]["q67"]
        m = (panel["T"] >= a0) & (panel["T"] < (S.ANCHORS[k + 1] if k < 4 else S.LAST_BOUND))
        g = panel[m & (panel["w"] < 0) & panel["z"].notna()]
        assert ((g["z"] > q) == g["gated"]).all()


def test_books_match_oc_bookic():
    """Rebuilt books must equal oc_bookic's formula cell by cell."""
    a = S.research_books_d2()
    b = B.research_books_d2()
    common = a.index.intersection(b.index)
    assert len(common) > 10000
    pd.testing.assert_frame_equal(a.reindex(common), b.reindex(common), check_dtype=False)


def test_grid_bounds(panel, res):
    """No decision bar at/after cutoff; gate math exact; years partition."""
    assert (panel["T"] < S.CUTOFF).all()
    assert panel["pnl"].notna().all() and panel["pnl_g"].notna().all()
    bounds = S.ANCHORS + [S.LAST_BOUND]
    total = 0
    for k in range(5):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        total += int(m.sum())
    assert total == len(panel), "years must partition the panel"
    assert set(panel["sym"].unique()) == set(SYMS)
    # gated shorts are exactly half; longs/flats bit-identical
    short_g = panel["gated"]
    np.testing.assert_allclose(panel["w_g"][short_g].to_numpy(float),
                               0.5 * panel["w"][short_g].to_numpy(float), rtol=1e-12)
    ung = ~panel["gated"].to_numpy()
    np.testing.assert_allclose(panel["w_g"][ung].to_numpy(float),
                               panel["w"][ung].to_numpy(float), rtol=1e-12)
    longs = panel["w"] > 0
    assert not panel["gated"][longs].any()
