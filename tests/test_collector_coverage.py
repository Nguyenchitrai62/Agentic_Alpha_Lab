"""Unit tests for scripts/collector_coverage.py (pure in-memory helpers only)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "collector_coverage", ROOT / "scripts" / "collector_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
GAP = 5 * 60 * 1000


def test_find_gaps_detects_only_large_gaps():
    iv = [(0, 1000), (1001, 2000), (2000 + GAP + 1, 3000)]
    gaps = mod.find_gaps(iv, GAP)
    assert len(gaps) == 1
    assert gaps[0]["gap_start_ms"] == 2000
    assert gaps[0]["gap_end_ms"] == 2000 + GAP + 1


def test_find_gaps_boundary_not_counted():
    iv = [(0, 1000), (1000 + GAP, 2000)]  # exactly gap_ms -> not a gap (strict >)
    assert mod.find_gaps(iv, GAP) == []
    assert mod.find_gaps([], GAP) == []
    assert mod.find_gaps([(0, 1)], GAP) == []


def test_find_gaps_sorts_and_handles_overlap():
    iv = [(10 * GAP, 10 * GAP + 1000), (0, 1000), (1000 + GAP + 5, 2000)]
    gaps = mod.find_gaps(iv, GAP)
    assert len(gaps) == 2  # sorted: 1000->301005 and 2000->10*GAP both exceed GAP
    assert gaps[0]["gap_start_ms"] == 1000
    assert gaps[1]["gap_start_ms"] == 2000
    # overlapping/contiguous intervals produce no positive gap
    assert mod.find_gaps([(0, 5000), (1000, 6000)], GAP) == []


def test_ms_to_utc_format():
    assert mod.ms_to_utc(0) == "1970-01-01T00:00:00+00:00"
    assert mod.ms_to_utc(1000).endswith("+00:00")


def test_module_has_no_side_effects_on_import():
    # importing must not touch the network, files, credentials or processes
    assert callable(mod.summarize) and callable(mod.find_gaps)
    assert callable(mod.read_ms_column) and callable(mod.ms_to_utc)
