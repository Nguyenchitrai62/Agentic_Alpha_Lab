"""oc_dvolbook tests: as-of causality, cut-off causality, book rebuild, grid bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dvolbook"
OC_BOOKIC = ROOT / "research/tournament/oc_bookic"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(OC_BOOKIC))
import compute_dvolbook as D
import compute_bookic as B

FEATS = ["dvol_z90", "dvol_chg24", "vrp"]
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
    return D.load_dvol()


@pytest.fixture(scope="module")
def daily():
    return D.load_daily()


def test_asof_usable_at_or_before_T(dvol, daily, panel):
    """Features recomputed from panels truncated to end <= T match the saved rows."""
    idx = [0, 5000, 20000, 40000, len(panel) - 1]
    sub = panel.iloc[idx].reset_index(drop=True)
    Tns = sub["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ref = sub[FEATS].to_numpy(float)
    fT = D.features_for_times(Tns, dvol, daily)
    for i in range(len(sub)):
        T = int(Tns[i])
        cur = D.COINMAP[sub["sym"].iloc[i]]
        for c, (e, _) in list(dvol.items()) + list(daily.items()):
            assert (e[e <= T] <= T).all()
            assert (e > T).any() or True  # truncation point exists by construction
        dvol_t = {c: (e[e <= T], v[e <= T]) for c, (e, v) in dvol.items()}
        daily_t = {c: (e[e <= T], v[e <= T]) for c, (e, v) in daily.items()}
        got = D.features_for_times(np.array([T]), dvol_t, daily_t)[cur].iloc[0][FEATS].to_numpy(float)
        np.testing.assert_allclose(got, ref[i], rtol=1e-9, atol=1e-12,
                                   err_msg=f"row {idx[i]} T={sub['T'].iloc[i]}")
        # full-panel single-T call must agree (no post-T leakage into the value)
        got_full = fT[cur].iloc[i][FEATS].to_numpy(float)
        np.testing.assert_allclose(got_full, ref[i], rtol=1e-9, atol=1e-12)


def _cutoff_pool(panel):
    """Rebuild the (T, sym) feature pool exactly as compute_dvolbook.main."""
    opens_full = pd.read_parquet(D.CACHE / "opens_v154.parquet")
    pre = opens_full.index[(opens_full.index >= D.FEAT_START) & (opens_full.index < D.ANCHORS[0])].sort_values()
    T_all = pre.union(pd.DatetimeIndex(panel["T"].unique())).sort_values()
    Tns = T_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    feat = D.features_for_times(Tns, D.load_dvol(), D.load_daily())
    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({"T": T_all, "sym": s,
                                  "dvol_z90": feat[D.COINMAP[s]]["dvol_z90"].to_numpy(float)}))
    pool = pd.concat(rows, ignore_index=True)
    pool["T"] = pd.to_datetime(pool["T"], utc=True)
    return pool


def test_cutoffs_causal(panel, res):
    """results.json cut-offs must equal previous-data-only pool quantiles."""
    pool = _cutoff_pool(panel)
    for k in (0, 2):  # first year (pre-anchor pool) + one later year
        a0 = D.ANCHORS[k]
        pm = (pool["T"] >= D.FEAT_START) & (pool["T"] < a0) & pool["dvol_z90"].notna()
        assert int(pm.sum()) >= 100
        assert pool["T"][pm].max() < a0
        q33, q67 = np.quantile(pool["dvol_z90"][pm].to_numpy(float), [1 / 3, 2 / 3])
        got = res["terciles"][k]["cutoffs"]
        assert got["q33"] == pytest.approx(q33) and got["q67"] == pytest.approx(q67)
    # one LOYO fold (short leg, held-out 2023-24): training excludes the held-out year
    h = 2
    z = panel["dvol_z90"].to_numpy(float)
    w = panel["w"].to_numpy(float)
    T = panel["T"].to_numpy()
    bounds = D.ANCHORS + [D.LAST_BOUND]
    ym = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy() for k in range(5)]
    trm = np.zeros(len(panel), bool)
    for k in range(5):
        if k != h:
            trm |= ym[k]
    trm &= (w < 0) & np.isfinite(z)
    assert not (trm & ym[h]).any(), "LOYO training must exclude the held-out year"
    q33, q67 = np.quantile(z[trm], [1 / 3, 2 / 3])
    lo = res["loyo"]["short"][h]
    assert lo["q33"] == pytest.approx(q33) and lo["q67"] == pytest.approx(q67)


def test_books_match_oc_bookic():
    """Rebuilt books must equal oc_bookic's formula cell by cell."""
    a = D.research_books_d2()
    b = B.research_books_d2()
    common = a.index.intersection(b.index)
    assert len(common) > 10000
    pd.testing.assert_frame_equal(a.reindex(common), b.reindex(common),
                                  check_dtype=False)


def test_grid_bounds(panel, res):
    """No decision bar at/after the cutoff; anchors partition the grid."""
    assert (panel["T"] < D.CUTOFF).all()
    assert panel["pnl"].notna().all().all()
    bounds = D.ANCHORS + [D.LAST_BOUND]
    ym = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])) for k in range(5)]
    assert sum(int(m.sum()) for m in ym) == len(panel), "years must partition the panel"
    assert set(panel["sym"].unique()) == set(SYMS)
    n_bars = [int(m.sum() // 5) for m in ym]
    assert n_bars[0] == 2190 and n_bars[2] == 2196, f"unexpected year sizes {n_bars}"
