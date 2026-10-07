"""Tests for oc_utamargin: ONE Bybit UTA running G2 + frozen carry overlay.

Fast checks only (no rebuild): file presence, cut discipline, frozen carry
identity, v421 equity identity, recon quality, margin-math consistency,
tier snapshot, JSON/REPORT consistency, no-1m rule.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_utamargin"
CASH = ROOT / "research/tournament/oc_cashcarry"
KPI = ROOT / "research/tournament" / "oc_kpi_g2"
CUT = pd.Timestamp("2026-09-24", tz="UTC")


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("analyze_utamargin.py", "results.json", "REPORT.md"):
        assert (W / f).exists(), f


def test_no_data_at_or_after_cut():
    r = _res()
    g0, g1, n = r["meta"]["grid"]
    assert pd.Timestamp(g1, tz="UTC") < CUT
    assert r["meta"]["cut"].startswith("2026-09-24")
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(ev["t"], utc=True).max() < CUT
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(bs["t"], utc=True).max() < CUT
    for m in r["worst_G2_minutes"]:
        assert pd.Timestamp(m["t"], tz="UTC") < CUT
    assert r["per_f"]["0.25"]["worst_hour"] < "2026-09-24"


def test_no_1m():
    src = (W / "analyze_utamargin.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_carry_frozen_from_oc_cashcarry():
    r = _res()
    cash = json.loads((CASH / "results.json").read_text())
    assert cash["n_trades"] == 33
    assert "33 entered" in r["meta"]["carry_src"]
    for t in cash["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
    # sizing convention stated, legs held to delivery (no early exits modelled)
    assert "held to delivery" in r["meta"]["carry_sizing"]


def test_v421_equity_identity():
    import pickle

    import numpy as np
    pkl = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421"
                        / "v421_runs.pkl").read_bytes())
    for s in range(4):
        v = pkl[s]["R2B1D17BFG2"]
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")["equity"].to_numpy(float)
        assert len(v["eq"]) == len(bs) == 10944
        assert np.allclose(v["eq"], bs)
    assert _res()["meta"]["v421_equity_identical_to_barsum"] is True


def test_recon_quality():
    r = _res()
    for s, rc in r["meta"]["recon_vs_barsum"].items():
        assert rc["median_abs_diff"] <= 0.005, (s, rc)
        assert rc["max_abs_diff"] <= 1.0, (s, rc)


def test_margin_math_consistent():
    r = _res()
    for f in ("0.25", "0.5"):
        v = r["per_f"][f]
        assert v["n_hours"] == 43805
        # free ratio is exactly 1 - IM/balance
        assert abs(v["min_free_ratio"] - (1 - v["max_IM_over_balance"])) < 1e-3
        assert v["n_mm_breach_hours"] == 0
        assert v["max_MM_over_balance"] < 0.05
        g = v["gap10_at_worst"]
        assert g["liquidated"] is False
        assert 0 < g["loss_pct_of_balance"] < 100
    a = r["per_f"]["0.25"]
    assert a["n_blocked_hours"] == 0
    assert a["max_IM_over_balance"] < 0.95
    b = r["per_f"]["0.5"]
    assert b["n_blocked_hours"] == 1
    assert b["max_IM_over_balance"] > 0.95
    assert b["skip"]["blocked_list"] == ["2025-09-25 18:00:00+00:00"]
    # the single blocked hour contains exits only — no new opens to skip
    kinds = b["skip"]["by_kind"]
    assert set(kinds) <= {"rung_tp", "rung_timeout"}, kinds
    assert "rung_fill" not in kinds and "book_fill" not in kinds
    # f=0.5 structurally needs USDT borrowing for the spot legs
    assert b["min_cash_headroom_frac"] < 0
    assert a["min_cash_headroom_frac"] > 0


def test_tiers_snapshot():
    r = _res()
    t = r["tiers"]
    assert r["meta"]["tier_fetch_date"] == "2026-10-06"
    assert t["BTCUSDT"][0]["limit"] == 300000.0
    assert abs(t["BTCUSDT"][0]["mmr"] - 0.0033) < 1e-9
    assert t["ETHUSDT"][0]["limit"] == 300000.0
    assert t["SOLUSDT"][0] == {"limit": 50000.0, "mmr": 0.005,
                               "deduct": 0.0, "maxLev": t["SOLUSDT"][0]["maxLev"]}
    # tier limits strictly increase within each symbol
    for s, rows in t.items():
        lims = [x["limit"] for x in rows]
        assert lims == sorted(lims) and len(lims) >= 2, s


def test_worst_minutes_clean():
    r = _res()
    assert len(r["worst_G2_minutes"]) == 10
    for m in r["worst_G2_minutes"]:
        for f in ("0.25", "0.5"):
            assert m[f"f{f}_gap10_liquidated"] is False
            assert m[f"f{f}_mm_breach"] is False
            assert 0 < m[f"f{f}_gap10_loss_pct_bal"] < 100


def test_report_consistent():
    rep = (W / "REPORT.md").read_text(encoding="utf-8")
    r = _res()
    assert "ADDITIVE OK at f = 0.25" in rep
    assert "SPLIT CAPITAL ONLY" in rep
    for f in ("0.25", "0.5"):
        v = r["per_f"][f]
        assert str(v["n_blocked_hours"]) in rep
        assert f'{v["max_IM_over_balance"] * 100:.2f}' in rep
        assert v["worst_hour"][:10] in rep
    assert "300,000" in rep and "0.33%" in rep
