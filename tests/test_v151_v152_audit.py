"""Tests for v151+v152 blind audit (Part A). No leader v151/v152 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v151_v152_audit")
REP = AUD / "replication.json"
ROWS151 = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
ROWS152 = ("t30_governed_dd30", "t35_governed_dd30", "primary_t40_governed_dd30")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v151/ or v152/ folders"
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
    assert d["version"] == "v151_v152_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows_spec_v151"].keys()) == set(ROWS151)
    assert set(d["rows_spec_v152"].keys()) == set(ROWS152)
    assert d["rows_spec_v151"]["reference_t15_ungoverned"]["governed"] is False
    assert d["rows_spec_v151"]["t20_governed"]["target"] == 0.20
    assert d["rows_spec_v152"]["t30_governed_dd30"]["gov_target"] == 0.30
    assert d["rows_spec_v152"]["t30_governed_dd30"]["gov_den"] == 0.15
    _check_rows_block(d["v144"]["rows"], ROWS151)
    _check_rows_block(d["v150"]["rows"], ROWS151)
    _check_rows_block(d["v151"]["rows"], ROWS151)
    _check_rows_block(d["v152"]["rows"], ROWS152)
    for gm in d["v144"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    for gm in d["v151"]["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    assert len(d["anchors_v92_144"]) == 5 and len(d["anchors_v94_144"]) == 5
    assert len(d["anchors_v92_150"]) == 5 and len(d["anchors_v103_150"]) == 5
    assert len(d["feats114x"]) == 44 and len(d["feats103x"]) == 60
    assert len(d["feats114o"]) == 31 and len(d["feats103o"]) == 41
    for c in OPT_FEATS:
        assert c in d["feats114o"] and c in d["feats103o"]
    assert not any(c.startswith("xs_") or c.startswith("xr_") for c in d["feats114o"])
    assert any(c.startswith("xs_") for c in d["feats114x"])
    assert d["opt"]["bars"] == 16944
    assert d["v151"]["overlap_bars"] == 10950
    assert d["v151"]["idx144"] == 10950 and d["v151"]["idx150"] == 10950
    # pvol anchors must match audited v129 rows (shared original-set training)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]


def test_ensemble_and_governor_math_synthetic():
    # A1 ensemble: 0.5*a + 0.5*b on union index, missing -> 0
    a = pd.Series([1.0, 2.0, np.nan], index=[0, 1, 2])
    b = pd.Series([10.0, np.nan, 30.0], index=[1, 2, 3])
    idx = a.index.union(b.index).sort_values()
    ens = 0.5 * a.reindex(idx).fillna(0.0) + 0.5 * b.reindex(idx).fillna(0.0)
    assert list(idx) == [0, 1, 2, 3]
    assert abs(float(ens.loc[0]) - 0.5) < 1e-12
    assert abs(float(ens.loc[1]) - 6.0) < 1e-12
    assert abs(float(ens.loc[2]) - 0.0) < 1e-12
    assert abs(float(ens.loc[3]) - 15.0) < 1e-12
    # A2 governor: g = clip((0.30 - DD)/0.15, 0, 1)
    def g30(dd):
        return float(np.clip((0.30 - dd) / 0.15, 0.0, 1.0))
    assert abs(g30(0.0) - 1.0) < 1e-12
    assert abs(g30(0.15) - 1.0) < 1e-12
    assert abs(g30(0.225) - 0.5) < 1e-12
    assert abs(g30(0.30) - 0.0) < 1e-12
    assert abs(g30(0.50) - 0.0) < 1e-12
    # v144/v151 governor for contrast
    def g20(dd):
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    assert abs(g20(0.15) - 0.5) < 1e-12 and abs(g30(0.15) - 1.0) < 1e-12
    assert 90 * 6 == 540
    # xs definition sums to zero per t
    df = pd.DataFrame({"t": [1, 1, 1], "c": [1.0, 2.0, 3.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    assert abs(df["xs"].sum()) < 1e-12
    d = _rep()
    assert np.isfinite(d["v152"]["rows"]["primary_t40_governed_dd30"]["monthly_pct"])


def test_opt_causality_truncation():
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


def test_no_leader_v151_v152_imports_in_blind_script():
    src = (AUD / "replicate_v151_v152.py").read_text()
    assert "v151_result.json" not in src
    assert "v152_result.json" not in src
    assert "v151_info_ensemble" not in src
    assert "v152_dd30_frontier" not in src
    assert "import v151" not in src and "from v151" not in src
    assert "import v152" not in src and "from v152" not in src
    assert "import v144" not in src and "from v144" not in src
    assert "import v150" not in src and "from v150" not in src
    assert "add_xs" not in src or "def add_xs_xr" in src  # own inline version only
    assert "rank(pct=True)" in src  # own xs definition
    assert "xs_" in src
    assert "GOV_WIN = 540" in src
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "0.0005" in src and "0.0002" in src
    assert "min_periods=6" in src and "min_periods=90" in src and "min_periods=3" in src
    for c in OPT_FEATS:
        assert c in src
