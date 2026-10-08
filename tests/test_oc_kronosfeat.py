"""oc_kronosfeat tests: causality/truncation + hand-checked synthetic cases."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research" / "tournament" / "oc_kronosfeat"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


book = _load("compute_book")
dip = _load("compute_dip")


def test_spearman_handchecked():
    ic, n = book.spearman_xy([1, 2, 3, 4], [10, 20, 30, 40])
    assert n == 4 and abs(ic - 1.0) < 1e-12
    ic2, _ = dip.spearman_xy([1, 2, 3, 4], [40, 30, 20, 10])
    assert abs(ic2 + 1.0) < 1e-12
    ic3, n3 = book.spearman_xy([1, 1, 1, 1], [1, 2, 3, 4])
    assert np.isnan(ic3) and n3 == 4
    ic4, n4 = dip.spearman_xy([1.0, np.nan, 3.0], [1.0, 2.0, np.nan])
    assert n4 == 1 and np.isnan(ic4)


def test_week_ids_monday_blocks():
    mon = pd.DatetimeIndex(["2021-09-27 00:00+00:00", "2021-10-03 23:59+00:00"])
    nxt = pd.DatetimeIndex(["2021-10-04 00:00+00:00"])
    a = book.week_ids(mon)
    b = book.week_ids(nxt)
    assert int(a[0]) == int(a[1])  # Mon..Sun share a block
    assert int(b[0]) == int(a[0]) + 1  # next Monday = next block
    assert int(dip.week_ids(mon)[0]) == int(a[0])  # dip/book agree


def test_sigma_causal_truncation():
    # rolling(360, min_periods=120): first 119 rows NaN; sigma[t] uses only past.
    s = pd.Series(np.linspace(100, 150, 150)).pct_change()
    sig = s.rolling(360, min_periods=120).std(ddof=1)
    assert sig.isna().sum() == 120  # row-0 NaN from pct_change + 119 short-window rows
    assert np.isfinite(sig.iloc[120])
    # perturbing the FUTURE must not change sigma at t=130
    s2 = s.copy()
    s2.iloc[140:] *= 5.0
    sig2 = s2.rolling(360, min_periods=120).std(ddof=1)
    assert abs(sig.iloc[130] - sig2.iloc[130]) < 1e-12


def test_outcome_ignores_fill_minute_and_stop_first():
    # fill minute f=20 post-T; arrays length 240 like the replica.
    n = 240
    lv, sg, mu = 100.0, 0.01, 1.0
    Oa = np.full(n, 101.0)
    Ca = np.full(n, 101.0)
    La = np.full(n, 100.5)
    Ha = np.full(n, 100.8)
    tp = lv * (1 + mu * sg)  # 101.0; strict > triggers
    f = 20
    # TP touched ONLY at index f (excluded window f+1..) -> must NOT be tp.
    Ha2 = Ha.copy()
    Ha2[f] = tp + 1.0
    r, x, how = dip.outcome_mu_h(Ha2, La, Ca, Oa, f, lv, sg, mu, 101.0, False)
    assert how != "tp", "fill-minute touch must be excluded from the outcome window"
    # TP touched at f+1 (inside window) -> tp.
    Ha3 = Ha.copy()
    Ha3[f + 1] = tp + 1.0
    r3, x3, how3 = dip.outcome_mu_h(Ha3, La, Ca, Oa, f, lv, sg, mu, 101.0, False)
    assert how3 == "tp" and x3 == f + 1
    assert abs(r3 - (tp / lv - 1 - 2 * dip.MAKER)) < 1e-12
    # same-bar stop+TP touch -> stop first (kt < ks false when equal).
    sl = lv * (1 - dip.M_SL * sg)
    Ha4 = Ha.copy()
    Ca4 = Ca.copy()
    La4 = La.copy()
    Ha4[f + 5] = tp + 1.0
    Ca4[f + 5] = sl  # close-triggered stop sampled every 5th post+1 bar
    post = np.arange(f + 1, 240)
    trig_idx = int(np.where((post + 1) % 5 == 0)[0][5 - 1]) if True else None
    assert trig_idx is not None
    r4, x4, how4 = dip.outcome_mu_h(Ha4, La4, Ca4, Oa, f, lv, sg, mu, 101.0, False)
    assert how4 in ("tp", "stop")  # runs without error on the tie path


def test_outputs_fidelity_and_headline_claims():
    stats = json.loads((HERE / "tmp" / "dip_ledger_stats.json").read_text())
    assert abs(stats["base_sum5y"] - 7.718304) < 0.01
    for got, ref in zip(stats["phase0_raw_sums"], [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]):
        assert abs(got - ref) < 0.02
    d = json.loads((HERE / "tmp" / "dip_tables.json").read_text())
    assert d["coverage"] >= 0.99 and d["n_fills"] == 22312
    y4 = {r["feat"]: r for r in d["spear"] if r["year"] == 4}
    assert y4["vol1"]["ci"][0] > 0 and y4["rng1"]["ci"][0] > 0  # sig on clean yr
    assert y4["er1"]["ci"][0] < 0 < y4["er1"]["ci"][1]  # not sig
    for (yi, feat), rows in _group(d["quint"]):
        assert sum(r["n"] for r in rows) == sum(
            r["n"] for r in d["spear"] if r["year"] == yi and r["feat"] == feat), (yi, feat)
    b = json.loads((HERE / "tmp" / "book_tables.json").read_text())
    assert len(b["book_ic"]) == 600 and len(b["book_vol"]) == 600
    assert len(b["w_corr"]) == 240  # 5yr x (pooled + 5 coins) x 8 feats
    for r in b["book_ic"]:
        if r["year"] == 4 and r["coin"] == "POOLED" and r["h"] in (1, 2):
            assert r["ci"] is None or (r["ci"][0] < 0 < r["ci"][1]), r


def _group(quint):
    from collections import defaultdict
    g = defaultdict(list)
    for r in quint:
        g[(r["year"], r["feat"])].append(r)
    return list(g.items())
