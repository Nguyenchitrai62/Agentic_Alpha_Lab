"""R80 Track-C: availability-guard regressions (fail BEFORE Track-B fix).

Codex case 3: check_availability() with missing/null/NaT metadata returns
ELIGIBLE because pd.Timestamp(None/NaT) yields NaT without raising and NaT
comparisons fall through. The `--claim causal` CLI with missing args follows
the same fail-open path (exit 0 ELIGIBLE).

Post-fix expectations asserted here; the None/NaT/CLI tests FAIL on current
code. Boundary/positive controls PASS now and pin non-regression.
Track C must NOT edit source; honest status now is FAIL-BEFORE-FIX.
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r79_vintage as vintage  # noqa: E402

DT = "2026-01-01T00:00:00Z"
FIT2 = "2023-12-01T00:00:00+00:00"
CAL2 = "2023-12-01T00:00:00Z"
ANCHOR = "2024-01-11T12:04:59.999000+00:00"


def test_availability_none_metadata_rejected():
    """check_availability(valid_decision, None, None) must be REJECTED.
    FAILS before Track-B fix (actual: ELIGIBLE)."""
    verdict, _ = vintage.check_availability(DT, None, None)
    assert verdict == "REJECTED"


def test_availability_nat_metadata_rejected():
    """check_availability(valid_decision, 'NaT', 'NaT') must be REJECTED.
    FAILS before Track-B fix (actual: ELIGIBLE)."""
    verdict, _ = vintage.check_availability(DT, "NaT", "NaT")
    assert verdict == "REJECTED"


def test_claim_cli_missing_args_fail_closed():
    """`--claim causal` with missing dates must refuse (exit 2, REJECTED),
    never authorize. FAILS before Track-B fix (actual: exit 0 ELIGIBLE)."""
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/opencode_r79_vintage.py"),
         "--claim", "causal"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert p.returncode == 2
    assert json.loads(p.stdout)["verdict"] == "REJECTED"


def test_availability_positive_control_eligible():
    """Fold-2 model + fold-2-era calibrator at the anchor stays ELIGIBLE
    (guards the fix against over-rejection). PASSES now."""
    verdict, _ = vintage.check_availability(ANCHOR, FIT2, CAL2)
    assert verdict == "ELIGIBLE"


def test_availability_boundary_equality_rejected():
    """decision == model fit-available is REJECTED (strict >). PASSES now."""
    verdict, _ = vintage.check_availability(FIT2, FIT2, CAL2)
    assert verdict == "REJECTED"


def test_availability_future_calibrator_rejected():
    """Per-fold-correct model cannot cure a future shared calibrator.
    PASSES now."""
    verdict, _ = vintage.check_availability(
        ANCHOR, FIT2, "2025-12-01T00:00:00Z")
    assert verdict == "REJECTED"
