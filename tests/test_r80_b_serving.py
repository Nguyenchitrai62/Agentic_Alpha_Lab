"""R80 Track-B: serving-boundary enforcement (FAIL-BEFORE required).

The strict guard must run at the REAL causal evaluation/serving boundary
(scripts/opencode_r76_infer.py, frozen fold-10 serving), not only the
standalone --claim tool. Frozen serving with a future-vintage model/calibrator
bundle must label old decisions REJECTED for causal evaluation
(evaluation_label "integration-only"); only decisions at/after the bundle's
availability may be ELIGIBLE (prospective observation only, no profit claim).

Mechanical-fixture transparency (declared, never silent):
- test_frozen_bundle_provenance_pinned: reads pinned artifacts only
  (configs/opencode_r76_infer.json + v29 fold-10 metadata.json + frozen
  calibrator docs). No model load, no inference.
- test_serving_annotation_on_real_slice: REAL frozen checkpoint inference
  (local, CPU) on an already-opened dev slice (first 40000 candles, decisions
  in 2022 << fold-10 vintage 2025-12-01). Reuses cached feature work; reruns
  the model as required. All rows must be REJECTED/integration-only. This is
  reproduction of the serving boundary, not holdout performance.
- Existing fixtures that inject raw rows directly (bypassing infer_full /
  infer_decisions) are unaffected: this change only ADDS annotation keys.

These tests FAIL before the r76_infer guard call-site wiring (missing keys /
AttributeError) and PASS after.
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r76_infer as r76  # noqa: E402

FOLD10_FIT = "2025-11-30T19:04:59.999000+00:00"
FOLD10_CAL = "2025-12-01T00:00:00+00:00"


def test_frozen_bundle_provenance_pinned():
    """Fold-10 bundle availability resolved from pinned artifact provenance."""
    prov = r76.frozen_bundle_vintage()
    assert prov["model_fit_available"] == FOLD10_FIT, prov
    # Calibrator asof preserved verbatim from pinned provenance; compare
    # normalized instants, not string spellings ("Z" vs "+00:00").
    assert pd.Timestamp(prov["calibrator_asof"]) == pd.Timestamp(FOLD10_CAL)
    assert "sources" in prov and prov["sources"]["model_fit_available"]
    assert prov["sources"]["calibrator_asof"]
    # UNKNOWN-heavy bundle must fail closed, never silently eligible.
    assert "UNKNOWN" not in (prov["model_fit_available"],
                             prov["calibrator_asof"])


def test_serving_verdict_rejects_w2_anchor():
    v = r76.serving_vintage_verdict("2024-01-11T12:04:59.999000+00:00")
    assert v["causal_eligibility"] == "REJECTED"
    assert v["evaluation_label"] == "integration-only"
    assert "vintage" in v["causal_eligibility_reason"].lower()


def test_serving_verdict_eligible_only_after_bundle():
    v = r76.serving_vintage_verdict("2025-12-15T00:00:00+00:00")
    assert v["causal_eligibility"] == "ELIGIBLE", v
    assert "prospective" in v["evaluation_label"]


def test_serving_verdict_missing_and_naive_rejected():
    for bad in (None, "NaT", "UNKNOWN", "", "2024-01-11 12:04:59"):
        v = r76.serving_vintage_verdict(bad)
        assert v["causal_eligibility"] == "REJECTED", (bad, v)
        assert v["evaluation_label"] == "integration-only"


def test_warmup_row_not_causal():
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet"
    ).iloc[:100].reset_index(drop=True)
    rows = r76.infer_decisions(candles)
    assert rows and rows[0]["status"] == "WARMUP"
    assert rows[0]["causal_eligibility"] == "NOT-A-DECISION"
    assert rows[0]["evaluation_label"] == "not-a-decision"


def test_serving_annotation_on_real_slice():
    """REAL frozen fold-10 inference on an already-opened 2022 slice.

    Every READY_DECISION predates the fold-10 bundle (fit 2025-11-30, cal
    2025-12-01) so each row MUST be REJECTED for causal eval with the
    integration-only label. No row may claim causal ELIGIBLE.
    """
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet"
    ).iloc[:40000].reset_index(drop=True)
    spec = r76.load_prespec()
    rows = r76.infer_decisions(candles, spec=spec,
                               device=torch.device("cpu"),
                               max_decisions=8)
    ready = [r for r in rows if r.get("status") == "READY_DECISION"]
    assert len(ready) >= 1, "slice must yield real decisions"
    for r in ready:
        assert r["causal_eligibility"] == "REJECTED", r["decision_time"]
        assert r["evaluation_label"] == "integration-only"
        assert "future" in r["causal_eligibility_reason"].lower() or \
            "vintage" in r["causal_eligibility_reason"].lower()
    # Provenance of the verdict is pinned, not invented.
    assert ready[0]["vintage_sources"]["calibrator_asof"]
    assert ready[0]["vintage_sources"]["model_fit_available"]
    # Model/logic untouched: gated action + votes schema intact.
    assert all("action" in r and "vote_confirmed" in r for r in ready)


def test_annotation_keys_do_not_alter_gating():
    raw = json.loads((ROOT / "configs/opencode_r76_infer.json").read_text())
    assert raw["batch_reference"]["ensemble"]["fold_used"] == 10
    assert raw["checkpoints"]["fold"] == 10
    assert r76.FOLD_USED == 10
