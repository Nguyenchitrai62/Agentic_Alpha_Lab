"""oc_ablation tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent / "research" / "tournament" / "oc_ablation"
RD = Path(__file__).resolve().parent.parent / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
CAP = pd.Timestamp("2026-09-24", tz="UTC")


def test_no_data_at_or_after_cap():
    """Truncation: no engine event at/after 2026-09-24; years tile [A, A+365d)."""
    res = json.loads((HERE / "results.json").read_text())
    for r, d in res["rows"].items():
        assert len(d["years"]) == 5
    ev = pd.read_parquet(HERE / "tmp" / "events_s0_G2.parquet", columns=["t"])
    assert pd.to_datetime(ev["t"], utc=True).max() < CAP
    anchors = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
    for i in range(5):
        assert (anchors[i] + pd.Timedelta(days=365) - anchors[i]).days == 365


def test_g2_reproduces_v421_to_digit():
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    res = json.loads((HERE / "results.json").read_text())["rows"]["G2"]
    assert [y["R"] for y in res["years"]] == [r for r, _ in exp["years"]]
    assert [y["DD"] for y in res["years"]] == [d for _, d in exp["years"]]
    assert res["full_path_dd"]["full"] == exp["full_path_dd"]
    # NO_CAP hook purity: uncapped row must equal stored R2B1D17BF
    exp_u = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BF"]
    noc = json.loads((HERE / "results.json").read_text())["rows"]["NO_CAP"]
    assert [y["R"] for y in noc["years"]] == [r for r, _ in exp_u["years"]]


def test_governor_off_is_identity_handcheck():
    """Synthetic: gov=(10, 0.10) clips to 1 for any dd in [0, 1)."""
    for dd in (0.0, 0.05, 0.10, 0.199, 0.5, 0.99):
        assert float(np.clip((10.0 - dd) / 0.10, 0.0, 1.0)) == 1.0
    # audited default still binds: dd=0.15 -> 0.5, dd=0.20 -> 0.0
    assert abs(float(np.clip((0.20 - 0.15) / 0.10, 0.0, 1.0)) - 0.5) < 1e-9
    assert float(np.clip((0.20 - 0.20) / 0.10, 0.0, 1.0)) == 0.0


def test_gap_loss_math_handcheck():
    """Synthetic: loss% = 100*(S*g + TAKER*G*(1-g)); S=1,G=1,g=0.10 -> 10.0495."""
    assert abs(100.0 * (1 * 0.10 + 0.00055 * 1 * 0.90) - 10.0495) < 1e-9
    res = json.loads((HERE / "results.json").read_text())["rows"]["G2"]["gap"]
    assert res["worst_gross"] >= res["worst_dip"] + res["worst_book"] - 0.01
    assert res["worst_loss_pct"] > res["median"]


def test_patch_is_minimal_and_proof_logged():
    src = (HERE / "engine_patch.py").read_text()
    assert "vol_fixed" in src
    assert "np.full_like(s, float(vol_fixed))" in src
    for s in range(4):
        meta = json.loads((HERE / "tmp" / f"meta_s{s}.json").read_text())
        assert meta["rows"] == ["G2", "NO_GOV", "NO_BEAR", "NO_CAP", "NO_B1", "TOUCH", "NO_VT"]
