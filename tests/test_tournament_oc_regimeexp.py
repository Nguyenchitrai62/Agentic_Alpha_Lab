"""Causality / reproducibility tests for oc_regimeexp (light, no 1m data)."""
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "research" / "tournament" / "oc_regimeexp" / "compute_regimeexp.py"
KPI = ROOT / "research" / "tournament" / "oc_kpi" / "results_equity.json"
RES = ROOT / "research" / "tournament" / "oc_regimeexp" / "results.json"
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def load_mod():
    spec = importlib.util.spec_from_file_location("oc_regimeexp_mod", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_monthly_table_matches_oc_kpi():
    r = json.loads(RES.read_text())
    k = json.loads(KPI.read_text())
    got = [(m["month"], m["ret"]) for m in r["months"]]
    exp = [(ym, float(p)) for ym, p in k["monthly"]]
    assert got == exp


def test_4h_opens_from_hourly_only():
    m = load_mod()
    b4 = m.load_btc_4h_open()
    h = pd.read_parquet(m.HOURLY, columns=["t", "open", "sym"])
    h = h[h["sym"] == "BTCUSDT"]
    h["t"] = pd.to_datetime(h["t"], utc=True)
    ref = h.set_index("t")["open"]
    sample = b4.sample(20, random_state=1)
    for _, row in sample.iterrows():
        assert float(row["o"]) == float(ref[row["T"]])
    assert b4["T"].max() < CUTOFF


def test_truncate_causality():
    m = load_mod()
    b4 = m.load_btc_4h_open()
    h = pd.read_parquet(m.HOURLY, columns=["t", "open", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].sort_values("t").reset_index(drop=True)
    h["t"] = pd.to_datetime(h["t"], utc=True)
    for ms in ["2022-06-01", "2024-11-01", "2026-08-01"]:
        m0 = pd.Timestamp(ms, tz="UTC")
        full = m.states(b4, h, [m0])[0]
        trunc = m.states(b4, h[h["t"] <= m0], [m0])[0]
        # truncated frame keeps bars t<=m0; states may only use t<m0 (+o(m0));
        # vol uses t<m0 so tail(721) identical; bear/trend from 4h opens
        for k in ("bear", "vol", "trend"):
            assert full[k] == trunc[k], (ms, k)
        assert abs(full["vol30"] - trunc["vol30"]) == 0.0


def test_no_future_timestamp_and_coverage():
    r = json.loads(RES.read_text())
    assert r["meta"]["n_months"] == 61
    assert len(r["months"]) == 61
    n_combo = sum(v["n"] for v in r["combos_n_ge5"].values())
    n_thin = sum(v["n"] for v in r["combos_thin_n_lt5"].values())
    assert n_combo + n_thin == 61
    assert r["current"]["asof_last_data"]["vol_end"] <= str(CUTOFF)
    for v in r["combos_n_ge5"].values():
        assert v["n"] >= 5
    for v in r["combos_thin_n_lt5"].values():
        assert v["n"] < 5
