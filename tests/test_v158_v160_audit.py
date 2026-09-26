"""Tests for v158+v159+v160 blind audit (Part A). No leader v158/v159/v160/v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v158_v160_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
ETH_OPT_FEATS = ["eth_opt_net6", "eth_opt_pcr_z", "eth_opt_skew6", "eth_opt_skew_z", "eth_opt_act_z"]
OPT10_FEATS = OPT_FEATS + ETH_OPT_FEATS
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
FNG_FEATS = ["fng", "fng7", "fng_chg7", "fng_z"]
COT_FEATS = ["cot_lev_net", "cot_am_net", "cot_lev_chg4", "cot_am_chg4", "cot_lev_z", "cot_am_z"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v158/v159/v160 folders"
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
    assert d["version"] == "v158_v160_audit_replication"
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
    _check_rows_block(d["Bp_btceth_xs"]["rows"], ROWS)
    _check_rows_block(d["D_cb"]["rows"], ROWS)
    _check_rows_block(d["G_fng"]["rows"], ROWS)
    _check_rows_block(d["H_cot"]["rows"], ROWS)
    _check_rows_block(d["v158"]["rows"], ROWS)
    _check_rows_block(d["v159"]["rows"], ROWS)
    _check_rows_block(d["v160"]["rows"], ROWS)
    for gm in d["A_v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for key in ("v158", "v159", "v160"):
        for gm in d[key]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
            assert gm["mean_g"] == 1.0
    # feature counts: A 44/60, B 49/65, Bp 54/70, D 49/65, G 48/64, H 50/66
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114B"]) == 49 and len(d["feats103B"]) == 65
    assert len(d["feats114Bp"]) == 54 and len(d["feats103Bp"]) == 70
    assert len(d["feats114D"]) == 49 and len(d["feats103D"]) == 65
    assert len(d["feats114G"]) == 48 and len(d["feats103G"]) == 64
    assert len(d["feats114H"]) == 50 and len(d["feats103H"]) == 66
    for c in OPT_FEATS:
        assert c in d["feats114B"] and c in d["feats103B"]
    for c in OPT10_FEATS:
        assert c in d["feats114Bp"] and c in d["feats103Bp"]
    for c in CB_FEATS:
        assert c in d["feats114D"] and c in d["feats103D"]
    for c in FNG_FEATS:
        assert c in d["feats114G"] and c in d["feats103G"]
    for c in COT_FEATS:
        assert c in d["feats114H"] and c in d["feats103H"]
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114B"])
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats103B"])
    assert not any(c.startswith("xs_eth_") or c.startswith("xr_eth_") for c in d["feats114Bp"])
    assert not any(c.startswith("xs_eth_") or c.startswith("xr_eth_") for c in d["feats103Bp"])
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in d["feats114Bp"])
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in d["feats114D"])
    assert not any(c.startswith("xs_fng") or c.startswith("xr_fng") for c in d["feats114G"])
    assert not any(c.startswith("xs_cot_") or c.startswith("xr_cot_") for c in d["feats114H"])
    assert any(c.startswith("xs_") for c in d["feats114x"])
    assert d["opt"]["bars"] >= 16944
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["opt10"]["bars"] >= 16944
    assert d["fng"]["daily_rows"] >= 3150
    assert d["cot"]["weekly_rows"] >= 440
    assert d["v158"]["overlap_ABpD"] == 10950
    assert d["v158"]["idxA"] == 10950 and d["v158"]["idxBp"] == 10950 and d["v158"]["idxD"] == 10950
    assert d["v159"]["idxA"] == 10950 and d["v159"]["idxB"] == 10950
    assert d["v159"]["idxD"] == 10950 and d["v159"]["idxG"] == 10950
    assert d["v160"]["idxA"] == 10950 and d["v160"]["idxB"] == 10950
    assert d["v160"]["idxD"] == 10950 and d["v160"]["idxH"] == 10950
    assert set(d["D_cb"]["coverage"].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]


def test_ensemble_and_governor_math_synthetic():
    # v158 3-way: (a+b+d)/3 on union index, missing -> 0
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    c = pd.Series([100.0, 200.0, 300.0], index=[0, 2, 3])
    idx = a.index.union(b.index).union(c.index).sort_values()
    ens = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0) + c.reindex(idx).fillna(0.0)) / 3
    assert list(idx) == [0, 1, 2, 3]
    assert abs(float(ens.loc[0]) - (1.0 + 0.0 + 100.0) / 3) < 1e-12
    assert abs(float(ens.loc[3]) - (0.0 + 30.0 + 300.0) / 3) < 1e-12
    # v159/v160 4-way: (a+b+d+g)/4 on union index, missing -> 0
    g = pd.Series([1000.0, 2000.0, 3000.0, 4000.0], index=[0, 1, 2, 3])
    ens4 = (a.reindex(idx).fillna(0.0) + b.reindex(idx).fillna(0.0) + c.reindex(idx).fillna(0.0) + g.reindex(idx).fillna(0.0)) / 4
    assert abs(float(ens4.loc[0]) - (1.0 + 0.0 + 100.0 + 1000.0) / 4) < 1e-12
    assert abs(float(ens4.loc[1]) - (2.0 + 10.0 + 0.0 + 2000.0) / 4) < 1e-12
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
    d = _rep()
    assert np.isfinite(d["v158"]["rows"]["primary_t25_governed"]["monthly_pct"])
    assert np.isfinite(d["v159"]["rows"]["primary_t25_governed"]["monthly_pct"])
    assert np.isfinite(d["v160"]["rows"]["primary_t25_governed"]["monthly_pct"])


def test_fng_cot_opt_causality_truncation():
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
    # FNG-style trailing features are truncation-invariant
    f = pd.Series(rng.uniform(0, 100, n))

    def _fng(f_):
        f7 = f_.rolling(7, min_periods=7).mean()
        chg7 = f_ - f_.shift(7)
        mu90 = f_.rolling(90, min_periods=60).mean()
        sd90 = f_.rolling(90, min_periods=60).std(ddof=1)
        return pd.DataFrame({"fng7": f7, "chg7": chg7, "z": (f_ - mu90) / sd90})

    full_f = _fng(f)
    for cut in (100, 150, 200):
        part_f = _fng(f.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full_f.iloc[:cut + 1].reset_index(drop=True),
                                      part_f.reset_index(drop=True), check_dtype=False)
    # COT-style trailing features are truncation-invariant
    x = pd.Series(rng.uniform(-0.5, 0.5, n))

    def _cot(x_):
        chg4 = x_ - x_.shift(4)
        mu52 = x_.rolling(52, min_periods=26).mean()
        sd52 = x_.rolling(52, min_periods=26).std(ddof=1)
        return pd.DataFrame({"chg4": chg4, "z": (x_ - mu52) / sd52})

    full_x = _cot(x)
    for cut in (100, 150, 200):
        part_x = _cot(x.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full_x.iloc[:cut + 1].reset_index(drop=True),
                                      part_x.reset_index(drop=True), check_dtype=False)
    # availability asof is backward-only: t+4h sees only avail <= t+4h
    av = pd.to_datetime(["2021-01-01", "2021-01-02", "2021-01-03"], utc=True)
    assert bool((pd.Timestamp("2021-01-02 05:00", tz="UTC") - av[1]).total_seconds() >= 0)


def test_no_leader_v158_imports_in_blind_script():
    src = (AUD / "replicate_v158_v160.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src  # drop protocol docstring
    assert "v158_ensemble" not in body
    assert "v159_ensemble" not in body
    assert "v160_ensemble" not in body
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "v158/v158_result" not in body and "v159/v159_result" not in body and "v160/v160_result" not in body
    assert "import v158" not in body and "from v158" not in body
    assert "import v159" not in body and "from v159" not in body
    assert "import v160" not in body and "from v160" not in body
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
    for c in ETH_OPT_FEATS:
        assert c in body
    for c in FNG_FEATS:
        assert c in body
    for c in COT_FEATS:
        assert c in body
    assert "tolerance" in body  # coinbase merge_asof tolerance
    assert "ensemble_ctx" in body  # shared union missing->0 ensemble helper
    assert ", 3)" in body  # three-way v158 ensemble
    assert ", 4)" in body  # four-way v159/v160 ensembles
    assert "Timedelta(hours=1)" in body  # FNG D+1h availability
    assert "Timedelta(days=4)" in body  # COT D+4d availability
    assert "merge_asof" in body
