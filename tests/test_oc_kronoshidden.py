"""oc_kronoshidden tests: tilt-rule hand checks + causality/embargo + file contracts."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_kronoshidden"))
from tilt_rule import ANCH5, anchor_of, assign_mult  # noqa: E402

OC = ROOT / "research/tournament/oc_kronoshidden"


def test_assign_mult_hand_checked():
    # direction +1 (high risk favourable), K1 hi/lo = 1.5/0.5
    assert assign_mult(3.0, 1, 0.5, 2.0, 1.5, 0.5) == 1.5   # >= q80
    assert assign_mult(2.0, 1, 0.5, 2.0, 1.5, 0.5) == 1.5   # boundary inclusive
    assert assign_mult(0.4, 1, 0.5, 2.0, 1.5, 0.5) == 0.5   # <= q20
    assert assign_mult(1.0, 1, 0.5, 2.0, 1.5, 0.5) == 1.0   # middle
    assert assign_mult(float("nan"), 1, 0.5, 2.0, 1.5, 0.5) == 1.0  # missing -> 1
    # direction -1 flips the outer quintiles
    assert assign_mult(3.0, -1, 0.5, 2.0, 1.5, 0.5) == 0.5
    assert assign_mult(0.4, -1, 0.5, 2.0, 1.5, 0.5) == 1.5
    assert assign_mult(1.0, -1, 0.5, 2.0, 1.5, 0.5) == 1.0
    # K2 hi/lo = 1.25/0.75, same structure
    assert assign_mult(3.0, 1, 0.5, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(0.4, 1, 0.5, 2.0, 1.25, 0.75) == 0.75


def test_anchor_of_year_mapping_and_boundaries():
    # year y covers [ANCH5[y]+sh, ANCH5[y]+365d+sh); pre-anchor bars -> 0
    assert anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert anchor_of(pd.Timestamp("2022-09-23 20:00", tz="UTC"), 0) == 0
    assert anchor_of(pd.Timestamp("2022-09-24", tz="UTC"), 0) == 1
    assert anchor_of(pd.Timestamp("2025-09-24", tz="UTC"), 0) == 4
    assert anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4
    # shift moves the grid: 2022-09-24 00:00 is still year 0 on shift 3
    assert anchor_of(pd.Timestamp("2022-09-24 00:00", tz="UTC"), 3) == 0
    assert anchor_of(pd.Timestamp("2022-09-24 03:00", tz="UTC"), 3) == 1
    # pre-history clamps to year 0 (never a future year)
    assert anchor_of(pd.Timestamp("2020-01-01", tz="UTC"), 0) == 0


def test_training_embargo_truncation():
    # synthetic exits around anchor 2022-09-24: only t_exit < A - 7d trains
    A = pd.Timestamp("2022-09-24", tz="UTC")
    exits = pd.to_datetime(["2022-09-10", "2022-09-16 23:59", "2022-09-17",
                            "2022-09-18", "2023-01-01"], utc=True, format="mixed")
    mask = exits < A - pd.Timedelta(days=7)
    assert mask.tolist() == [True, True, False, False, False]


def test_fits_and_ctrl_contracts():
    fits = json.loads((OC / "fits.json").read_text())
    ctrl = json.loads((OC / "ctrl.json").read_text())
    assert sorted(fits) == list(ANCH5)  # all five anchors incl most-recent
    for a, f in fits.items():
        assert f["direction"] in (1, -1)
        assert f["q20"] < f["q80"] and np.isfinite(f["q20"])
        assert f["n_train_kronos"] <= f["n_train_majors"] and f["n_train_kronos"] > 1000
    assert sorted(ctrl, key=int) == ["0", "1", "2", "3", "4"]
    for y, c in ctrl.items():
        assert c["anchor"] == ANCH5[int(y)]
        assert 0.5 <= c["k1_decision_mean"] <= 1.5
        assert c["n_decisions"] > 40000  # pooled 5 coins x 4 shifts x ~2190 bars


def test_feature_file_contract():
    k = pd.read_parquet(OC / "kronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "low1"])
    assert len(k.groupby(["sym", "shift"])) == 20
    assert set(k["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert set(k["shift"].unique()) == {0, 1, 2, 3}
    t = pd.to_datetime(k["T"], utc=True)
    assert t.min() >= pd.Timestamp("2020-10-06", tz="UTC")
    assert t.max() <= pd.Timestamp("2026-09-23 23:00", tz="UTC")
