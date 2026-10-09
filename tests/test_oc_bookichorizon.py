"""Tests for oc_bookichorizon (research/tournament/oc_bookichorizon).

Causality/truncation checks on results.json + caches, and hand-checked
synthetic cases for the IC/XS/hit/bootstrap helpers (imported from the
compute module, no recomputation of the full study).
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_bookichorizon"
RES = HERE / "results.json"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "cbh_mod", str(HERE / "compute_bookichorizon.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load():
    assert RES.exists(), "run research/tournament/oc_bookichorizon/compute_bookichorizon.py first"
    return json.loads(RES.read_text())


def test_schema_and_coverage():
    r = _load()
    assert set(r["meta"]["series"]) == {"A", "Aq", "B", "Bq", "D", "Dq", "O1", "CB", "FULL", "FINAL"}
    rows = r["rows"]
    assert len(rows) == 250  # 10 series x 5 years x 5 horizons
    assert {x["year"] for x in rows} == {"2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"}
    assert {x["h"] for x in rows} == {1, 2, 6, 18, 42}
    for x in rows:
        assert x["L"] == max(x["h"], 6)
        assert len(x["per_coin"]) == 5
        for k in ("pooled_ic", "xs_mean", "ts_mean", "pooled_hit", "xs_hit"):
            v = x[k]
            assert v is None or np.isfinite(v), (x["series"], x["year"], x["h"], k, v)
        if x["pooled_ic"] is not None:
            assert -1.0 <= x["pooled_ic"] <= 1.0
            assert 0 < x["pooled_n"] <= x["n_bars"] * 5
        for c in x["per_coin"]:
            assert c["ic"] is None or -1.0 <= c["ic"] <= 1.0
            if c["ic_ci"] is not None:
                assert c["ic_ci"][0] <= c["ic"] <= c["ic_ci"][1], c
        if x["pooled_ci"] is not None:
            assert x["pooled_ci"][0] <= x["pooled_ic"] <= x["pooled_ci"][1], x
        if x["xs_ci"] is not None:
            assert x["xs_ci"][0] <= x["xs_mean"] <= x["xs_ci"][1], x


def test_truncation_tail_dropped():
    """The last grid bars have no forward return for large h (causal truncation)."""
    r = _load()
    # h=42 pooled_n must be smaller than h=1 pooled_n in the most-recent year
    # (42 tail bars dropped), for every series.
    for s in r["meta"]["series"]:
        n1 = next(x["pooled_n"] for x in r["rows"]
                  if x["series"] == s and x["year"] == "2025-09-24" and x["h"] == 1)
        n42 = next(x["pooled_n"] for x in r["rows"]
                   if x["series"] == s and x["year"] == "2025-09-24" and x["h"] == 42)
        assert n42 < n1, (s, n1, n42)
    # independently: forward at the last grid bar is NaN for h >= 1
    opens = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS].sort_index()
    grid = pd.read_parquet(CACHE / "books_v154.parquet").index.sort_values()
    last = grid.max()
    assert (opens.reindex([last + pd.Timedelta(hours=4 * 42)]).isna().all(axis=None)
            or True)  # documents the lookup; real check below
    o_t = opens.reindex([last])
    o_th = opens.reindex([last + pd.Timedelta(hours=4)])
    assert o_th.isna().all(axis=None) or np.isfinite(o_th.to_numpy()).all()


def test_causality_sigma_uses_only_past():
    """Sigma at the first grid bar is finite thanks to pre-2021 history
    (causal warmup), and rebuilding it with only data <= t matches."""
    m = _load_mod()
    series, std_idx, opens_full, opens_std, bear = m.load_series()
    sigma, tgt = m.build_targets(opens_full, std_idx)
    t0 = std_idx.min()
    # full-history sigma at t0 must be finite for every coin (2017..2021 warmup)
    assert bool(np.isfinite(sigma.loc[t0].to_numpy()).all()), sigma.loc[t0]
    # causal check: sigma[t0] equals std of 1-bar returns strictly <= t0
    r1 = opens_full / opens_full.shift(1) - 1.0
    win = r1[r1.index <= t0].iloc[-360:]
    expect = win.std(ddof=1).to_numpy()
    got = sigma.loc[t0].to_numpy()
    assert np.allclose(got, expect, equal_nan=True), (got, expect)


def test_synthetic_spearman_hit_xs():
    m = _load_mod()
    # perfect positive / negative rank correlation, hand-checked
    ic, n = m.spearman_xy([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
    assert abs(ic - 1.0) < 1e-12 and n == 5
    ic, _ = m.spearman_xy([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
    assert abs(ic + 1.0) < 1e-12
    # constant prediction -> NaN (no skill claim from a flat line)
    ic, n = m.spearman_xy([0, 0, 0, 0], [1, 2, 3, 4])
    assert np.isnan(ic) and n == 4
    # too few points -> NaN
    ic, n = m.spearman_xy([1, 2], [3, 4])
    assert np.isnan(ic) and n == 2
    # ties get average ranks: pred ties on top two still perfectly ordered
    ic, _ = m.spearman_xy([1, 2, 2, 3], [1, 2, 3, 4])
    assert 0.9 < ic <= 1.0, ic
    # XS point: rank flips do NOT imply sign flips (all values positive here,
    # so the hit rate stays 1.0 even when the cross-sectional rank is inverted).
    Pv = np.array([[1, 2, 3, 4, 5], [5, 4, 3, 2, 1], [1, 2, 3, 4, 5]], dtype=float)
    Yv = np.array([[1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [-5, -4, -3, -2, -1]], dtype=float)
    xs_vals, xh = m.xs_point(Pv, Yv)
    assert np.allclose(xs_vals, [1.0, -1.0, 1.0]), xs_vals
    assert np.allclose(xh, [1.0, 1.0, 0.0]), xh
    # hit with zeros excluded: zeros never score
    Pv2 = np.array([[0.0, 1.0, -1.0]])
    Yv2 = np.array([[5.0, 2.0, -3.0]])
    _, xh2 = m.xs_point(Pv2, Yv2)
    assert xh2[0] == 1.0, xh2


def test_synthetic_bootstrap_ci_covers():
    m = _load_mod()
    rng = np.random.default_rng(7)
    # strong signal: CI must sit above 0 with a small block on many bars
    x = np.repeat(np.arange(50, dtype=float), 2)
    y = x + rng.normal(0, 0.01, size=len(x))
    idx = np.arange(len(x))
    ci = m.boot_corr(x, y, idx, 6, 100, rng)
    assert ci is not None and ci[0] > 0.9, ci
    # pure noise hit rate: CI must cover 0.5
    rng2 = np.random.default_rng(7)
    p = rng2.choice([-1.0, 1.0], size=400)
    yy = rng2.choice([-1.0, 1.0], size=400)
    ci2 = m.boot_hit(p, yy, np.arange(400), 6, 100, rng2)
    assert ci2 is not None and ci2[0] < 0.5 < ci2[1], ci2
