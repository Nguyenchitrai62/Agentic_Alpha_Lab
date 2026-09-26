"""Tests for v154 blind audit (Part A). No leader v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v154_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v154/ folder"
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
    assert d["version"] == "v154_audit_replication"
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
    for gm in d["A_v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v154"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    # feature counts: A 44/60, B 49/65 (opt before xs, no xs of opt), D 49/65 (cb before xs, no xs of cb)
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114B"]) == 49 and len(d["feats103B"]) == 65
    assert len(d["feats114D"]) == 49 and len(d["feats103D"]) == 65
    for c in OPT_FEATS:
        assert c in d["feats114B"] and c in d["feats103B"]
    for c in CB_FEATS:
        assert c in d["feats114D"] and c in d["feats103D"]
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114B"])
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats103B"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats114D"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats103D"])
    assert any(c.startswith("xs_") for c in d["feats114x"])
    assert d["opt"]["bars"] >= 16944  # grid grows as Deribit file is extended; live window unchanged
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["v154"]["overlap_ABD"] == 10950
    assert d["v154"]["idxA"] == 10950 and d["v154"]["idxB"] == 10950 and d["v154"]["idxD"] == 10950
    # coinbase coverage recorded per sym
    assert set(d["D_cb"]["coverage"].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]


def test_ensemble_and_governor_math_synthetic():
    # v154 ensemble: (a+b+d)/3 on union index, missing -> 0
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    c = pd.Series([100.0, 200.0, 300.0], index=[0, 2, 3])
    idx = a.index.union(b.index).union(c.index).sort_values()
    ens = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0) + c.reindex(idx).fillna(0.0)) / 3
    assert list(idx) == [0, 1, 2, 3]
    assert abs(float(ens.loc[0]) - (1.0 + 0.0 + 100.0) / 3) < 1e-12
    assert abs(float(ens.loc[1]) - (2.0 + 10.0 + 0.0) / 3) < 1e-12
    assert abs(float(ens.loc[2]) - (0.0 + 0.0 + 200.0) / 3) < 1e-12
    assert abs(float(ens.loc[3]) - (0.0 + 30.0 + 300.0) / 3) < 1e-12
    # v144/v154 governor: g = clip((0.20 - DD)/0.10, 0, 1)
    def g20(dd):
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    assert abs(g20(0.0) - 1.0) < 1e-12
    assert abs(g20(0.15) - 0.5) < 1e-12
    assert abs(g20(0.30) - 0.0) < 1e-12
    assert 90 * 6 == 540
    # xs definition sums to zero per t
    df = pd.DataFrame({"t": [1, 1, 1], "c": [1.0, 2.0, 3.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    assert abs(df["xs"].sum()) < 1e-12
    d = _rep()
    assert np.isfinite(d["v154"]["rows"]["primary_t25_governed"]["monthly_pct"])


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
    # coinbase-style trailing features are truncation-invariant
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


def test_no_leader_v154_imports_in_blind_script():
    src = (AUD / "replicate_v154.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src  # drop protocol docstring
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "v154/v154_result" not in body
    assert "import v154" not in body and "from v154" not in body
    assert "import v144" not in body and "from v144" not in body
    assert "import v150" not in body and "from v150" not in body
    assert "import v111" not in body and "from v111" not in body
    assert "import v151" not in body and "from v151" not in body
    assert "spec_from_file_location" not in body and "exec_module" not in body
    assert "add_xs" not in body or "def add_xs_xr" in body  # own inline version only
    assert "rank(pct=True)" in body  # own xs definition
    assert "xs_" in body
    assert "GOV_WIN = 540" in body
    assert "range(2, 15)" in body
    assert "minutes=15" in body
    assert "0.0005" in body and "0.0002" in body
    assert "min_periods=6" in body and "min_periods=90" in body and "min_periods=3" in body
    for c in OPT_FEATS:
        assert c in body
    for c in CB_FEATS:
        assert c in body
    assert "tolerance" in body  # coinbase merge_asof tolerance
    assert "/ 3" in body  # three-way ensemble
