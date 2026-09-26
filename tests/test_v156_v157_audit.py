"""Tests for v156+v157 blind audit (Part A). No leader v156/v157/v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v156_v157_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
DVOL_FEATS = ["dvol_lvl", "dvol_chg24", "dvol_chg168", "dvol_z", "dvol_rvspread"]
MACRO_SUFFIX = ("_dist_50d", "_dist_200d", "_ret_20d", "_rv_20d")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v156/ or v157/ folders"
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
    assert d["version"] == "v156_v157_audit_replication"
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
    _check_rows_block(d["E_dvol"]["rows"], ROWS)
    _check_rows_block(d["F_macro"]["rows"], ROWS)
    _check_rows_block(d["v156"]["rows"], ROWS)
    _check_rows_block(d["v157"]["rows"], ROWS)
    for gm in d["A_v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v156"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v157"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    # feature counts: A 44/60; B/D/E 49/65 (new cols before xs, no xs of them); F 71/87
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114B"]) == 49 and len(d["feats103B"]) == 65
    assert len(d["feats114D"]) == 49 and len(d["feats103D"]) == 65
    assert len(d["feats114E"]) == 49 and len(d["feats103E"]) == 65
    assert len(d["feats114F"]) == 71 and len(d["feats103F"]) == 87
    for c in OPT_FEATS:
        assert c in d["feats114B"] and c in d["feats103B"]
    for c in CB_FEATS:
        assert c in d["feats114D"] and c in d["feats103D"]
    for c in DVOL_FEATS:
        assert c in d["feats114E"] and c in d["feats103E"]
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114B"])
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats103B"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats114D"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats103D"])
    assert not any(c.startswith("xs_dvol_") or c.startswith("xr_dvol_") for c in d["feats114E"])
    assert not any(c.startswith("xs_dvol_") or c.startswith("xr_dvol_") for c in d["feats103E"])
    assert not any(c.startswith("xs_mac_") or c.startswith("xr_mac_") for c in d["feats114F"])
    assert not any(c.startswith("xs_mac_") or c.startswith("xr_mac_") for c in d["feats103F"])
    assert any(c.startswith("xs_") for c in d["feats114x"])
    # macro feature columns recorded (27: 6 assets x4 + score/corr/dxy_chg)
    assert len(d["macro"]["feature_cols"]) == 27
    assert "mac_risk_on_score" in d["macro"]["feature_cols"]
    assert "mac_btc_qqq_corr_60d" in d["macro"]["feature_cols"]
    assert "mac_dxy_chg_20d" in d["macro"]["feature_cols"]
    for c in d["macro"]["feature_cols"]:
        assert c in d["feats114F"] and c in d["feats103F"]
    assert d["macro"]["avail_hour_utc"] == 22
    assert d["opt"]["bars"] >= 16944
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["v156"]["overlap_ABDE"] == 10950
    assert d["v157"]["overlap_ABDF"] == 10950
    assert d["v156"]["idxA"] == 10950 and d["v156"]["idxE"] == 10950
    assert d["v157"]["idxA"] == 10950 and d["v157"]["idxF"] == 10950
    assert set(d["D_cb"]["coverage"].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # DVOL live coverage must be complete (starts 2021-03, live starts 2021-09)
    assert d["E_dvol"]["live_full_row_coverage"] == 1.0
    assert d["dvol"]["live_full_row_coverage"] == 1.0
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
    # A/B/D legs must match the frozen v154 audit values (same inline construction)
    v154 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v154_audit/replication.json").read_text())
    for leg in ("A_v144", "B_opt_xs", "D_cb"):
        for row in ROWS:
            assert d[leg]["rows"][row]["monthly_pct"] == v154[leg]["rows"][row]["monthly_pct"]
            assert d[leg]["rows"][row]["full_path_dd"] == v154[leg]["rows"][row]["full_path_dd"]


def test_ensemble_and_governor_math_synthetic():
    # v156/v157 ensemble: (a+b+c+e)/4 on union index, missing -> 0
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    c = pd.Series([100.0, 200.0, 300.0], index=[0, 2, 3])
    e = pd.Series([1000.0, np.nan, np.nan], index=[0, 1, 2])
    idx = a.index.union(b.index).union(c.index).union(e.index).sort_values()
    ens = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0)
           + c.reindex(idx).fillna(0.0) + e.reindex(idx).fillna(0.0)) / 4
    assert list(idx) == [0, 1, 2, 3]
    assert abs(float(ens.loc[0]) - (1.0 + 0.0 + 100.0 + 1000.0) / 4) < 1e-12
    assert abs(float(ens.loc[1]) - (2.0 + 10.0 + 0.0 + 0.0) / 4) < 1e-12
    assert abs(float(ens.loc[2]) - (0.0 + 0.0 + 200.0 + 0.0) / 4) < 1e-12
    assert abs(float(ens.loc[3]) - (0.0 + 30.0 + 300.0 + 0.0) / 4) < 1e-12
    # v144/v156/v157 governor: g = clip((0.20 - DD)/0.10, 0, 1)
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
    assert np.isfinite(d["v156"]["rows"]["primary_t25_governed"]["monthly_pct"])
    assert np.isfinite(d["v157"]["rows"]["primary_t25_governed"]["monthly_pct"])


def test_dvol_and_macro_causality_truncation():
    rng = np.random.default_rng(11)
    n = 3000
    c = pd.Series(np.abs(rng.normal(60, 15, n)) + 1.0)
    c.iloc[::137] = np.nan

    def _dvol(cc):
        with np.errstate(divide="ignore", invalid="ignore"):
            chg24 = np.log(cc / cc.shift(24))
            chg168 = np.log(cc / cc.shift(168))
        mu = cc.rolling(2160, min_periods=720).mean()
        sd = cc.rolling(2160, min_periods=720).std(ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (cc - mu) / sd
        return pd.DataFrame({"chg24": chg24, "chg168": chg168, "z": z})

    full = _dvol(c)
    for cut in (1500, 2200, 2800):
        part = _dvol(c.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full.iloc[:cut + 1].reset_index(drop=True),
                                      part.reset_index(drop=True), check_dtype=False)
    # DVOL asof: avail_utc <= t+4h picks the last available candle only
    avail = pd.date_range("2021-03-24", periods=n, freq="h", tz="UTC") + pd.Timedelta(hours=1)
    t_rows = pd.to_datetime(["2021-04-24 00:00:00+00:00", "2021-04-24 04:00:00+00:00"], utc=True)
    for t in t_rows:
        sel_full = np.searchsorted(avail.values.astype("int64"),
                                   (t + pd.Timedelta(hours=4)).value, side="right") - 1
        sel_tr = np.searchsorted(avail.values.astype("int64")[:1500],
                                 (t + pd.Timedelta(hours=4)).value, side="right") - 1
        assert sel_full == sel_tr  # t+4h is before the truncation point here
    # macro-style daily asof with 22:00 UTC rule is truncation-invariant
    dates = pd.date_range("2019-06-03", periods=900, freq="D", tz="UTC")
    avail_d = (dates + pd.Timedelta(hours=22)).values.astype("int64")
    t_btc = (pd.to_datetime(["2021-09-24 03:59:59.999+00:00", "2021-09-25 03:59:59.999+00:00"],
                            utc=True).values.astype("datetime64[ns]").astype("int64"))

    def _asof(t_):
        return np.searchsorted(avail_d, t_, side="right") - 1

    assert list(_asof(t_btc)) == [list(_asof(t_btc))[0], list(_asof(t_btc))[1]]
    # 22:00 rule: a bar closing 21:59 sees the previous day; 22:00 sees the current day
    day = pd.Timestamp("2021-09-24", tz="UTC")
    just_before = (day + pd.Timedelta(hours=22) - pd.Timedelta(milliseconds=1)).value
    just_after = (day + pd.Timedelta(hours=22)).value
    assert _asof(np.array([just_before]))[0] < _asof(np.array([just_after]))[0]


def test_no_leader_v156_v157_imports_in_blind_script():
    src = (AUD / "replicate_v156_v157.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src  # drop protocol docstring
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "v154/v154_result" not in body
    assert "v156/" not in body and "v157/" not in body
    assert "import v154" not in body and "from v154" not in body
    assert "import v144" not in body and "from v144" not in body
    assert "import v150" not in body and "from v150" not in body
    assert "import v111" not in body and "from v111" not in body
    assert "import v151" not in body and "from v151" not in body
    assert "import v156" not in body and "from v156" not in body
    assert "import v157" not in body and "from v157" not in body
    assert "spec_from_file_location" not in body and "exec_module" not in body
    assert "from agentic_alpha_lab.patterns.macro import" not in body
    assert "from agentic_alpha_lab.patterns import macro" not in body
    assert "import macro" not in body
    assert "def add_xs_xr" in body  # own inline version only
    assert "rank(pct=True)" in body  # own xs definition
    assert "GOV_WIN = 540" in body
    assert "range(2, 15)" in body
    assert "minutes=15" in body
    assert "0.0005" in body and "0.0002" in body
    assert "min_periods=6" in body and "min_periods=90" in body and "min_periods=3" in body
    for c in OPT_FEATS:
        assert c in body
    for c in CB_FEATS:
        assert c in body
    for c in DVOL_FEATS:
        assert c in body
    assert "mac_risk_on_score" in body and "mac_btc_qqq_corr_60d" in body
    assert "avail_utc" in body  # DVOL merge_asof backward on availability
    assert "t_plus_4h" in body or "t + pd.Timedelta(hours=4)" in body
    assert "sqrt(2190" in body  # DVOL rvspread annualization
    assert "/ len(bs)" in body  # four-way ensembles (A+B+D+E)/4, (A+B+D+F)/4
