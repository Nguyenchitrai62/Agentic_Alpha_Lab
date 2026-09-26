"""Tests for v148+v149 blind audit (Part A). No leader v148/v149 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v148_v149_audit")
REP = AUD / "replication.json"
ROWS = ("gated_0.20", "gated_0.25", "ungoverned_0.15")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v148/ or v149/ folders"
    return json.loads(REP.read_text())


def _check_rows_block(block):
    assert set(block.keys()) == set(ROWS)
    for row in ROWS:
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
        assert r["worst_year_dd"] >= 0


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v148_v149_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows_spec"].keys()) == set(ROWS)
    # v144 base rows
    _check_rows_block(d["v144"]["rows"])
    for gm in d["v144"]["rows"]["ungoverned_0.15"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    assert len(d["v144"]["anchors_v92"]) == 5
    assert len(d["v144"]["anchors_v94"]) == 5
    assert len(d["v144"]["anchors_v103"]) == 5
    assert d["v144"]["feats114x_n"] == 44
    assert d["v144"]["feats103x_n"] == 60
    assert "y" not in d["v144"]["feats114x"] and "y6" not in d["v144"]["feats103x"]
    # v148 bootstrap block
    assert set(d["v148"].keys()) == set(ROWS)
    for row in ROWS:
        b = d["v148"][row]
        assert 1820 <= b["n_daily"] <= 1826
        assert len(b["daily"]) == b["n_daily"]
        assert all(np.isfinite(v) for v in b["daily"])
        boot = b["bootstrap"]
        assert boot["n_days"] == b["n_daily"]
        assert boot["n_paths"] == 5000
        assert boot["horizon"] == 365
        assert boot["seed"] == 0
        assert abs(boot["p"] - 1 / 30) < 1e-12
        assert len(boot["ret_quantiles_pct_5_25_50_75_95"]) == 5
        assert len(boot["dd_quantiles_pct_5_25_50_75_95"]) == 5
        for q in boot["ret_quantiles_pct_5_25_50_75_95"]:
            assert np.isfinite(q)
        for pkey in ("p_maxdd_gt_20", "p_return_lt_0", "p_monthly_ge_5pct"):
            assert 0.0 <= boot[pkey] <= 1.0
    # v149 rows
    _check_rows_block(d["v149"]["rows"])
    for gm in d["v149"]["rows"]["ungoverned_0.15"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    assert d["v149"]["feats114_vol_n"] == 26 + 8
    assert d["v149"]["feats103_vol_n"] == 36 + 12
    assert len(d["v149"]["anchors_v114_pvol_xs"]) == 5
    assert len(d["v149"]["anchors_v103_pvol_xs"]) == 5
    for c in ("vol42", "vol180", "vol_ratio", "volz"):
        assert f"xs_{c}" in d["v149"]["feats114_vol"]
        assert f"xr_{c}" in d["v149"]["feats114_vol"]
    for c in ("vol42", "vol180", "vol_ratio", "volz", "rng6", "ntr_z"):
        assert f"xs_{c}" in d["v149"]["feats103_vol"]
        assert f"xr_{c}" in d["v149"]["feats103_vol"]


def test_governor_exec_bootstrap_and_pvol_guards():
    d = _rep()
    for dd, want in [(0.0, 1.0), (0.10, 1.0), (0.15, 0.5), (0.20, 0.0), (0.30, 0.0)]:
        assert abs(float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) - want) < 1e-9
    assert 90 * 6 == 540
    assert (pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(days=1825)) == pd.Timestamp("2026-09-23", tz="UTC")
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["v144"]["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["v144"]["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    assert d["v144"]["n_replaced"]["v114_lo"] > 50000
    src = (AUD / "replicate_v148_v149.py").read_text()
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "D10 = 0.0010" in src or "0.0010" in src
    assert "0.0005" in src and "0.0002" in src
    assert "GOV_WIN = 540" in src
    assert "xs_" in src and "rank(pct=True)" in src
    assert "VOL_XS114" in src and "VOL_XS103" in src
    assert "rng6" in src and "ntr_z" in src
    assert "default_rng(0)" in src
    assert "geometric" in src and "integers" in src
    assert "BOOT_PATHS" in src or "5000" in src
    assert "floor(\"D\")" in src or 'floor("D")' in src or "floor('D')" in src
    assert "v148_result.json" not in src
    assert "v149_result.json" not in src
    assert "v148_robustness_bootstrap" not in src
    assert "v149_xs_vol_forecast" not in src
    assert "import v148" not in src and "import v149" not in src and "import v144" not in src


def test_daily_and_bootstrap_causality_synthetic():
    # daily aggregation: prod(1 + 4h nets of the UTC day) - 1
    idx = pd.DatetimeIndex([
        "2021-09-24 00:00+00:00", "2021-09-24 04:00+00:00",
        "2021-09-24 08:00+00:00", "2021-09-24 12:00+00:00",
        "2021-09-24 16:00+00:00", "2021-09-24 20:00+00:00",
    ])
    nets = np.array([0.001, -0.0005, 0.002, 0.0, 0.001, -0.001])
    s = pd.Series(nets, index=idx)
    daily = (1.0 + s).groupby(s.index.floor("D")).prod() - 1.0
    assert len(daily) == 1
    assert abs(float(daily.iloc[0]) - float(np.prod(1.0 + nets) - 1.0)) < 1e-12
    # xs/xr definition sums to zero / bounded rank
    df = pd.DataFrame({"t": [1, 1, 1, 2, 2, 2], "c": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    df["xr"] = df.groupby("t")["c"].transform(lambda x: x.rank(pct=True))
    assert abs(df[df.t == 1]["xs"].sum()) < 1e-12
    assert ((df["xr"] > 0) & (df["xr"] <= 1.0)).all()
    # stationary bootstrap wrap: (start + k) % n stays in range
    n, horizon = 7, 10
    rng = np.random.default_rng(0)
    pos, total = 0, 0
    while pos < horizon:
        remaining = horizon - pos
        start = int(rng.integers(n))
        blk = min(int(rng.geometric(1 / 30)), remaining)
        for k in range(blk):
            assert 0 <= (start + k) % n < n
            total += 1
        pos += blk
    assert total == horizon
    # monthly conversion used for P((1+ret)^(1/12)-1 >= 0.05)
    assert abs((1.0 + 0.795856) ** (1.0 / 12.0) - 1.0 - 0.05) < 1e-4
    d = _rep()
    assert np.isfinite(d["v149"]["rows"]["gated_0.25"]["monthly_pct"])
