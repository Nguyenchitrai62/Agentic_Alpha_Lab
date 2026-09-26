"""Tests for round77 W3 independent raw->equity comparison. RESEARCH ONLY.

Prep-now tests (run WITHOUT W1/W2; real frozen artifacts loaded ONLY by the
harness path here): pre-spec frozen, audit sensitivity (flags the known r75
replay loader, clears clean probes), anti-circularity engine audit (blocker
B2: streaming path must not touch run_backtest), harness identity/tamper
detection, NEGATIVE CONTROLS (wrong TP1 fraction / fee / entry timestamp /
control routing MUST make parity FAIL), rebuild-driver determinism + prefix
consistency on a real dev slice, denial-helper correctness, no
fit/network in the driver, fail-closed compare gate.

Verify-time tests (SKIP until W1 runner + W2 fixtures land): full
signal-set identity + 1e-6 portfolio parity (normal + fee .00055),
replay-inputs-denied live predictions, prefix/future perturbation with model
rerun, restart with partials + pending entries, non-WAIT capture + WAIT
behavior, checkpoint-call proof. No tuning, no live paths, no cloud.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencode_r77_verify as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
READY = P.w1w2_status()["ready"]
needs_w1w2 = pytest.mark.skipif(
    not READY, reason="PREP-READY: W1 runner / W2 fixtures absent")


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
    assert spec["hypothesis_id"] == "opencode-r77-stateful-advisory-verify"
    assert spec["frozen_reference_policy"]["branch"] == "confirmed_dd_guard"
    assert spec["frozen_reference_policy"]["checkpoints"]["seeds"] == [
        1729, 1730, 1731]
    assert spec["costs"]["fee_stress"]["fee_rate_per_fill"] == 0.00055
    assert spec["tolerances"]["equity_tol"] == 1e-6
    assert spec["tolerances"]["signal_identity_tol"] == 0.0
    assert spec["pass_rules"]["signal_identity"]
    assert spec["pass_rules"]["portfolio_match"]
    assert spec["pass_rules"]["no_replay"]  # zero forbidden-input loads + denial run
    assert spec["no_replay_inputs"]["audit_method"]
    assert spec["pass_rules"]["negative_controls_fail"]
    assert spec["streaming_side_ban"]
    assert spec["expected_w1_runner"]["manifest"]
    assert spec["expected_w1_runner"]["cli"]
    assert spec["expected_w2_fixtures"]["semantic_cases"]
    assert spec["checkpoint_call_proof"]["fields_required"]
    assert spec["status"].startswith("PRE-SPEC")


def test_audit_flags_known_replay_loader():
    """Sensitivity proof: the r75 streaming loader reads predictions.npz and
    signals.parquet, so the audit MUST flag it."""
    rep = P.audit_no_replay([ROOT / "scripts/opencode_r75_streaming.py"])
    assert rep["pass"] is False
    hits = rep["violations"][str(ROOT / "scripts/opencode_r75_streaming.py")]
    assert any("predictions" in h or "signals" in h for h in hits), hits


def test_audit_clears_clean_probe_and_flags_dirty_probe(tmp_path):
    clean = tmp_path / "clean_stream.py"
    clean.write_text(
        "def stream(candles, decisions, model):\n"
        "    feats = build_features(candles)\n"
        "    return model.forward(feats)\n")
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


def test_audit_engine_flags_run_backtest_on_streaming_path(tmp_path):
    """Blocker B2 guard: a streaming module calling run_backtest MUST fail
    the anti-circularity audit; a pure incremental probe MUST pass."""
    circular = tmp_path / "circular_stream.py"
    circular.write_text(
        "from agentic_alpha_lab.backtest.engine import run_backtest\n"
        "def stream(candles, sig):\n"
        "    return run_backtest(candles, sig, 100.0)\n")
    incremental = tmp_path / "incremental_stream.py"
    incremental.write_text(
        "class FeedExecAccount:\n"
        "    def on_fill(self, fill):\n"
        "        self.equity += fill.net_pnl\n")
    assert P.audit_streaming_engine([incremental])["pass"] is True
    rep = P.audit_streaming_engine([circular])
    assert rep["pass"] is False
    assert any("run_backtest" in h for h in
               rep["violations"][str(circular)])


def test_compare_identity_passes_on_real_signals(real_slice):
    a = real_slice["signals_all"]
    rep = P.compare_signal_frames(a, a.copy(deep=True))
    assert rep["count_match"] is True
    assert rep["all_bit_exact"] is True, rep["max_abs_diff"]
    assert rep["n_batch"] == rep["n_stream"]


def test_negative_control_wrong_tp1_fraction_fails(real_slice):
    """Deliberately wrong TP1 fraction in a test double MUST break parity."""
    a = real_slice["signals"]
    b = a.copy(deep=True)
    b["tp1_fraction"] = 0.75
    rep = P.compare_signal_frames(a, b)
    assert rep["count_match"] is True
    assert rep["all_bit_exact"] is False


def test_negative_control_entry_timestamp_shift_fails(real_slice):
    """Shifted entry timestamps MUST break signal identity."""
    a = real_slice["signals"]
    b = a.copy(deep=True)
    b["signal_time"] = (pd.to_datetime(b["signal_time"])
                        + pd.Timedelta(minutes=5)).astype(str)
    rep = P.compare_signal_frames(a, b)
    assert rep["all_bit_exact"] is False


def test_negative_control_wrong_routing_fails(real_slice):
    """Wrong control/side routing (flipped direction) MUST break parity."""
    a = real_slice["signals"]
    b = a.copy(deep=True)
    b.loc[b.index[0], "direction"] = -int(b.loc[b.index[0], "direction"])
    rep = P.compare_signal_frames(a, b)
    assert rep["count_match"] is True
    assert rep["all_bit_exact"] is False


def test_negative_control_wrong_fee_fails(spec, real_slice):
    """Wrong fee in a test double MUST break the 1e-6 equity match AND the
    rebuild driver must actually respond to the fee (stress fees >= normal)."""
    ref = P.rebuild_reference_equity(
        real_slice["candles"], real_slice["signals"], spec)
    branch0 = spec["comparison_branches"][0]
    tampered = {branch0: dict(ref[branch0],
                              fees=ref[branch0]["fees"] * 1.1,
                              final_equity=ref[branch0]["final_equity"] - 0.01,
                              per_trade_equity_after=[
                                  v - 0.01 for v in
                                  ref[branch0]["per_trade_equity_after"]])}
    rep = P.compare_equity(ref, tampered)
    assert rep["pass"] is False
    assert rep["branches"][branch0]["pass"] is False
    normal_fees = ref["normal (fee 0.0002/fill)"]["fees"]
    stress_fees = ref["fee_stress (fee 0.00055/fill)"]["fees"]
    assert stress_fees >= normal_fees


def test_rebuild_reference_deterministic_on_real_slice(spec, real_slice):
    first = P.rebuild_reference_equity(
        real_slice["candles"], real_slice["signals"], spec)
    second = P.rebuild_reference_equity(
        real_slice["candles"], real_slice["signals"], spec)
    for run in (first, second):
        for branch in run:
            run[branch].pop("rebuild_ms", None)  # timing is diagnostic only
    assert first == second
    for branch in ("normal (fee 0.0002/fill)", "fee_stress (fee 0.00055/fill)"):
        for key in ("final_equity", "gross_pnl", "fees", "funding", "net_pnl",
                    "max_drawdown", "trade_count", "coverage_signals",
                    "per_trade_equity_after", "per_trade"):
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
    full = P.rebuild_reference_equity(candles, signals, spec)[branch0]
    pre = P.rebuild_reference_equity(candles, prefix, spec)[branch0]
    k = len(pre["per_trade_equity_after"])
    assert k >= 1
    assert full["per_trade_equity_after"][:k] == pre["per_trade_equity_after"]


def test_denied_inputs_helper_hides_and_restores(tmp_path):
    """Denial harness: probe sees files ABSENT inside the context, files are
    restored afterwards (fail-safe even on exception)."""
    f1 = tmp_path / "predictions.npz"
    f1.write_bytes(b"stored")
    f2 = tmp_path / "control.csv"
    f2.write_bytes(b"stored")
    seen = {}

    def probe():
        seen["f1"] = f1.is_file()
        seen["f2"] = f2.is_file()
        return (not seen["f1"]) and (not seen["f2"])

    with P.denied_inputs([f1, f2]) as denied:
        assert probe() is True
        assert len(denied) == 2
    assert f1.is_file() and f2.is_file()

    class Boom(Exception):
        pass

    try:
        with P.denied_inputs([f1]):
            raise Boom()
    except Boom:
        pass
    assert f1.is_file()


def test_no_fit_no_network_in_driver():
    import re
    text = (ROOT / "scripts/opencode_r77_verify.py").read_text()
    for pat in (r"\.fit\(", r"requests?\.", r"socket\.", r"urllib",
                r"tune", r"threshold\s*="):
        assert not re.search(pat, text), pat


def test_w1w2_status_structure():
    st = P.w1w2_status()
    assert set(("w1_files", "w2_files", "manifest_present",
                "runner_present", "ready")) <= set(st)
    if not st["ready"]:
        assert st["manifest_present"] == (
            ROOT / "artifacts/research/opencode_r77_advisory/runner/manifest.json"
        ).is_file()
        assert st["runner_present"] == (
            ROOT / "scripts/opencode_r77_runner.py").is_file()


def test_full_compare_fail_closed_when_absent():
    if READY:
        pytest.skip("W1/W2 present: verify-time path owns this gate")
    with pytest.raises(P.ReadinessError):
        P.run_full_comparison()


@needs_w1w2
def test_full_raw_to_equity_parity():
    """Verify-time: streaming (incremental journals) vs batch signal identity
    + 1e-6 equity parity."""
    out = P.run_full_comparison()
    assert out["streaming_engine"] != "run_backtest"
    assert out["signal_identity"]["all_bit_exact"] is True
    assert out["equity_parity"]["pass"] is True


@needs_w1w2
def test_replay_inputs_denied_still_predicts():
    """Verify-time: with stored predictions/signals/control CSVs removed or
    denied, the streaming path still yields actual predictions AND the W1
    manifest proves the checkpoint forward pass ran."""
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


@needs_w1w2
def test_checkpoint_call_proof():
    """Verify-time: model forward actually invoked (call log + timing/device,
    not just outputs)."""
    out = P.run_full_comparison()
    assert out["checkpoint_calls_on_slice"] >= 1
    assert out["checkpoint_call_evidence"]["per_call_timing"] is True
    assert out["checkpoint_call_evidence"]["device_reported"] is True


@needs_w1w2
def test_full_compare_reports_both_legs_no_vacuous_misread():
    """Guard against vacuous-PASS misreads: the slice leg is honestly
    labeled VACUOUS-EMPTY (frozen checkpoint abstains), and the verdict
    additionally requires the non-vacuous 10-builder fixture streaming leg
    (>=1 non-WAIT streaming fill, all within 1e-6)."""
    out = P.run_full_comparison()
    assert "VACUOUS-EMPTY" in out["signal_identity"]["slice_leg"]["note"]
    assert out["signal_identity"]["fixture_leg_all_pass"] is True
    assert out["equity_parity"]["fixture_leg_pass"] is True
    assert out["coverage"]["slice_nonwait"] == 0
    assert out["coverage"]["n_nonwait_stream"] >= 1
    assert out["verdict"] == "PASS"


def test_prespec_file_matches_loader(spec):
    raw = json.loads((ROOT / "configs/opencode_r77_verify.json").read_text())
    assert raw["hypothesis_id"] == spec["hypothesis_id"]
