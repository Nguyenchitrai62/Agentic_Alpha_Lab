"""oc_rearm tests: re-arm search + G=2.0 cap walk + B1/D0 spot checks (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_rearm"
sys.path.insert(0, str(OC))
import rearm as R

sys.path.insert(0, str(OC))
import run_rearm as RR


def test_refill_strict_and_start_bound():
    lv = 100.0
    low = np.full(10, 100.0)
    assert R.find_refill(low, lv, 0) is None  # equal is not a trade-through
    low[5] = 99.9
    assert R.find_refill(low, lv, 0) == 5
    assert R.find_refill(low, lv, 6) is None  # search starts after the touch
    assert R.find_refill(low, lv, 10) is None  # start past the window
    assert R.find_refill(low, lv, 99) is None


def test_refill_nan_never_fills():
    lv = 100.0
    low = np.array([np.nan, np.nan, 99.0])
    assert R.find_refill(low, lv, 0) == 2
    assert R.find_refill(np.array([np.nan, np.nan]), lv, 0) is None


def test_rearm_only_after_inside_bar_tp():
    # TP exit inside the bar -> re-arm window open (caller searches from x+1).
    sg, f, px = 0.01, 20, 98.0
    n = 240
    O = np.full(n, px)
    H = np.full(n, px)
    L = np.full(n, px)
    C = np.full(n, px)
    H[30] = px * (1 + sg) + 0.01
    ret, x, how = R.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30 and np.isfinite(ret)
    # A TP at the last live minute leaves no room for a refill.
    H2 = np.full(n, px)
    H2[239] = px * (1 + sg) + 0.01
    _, x2, how2 = R.outcome_from_fill(H2, L, C, O, f, px, sg, 99.0, False)
    assert how2 == "tp"
    assert R.find_refill(np.full(R.LIVE_B - R.LIVE_A + 1, px + 1.0), px, (x2 + 1) - R.LIVE_A) is None


def test_no_rearm_after_stop_or_timeout():
    sg, f, px = 0.01, 20, 98.0
    n = 240
    O = np.full(n, px)
    H = np.full(n, px)
    L = np.full(n, px)
    C = np.full(n, px)
    # stop: close5 touch below sl with no earlier TP
    C[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = R.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "stop"  # run_rearm re-arms only on how == "tp"
    # timeout: flat market drifts to the next-bar open
    _, x, how = R.outcome_from_fill(H, L, np.full(n, px), O, f, px, sg, 99.0, False)
    assert how == "time" and x == 240


def test_size_recomputed_at_refill_minute():
    assert R.size_mult(0) == 1.0
    assert R.size_mult(3) == 0.25
    # flushing count is per-minute: different minutes may give different sizes
    cmat = np.array([[97.5, 99.0], [97.5, 99.0], [100.0, 100.0], [100.0, 100.0]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    nvec = R.n_vector(cmat, oo, ss)
    assert nvec.tolist() == [2, 0]
    assert R.size_mult(int(nvec[0])) != R.size_mult(int(nvec[1]))


def test_cap_cut_to_room_and_skip():
    # G=2.0: two open fills of 1.0 leave no room for a third while open.
    f = [10, 11, 12]
    x = [200, 200, 200]
    w = [1.0, 1.0, 1.0]
    kept = R.gross_cap_weights(f, x, w, [0, 1, 2], G=2.0)
    assert kept == {0: 1.0, 1: 1.0, 2: 0.0}
    # A fill after the first two closed gets full room again.
    kept = R.gross_cap_weights([10, 11, 201], [200, 200, 239], [1.0, 1.0, 1.0], [0, 1, 2], G=2.0)
    assert kept == {0: 1.0, 1: 1.0, 2: 1.0}
    # Partial cut to the room left.
    kept = R.gross_cap_weights([10, 11], [200, 200], [1.5, 1.0], [0, 1], G=2.0)
    assert kept[0] == 1.5 and abs(kept[1] - 0.5) < 1e-12


def test_cap_parent_skip_drops_rearm():
    # Base fill skipped (no room) -> its re-armed child is dropped too.
    f = [10, 11, 12, 30]
    x = [200, 200, 200, 200]
    w = [1.0, 1.0, 1.0, 0.5]
    parent = [-1, -1, -1, 2]  # child of the third base fill
    kept = R.gross_cap_weights(f, x, w, [0, 1, 2, 3], G=2.0, parent=parent)
    assert kept[2] == 0.0 and kept[3] == 0.0
    # Same but with room: parent kept -> child kept.
    kept = R.gross_cap_weights([10, 50], [200, 200], [1.0, 0.5], [0, 1], G=2.0, parent=[-1, 0])
    assert kept == {0: 1.0, 1: 0.5}


def test_daily_path_helpers():
    S, Wd, DD, nd = RR.daily_path([("2022-01-01", 1.0), ("2022-01-01", -0.5), ("2022-01-02", -1.0)])
    assert abs(S - (-0.5)) < 1e-12
    assert abs(Wd - (-1.0)) < 1e-12
    assert abs(DD - 1.0) < 1e-12 and nd == 2
    assert RR.daily_path([]) == (0.0, 0.0, 0.0, 0)
    S, _, DD, _ = RR.daily_path([("2022-01-01", 1.0), ("2022-01-02", 2.0)])
    assert DD == 0.0 and S == 3.0
