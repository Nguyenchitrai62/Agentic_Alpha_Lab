"""oc_dombook tests: causality (truncate & recompute) + alignment + aggregation.

Light: 4h opens + member books + results.json only, one process.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_dombook.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dombook"
sys.path.insert(0, str(OC))
import compute_dombook as C

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)


def _frames():
    books_full = C.research_books_d2()
    opens_full = pd.read_parquet(C.CACHE / "opens_v154.parquet")
    grid = books_full.index.intersection(opens_full.dropna(how="all").index).sort_values()
    grid = grid[grid < C.CUTOFF]
    return books_full, opens_full, grid


def test_regime_causal():
    _, opens_full, _ = _frames()
    ref = C.compute_dom30(opens_full)
    rng = np.random.default_rng(11)
    valid = ref.dropna().index
    for _ in range(5):
        t = valid[int(rng.integers(0, len(valid)))]
        probe = C.compute_dom30(opens_full.loc[opens_full.index <= t])
        assert probe.loc[t] == ref.loc[t], f"dom30 not causal at {t}"


def test_no_future_open_used():
    _, opens_full, _ = _frames()
    t = pd.Timestamp("2024-03-15 00:00:00", tz="UTC")
    base = C.compute_dom30(opens_full.loc[opens_full.index <= t]).loc[t]
    spiked = opens_full.copy()
    spiked.loc[spiked.index > t] *= 2.0
    after = C.compute_dom30(spiked).loc[t]
    assert base == after, "future opens must not change dom30 at t"


def test_scale_causal():
    """s0 at rows <= cut identical when recomputed on the truncated frame."""
    books_full, opens_full, grid = _frames()
    cut = pd.Timestamp("2024-06-01 00:00:00", tz="UTC")
    tgrid = grid[grid <= cut]
    books = books_full.reindex(tgrid)
    opens = opens_full.reindex(tgrid)[SYMS]
    fwd1 = opens.shift(-1) / opens - 1.0
    m = fwd1.notna().all(axis=1)
    books, fwd1 = books[m], fwd1[m]
    U = pd.Series((books.to_numpy() * fwd1.to_numpy()).sum(axis=1), index=books.index)
    sig = U.shift(1).rolling(360, min_periods=120).std(ddof=1) * C.ANN
    s_tr = pd.Series(np.where(sig.notna() & (sig > 0),
                              np.minimum(C.TARGET / sig.where(sig > 0, np.nan), C.CAP), 1.0),
                     index=books.index).fillna(1.0)
    # Full-run reference recomputed identically (same formula, full frame).
    fwd1f = opens_full.reindex(grid)[SYMS]
    fwd1f = fwd1f.shift(-1) / opens_full.reindex(grid)[SYMS] - 1.0
    bf = books_full.reindex(grid)
    ok = fwd1f.notna().all(axis=1)
    bf, fwd1f = bf[ok], fwd1f[ok]
    Uf = pd.Series((bf.to_numpy() * fwd1f.to_numpy()).sum(axis=1), index=bf.index)
    sigf = Uf.shift(1).rolling(360, min_periods=120).std(ddof=1) * C.ANN
    s_full = pd.Series(np.where(sigf.notna() & (sigf > 0),
                               np.minimum(C.TARGET / sigf.where(sigf > 0, np.nan), C.CAP), 1.0),
                       index=bf.index).fillna(1.0)
    common = s_tr.index.intersection(s_full.index)
    pd.testing.assert_series_equal(s_tr.loc[common], s_full.loc[common],
                                   check_names=False, obj="s0 must be causal")


def test_cutoffs_strictly_before_anchor():
    res = json.loads((OC / "results.json").read_text())
    pyr = res["per_year"]
    assert len(pyr) == 5
    hs = [r["hist_bars"] for r in pyr]
    assert hs == sorted(hs) and hs[0] > 8000, hs  # full opens history, grows
    for r in pyr:
        assert r["n_lo"] + r["n_mid"] + r["n_hi"] == r["n"], r
        assert r["n_nan_regime"] == 0, r
        assert np.isfinite(r["cut_lo"]) and np.isfinite(r["cut_hi"]), r
        assert (r["dret"] > 0) == r["ret_better"], r
        assert (r["ddd"] >= -1e-12) == r["dd_not_worse"], r
    assert res["meta"]["n_orphan_bars"] == 6
    assert res["meta"]["grid_end"] < "2026-09-24"
    g = res["gates"]
    assert g["promising"] == (g["ret_sign_years"] >= 4 and g["ret_loo_holds"] >= 4
                              and g["dd_not_worse_years"] >= 4), g
    assert g["promising"] is False


def test_turnover_cost():
    res = json.loads((OC / "results.json").read_text())
    for r in res["per_year"]:
        assert r["cost_base"] >= 0 and r["cost_scaled"] >= 0, r
        assert r["cost_base"] > 0 and r["cost_scaled"] > 0, r  # book always turns
    # Synthetic: flat weights -> zero turnover under the same formula.
    w = pd.DataFrame(np.full((10, 5), 0.02), columns=SYMS)
    to = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    assert float(to.iloc[1:].sum()) == 0.0
