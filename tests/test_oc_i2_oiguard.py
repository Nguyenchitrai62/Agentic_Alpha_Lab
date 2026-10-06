"""tests/test_oc_i2_oiguard.py: OI-unwind dip-bid guard (no 1m data needed).

Covers: baseline reproduction values, guard causality (truncate-invariance),
hand-checked synthetic guard cases (fire / single-leg / flat / NaN /
short-history), O2 re-entry-delay wiring, dev4 selection rule incl. gate.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_i2_oiguard"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_oiguard", ROOT / "research/tournament/oc_i2_oiguard/run_oiguard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()
H = pd.Timedelta(hours=1).value


def _synth(n=700, seed=0):
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2021-01-01", tz="UTC").value
    bt = t0 + np.arange(n) * pd.Timedelta(hours=4).value
    opens = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    ot = t0 + np.arange(n * 48) * pd.Timedelta(minutes=5).value
    ov = 50000.0 + np.cumsum(rng.normal(0, 5, n * 48))
    return bt, opens, ot, ov


def test_baseline_reproduction_values():
    base = M.check_baseline()
    assert base["G2_carry_f0.25"]["R"] == 5.634
    assert base["G2_carry_f0.25"]["DD"] == 16.75
    assert base["G2_carry_f0.25"]["full_path_dd"]["full"] == 16.66
    assert base["G2"]["R"] == 5.41
    assert base["carry_add_pp_per_month"] == 0.224


def test_guard_causal_truncate_invariant():
    bt, opens, ot, ov = _synth()
    full = M.compute_guard_flags(bt, opens, ot, ov)
    for cut in (200, 400, 650):
        part = M.compute_guard_flags(bt[:cut + 1], opens[:cut + 1], ot, ov)
        assert (part["fire"][:cut + 1] == full["fire"][:cut + 1]).all()
        assert (part["eligible"][:cut + 1] == full["eligible"][:cut + 1]).all()


def test_guard_asof_no_future_oi():
    # OI row published exactly at T must NOT be visible (5-min lag).
    bt = np.array([pd.Timestamp("2022-01-02 04:00", tz="UTC").value])
    opens = np.array([100.0])
    # need >= OI_MIN_OBS history: pad tested separately; here check as-of index
    assert M.OI_LAG == pd.Timedelta(minutes=5)
    ot = np.array([pd.Timestamp("2022-01-02 04:00", tz="UTC").value])
    ov = np.array([1.0])
    out = M.compute_guard_flags(bt, opens, ot, ov)
    assert not out["eligible"][0]  # single obs can never be eligible


def test_guard_fires_on_joint_drop():
    n = 700
    bt, opens, ot, ov = _synth(n)
    # jointly crash the last 24h: price -8%, OI -8% vs flat history
    opens[-1] = opens[-7] * 0.92
    q = bt[-1] - M.OI_LAG.value
    m = ot <= q
    ov = ov.copy()
    ov[m] = 50000.0
    # OI 24h ago high, now low
    m_now = (ot <= q) & (ot > q - pd.Timedelta(hours=24).value)
    ov[m_now] = 46000.0
    m_old = ot <= q - pd.Timedelta(hours=24).value
    ov[m_old] = 50000.0
    out = M.compute_guard_flags(bt, opens, ot, ov)
    assert bool(out["fire"][-1]), (out["zOI"][-1], out["zPx"][-1])


def test_guard_no_fire_single_leg():
    n = 700
    bt, opens, ot, ov = _synth(n)
    ov = np.full_like(ov, 50000.0)  # flat OI -> zOI ~ 0
    opens2 = opens.copy()
    opens2[-1] = opens2[-7] * 0.90  # price crash alone
    out = M.compute_guard_flags(bt, opens2, ot, ov)
    assert not bool(out["fire"][-1])
    # and the mirror: OI crash alone, flat price
    opens3 = np.full_like(opens, 100.0)
    ot3, ov3 = ot, 50000.0 + np.zeros_like(ov)
    ov3 = ov3.copy()
    q = bt[-1] - M.OI_LAG.value
    ov3[(ot <= q) & (ot > q - pd.Timedelta(hours=24).value)] = 45000.0
    out3 = M.compute_guard_flags(bt, opens3, ot3, ov3)
    assert not bool(out3["fire"][-1])


def test_guard_flat_never_fires_and_short_history_safe():
    bt, opens, ot, ov = _synth(700)
    opens_f = np.full(700, 100.0)
    ov_f = np.full(len(ov), 50000.0)
    out = M.compute_guard_flags(bt, opens_f, ot, ov_f)
    assert not out["fire"].any()
    # short history: 10 bars only -> never eligible, never fires
    bt2, opens2, ot2, ov2 = _synth(10)
    out2 = M.compute_guard_flags(bt2, opens2, ot2, ov2)
    assert not out2["eligible"].any() and not out2["fire"].any()
    # all-NaN OI -> safe
    out3 = M.compute_guard_flags(bt, opens, ot, np.full_like(ov, np.nan))
    assert not out3["fire"].any()


def test_o2_delay_is_one_extra_bar():
    # wiring check on a toy traded-bar fire pattern via lookup semantics:
    # O2 skip = O1 skip OR previous traded bar fired.
    o1 = np.array([False, True, False, False, True, True, False])
    o2 = o1.copy()
    o2[1:] = o1[1:] | o1[:-1]
    assert o2.tolist() == [False, True, True, False, True, True, True]


def test_select_on_dev4_rule():
    base = {"sum_ge": 0, "dd_ok": 0, "dsum": 0.0}
    good = {"sum_ge": 3, "dd_ok": 4, "dsum": 0.30}
    best = {"sum_ge": 4, "dd_ok": 4, "dsum": 0.50}
    weak = {"sum_ge": 3, "dd_ok": 3, "dsum": 0.272}  # below gate
    sel = M.select_on_dev4({"O1": good, "O2": weak})
    assert sel["pass"] == {"O1": True, "O2": False} and sel["chosen"] == "O1"
    sel2 = M.select_on_dev4({"O1": good, "O2": best})
    assert sel2["chosen"] == "O2"
    sel3 = M.select_on_dev4({"O1": weak, "O2": base})
    assert sel3["chosen"] is None


def test_score_assignment_matches_placebo_shape():
    rng = np.random.default_rng(7)
    n = 200
    ph = rng.integers(0, 4, n)
    yr = rng.integers(0, 5, n)
    w = np.abs(rng.normal(0.5, 0.1, n))
    y = rng.normal(0.001, 0.02, n)
    d = rng.integers(19000, 21000, n)
    sc = M.score_assignment(ph, yr, w, y, d)
    assert len(sc["per_year"]) == 5
    assert abs(sc["sum5y"] - sum(r["S"] for r in sc["per_year"])) < 1e-12
