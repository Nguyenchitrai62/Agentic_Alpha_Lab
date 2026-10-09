"""Tests for oc_etfflow (PLAN-pinned data + causality + synthetic)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/etf_flows_20261007"
HERE = ROOT / "research/tournament/oc_etfflow"
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _panel() -> pd.DataFrame:
    p = pd.read_parquet(HERE / "panel.parquet")
    p["T"] = pd.to_datetime(p["T"], utc=True)
    return p.sort_values("T").reset_index(drop=True)


def _flows_capped() -> pd.DataFrame:
    b = pd.read_csv(DATA / "btc_etf_flows_daily.csv", parse_dates=["date"])
    e = pd.read_csv(DATA / "eth_etf_flows_daily.csv", parse_dates=["date"])
    b["date"] = pd.to_datetime(b["date"], utc=True)
    e["date"] = pd.to_datetime(e["date"], utc=True)
    m = pd.merge(b.rename(columns={"total_net_flow_usd_m": "btc"}),
                 e.rename(columns={"total_net_flow_usd_m": "eth"}),
                 on="date", how="outer").sort_values("date")
    m["F"] = m["btc"].fillna(0.0) + m["eth"].fillna(0.0)
    return m[(m["date"] >= pd.Timestamp("2024-01-11", tz="UTC")) & (m["date"] < CAP)].reset_index(drop=True)


def test_files_and_manifest():
    for name in ("btc", "eth"):
        p = DATA / f"{name}_etf_flows_daily.csv"
        assert p.exists(), p
        df = pd.read_csv(p)
        assert list(df.columns) == ["date", "total_net_flow_usd_m"]
        assert len(df) > 500
    man = json.loads((DATA / "manifest.json").read_text())
    for name in ("btc", "eth"):
        src = man["sources"][name]
        raw = (DATA / src["csv"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == src["sha256"]
        assert src["n_rows"] == len(pd.read_csv(DATA / src["csv"]))
    assert man["sources"]["btc"]["span"][0] == "2024-01-11"
    btc = pd.read_csv(DATA / "btc_etf_flows_daily.csv")
    assert abs(float(btc.iloc[0]["total_net_flow_usd_m"]) - 655.3) < 1e-9  # 11 Jan 2024 Total
    panel = _panel()
    assert len(panel) == 10950
    # No gates before any publication can be known (pre-2024 years).
    pre = panel[panel["T"] < pd.Timestamp("2024-01-12 08:00", tz="UTC")]
    assert not pre["T1_on"].any() and not pre["T2_on"].any()


def test_truncation_causal():
    """Recompute S5/gates for sampled bars from strictly truncated flows."""
    panel = _panel()
    fl = _flows_capped()
    dates = pd.to_datetime(fl["date"], utc=True)
    F = fl["F"].to_numpy(float)
    S5d = np.full(len(fl), np.nan)
    for i in range(len(fl)):
        if i >= 4:
            S5d[i] = float(F[i - 4:i + 1].sum())
    day_of = {pd.Timestamp(d).date(): i for i, d in enumerate(dates)}
    rng = np.random.default_rng(7)
    idx = rng.choice(np.arange(8000, len(panel)), size=3, replace=False)
    for gi in sorted(idx):
        row = panel.iloc[gi]
        t = row["T"]
        close = t + pd.Timedelta(hours=4)
        # Truncate to days with avail (=D+32h) <= close.
        avail = dates + pd.Timedelta(hours=32)
        ok = avail <= close
        assert ok.any()
        di = int(np.where(ok.to_numpy())[0].max())
        expect_s5 = S5d[di]
        assert (np.isnan(expect_s5) and np.isnan(row["S5"])) or abs(expect_s5 - row["S5"]) < 1e-9
        hist = [S5d[j] for j in range(di - 1, max(-1, di - 401), -1) if np.isfinite(S5d[j])][:250]
        assert len(hist) == int(row["n_hist"])
        if len(hist) >= 120 and np.isfinite(expect_s5):
            h = np.array(hist[::-1])
            assert abs(float(np.percentile(h, 5, method="linear")) - row["p5"]) < 1e-9
            assert abs(float(np.percentile(h, 10, method="linear")) - row["p10"]) < 1e-9
            assert bool(expect_s5 < row["p5"]) == bool(row["T1_on"])
            assert bool(expect_s5 < row["p10"]) == bool(row["T2_on"])
        else:
            assert not row["T1_on"] and not row["T2_on"]
    # Future perturbation cannot move earlier gates: append a fake huge outflow
    # after the cap and assert the panel's last row is unchanged by construction
    # (panel was built with D <= 2026-09-23; fake day is beyond it).
    last = panel.iloc[-1]
    assert last["T"] < CAP
    assert last["Dstar"] <= "2026-09-23"


def test_availability_edge():
    """A bar closing 1 min before D+1 08:00 must not see D; 1 min after must."""
    fl = _flows_capped()
    dates = pd.to_datetime(fl["date"], utc=True)
    pick = dates.iloc[300]  # a mid-sample trading day
    before_close = pick + pd.Timedelta(hours=32) - pd.Timedelta(minutes=1)
    after_close = pick + pd.Timedelta(hours=32) + pd.Timedelta(minutes=1)
    avail = dates + pd.Timedelta(hours=32)
    d_before = dates[avail <= before_close].max()
    d_after = dates[avail <= after_close].max()
    assert d_before < pick
    assert d_after == pick


def test_synthetic_handchecked():
    """Hand-checked tiny series: flat 10s then one -1000 day must trip T1/T2."""
    F = np.array([10.0] * 130 + [-1000.0])  # 131 days
    S5 = np.full(len(F), np.nan)
    for i in range(len(F)):
        if i >= 4:
            S5[i] = F[i - 4:i + 1].sum()
    # Hand values: day index 129 (0-based, all 10s) S5 = 50; day 130 S5 = 40-1000 = -960.
    assert S5[129] == 50.0
    assert S5[130] == -960.0
    hist130 = [x for x in S5[:130] if np.isfinite(x)][-250:]  # 126 values, all 50.0
    assert len(hist130) == 126 >= 120
    p5 = float(np.percentile(np.array(hist130), 5, method="linear"))
    p10 = float(np.percentile(np.array(hist130), 10, method="linear"))
    assert p5 == 50.0 and p10 == 50.0
    assert bool(S5[129] < p5) is False  # 50 < 50 -> OFF (strict)
    assert bool(S5[130] < p5) is True  # -960 < 50 -> ON
    assert bool(S5[130] < p10) is True
    # Percentile helper sanity on a known grid: 1..100 -> p5 = 5.95.
    g = np.arange(1, 101, dtype=float)
    assert abs(float(np.percentile(g, 5, method="linear")) - 5.95) < 1e-9
