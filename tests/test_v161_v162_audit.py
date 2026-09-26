"""Tests for v161+v162 blind audit (Part A). No leader v161/v162/v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v161_v162_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
KP_FEATS = ["kp_btc_dev", "kp_btc_z", "kp_btc_chg", "kp_rp_dev", "kp_rp_z", "kp_rp_chg"]
MONO_FEATS = ["ret6", "ret42", "ret90", "ret180", "ret540", "snr6", "snr42",
              "snr90", "snr180", "snr540", "ema20", "ema200", "d50", "d200",
              "rib", "btc_ret42", "btc_ret180", "btc_rib", "btc_snr42"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v161/v162 folders"
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
    assert d["version"] == "v161_v162_audit_replication"
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
    _check_rows_block(d["K_kp"]["rows"], ROWS)
    _check_rows_block(d["v154"]["rows"], ROWS)
    _check_rows_block(d["v161"]["rows"], ROWS)
    _check_rows_block(d["A_mono"]["rows"], ROWS)
    _check_rows_block(d["B_mono"]["rows"], ROWS)
    _check_rows_block(d["D_mono"]["rows"], ROWS)
    _check_rows_block(d["v162"]["rows"], ROWS)
    for gm in d["A_v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for key in ("v154", "v161", "v162"):
        for gm in d[key]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
            assert gm["mean_g"] == 1.0
    # feature counts: A 44/60, B 49/65, D 49/65, K 50/66
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114B"]) == 49 and len(d["feats103B"]) == 65
    assert len(d["feats114D"]) == 49 and len(d["feats103D"]) == 65
    assert len(d["feats114K"]) == 50 and len(d["feats103K"]) == 66
    for c in OPT_FEATS:
        assert c in d["feats114B"] and c in d["feats103B"]
    for c in CB_FEATS:
        assert c in d["feats114D"] and c in d["feats103D"]
    for c in KP_FEATS:
        assert c in d["feats114K"] and c in d["feats103K"]
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114B"])
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats103B"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats114D"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats103D"])
    assert not any(c.startswith("xs_kp_") or c.startswith("xr_kp_") for c in d["feats114K"])
    assert not any(c.startswith("xs_kp_") or c.startswith("xr_kp_") for c in d["feats103K"])
    assert any(c.startswith("xs_") for c in d["feats114x"])
    assert d["opt"]["bars"] >= 16944
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["kp"]["bars"] >= 19000
    assert set(d["mono_feats"]) == set(MONO_FEATS)
    assert len(d["mono_cst_114x"]) == len(d["feats114x"])
    assert d["v154"]["overlap_ABD"] == 10950
    assert d["v154"]["idxA"] == 10950 and d["v154"]["idxB"] == 10950 and d["v154"]["idxD"] == 10950
    assert d["v161"]["idxA"] == 10950 and d["v161"]["idxK"] == 10950
    assert d["v162"]["idxAm"] == 10950 and d["v162"]["idxBm"] == 10950 and d["v162"]["idxDm"] == 10950
    assert set(d["D_cb"]["coverage"].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
    # A/B/D legs must match frozen v154 replication (shared base)
    v154 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v154_audit/replication.json").read_text())
    for leg in (("A_v144", "A_v144"), ("B_opt_xs", "B_opt_xs"), ("D_cb", "D_cb")):
        for row in ROWS:
            assert d[leg[0]]["rows"][row]["monthly_pct"] == v154[leg[1]]["rows"][row]["monthly_pct"]
            assert d[leg[0]]["rows"][row]["full_path_dd"] == v154[leg[1]]["rows"][row]["full_path_dd"]
    for row in ROWS:
        assert d["v154"]["rows"][row]["monthly_pct"] == v154["v154"]["rows"][row]["monthly_pct"]
        assert d["v154"]["rows"][row]["full_path_dd"] == v154["v154"]["rows"][row]["full_path_dd"]


def test_ensemble_and_governor_math_synthetic():
    # v161 4-way: (a+b+d+k)/4 on union index, missing -> 0
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    c = pd.Series([100.0, 200.0, 300.0], index=[0, 2, 3])
    k = pd.Series([1000.0, 2000.0, 3000.0, 4000.0], index=[0, 1, 2, 3])
    idx = a.index.union(b.index).union(c.index).union(k.index).sort_values()
    ens4 = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0) + c.reindex(idx).fillna(0.0) + k.reindex(idx).fillna(0.0)) / 4
    assert list(idx) == [0, 1, 2, 3]
    assert abs(float(ens4.loc[0]) - (1.0 + 0.0 + 100.0 + 1000.0) / 4) < 1e-12
    assert abs(float(ens4.loc[1]) - (2.0 + 10.0 + 0.0 + 2000.0) / 4) < 1e-12
    # v162 3-way mono: (am+bm+dm)/3 on union index, missing -> 0
    ens3 = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0) + c.reindex(idx).fillna(0.0)) / 3
    assert abs(float(ens3.loc[0]) - (1.0 + 0.0 + 100.0) / 3) < 1e-12
    # v144 governor: g = clip((0.20 - DD)/0.10, 0, 1)
    def g20(dd):
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    assert abs(g20(0.0) - 1.0) < 1e-12
    assert abs(g20(0.15) - 0.5) < 1e-12
    assert abs(g20(0.30) - 0.0) < 1e-12
    assert 90 * 6 == 540
    df = pd.DataFrame({"t": [1, 1, 1], "c": [1.0, 2.0, 3.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    assert abs(df["xs"].sum()) < 1e-12
    # monotonic_cst alignment: +1 on MONO set, 0 elsewhere
    feats = ["ret6", "xs_ret42", "opt_net6", "kp_btc_dev", "rib", "asset"]
    cst = [1 if c in MONO_FEATS else 0 for c in feats]
    assert cst == [1, 0, 0, 0, 1, 0]
    d = _rep()
    assert np.isfinite(d["v161"]["rows"]["primary_t25_governed"]["monthly_pct"])
    assert np.isfinite(d["v162"]["rows"]["primary_t25_governed"]["monthly_pct"])


def test_kp_and_cb_causality_truncation():
    rng = np.random.default_rng(7)
    n = 600
    # kimchi-style trailing smooth is truncation-invariant
    kp = pd.Series(rng.uniform(69000, 73000, n))

    def _smooth(s_):
        p6 = s_.rolling(6, min_periods=4).mean()
        p42 = s_.rolling(42, min_periods=30).mean()
        m540 = s_.rolling(540, min_periods=270).mean()
        s540 = s_.rolling(540, min_periods=270).std()
        return pd.DataFrame({"dev": p6 - m540, "z": (p6 - m540) / s540, "chg": p6 - p42})

    full = _smooth(kp)
    for cut in (300, 450, 550):
        part = _smooth(kp.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full.iloc[:cut + 1].reset_index(drop=True),
                                      part.reset_index(drop=True), check_dtype=False)
    # rp smooth is truncation-invariant
    rp = pd.Series(rng.uniform(-500, 500, n))
    full_r = _smooth(rp)
    for cut in (300, 450, 550):
        part_r = _smooth(rp.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full_r.iloc[:cut + 1].reset_index(drop=True),
                                      part_r.reset_index(drop=True), check_dtype=False)
    # availability asof is backward-only: t+3h sees only 1h open_time <= t+3h
    av = pd.to_datetime(["2021-01-01 00:00", "2021-01-01 01:00"], utc=True)
    key = pd.Timestamp("2021-01-01 00:30", tz="UTC") + pd.Timedelta(hours=3)
    assert bool((key - av[1]).total_seconds() >= 0)
    assert bool((pd.Timestamp("2021-01-01 05:00", tz="UTC") - av[1]).total_seconds() >= 0)


def test_no_leader_v161_imports_in_blind_script():
    src = (AUD / "replicate_v161_v162.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src  # drop protocol docstring
    assert "v162_ensemble" not in body
    assert "v161_ensemble" not in body
    assert "v161_kimchi" not in body
    assert "v162_mono" not in body
    assert "v161_upbit" not in body
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "v161/v161_result" not in body and "v162/v162_result" not in body
    assert "import v161" not in body and "from v161" not in body
    assert "import v162" not in body and "from v162" not in body
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
    assert "min_periods=4" in body and "min_periods=30" in body and "min_periods=270" in body
    assert "min_periods=6" in body and "min_periods=90" in body and "min_periods=3" in body
    for c in OPT_FEATS:
        assert c in body
    for c in CB_FEATS:
        assert c in body
    for c in KP_FEATS:
        assert c in body
    for c in MONO_FEATS:
        assert c in body
    assert "tolerance" in body  # upbit/coinbase merge_asof tolerance
    assert "merge_asof" in body
    assert "monotonic_cst" in body
    assert "mono_cst_for" in body
    assert "ensemble_ctx" in body  # shared union missing->0 ensemble helper
    assert ", 4)" in body  # four-way v161 ensemble
    assert ", 3)" in body  # three-way v154/v162 ensembles
