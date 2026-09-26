"""Tests for round76 W3 independent raw->equity comparison. RESEARCH ONLY.

Prep-now tests (run WITHOUT W1/W2, real frozen artifacts loaded ONLY by the
harness path here): pre-spec frozen, audit-method sensitivity (flags the known
r75 replay loader, clears clean probes), harness identity/tamper detection,
rebuild-driver determinism + prefix consistency on a real dev slice, no
fit/network in the driver, fail-closed compare gate.

Verify-time tests (SKIP until W1 manifest + W2 feedexec land): full
signal-set identity + 1e-6 portfolio parity (normal + fee .00055),
replay-inputs-denied live predictions, prefix/future perturbation with model
rerun, restart with partials + pending entries, non-WAIT capture + WAIT
behavior. No tuning, no live paths, no cloud.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencode_r76_parity as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
try:
    sys.path.insert(0, str(ROOT / "scripts"))
    import opencode_r76_parity_verify as V
    READY = bool(V.verify_inputs_present().get("ready"))
except Exception:
    V = None
    READY = P.w1w2_status()["ready"]
needs_w1w2 = pytest.mark.skipif(
    not READY, reason="PREP-READY: W1 manifest / W2 feedexec absent")


@pytest.fixture(scope="module")
def spec():
    return P.load_prespec()


@pytest.fixture(scope="module")
def real_slice():
    """Small REAL dev slice (already-opened interval, harness-only loads)."""
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet")
    signals_all = pd.read_parquet(
        ROOT / "artifacts/research/opencode_v15_mapensemble/"
        "confirmed_dd_guard/signals.parquet")
    cut = 205000
    candles = candles.iloc[:cut].reset_index(drop=True)
    signals = signals_all[signals_all["bar_index"] <= 200000].reset_index(
        drop=True)
    assert len(signals) >= 2, "slice must hold multiple real signals"
    return {"candles": candles, "signals": signals,
            "signals_all": signals_all}


def test_prespec_frozen_and_complete(spec):
    assert spec["hypothesis_id"] == "opencode-r76-real-inference-parity"
    assert spec["frozen_reference_policy"]["branch"] == "confirmed_dd_guard"
    assert spec["frozen_reference_policy"]["checkpoints"]["seeds"] == [
        1729, 1730, 1731]
    assert spec["costs"]["fee_stress"]["fee_rate_per_fill"] == 0.00055
    assert spec["pass_rules"]["portfolio_match"].startswith(
        "per-branch final equity")
    assert "1e-6" in spec["pass_rules"]["portfolio_match"]
    assert spec["pass_rules"]["no_replay_inputs"]["audit_method"]
    assert spec["expected_w1_artifacts"]["manifest"]
    assert spec["expected_w2_artifacts"]["feedexec_outputs"]
    assert spec["status"] == "PRE-SPEC (prep phase; no verification numbers claimed)"


def test_audit_flags_known_replay_loader():
    """Sensitivity proof: the r75 streaming loader reads predictions.npz, so
    the audit MUST flag it (method would catch replay in W1/W2 too)."""
    rep = P.audit_no_replay([ROOT / "scripts/opencode_r75_streaming.py"])
    assert rep["pass"] is False
    hits = rep["violations"][str(ROOT / "scripts/opencode_r75_streaming.py")]
    assert any("predictions" in h or "npz" in h for h in hits), hits


def test_audit_clears_clean_probe_and_flags_dirty_probe(tmp_path):
    clean = tmp_path / "clean_stream.py"
    clean.write_text(
        "from agentic_alpha_lab.backtest.engine import run_backtest\n"
        "def stream(candles, decisions):\n"
        "    return run_backtest(candles, decisions, 100.0)\n")
    dirty = tmp_path / "dirty_stream.py"
    dirty.write_text(
        "import pandas as pd\n"
        "def stream():\n"
        "    p = pd.read_parquet('artifacts/x/signals.parquet')\n"
        "    return p\n")
    assert P.audit_no_replay([clean])["pass"] is True
    rep = P.audit_no_replay([dirty])
    assert rep["pass"] is False
    assert any("signals" in h for h in
               rep["violations"][str(dirty)])


def test_compare_identity_passes_on_real_signals(real_slice):
    a = real_slice["signals_all"]
    rep = P.compare_signal_frames(a, a.copy(deep=True))
    assert rep["count_match"] is True
    assert rep["all_bit_exact"] is True, rep["max_abs_diff"]
    assert rep["n_batch"] == rep["n_stream"] == 94


def test_compare_detects_single_row_tamper(real_slice):
    a = real_slice["signals_all"]
    b = a.copy(deep=True)
    b.loc[3, "direction"] = -int(b.loc[3, "direction"])
    rep = P.compare_signal_frames(a, b)
    assert rep["count_match"] is True
    assert rep["all_bit_exact"] is False


def test_rebuild_driver_deterministic_on_real_slice(spec, real_slice):
    first = P.rebuild_equity(real_slice["candles"], real_slice["signals"], spec)
    second = P.rebuild_equity(real_slice["candles"], real_slice["signals"], spec)
    assert first == second
    for branch in spec["comparison_branches"]:
        for key in ("final_equity", "gross_pnl", "fees", "funding", "net_pnl",
                    "max_drawdown", "trade_count", "coverage_signals",
                    "per_trade_equity_after"):
            assert key in first[branch], (branch, key)


def test_rebuild_prefix_consistency(spec, real_slice):
    """Prefix signals rerun => identical leading per-trade equity path."""
    candles = real_slice["candles"]
    signals = real_slice["signals"]
    bmax = int(signals["bar_index"].max())
    bcut = int(signals["bar_index"].iloc[len(signals) // 2])
    assert bcut < bmax
    prefix = signals[signals["bar_index"] <= bcut].reset_index(drop=True)
    assert 1 <= len(prefix) < len(signals)
    branch0 = spec["comparison_branches"][0]
    full = P.rebuild_equity(candles, signals, spec)[branch0]
    pre = P.rebuild_equity(candles, prefix, spec)[branch0]
    k = len(pre["per_trade_equity_after"])
    assert k >= 1
    assert full["per_trade_equity_after"][:k] == pre["per_trade_equity_after"]


def test_no_fit_no_network_in_driver():
    import re
    text = (ROOT / "scripts/opencode_r76_parity.py").read_text()
    for pat in (r"\.fit\(", r"requests?\.", r"socket\.", r"urllib",
                r"tune", r"threshold\s*="):
        assert not re.search(pat, text), pat


def test_w1w2_status_structure():
    st = P.w1w2_status()
    assert set(("w1_files", "w2_files", "manifest_present",
                "adapter_config_present", "ready")) <= set(st)
    if not st["ready"]:
        # Incomplete readiness: the status must truthfully report which inputs
        # are actually on disk (siblings land at different times; the gate
        # stays fail-closed until all three are present).
        from pathlib import Path as _P
        root = _P(__file__).resolve().parents[1]
        w1 = root / "artifacts/research/opencode_r76_real_inference/manifest"
        assert st["manifest_present"] == (w1 / "manifest.json").is_file()
        assert st["adapter_config_present"] == (len(list(w1.glob("adapter_config*.json"))) > 0)


def test_full_compare_fail_closed_when_absent():
    if READY:
        pytest.skip("W1/W2 present: verify-time path owns this gate")
    with pytest.raises(P.ReadinessError):
        P.run_full_comparison()


@needs_w1w2
def test_full_raw_to_equity_parity():
    """Verify-time: streaming vs batch signal identity + 1e-6 equity parity."""
    out = P.run_full_comparison()
    assert out["signal_identity"]["all_bit_exact"] is True
    assert out["equity_parity"]["pass"] is True


@needs_w1w2
def test_replay_inputs_denied_still_predicts():
    """Verify-time: with stored predictions/signals/control CSVs removed or
    denied, the streaming path still yields actual predictions AND the W2
    provenance proves the checkpoint forward pass ran."""
    out = P.run_full_comparison()
    assert out["no_replay_audit"]["pass"] is True
    assert "runtime-denial" in out["no_replay_audit"]["method"]
    assert out["no_replay_audit"]["denial"]["pass"] is True
    assert out["no_replay_audit"]["static_load_sensitive"]["pass"] is True
    assert out["checkpoint_calls_on_slice"] >= 1


@needs_w1w2
def test_prefix_perturbation_rebuilds_model():
    """Verify-time: prefix rerun exact; future perturbation rebuilds features
    + reruns the model (provenance inference-call log), never stored outputs."""
    out = P.run_full_comparison()
    assert out["prefix"]["exact"] is True
    assert out["future_perturbation"]["features_rebuilt"] is True
    assert out["future_perturbation"]["model_rerun"] is True


@needs_w1w2
def test_restart_with_partials_and_pending():
    """Verify-time: kill/resume mid-slice with partials + pending entries."""
    out = P.run_full_comparison()
    assert out["restart"]["fills_identical"] is True
    assert out["restart"]["equity_identical"] is True


@needs_w1w2
def test_nonwait_capture_and_wait_behavior():
    """Verify-time: >=1 non-WAIT historical case; WAIT rows emit no signal
    without forcing a fresh market signal."""
    out = P.run_full_comparison()
    assert out["coverage"]["n_nonwait_stream"] >= 1
    assert out["coverage"]["wait_rows_emitted"] == 0
    assert out["coverage"]["forced_signals"] == 0


def test_prespec_file_matches_loader(spec):
    raw = json.loads((ROOT / "configs/opencode_r76_parity.json").read_text())
    assert raw["hypothesis_id"] == spec["hypothesis_id"]
