"""Tests for research/tournament/data_hlfunding (synthetic only, no network).

Covers: 8h-window assignment/summing on hand-checked cases (hourly and mixed
8h/hourly cadence), de-dup on time, causality/truncation (post-cutoff rows
never change pre-cutoff windows), and fetched-artifact schema/manifest
consistency (skipped if the fetch has not been run).
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "research" / "tournament" / "data_hlfunding" / "analyze_hl_vs_binance.py"
DATA = ROOT / "data" / "raw" / "hyperliquid_20261007"


def load_mod():
    spec = importlib.util.spec_from_file_location("hl_vs_binance", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load_mod()
TS = pd.Timestamp


def synth_hourly(start, hours, rate=0.0001, premium=0.0):
    idx = pd.date_range(start=start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"time": idx,
                         "fundingRate": [rate] * hours,
                         "premium": [premium] * hours})


# ------------------------------------------------- hand-checked windowing

def test_two_full_windows_hand_checked():
    df = synth_hourly("2024-01-01 00:00", 16, rate=0.0001)
    out = M.hl_8h(df)
    assert len(out) == 2
    assert out["win"].tolist() == [TS("2024-01-01 00:00", tz="UTC"),
                                   TS("2024-01-01 08:00", tz="UTC")]
    assert out["hl_sum"].tolist() == pytest.approx([0.0008, 0.0008])
    assert out["hl_n"].tolist() == [8, 8]


def test_mixed_cadence_early_8h_row_plus_hourly():
    # one 8h-era row (single value = the 8h rate) then a full hourly window
    early = pd.DataFrame({"time": [TS("2023-05-12 00:00:00.048", tz="UTC")],
                          "fundingRate": [-0.0006133368], "premium": [0.0]})
    late = synth_hourly("2023-06-10 08:00", 8, rate=0.0002)
    out = M.hl_8h(pd.concat([early, late], ignore_index=True))
    assert len(out) == 2
    assert out["hl_sum"].iloc[0] == pytest.approx(-0.0006133368)
    assert out["hl_n"].iloc[0] == 1
    assert out["hl_sum"].iloc[1] == pytest.approx(0.0016)
    # mixed signs sum algebraically, not absolutely
    mix = synth_hourly("2024-03-01 00:00", 8, rate=0.0)
    mix.loc[0, "fundingRate"] = 0.0005
    mix.loc[1, "fundingRate"] = -0.0005
    out2 = M.hl_8h(mix)
    assert out2["hl_sum"].iloc[0] == pytest.approx(0.0)


def test_ms_offsets_stay_in_their_hour_window():
    # venue timestamps carry ms offsets past the hour; flooring must keep them
    df = pd.DataFrame({"time": [TS("2024-01-01 07:59:59.999", tz="UTC"),
                                TS("2024-01-01 08:00:00.001", tz="UTC")],
                       "fundingRate": [1.0, 10.0], "premium": [0.0, 0.0]})
    out = M.hl_8h(df)
    assert len(out) == 2
    assert out["hl_sum"].tolist() == pytest.approx([1.0, 10.0])


# ------------------------------------------------- causality / truncation

def test_post_cutoff_rows_never_change_pre_cutoff_windows():
    df = synth_hourly("2024-01-01 00:00", 72, rate=0.0001)
    base = M.hl_8h(df)
    cut = TS("2024-01-02 00:00", tz="UTC")
    # perturb + shuffle every row at/after the cutoff
    alt = df.copy()
    mask = alt["time"] >= cut
    alt.loc[mask, "fundingRate"] = -0.009
    alt = alt.iloc[::-1].reset_index(drop=True)
    out = M.hl_8h(alt)
    pre = base["win"] < cut
    assert pre.sum() > 0
    pd.testing.assert_frame_equal(base[pre].reset_index(drop=True),
                                  out[out["win"] < cut].reset_index(drop=True))
    assert (base.loc[~pre, "hl_sum"] != out.loc[~pre.values, "hl_sum"]).all()


def test_dedup_on_time_keeps_first():
    df = synth_hourly("2024-01-01 00:00", 8, rate=0.0001)
    dup = pd.concat([df, df.iloc[[3]].assign(fundingRate=0.5)], ignore_index=True)
    dd = dup.sort_values("time").drop_duplicates(subset="time", keep="first")
    out = M.hl_8h(dd.reset_index(drop=True))
    assert out["hl_sum"].iloc[0] == pytest.approx(0.0008)


# ------------------------------------------------- fetched artifacts

def test_fetched_parquet_schema_and_manifest():
    if not DATA.exists():
        pytest.skip("hyperliquid fetch not run")
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["endpoint"] == "https://api.hyperliquid.xyz/info"
    assert manifest["fetch_end_ms"] > manifest["fetch_start_ms"]
    for coin in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
        name = f"HL_{coin}_funding_1h.parquet"
        p = DATA / name
        assert p.exists(), name
        df = pd.read_parquet(p)
        assert df.columns.tolist() == ["time", "fundingRate", "premium"]
        assert str(df["time"].dt.tz) == "UTC"
        assert df["fundingRate"].dtype == "float64" and df["premium"].dtype == "float64"
        assert int(df.isna().sum().sum()) == 0
        assert int(df.duplicated("time").sum()) == 0
        assert bool((df["time"].diff().dropna() > pd.Timedelta(0)).all())
        entry = manifest["files"][name]
        assert entry["rows"] == len(df)
        assert entry["first"] == str(df["time"].iloc[0])
        assert entry["last"] == str(df["time"].iloc[-1])
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert entry["sha256"] == sha
    snaps = sorted(DATA.glob("metaAndAssetCtxs_*.json"))
    assert snaps, "metaAndAssetCtxs snapshot missing"
    assert "metaAndAssetCtxs snapshot" in json.dumps(manifest["files"])


def test_descriptive_csv_columns_and_no_return_statistic():
    csv = ROOT / "research" / "tournament" / "data_hlfunding" / "hl_vs_binance_8h.csv"
    if not csv.exists():
        pytest.skip("analysis not run")
    df = pd.read_csv(csv)
    assert df.columns.tolist() == ["coin", "year", "n", "corr", "spread_mean_bps",
                                   "spread_p90_bps", "opp_sign_share", "opp_n", "sign_n"]
    assert set(df["coin"].unique()) <= {"BTC", "ETH", "SOL", "BNB", "XRP"}
    assert (df["n"] > 0).all() and (df["opp_n"] <= df["sign_n"]).all()
    src = MOD.read_text(encoding="utf-8")
    for banned in ["pct_change", "log_ret", "fwd_ret", "future_return", "premium_1m", "spot", "klines"]:
        assert banned not in src
    # every data file the analysis reads must be a funding file
    import re
    reads = re.findall(r"read_parquet\(([^)]+)\)", src)
    assert reads, "analysis must read funding parquet files"
    assert all("funding" in r for r in reads)
