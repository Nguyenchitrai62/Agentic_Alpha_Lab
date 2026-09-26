"""Tests for v163 blind audit (Part A). No leader v163/v154/v144/v150/v111 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v163_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v163/ folder"
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
    assert d["version"] == "v163_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows_spec"].keys()) == set(ROWS)
    assert d["rows_spec"]["reference_t15_ungoverned"]["governed"] is False
    assert d["rows_spec"]["t20_governed"]["target"] == 0.20
    assert d["rows_spec"]["primary_t25_governed"]["gov_target"] == 0.20
    assert d["rows_spec"]["primary_t25_governed"]["gov_den"] == 0.10
    _check_rows_block(d["A_v144_smooth"]["rows"], ROWS)
    _check_rows_block(d["B_opt_xs_smooth"]["rows"], ROWS)
    _check_rows_block(d["D_cb_smooth"]["rows"], ROWS)
    _check_rows_block(d["v163"]["rows"], ROWS)
    for gm in d["A_v144_smooth"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v163"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
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
    assert d["opt"]["bars"] >= 16944
    assert d["opt"]["first"] == "2019-01-01 00:00:00+00:00"
    assert d["v163"]["overlap_ABD"] == 10950
    assert d["v163"]["idxA"] == 10950 and d["v163"]["idxB"] == 10950 and d["v163"]["idxD"] == 10950
    assert set(d["D_cb_smooth"]["coverage"].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # smoothing spec must be logged
    assert "ewm" in d["meta"]["smoothing"] and "span=6" in d["meta"]["smoothing"]
    assert "adjust=False" in d["meta"]["smoothing"]
    # pvol anchors must match audited v129 rows (shared original-set training, untouched by smoothing)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
    # return-model train rows must match the v154 blind replication (training unchanged; only preds smoothed)
    v154 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v154_audit/replication.json").read_text())
    for leg in ("A", "B", "D"):
        for m in ("v92", "v94", "v103"):
            b = d[f"anchors_{m}_{leg}"]
            r = v154[f"anchors_{m}_{leg}"]
            assert len(b) == len(r) == 5
            for bb, rr in zip(b, r):
                for k in rr:
                    if k.startswith("train_rows"):
                        assert bb[k] == rr[k], (leg, m, k)
                assert bb["n_pred_rows"] == rr["n_pred_rows"]


def test_ensemble_and_governor_math_synthetic():
    # v163 ensemble: (a+b+d)/3 on union index, missing -> 0
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
    # v144/v163 governor: g = clip((0.20 - DD)/0.10, 0, 1)
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
    assert np.isfinite(d["v163"]["rows"]["primary_t25_governed"]["monthly_pct"])


def test_smoothing_is_causal_and_matches_spec():
    # ewm(span=6, adjust=False) must equal the manual recursion and be truncation-invariant
    rng = np.random.default_rng(11)
    pred = pd.Series(rng.normal(0, 1, 60))
    alpha = 2 / (6 + 1)
    manual = np.empty(60)
    manual[0] = pred.iloc[0]
    for i in range(1, 60):
        manual[i] = alpha * pred.iloc[i] + (1 - alpha) * manual[i - 1]
    ewm = pred.ewm(span=6, adjust=False).mean().to_numpy()
    assert np.max(np.abs(ewm - manual)) < 1e-10
    # truncation invariance: rows <= cut identical when smoothed on truncated frame
    full = pred.ewm(span=6, adjust=False).mean()
    for cut in (20, 35, 50):
        part = pred.iloc[: cut + 1].ewm(span=6, adjust=False).mean()
        pd.testing.assert_series_equal(
            full.iloc[: cut + 1].reset_index(drop=True),
            part.reset_index(drop=True), check_dtype=False)
    # per-sym isolation: smoothing one sym must not depend on another sym
    df = pd.DataFrame({
        "sym": ["A"] * 30 + ["B"] * 30,
        "t": list(pd.date_range("2021-01-01", periods=30, freq="4h")) * 2,
        "pred": np.concatenate([pred.iloc[:30].to_numpy(), rng.normal(5, 1, 30)]),
    })
    df = df.sort_values(["sym", "t"]).reset_index(drop=True)
    sm = df.groupby("sym")["pred"].transform(lambda s: s.ewm(span=6, adjust=False).mean())
    a_only = df[df.sym == "A"]["pred"].ewm(span=6, adjust=False).mean().to_numpy()
    assert np.max(np.abs(sm[df.sym == "A"].to_numpy() - a_only)) < 1e-12


def test_no_leader_v163_imports_in_blind_script():
    src = (AUD / "replicate_v163.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src  # drop protocol docstring
    assert "v163_prediction_smoothing" not in body
    assert "v163/v163_result" not in body
    assert "v154_ensemble_coinbase" not in body
    assert "v151_info_ensemble" not in body
    assert "v150_options_flow" not in body
    assert "v144_deploy_v3" not in body
    assert "v111_coinbase_premium" not in body
    assert "import v163" not in body and "from v163" not in body
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
    assert "ewm(span=6" in body and "adjust=False" in body  # v163 smoothing
    assert "def smooth_pred_frame" in body
    assert "groupby(\"sym\")" in body or "groupby('sym')" in body
    assert "ROWS_V163" in body
