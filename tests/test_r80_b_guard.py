"""R80 Track-B: strict vintage-guard regression (FAIL-BEFORE required).

Counterexample (Codex R79 review, evidence
artifacts/research/opencode_background/leader_r79_gap_repro/availability_result.json):
  check_availability(valid_decision, None, None) -> ELIGIBLE
  check_availability(valid_decision, 'NaT', 'NaT') -> ELIGIBLE
Cause: pd.Timestamp(None/NaT) returns NaT without raising; NaT comparisons are
False, so the guard silently falls through to ELIGIBLE. The --claim causal CLI
with missing args follows the same fail-open path.

Strict contract under test (scripts/opencode_r79_vintage.py:check_availability):
- missing/null/empty/NaT/NaN/UNKNOWN/invalid decision AND asset timestamps
  MUST be REJECTED (never ELIGIBLE);
- explicit timezones are normalized to UTC; ambiguous naive values are REJECTED;
- NO exception and NO NaT comparison may yield ELIGIBLE (fail closed);
- model rule (decision_time > fit-available, equality REJECTED) AND calibrator
  rule (decision_time >= asof) both hold, including fit/label/embargo-derived
  cutoffs (fold-2 fit-available 2023-11-30T19:04:59.999Z, fold-10 bundle future
  at the W2 anchor);
- --claim causal with missing args exits nonzero (2), never ELIGIBLE/0.

These tests FAIL on the pre-fix guard and PASS after repair.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r79_vintage as V  # noqa: E402

VALID = "2024-01-11T12:04:59.999000+00:00"
FIT2 = "2023-11-30T19:04:59.999000+00:00"   # fold-2 simulated fit-available
CAL2 = "2023-12-01T00:00:00Z"               # fold-2-era iso4 asof
CAL10 = "2025-12-01T00:00:00Z"              # frozen fold-10 calibrator asof
FIT10 = "2025-11-30T19:04:59.999000+00:00"  # fold-10 simulated fit-available

BAD_VALUES = [
    None, pd.NaT, float("nan"),
    "", "   ",
    "UNKNOWN", "unknown", "Unknown",
    "None", "null", "NULL", "NaT", "nan", "NaN", "undefined", "N/A",
    "not-a-date", "2024-13-99", "12/34/5678",
    {"evil": "dict"}, ["list"], 12345, 3.14, True,
]


def test_counterexample_none_none_rejected():
    verdict, reason = V.check_availability(VALID, None, None)
    assert verdict == "REJECTED", (verdict, reason)
    assert "UNKNOWN" in reason or "missing" in reason or "metadata" in reason


def test_counterexample_nat_strings_rejected():
    verdict, reason = V.check_availability(VALID, "NaT", "NaT")
    assert verdict == "REJECTED", (verdict, reason)


@pytest.mark.parametrize("bad", BAD_VALUES, ids=[f"bad{i}" for i in range(len(BAD_VALUES))])
def test_bad_decision_always_rejected(bad):
    verdict, _ = V.check_availability(bad, FIT2, CAL2)
    assert verdict == "REJECTED"


@pytest.mark.parametrize("bad", BAD_VALUES, ids=[f"bad{i}" for i in range(len(BAD_VALUES))])
def test_bad_model_fit_always_rejected(bad):
    verdict, _ = V.check_availability(VALID, bad, CAL2)
    assert verdict == "REJECTED"


@pytest.mark.parametrize("bad", BAD_VALUES, ids=[f"bad{i}" for i in range(len(BAD_VALUES))])
def test_bad_calibrator_asof_always_rejected(bad):
    verdict, _ = V.check_availability(VALID, FIT2, bad)
    assert verdict == "REJECTED"


def test_fold0_asof_none_rejected():
    """Fold-0 calibrator asof=None must NOT be casually eligible."""
    verdict, _ = V.check_availability("2023-07-01T00:00:00Z",
                                      "2023-05-31T19:04:59.999000+00:00", None)
    assert verdict == "REJECTED"


@pytest.mark.parametrize("naive", [
    "2024-01-11 12:04:59",
    "2024-01-11T12:04:59.999000",   # no offset: ambiguous wall time
    pd.Timestamp("2024-01-11 12:04:59"),  # naive Timestamp object
])
def test_ambiguous_naive_rejected(naive):
    verdict, reason = V.check_availability(naive, FIT2, CAL2)
    assert verdict == "REJECTED", (verdict, reason)
    assert "naive" in reason.lower() or "timezone" in reason.lower()


def test_explicit_timezone_variants_eligible():
    iso_z = "2024-01-11T12:04:59.999000Z"
    iso_off = "2024-01-11T12:04:59.999000+00:00"
    aware_ts = pd.Timestamp("2024-01-11 12:04:59.999000+00:00")
    for dec in (iso_z, iso_off, aware_ts):
        verdict, _ = V.check_availability(dec, FIT2, CAL2)
        assert verdict == "ELIGIBLE", dec


def test_non_utc_offset_normalized():
    # 07:04:59-05:00 == 12:04:59Z, still after fit2 and after cal2.
    verdict, _ = V.check_availability("2024-01-11T07:04:59.999000-05:00",
                                      FIT2, CAL2)
    assert verdict == "ELIGIBLE"


def test_model_boundary_equality_rejected():
    verdict, _ = V.check_availability(FIT2, FIT2, CAL2)
    assert verdict == "REJECTED"


def test_model_one_ns_after_fit_eligible():
    # Calibrator pinned at the fit instant so only the model boundary binds:
    # decision 1ns after fit-available is strictly greater -> ELIGIBLE.
    just_after = (pd.Timestamp(FIT2) + pd.Timedelta(nanoseconds=1)).isoformat()
    verdict, _ = V.check_availability(just_after, FIT2, FIT2)
    assert verdict == "ELIGIBLE"


def test_calibrator_boundary_equality_eligible():
    verdict, _ = V.check_availability(CAL2, FIT2, CAL2)
    assert verdict == "ELIGIBLE"


def test_calibrator_one_bar_too_new_rejected():
    too_new = (pd.Timestamp(VALID) + pd.Timedelta(minutes=5)).isoformat()
    verdict, _ = V.check_availability(VALID, FIT2, too_new)
    assert verdict == "REJECTED"


def test_per_fold_model_does_not_cure_future_calibrator():
    verdict, _ = V.check_availability(VALID, FIT2, CAL10)
    assert verdict == "REJECTED"


def test_frozen_fold10_bundle_rejected_at_w2_anchor():
    verdict, _ = V.check_availability(VALID, FIT10, CAL10)
    assert verdict == "REJECTED"


def test_no_exception_ever_yields_eligible():
    # Objects whose Timestamp() coercion raises must fail closed, not raise.
    for evil in ({"a": 1}, ["x"], object()):
        verdict, reason = V.check_availability(evil, FIT2, CAL2)
        assert verdict == "REJECTED", (evil, verdict)
        assert isinstance(reason, str) and reason


def _run_claim(*argv):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/opencode_r79_vintage.py"), *argv],
        capture_output=True, text=True, cwd=str(ROOT))


def test_claim_causal_missing_args_exits_nonzero():
    proc = _run_claim("--claim", "causal")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REJECTED" in proc.stdout


def test_claim_causal_partial_args_exits_nonzero():
    proc = _run_claim("--claim", "causal", "--decision", VALID)
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_claim_causal_nat_args_exits_nonzero():
    proc = _run_claim("--claim", "causal", "--decision", VALID,
                      "--model-fit-available", "NaT",
                      "--calibrator-asof", "NaT")
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_claim_causal_eligible_triple_exits_zero():
    proc = _run_claim("--claim", "causal", "--decision", VALID,
                      "--model-fit-available", FIT2,
                      "--calibrator-asof", CAL2)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ELIGIBLE" in proc.stdout


def test_claim_causal_future_vintage_exits_nonzero():
    proc = _run_claim("--claim", "causal", "--decision", VALID,
                      "--model-fit-available", FIT10,
                      "--calibrator-asof", CAL10)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REJECTED" in proc.stdout
