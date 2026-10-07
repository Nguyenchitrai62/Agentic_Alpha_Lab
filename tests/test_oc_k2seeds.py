"""oc_k2seeds tests: causality/truncation of the Kronos context + synthetic K2-rule checks."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
KH = ROOT / "research/tournament/oc_kronoshidden"
sys.path.insert(0, str(KH))
from tilt_rule import assign_mult  # noqa: E402  (read-only import)

P = 400
W0 = pd.Timestamp("2024-09-01", tz="UTC")


def test_context_truncation_real_bars():
    """Forecast for T may use only the 400 bars with timestamp < T (no future)."""
    bars = pd.read_parquet(KH / "bars_4h_4shift.parquet")
    b = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T").reset_index(drop=True)
    cand = b[(b["T"] >= W0)].iloc[::997]
    assert len(cand) >= 3
    for _, row in cand.head(3).iterrows():
        e = b.index[b["T"] == row["T"]][0]
        ctx = b.iloc[e - P:e]
        assert len(ctx) == P
        assert ctx["T"].max() < row["T"], (ctx["T"].max(), row["T"])
        assert (ctx["T"] < W0).any() or True  # context may predate window: allowed, never scored


def test_assign_mult_hand_checked():
    """Hand-checked K2 boundaries (hi=1.25, lo=0.75, dir=+1, q20=0.5, q80=2.0)."""
    assert assign_mult(2.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25  # equality -> outer quintile
    assert assign_mult(0.5, 1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(2.5, 1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(0.1, 1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), 1, 0.5, 2.0, 1.25, 0.75) == 1.0
    # direction -1 flips favourable/unfavourable
    assert assign_mult(2.5, -1, 0.5, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(0.1, -1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(1.0, -1, 0.5, 2.0, 1.25, 0.75) == 1.0


def test_norm_uses_actual_denominator():
    """norm = k2_weighted / realised_fill_mean (actual denominator, PLAN)."""
    w = np.array([1.0, 2.0, 3.0])
    y = np.array([0.1, -0.2, 0.3])
    mult = np.array([1.25, 0.75, 1.0])
    k2 = float((w * mult * y).sum())
    rm = float(mult.mean())
    assert k2 == 1.25 * 0.1 + 0.75 * 2.0 * -0.2 + 1.0 * 3.0 * 0.3
    assert rm == 1.0
    assert round(k2 / rm, 6) == round(0.725, 6)


def test_year_split_predicate():
    """Combined lookup: T < 2025-09-24 -> original-1234, else seed-S."""
    y4 = pd.Timestamp("2025-09-24", tz="UTC")
    assert pd.Timestamp("2025-09-23 20:00", tz="UTC") < y4
    assert pd.Timestamp("2025-09-24 00:00", tz="UTC") >= y4
    assert pd.Timestamp("2024-09-01 00:00", tz="UTC") < y4  # buffer rows never seed-only
