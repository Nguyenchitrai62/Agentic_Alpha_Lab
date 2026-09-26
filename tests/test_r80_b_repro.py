"""R80 Track-B: derived-table fix + bounded vintage-repro vs stored reference.

1. R79 derived tables casually label the fold-0 asof-None bundle eligible
   (artifacts/research/opencode_r79/b_eligible_intervals.json fold-0 row:
   eligible_bundle_for_causal_eval with calibrator "(asof None)"). Fold-0
   calibrator asof=None (eligible_rows 0, latest_label_end None in all three
   frozen calibrator docs) must be WITHHELD for causal eval; UNKNOWNs preserved.
   FAIL-BEFORE: r80 fixed table absent / fold-0 row still claims eligible with
   a None asof.

2. Bounded repro on ALREADY-OPENED anchors only (W2 decision rows [2450,2485),
   fold-2 test positions [166,201) via pinned mapping decision_row - 2284):
   CORRECT per-fold (fold-2) checkpoint rerun + fold-2-era calibrator raw output
   compared against the ACTUAL stored historical reference
   (artifacts/research/swing_v15_continuous_20260905/training/seed{1729,1730,
   1731}/temporal_neural/fold_2/predictions.npy + signals.parquet, and the
   published confirmed_dd_guard anchors at rows 2457/2477), not only
   fold2-vs-fold10. Unexplained residual differences are reported honestly.
   Reproduction, not holdout performance. No new fit, no new interval.

FAIL-BEFORE: artifacts/research/opencode_r80/b_repro_vs_stored.json and
b_eligible_intervals.json absent. PASS-AFTER: present with required fields and
honest residual classification.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

R80 = ROOT / "artifacts/research/opencode_r80"


def test_r80_eligible_intervals_withhold_fold0():
    p = R80 / "b_eligible_intervals.json"
    assert p.exists(), "r80 fixed eligible-intervals table missing"
    doc = json.loads(p.read_text(encoding="utf-8"))
    rows = {r["fold"]: r for r in doc["per_fold_table"]}
    f0 = rows[0]
    blob = json.dumps(f0)
    assert "WITHHELD" in blob, f0
    assert "UNKNOWN" in blob, "UNKNOWNs must be preserved, not invented"
    assert "(asof None)" not in blob.replace("WITHHELD", ""), f0
    # No fold may claim an eligible bundle while its calibrator asof is None.
    for k, r in rows.items():
        if '"asof": null' in json.dumps(r) or "'asof': None" in repr(r):
            assert "WITHHELD" in json.dumps(r), (k, r)
    assert doc["no_profitability_promotion"] is True


def test_r80_repro_vs_stored_present_and_bounded():
    p = R80 / "b_repro_vs_stored.json"
    assert p.exists(), "r80 repro-vs-stored artifact missing"
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["anchor_rows"] == [2450, 2485]
    assert doc["reference_fold"] == 2
    assert doc["mapping"] == "stored_test_position = decision_row - 2284"
    # Mapping pinned by the stored fold-2 signals' first bar.
    assert doc["mapping_proof"]["first_test_bar"] == 201312
    assert doc["mapping_proof"]["first_test_decision_row"] == 2284
    for seed in ("1729", "1730", "1731"):
        per = doc["per_seed_vs_stored"][seed]
        for key in ("stored_path", "stored_sha256", "dmax", "mean_abs",
                    "n_compared"):
            assert key in per, (seed, per)
        assert per["n_compared"] == 35
        assert per["dmax"] >= 0.0
    assert doc["residual_class"] in ("EXPLAINED", "UNEXPLAINED", "MIXED")
    assert doc["stored_reference_note"]
    assert doc["label"] == "vintage-repro"


def test_r80_repro_published_anchors_compared():
    doc = json.loads((R80 / "b_repro_vs_stored.json").read_text(
        encoding="utf-8"))
    anchors = {a["decision_row"]: a for a in doc["published_anchor_check"]}
    assert set(anchors) == {2457, 2477}
    for row, a in anchors.items():
        assert a["published_action"] == "SHORT", (row, a)
        assert "stageB_action" in a and "match" in a


def test_stored_fold0_calibrator_unknown_preserved():
    """Pinned provenance: fold-0 calibrator records carry no asof/labels.

    The stored fold-0 records are warmup-WAIT stubs (0 eligible rows, no asof,
    no latest_label_end, no x/y map) — availability UNKNOWN, never eligible.
    """
    for name in ("isotonic_2", "isotonic_4", "isotonic_all"):
        doc = json.loads((
            ROOT / f"artifacts/research/opencode_v02_reproduce_v30/{name}/"
            "calibrators.json").read_text(encoding="utf-8"))
        rec0 = next(r for r in doc if r["fold"] == 0)
        assert rec0.get("asof") is None, (name, rec0)
        assert rec0.get("latest_label_end") is None, (name, rec0)
        assert rec0["eligible_rows"] == 0
        assert rec0["warmup"] == "WAIT"


def test_attestation_current_and_honest():
    p = R80 / "b_current_attestation.json"
    assert p.exists(), "r80 current attestation missing"
    doc = json.loads(p.read_text(encoding="utf-8"))
    observed = pd.Timestamp(doc["observed_at"])
    assert observed.tzinfo is not None, "observed_at must carry timezone"
    # CURRENT attestation: observed at this run (2026-09), NEVER 2025-12-01.
    assert observed >= pd.Timestamp("2026-09-01T00:00:00Z"), doc["observed_at"]
    assert not doc["observed_at"].startswith("2025-12-01"), \
        "attestation must never be backdated to 2025-12-01"
    assert doc["authorizes_trading"] is False
    assert doc["authorizes_past_claims"] is False
    for key in ("checkpoints", "calibrators", "configs", "sources"):
        assert doc["asset_sha256"][key], key
    folds = doc["fit_calibration_ranges"]
    assert len(folds) == 11
    assert folds[0]["calibrators"]["isotonic_4"]["asof"] == "UNKNOWN"
    assert folds[0]["causal_eligibility"] == "WITHHELD"
    assert doc["no_profitability_promotion"] is True


def test_w2_anchor_inside_fold2_window():
    dec = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/decisions.parquet")
    anchor = dec.iloc[2450:2485]
    assert (anchor["bar_index"] >= 201312).all()
    assert (anchor["bar_index"] < 227000).all()
