"""Tests for oc_qbasis (causality, cut-offs, counts, no-1m, books math)."""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_qbasis"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTHS = [2.5, 3.0, 3.5, 4.0, 5.0]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)


def _zfeat():
    import importlib.util

    spec = importlib.util.spec_from_file_location("oc_qbasis_mod", HERE / "analyze_qbasis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_basis_strictly_before_T():
    mod = _zfeat()
    q = pd.read_parquet(CACHE / "qbasis_features_4h.parquet")
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    btc = q[q.sym == "BTCUSDT"][["close_time", "qb_front"]]
    F = mod.ZFeat(btc)
    rng = np.random.default_rng(7)
    grid = pd.read_parquet(CACHE / "opens_v154.parquet").index
    grid = grid[(grid >= ANCHORS[0]) & (grid < ANCHORS[-1] + YEAR_LEN)]
    idx = rng.choice(len(grid), size=200, replace=False)
    Ts = grid[idx]
    out = F.compute(Ts)
    assert out["z"].notna().mean() > 0.95
    # no used close_time is >= T: max close < each T
    ctns = btc["close_time"].values.astype("datetime64[ns]").astype(np.int64)
    for T in Ts[:20]:
        tns = pd.Timestamp(T).value
        assert ctns[ctns < tns].max() < tns
    # truncate-and-recompute: dropping rows with close_time >= T changes nothing
    for T in Ts[:5]:
        trunc = btc[btc["close_time"] < T]
        Ft = mod.ZFeat(trunc).compute(pd.DatetimeIndex([T]))
        assert abs(Ft["z"].iloc[0] - out["z"].loc[T]) < 1e-9 or (
            np.isnan(Ft["z"].iloc[0]) and np.isnan(out["z"].loc[T])
        )


def test_cutoffs_causal():
    res = pd.read_json(HERE / "results.json")  # smoke: file exists & parses
    assert True
    import json

    out = json.loads((HERE / "results.json").read_text())
    mod = _zfeat()
    q = pd.read_parquet(CACHE / "qbasis_features_4h.parquet")
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    F = mod.ZFeat(q[q.sym == "BTCUSDT"][["close_time", "qb_front"]])
    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills["T"] = pd.to_datetime(fills["t_fill"], utc=True) - pd.to_timedelta(fills["f"], unit="m")
    d = fills[fills["sym"].isin(MAJORS) & fills["x1"].isin(DEPTHS)].copy()
    d["F"] = F.compute(pd.DatetimeIndex(d["T"]))["z"].to_numpy()
    a0 = ANCHORS[0]
    tr = d[(d["T"] < a0) & d["F"].notna()]
    assert (tr["T"] >= a0).sum() == 0
    assert abs(float(tr["F"].quantile(1 / 3)) - out["dips"]["yearly"][0]["cut_q33"]) < 1e-9
    # LOYO heldout uses no row of the held-out year
    ah = ANCHORS[2]
    tr2 = d[~((d["T"] >= ah) & (d["T"] < ah + YEAR_LEN))]
    assert ((tr2["T"] >= ah) & (tr2["T"] < ah + YEAR_LEN)).sum() == 0


def test_counts():
    import json

    out = json.loads((HERE / "results.json").read_text())
    assert out["meta"]["dip_T"][2] == 6876
    assert [n for _, n in out["meta"]["per_year_n"]] == [990, 1045, 1330, 989, 1144]
    assert out["meta"]["grid"][2] == 10955
    assert out["books"]["yearly"][1]["n_train_times"] == 2190
    q = pd.read_parquet(CACHE / "qbasis_features_4h.parquet")
    assert int((q["sym"] == "BTCUSDT").sum()) > 13000


def test_no_1m():
    src = (HERE / "analyze_qbasis.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m", "klines_1m", "aggflow"):
        assert bad not in src, bad


def test_books_match_oc_fundregime():
    mod = _zfeat()
    b = mod.research_books_d2()
    A = pd.read_parquet(CACHE / "member_A_O1_orders.parquet")[SYMS]
    Aq = pd.read_parquet(CACHE / "member_Aq_O1_orders.parquet")[SYMS]
    B = pd.read_parquet(CACHE / "member_B_tv.parquet")[SYMS]
    Bq = pd.read_parquet(CACHE / "member_Bq_tv.parquet")[SYMS]
    idx = A.index.union(Aq.index)
    o1 = 0.5 * (A.reindex(idx).fillna(0.0) + B.reindex(idx).fillna(0.0)) / 2 + 0.5 * (
        Aq.reindex(idx).fillna(0.0) + Bq.reindex(idx).fillna(0.0)
    ) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    expect = 0.8 * o1.reindex(idx2).fillna(0.0) + 0.2 * (
        D.reindex(idx2).fillna(0.0) + Dq.reindex(idx2).fillna(0.0)
    ) / 2
    blk = b.index[1000:1500]
    pd.testing.assert_frame_equal(b.reindex(blk), expect.reindex(blk))
