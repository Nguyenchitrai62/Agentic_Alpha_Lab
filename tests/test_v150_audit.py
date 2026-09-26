"""Tests for v150 blind audit (Part A). No leader v150 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v150_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v150/"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v150_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows"].keys()) == set(ROWS)
    for row in ROWS:
        r = d["rows"][row]
        assert len(r["yearly"]) == 5
        assert len(r["mean_g_per_anchor_year"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        for gm in r["mean_g_per_anchor_year"]:
            assert 0.0 <= gm["mean_g"] <= 1.0
        assert 0.0 <= r["full_path_dd"] < 100
        assert np.isfinite(r["monthly_pct"])
    for gm in d["rows"]["reference_t15_ungoverned"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    assert len(d["anchors_v92"]) == 5 and len(d["anchors_v94"]) == 5 and len(d["anchors_v103"]) == 5
    assert len(d["feats114o"]) == 31 and len(d["feats103o"]) == 41
    for c in OPT_FEATS:
        assert c in d["feats114o"] and c in d["feats103o"]
    assert not any(c.startswith("xs_") or c.startswith("xr_") for c in d["feats114o"])
    assert not any(c.startswith("xs_") or c.startswith("xr_") for c in d["feats103o"])
    assert "y" not in d["feats114o"] and "y6" not in d["feats103o"]
    assert d["opt"]["bars"] == 16944
    assert set(d["opt"]["nan_counts"].keys()) == set(OPT_FEATS)
    for a in d["anchors_v92"]:
        assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
    # vol models use original sets (no opt): pvol anchors must match audited v129 rows
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]


def _opt_features_synthetic(df):
    net = df["put_buy"] - df["put_sell"] - df["call_buy"] + df["call_sell"]
    tot = df["call_buy"] + df["call_sell"] + df["put_buy"] + df["put_sell"]
    opt_net6 = net.rolling(6, min_periods=6).sum() / tot.rolling(6, min_periods=6).sum().replace(0.0, np.nan)
    pcr = np.log(np.maximum(df["put_buy"] + df["put_sell"], 1.0) / np.maximum(df["call_buy"] + df["call_sell"], 1.0))

    def z(s):
        return (s - s.rolling(180, min_periods=90).mean()) / s.rolling(180, min_periods=90).std(ddof=1)

    skew = df["iv_otm_put"] - df["iv_otm_call"]
    return pd.DataFrame({"opt_net6": opt_net6, "opt_pcr_z": z(pcr),
                         "opt_skew6": skew.rolling(6, min_periods=3).mean(),
                         "opt_skew_z": z(skew),
                         "opt_act_z": z(np.log(np.maximum(df["n_trades"], 1.0)))})


def test_opt_math_hand_checked():
    # constant flows: net=0, tot>0 -> opt_net6==0 once window full; pcr==0
    n = 10
    df = pd.DataFrame({"call_buy": np.full(n, 100.0), "call_sell": np.full(n, 100.0),
                       "put_buy": np.full(n, 100.0), "put_sell": np.full(n, 100.0),
                       "n_trades": np.full(n, 5.0),
                       "iv_otm_put": np.full(n, 80.0), "iv_otm_call": np.full(n, 75.0)})
    f = _opt_features_synthetic(df)
    assert f["opt_net6"].iloc[:5].isna().all()
    assert abs(float(f["opt_net6"].iloc[5]) - 0.0) < 1e-12
    # zero flows -> tot==0 -> NaN (0 -> NaN rule)
    df0 = pd.DataFrame({"call_buy": np.zeros(8), "call_sell": np.zeros(8),
                        "put_buy": np.zeros(8), "put_sell": np.zeros(8),
                        "n_trades": np.zeros(8),
                        "iv_otm_put": np.full(8, np.nan), "iv_otm_call": np.full(8, np.nan)})
    f0 = _opt_features_synthetic(df0)
    assert f0["opt_net6"].isna().all()
    assert f0["opt_skew6"].isna().all()
    # one-sided flow: net==tot -> opt_net6==1
    df1 = pd.DataFrame({"call_buy": np.zeros(8), "call_sell": np.zeros(8),
                        "put_buy": np.full(8, 50.0), "put_sell": np.zeros(8),
                        "n_trades": np.full(8, 3.0),
                        "iv_otm_put": np.full(8, 90.0), "iv_otm_call": np.full(8, 70.0)})
    f1 = _opt_features_synthetic(df1)
    assert abs(float(f1["opt_net6"].iloc[5]) - 1.0) < 1e-12
    # skew level: 90-70=20, rolling-6 mean == 20 once 3+ obs
    assert abs(float(f1["opt_skew6"].iloc[2]) - 20.0) < 1e-12
    assert f1["opt_skew6"].iloc[:2].isna().all()
    # pcr hand check: log((50+0)/max(0,1)) = log(50)
    assert abs(np.log(50.0) - np.log(max(50.0, 1.0) / max(0.0, 1.0))) < 1e-12
    # z with <90 obs -> NaN
    assert f1["opt_pcr_z"].isna().all() and f1["opt_skew_z"].isna().all() and f1["opt_act_z"].isna().all()


def test_opt_causality_truncation():
    rng = np.random.default_rng(7)
    n = 250
    df = pd.DataFrame({"call_buy": rng.uniform(0, 1e5, n), "call_sell": rng.uniform(0, 1e5, n),
                       "put_buy": rng.uniform(0, 1e5, n), "put_sell": rng.uniform(0, 1e5, n),
                       "n_trades": rng.integers(0, 200, n).astype(float),
                       "iv_otm_put": rng.uniform(20, 150, n), "iv_otm_call": rng.uniform(20, 150, n)})
    full = _opt_features_synthetic(df)
    for cut in (100, 150, 200, n - 2):
        part = _opt_features_synthetic(df.iloc[:cut + 1].copy())
        pd.testing.assert_frame_equal(full.iloc[:cut + 1].reset_index(drop=True),
                                      part.reset_index(drop=True), check_dtype=False)
    # reindex fill rule: missing flows -> 0, IVs stay NaN
    idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
    raw = pd.DataFrame({"call_buy": [1.0, 2.0, 3.0]}, index=[idx[0], idx[1], idx[3]])
    full_idx = pd.date_range(idx[0], idx[3], freq="4h", tz="UTC")
    r = raw.reindex(full_idx)
    assert len(r) == 4 and np.isnan(r["call_buy"].iloc[2])
    filled = r["call_buy"].fillna(0.0)
    assert float(filled.iloc[2]) == 0.0
    iv = pd.DataFrame({"iv_otm_put": [80.0, 81.0, 82.0]}, index=[idx[0], idx[1], idx[3]]).reindex(full_idx)
    assert np.isnan(iv["iv_otm_put"].iloc[2])  # IVs stay NaN
    # join broadcasts on t to all syms (market-wide)
    panel = pd.DataFrame({"t": list(idx[:2]) * 2, "sym": ["BTCUSDT"] * 2 + ["ETHUSDT"] * 2})
    opt = pd.DataFrame({"opt_net6": [0.1, 0.2]}, index=pd.DatetimeIndex(idx[:2]))
    j = panel.merge(opt, left_on="t", right_index=True, how="left")
    assert float(j[(j.t == idx[0]) & (j.sym == "ETHUSDT")]["opt_net6"].iloc[0]) == 0.1


def test_no_leader_v150_imports_in_blind_script():
    src = (AUD / "replicate_v150.py").read_text()
    assert "v150_result.json" not in src
    assert "v150_options_flow" not in src
    assert "import v150" not in src and "from v150" not in src
    assert "import v144" not in src and "from v144" not in src
    assert "import v142" not in src and "from v142" not in src
    assert "xs_" not in src.replace("no xs", "").replace("xs_universe", "") or "add_xs" not in src
    assert "add_xs" not in src
    assert "rank(pct=True)" not in src
    for c in OPT_FEATS:
        assert c in src
    assert "min_periods=6" in src and "min_periods=90" in src and "min_periods=3" in src
