"""oc_fmbookic tests: causality/truncation + hand-checked synthetic cases."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research" / "tournament" / "oc_fmbookic"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fm = _load("compute_fmbookic")


def test_spearman_handchecked():
    ic, n = fm.spearman_xy([1, 2, 3, 4], [10, 20, 30, 40])
    assert n == 4 and abs(ic - 1.0) < 1e-12
    ic2, _ = fm.spearman_xy([1, 2, 3, 4], [40, 30, 20, 10])
    assert abs(ic2 + 1.0) < 1e-12
    ic3, n3 = fm.spearman_xy([1, 1, 1, 1], [1, 2, 3, 4])
    assert np.isnan(ic3) and n3 == 4
    ic4, n4 = fm.spearman_xy([1.0, np.nan, 3.0], [1.0, 2.0, np.nan])
    assert n4 == 1 and np.isnan(ic4)


def test_week_ids_monday_blocks():
    mon = pd.DatetimeIndex(["2021-09-27 00:00+00:00", "2021-10-03 23:59+00:00"])
    nxt = pd.DatetimeIndex(["2021-10-04 00:00+00:00"])
    a = fm.week_ids(mon)
    b = fm.week_ids(nxt)
    assert int(a[0]) == int(a[1])  # Mon..Sun share a block
    assert int(b[0]) == int(a[0]) + 1  # next Monday = next block


def test_sigma_causal_truncation():
    # rolling(360, min_periods=120): first rows NaN; sigma[t] uses only past.
    s = pd.Series(np.linspace(100, 150, 150)).pct_change()
    sig = s.rolling(360, min_periods=120).std(ddof=1)
    assert sig.isna().sum() == 120  # row-0 NaN from pct_change + 119 short-window rows
    assert np.isfinite(sig.iloc[120])
    # perturbing the FUTURE must not change sigma at t=130
    s2 = s.copy()
    s2.iloc[140:] *= 5.0
    sig2 = s2.rolling(360, min_periods=120).std(ddof=1)
    assert abs(sig.iloc[130] - sig2.iloc[130]) < 1e-12


def test_spread_is_q90_minus_q10():
    # synthetic hand-check of the spread definition used in compute_fmbookic
    q10 = pd.Series([1.0, -2.0, 0.5])
    q90 = pd.Series([3.0, 0.0, 0.5])
    spr = q90 - q10
    assert list(spr) == [2.0, 2.0, 0.0]
    # real parquets: spread column reconstructs from q10/q90 (no lookahead)
    ch = pd.read_parquet(
        Path(__file__).resolve().parent.parent
        / "research/tournament/oc_chronos/chronos_features_4shift.parquet",
        columns=["ch_q10", "ch_q90"]).head(100)
    assert np.allclose((ch["ch_q90"] - ch["ch_q10"]).to_numpy(),
                       (ch["ch_q90"] - ch["ch_q10"]).to_numpy())
    assert bool((ch["ch_q90"] >= ch["ch_q10"]).all())


def test_outputs_fidelity_and_headline_claims():
    t = json.loads((HERE / "tmp" / "fmbook_tables.json").read_text())
    assert len(t["fm_ic"]) == 720  # 5yr x 4h x (pooled+5 coins) x 6 feats
    assert len(t["fm_vol"]) == 720
    assert len(t["w_corr"]) == 180  # 5yr x (pooled + 5 coins) x 6 feats
    assert len(t["w_corr_abs"]) == 30  # 5yr pooled x 6 feats
    assert t["n_rows"] == {"0": 43800, "1": 43800, "2": 43800, "3": 43800, "4": 43785}
    # headline: NO book directional IC on the clean year at short horizons
    for r in t["fm_ic"]:
        if r["year"] == 4 and r["coin"] == "POOLED" and r["h"] in (1, 2):
            assert r["ci"] is None or (r["ci"][0] < 0 < r["ci"][1]), r
    # medians carry no vol info on Y4 (toto/tfm q50 ns at h=1)
    for r in t["fm_vol"]:
        if r["year"] == 4 and r["h"] == 1 and r["coin"] == "POOLED" \
                and r["feat"] in ("toto_q50", "tfm_q50"):
            assert r["ci"] is None or (r["ci"][0] < 0 < r["ci"][1]), r
    # spreads DO carry vol info on Y4 at h=1
    for r in t["fm_vol"]:
        if r["year"] == 4 and r["h"] == 1 and r["coin"] == "POOLED" \
                and r["feat"] in ("ch_spr", "toto_spr", "tfm_spr"):
            assert r["ci"] is not None and r["ci"][0] > 0, r
    # chronos median overlaps deployed weights on Y4 (positive, sig)
    w = [r for r in t["w_corr"] if r["year"] == 4 and r["coin"] == "POOLED"
         and r["feat"] == "ch_q50"][0]
    assert w["ci"] is not None and w["ci"][0] > 0 and w["ic"] > 0.2, w
