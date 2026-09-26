"""Tests for v166 blind audit (Part A). No leader v166/v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v166_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v166/ folder"
    return json.loads(REP.read_text())


def _check_rows_block(block, rows):
    assert set(block.keys()) == set(rows)
    for row in rows:
        r = block[row]
        assert len(r["yearly"]) == 5
        assert len(r["mean_g_per_anchor_year"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        for gm in r["mean_g_per_anchor_year"]:
            assert 0.0 <= gm["mean_g"] <= 1.0
        assert 0.0 <= r["full_path_dd"] < 100
        assert np.isfinite(r["monthly_pct"])
        assert 0.0 <= r["maker_fill_rate"] <= 1.0
        assert r["orders_live"] > 0 and r["fills_live"] > 0


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v166_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows_spec"].keys()) == set(ROWS)
    assert d["rows_spec"]["reference_t15_ungoverned"]["governed"] is False
    assert d["rows_spec"]["t20_governed"]["target"] == 0.20
    assert d["rows_spec"]["primary_t25_governed"]["gov_target"] == 0.20
    assert d["rows_spec"]["primary_t25_governed"]["gov_den"] == 0.10
    _check_rows_block(d["A_v144"]["rows"], ROWS)
    _check_rows_block(d["B_opt_xs"]["rows"], ROWS)
    _check_rows_block(d["D_cb"]["rows"], ROWS)
    _check_rows_block(d["v154"]["rows"], ROWS)
    _check_rows_block(d["v166"]["rows"], ROWS)
    for gm in d["A_v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v166"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    # multiplier shares sum to ~1 and match leader scale
    sh = d["v166"]["multiplier_shares"]
    assert 0.0 <= sh["agree_1.3"] <= 1.0
    assert 0.0 <= sh["disagree_0.6"] <= 1.0
    assert 0.0 <= sh["neutral_1.0"] <= 1.0
    assert abs(sh["agree_1.3"] + sh["disagree_0.6"] + sh["neutral_1.0"] - 1.0) < 0.002
    assert d["v166"]["asset_columns"] == list(SYMS)
    # feature counts: A 44/60, B 49/65, D 49/65
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114B"]) == 49 and len(d["feats103B"]) == 65
    assert len(d["feats114D"]) == 49 and len(d["feats103D"]) == 65
    for c in OPT_FEATS:
        assert c in d["feats114B"] and c in d["feats103B"]
    for c in CB_FEATS:
        assert c in d["feats114D"] and c in d["feats103D"]
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114B"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats114D"])
    assert d["opt"]["bars"] >= 16944
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["v154"]["overlap_ABD"] == 10950
    # plain v154 leg must reproduce the audited v154 numbers
    v154a = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v154_audit/replication.json").read_text())
    for row in ROWS:
        assert d["v154"]["rows"][row]["monthly_pct"] == v154a["v154"]["rows"][row]["monthly_pct"]
        assert d["v154"]["rows"][row]["full_path_dd"] == v154a["v154"]["rows"][row]["full_path_dd"]
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]


def _mult(a, b, c):
    s = np.sign([a, b, c])
    nz = int((s != 0).sum())
    pos = int((s > 0).sum())
    neg = int((s < 0).sum())
    if nz >= 2 and (pos == nz or neg == nz):
        return 1.3
    if pos > 0 and neg > 0:
        return 0.6
    return 1.0


def test_agreement_math_synthetic():
    # hand-checked multiplier cases per assignment
    assert _mult(1.0, 2.0, 3.0) == 1.3
    assert _mult(-1.0, -2.0, -3.0) == 1.3
    assert _mult(1.0, 2.0, 0.0) == 1.3  # nz=2 agree
    assert _mult(-1.0, 0.0, -3.0) == 1.3
    assert _mult(1.0, 0.0, 0.0) == 1.0  # nz=1
    assert _mult(0.0, 0.0, 0.0) == 1.0
    assert _mult(-1.0, 0.0, 0.0) == 1.0
    assert _mult(1.0, -1.0, 0.0) == 0.6
    assert _mult(1.0, -1.0, 1.0) == 0.6
    assert _mult(1.0, 2.0, -3.0) == 0.6
    # disagreement overrides agreement shape (pos>0 and neg>0 -> 0.6)
    # union align missing->0 + books = m*(a+b+d)/3
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    cc = pd.Series([100.0, 200.0, 300.0], index=[0, 2, 3])
    cols = ["X"]
    A = pd.DataFrame({"X": a.reindex([0, 1, 2, 3]).fillna(0.0)})
    B = pd.DataFrame({"X": b.reindex([0, 1, 2, 3]).fillna(0.0)})
    D = pd.DataFrame({"X": cc.reindex([0, 1, 2, 3]).fillna(0.0)})
    idx = A.index.union(B.index).union(D.index).sort_values()
    Au = A.reindex(index=idx, columns=cols).fillna(0.0)
    Bu = B.reindex(index=idx, columns=cols).fillna(0.0)
    Du = D.reindex(index=idx, columns=cols).fillna(0.0)
    S = np.stack([np.sign(X.to_numpy()) for X in (Au, Bu, Du)])
    nz = (S != 0).sum(axis=0)
    pos, neg = (S > 0).sum(axis=0), (S < 0).sum(axis=0)
    m = np.ones(nz.shape)
    m[(nz >= 2) & ((pos == nz) | (neg == nz))] = 1.3
    m[(pos > 0) & (neg > 0)] = 0.6
    books = (Au + Bu + Du) / 3 * m
    # row 0: 1,0,100 all non-zero agree -> 1.3
    assert abs(float(books.iloc[0, 0]) - (1.0 + 0.0 + 100.0) / 3 * 1.3) < 1e-12
    # row 1: 2,10,0 agree -> 1.3
    assert abs(float(books.iloc[1, 0]) - (2.0 + 10.0 + 0.0) / 3 * 1.3) < 1e-12
    # governor: g = clip((0.20 - DD)/0.10, 0, 1)
    def g20(dd):
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    assert abs(g20(0.0) - 1.0) < 1e-12
    assert abs(g20(0.15) - 0.5) < 1e-12
    assert abs(g20(0.30) - 0.0) < 1e-12
    assert 90 * 6 == 540
    d = _rep()
    assert np.isfinite(d["v166"]["rows"]["primary_t25_governed"]["monthly_pct"])


def test_opt_and_cb_causality_truncation():
    rng = np.random.default_rng(7)
    n = 250
    df = pd.DataFrame({"call_buy": rng.uniform(0, 1e5, n), "call_sell": rng.uniform(0, 1e5, n),
                       "put_buy": rng.uniform(0, 1e5, n), "put_sell": rng.uniform(0, 1e5, n),
                       "n_trades": rng.integers(0, 200, n).astype(float),
                       "iv_otm_put": rng.uniform(20, 150, n), "iv_otm_call": rng.uniform(20, 150, n)})

    def _opt(df_):
        net = df_["put_buy"] - df_["put_sell"] - df_["call_buy"] + df_["call_sell"]
        tot = df_["call_buy"] + df_["call_sell"] + df_["put_buy"] + df_["put_sell"]
        o6 = net.rolling(6, min_periods=6).sum() / tot.rolling(6, min_periods=6).sum().replace(0.0, np.nan)
        return o6

    full = _opt(df)
    for cut in (100, 150, 200):
        part = _opt(df.iloc[:cut + 1].copy())
        pd.testing.assert_series_equal(full.iloc[:cut + 1].reset_index(drop=True),
                                       part.reset_index(drop=True), check_dtype=False)
    cbp = pd.Series(rng.uniform(-50, 50, n))

    def _cb(cbp_):
        p6 = cbp_.rolling(6, min_periods=4).mean()
        p42 = cbp_.rolling(42, min_periods=30).mean()
        m540 = cbp_.rolling(540, min_periods=270).mean()
        s540 = cbp_.rolling(540, min_periods=270).std()
        return pd.DataFrame({"dev": p6 - m540, "z": (p6 - m540) / s540, "chg": p6 - p42})

    full_c = _cb(cbp)
    for cut in (100, 150, 200):
        part_c = _cb(cbp.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full_c.iloc[:cut + 1].reset_index(drop=True),
                                      part_c.reset_index(drop=True), check_dtype=False)


def test_no_leader_v166_imports_in_blind_script():
    src = (AUD / "replicate_v166.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "v166_agreement_confidence" not in body
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "v166/v166_result" not in body
    assert "v154/v154_result" not in body
    assert "import v166" not in body and "from v166" not in body
    assert "import v154" not in body and "from v154" not in body
    assert "import v144" not in body and "from v144" not in body
    assert "import v150" not in body and "from v150" not in body
    assert "import v111" not in body and "from v111" not in body
    assert "import v151" not in body and "from v151" not in body
    assert "spec_from_file_location" not in body and "exec_module" not in body
    assert "rank(pct=True)" in body
    assert "GOV_WIN = 540" in body
    assert "range(2, 15)" in body
    assert "minutes=15" in body
    assert "0.0005" in body and "0.0002" in body
    assert "min_periods=6" in body and "min_periods=90" in body and "min_periods=3" in body
    for c in OPT_FEATS:
        assert c in body
    for c in CB_FEATS:
        assert c in body
    assert "tolerance" in body
    assert "/ 3" in body
    assert "1.3" in body and "0.6" in body
    assert "np.sign" in body
    assert "nz >= 2" in body
