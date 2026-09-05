"""Guards in CLI wrappers, separate from immutable frozen model implementation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_degenerate_bootstrap_for_tiny_trade_sample():
    bootstrap = load_script("evaluate_tree_pipeline").trade_bootstrap
    for count in (0, 1, 5):
        report = bootstrap([SimpleNamespace(equity_before=100, equity_after=105)] * count)
        assert report["replicates"] == 0
        assert "net_return_percent_p025_p50_p975" not in report


def test_frozen_decision_clock_is_utc_and_exact():
    clock = load_script("infer_tree_pipeline").on_decision_clock
    assert clock("2026-06-09T00:04:59.999Z", 72)
    assert clock("2026-06-09T13:04:59.999+07:00", 72)
    assert not clock("2026-06-09T00:09:59.999Z", 72)
    assert not clock("2026-06-09T00:04:59Z", 72)
