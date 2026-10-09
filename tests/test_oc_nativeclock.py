"""oc_nativeclock tests: causality/truncation + hand-checked synthetic case (light, no 1m)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE = ROOT / "research/tournament/oc_nativeclock"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bear_filter(std: pd.DataFrame, btc: pd.Series) -> pd.DataFrame:
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    return sb


def test_g2_reproduced_to_the_digit():
    repro = json.loads((HERE / "tmp/g2_repro.json").read_text())
    assert repro["R"] == 5.41 and repro["W"] == 2.588
    assert repro["DD"] == 16.91 and repro["full_path_dd"] == 16.82
    assert [(y["R"], y["DD"]) for y in repro["years"]] == [
        (2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27), (4.648, 12.9)]


def test_forward_fill_causality_no_future_row():
    """Truncation: books ffill'd onto a truncated shifted index equal the head
    of the full-shifted books (ffill never looks ahead)."""
    eu = _load("eu_tnc", RD / "engine_user/engine_user.py")
    fw = _load("fw_tnc", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    std = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    sb = bear_filter(std, opens_std["BTCUSDT"].reindex(books154.index))
    for s in (0, 1, 2, 3):
        idx = books154.index + pd.Timedelta(hours=s)
        full = sb.reindex(idx, method="ffill").fillna(0.0)
        trunc = sb.reindex(idx[: len(idx) - 7], method="ffill").fillna(0.0)
        a, b = full.iloc[: len(trunc)].to_numpy(), trunc.to_numpy()
        assert np.max(np.abs(a - b)) == 0.0, s
        # every decision bar's source row is at or before the bar (causal)
        pos = sb.index.searchsorted(idx, side="right") - 1
        assert (pos >= 0).all() and (sb.index[pos.clip(0, len(sb) - 1)] <= idx).all()


def test_hand_checked_synthetic_bear_and_ffill():
    """Hand-checked: bear x0.5 halves longs only; ffill carries the last row."""
    t = pd.date_range("2022-01-01", periods=1300, freq="4h", tz="UTC")
    std = pd.DataFrame({"BTCUSDT": 1.0, "ETHUSDT": -2.0}, index=t)
    btc = pd.Series(np.arange(1300, dtype=float), index=t)
    sb = bear_filter(std, btc)
    # first 600 bars: rolling mean NaN -> bear False -> unchanged
    assert float(sb["BTCUSDT"].iloc[0]) == 1.0
    # last bar: value (1299) above its trailing mean -> not bear -> unchanged
    assert float(sb["BTCUSDT"].iloc[-1]) == 1.0
    # force a bear bar: falling series tail
    btc2 = pd.Series(np.concatenate([np.full(1200, 100.0), np.linspace(100, 50, 100)]), index=t)
    sb2 = bear_filter(std, btc2)
    assert float(sb2["BTCUSDT"].iloc[-1]) == 0.5  # long halved
    assert float(sb2["ETHUSDT"].iloc[-1]) == -2.0  # short kept
    # ffill on a shifted grid carries the latest standard row (stale, never future)
    idx = t + pd.Timedelta(hours=2)
    f = sb2.reindex(idx, method="ffill")
    assert float(f["BTCUSDT"].iloc[0]) == float(sb2["BTCUSDT"].iloc[0])
    assert (f.index == idx).all()


def test_native_equals_ref_and_phase0_unchanged():
    chk = json.loads((HERE / "tmp/native_books_check.json").read_text())
    for s in ("0", "1", "2", "3"):
        assert chk["shifts"][s]["max_abs_diff_native_vs_ref"] == 0.0
        assert chk["shifts"][s]["phase0_unchanged"] is True
    audit = json.loads((HERE / "tmp/member_audit.json").read_text())
    assert set(audit["members"]) == {"A", "Aq", "B", "Bq", "D", "Dq"}
    assert all(v["verdict"].startswith("FORWARD-FILL") for v in audit["members"].values())
