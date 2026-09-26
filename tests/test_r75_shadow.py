"""Tests for the round75 track-C advisory shadow service. Paper/plumbing only."""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import copy
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r75_shadow as sh  # noqa: E402

CONFIG = json.loads((_ROOT / "configs/opencode_r75_shadow.json").read_text())
FIXTURE = _ROOT / CONFIG["data"]["default_fixture"]


def _fixture_df():
    df = pd.read_parquet(FIXTURE)
    df.index = df["bar_index"].astype(int)
    return df


def _policy():
    return sh.load_policy(CONFIG, _ROOT)


def _runner(df, out, start, end, policy=None, freshness=None):
    out.mkdir(parents=True, exist_ok=True)
    for f in ("decisions.jsonl", "alerts.jsonl", "fills.jsonl"):
        (out / f).write_text("", encoding="utf-8")
    return sh.ShadowRunner(copy.deepcopy(CONFIG), policy or _policy(), df,
                           freshness or sh.REHEARSAL_LABEL,
                           {"mode": "test"}, out, _ROOT, start, end)


def _walk(runner, out, from_pos=None):
    for k, pos in enumerate(range(from_pos if from_pos is not None else runner.pos0,
                                  runner.pos1 + 1)):
        runner.step(pos)
        if runner.strategy is not None and k % 50 == 0:
            runner.strategy.save_state(out / "state.json")
    if runner.strategy is not None:
        runner.strategy.save_state(out / "state.json")
    return [json.loads(l) for l in open(out / "decisions.jsonl", encoding="utf-8")]


def _stash_b_bundle(tmp_path):
    """Move the leader integration adapter aside (if present) so fallback tests
    are hermetic regardless of integration state. Returns restore callable."""
    stream = _ROOT / "artifacts/research/opencode_r75_practical/streaming"
    real = stream / "reference_policy.json"
    stash = tmp_path / "reference_policy.json.stash"
    moved = False
    if real.exists():
        stash.write_bytes(real.read_bytes())
        real.unlink()
        moved = True
    def restore():
        if moved:
            real.write_bytes(stash.read_bytes())
    return restore


def test_policy_source_own_frozen_no_invented_weights(tmp_path):
    restore = _stash_b_bundle(tmp_path)
    try:
        policy = _policy()
        assert policy["source"] == "OWN-FROZEN"  # streaming/ bundle absent
        assert policy["signals"] is not None and len(policy["signals"]) == 94
        assert "B bundle absent" in policy["reason"]
    finally:
        restore()


def test_b_bundle_adopted_when_present(tmp_path):
    restore = _stash_b_bundle(tmp_path)
    probe = _ROOT / "artifacts/research/opencode_r75_practical/streaming/_test_adopt.json"
    try:
        sig = _ROOT / "artifacts/research/opencode_v15_mapensemble/confirmed_dd_guard/signals.parquet"
        tr = _ROOT / "artifacts/research/opencode_v15_mapensemble/confirmed_dd_guard/normal_trades.csv"
        assert sig.exists() and tr.exists()
        probe.write_text(json.dumps({
            "policy_id": "opencode_r75_confirmed_dd_guard",
            "signals_parquet": str(sig), "baseline_trades": str(tr),
            "baseline_signals": str(sig)}), encoding="utf-8")
        cfg = copy.deepcopy(CONFIG)
        cfg["shadow"] = dict(cfg["shadow"])
        cfg["shadow"]["b_bundle_path"] = str(probe.relative_to(_ROOT))
        policy = sh.load_policy(cfg, _ROOT)
        assert policy["source"] == "B-BUNDLE"
        assert policy["signals"] is not None and len(policy["signals"]) == 94
        assert "adopted B bundle" in policy["reason"]
    finally:
        if probe.exists():
            probe.unlink()
        restore()


def test_fixture_determinism(tmp_path):
    df = _fixture_df()
    d1 = _walk(_runner(df, tmp_path / "a", 440900, 441099), tmp_path / "a")
    d2 = _walk(_runner(df, tmp_path / "b", 440900, 441099), tmp_path / "b")
    assert len(d1) == len(d2) == 200
    h = lambda ds: hashlib.sha256(json.dumps(ds, sort_keys=True).encode()).hexdigest()
    assert h(d1) == h(d2)


def test_wait_on_nonfinite_row(tmp_path):
    df = _fixture_df().copy()
    df.loc[440950, "close"] = float("nan")
    recs = _walk(_runner(df, tmp_path / "o", 440940, 440960), tmp_path / "o")
    bad = [r for r in recs if r["bar_id"] == 440950]
    assert len(bad) == 1 and bad[0]["action"] == "WAIT"
    assert bad[0]["reason"] == "DATA_NONFINITE_OHLC"


def test_wait_on_gap(tmp_path):
    df = _fixture_df()
    df2 = df[~df.index.isin([440950])]  # drop one closed bar -> gap
    recs = _walk(_runner(df2, tmp_path / "o", 440940, 440960), tmp_path / "o")
    bad = [r for r in recs if r["bar_id"] == 440951]
    assert len(bad) == 1 and bad[0]["action"] == "WAIT" and bad[0]["reason"] == "DATA_GAP"


def test_wait_on_missing_checkpoints(tmp_path):
    df = _fixture_df()
    policy = {"source": "OWN-FROZEN", "policy_id": "x", "signals": None,
              "fallback_note": "no signals file"}
    recs = _walk(_runner(df, tmp_path / "o", 440940, 440960, policy=policy), tmp_path / "o")
    assert recs and all(r["action"] == "WAIT" and r["reason"] == "CHECKPOINT_MISSING" for r in recs)


def test_wait_on_nonfinite_output(tmp_path):
    df = _fixture_df()
    runner = _runner(df, tmp_path / "o", 440940, 440960)

    class BadPred:
        kind = "BAD_TEST_ONLY"

        def predict_proba(self, frame):
            return {"action": "LONG", "confidence": float("nan")}

    runner.strategy.predictor = BadPred()
    recs = _walk(runner, tmp_path / "o")
    assert recs and all(r["reason"] == "NONFINITE_OUTPUT" for r in recs)


def test_halt_and_trip_paths(tmp_path):
    import opencode_paper_trader_v2 as v2
    halt = v2.DailyLossHalt(0.03)
    halt.roll_day("2026-01-01", 100.0)
    assert halt.evaluate(100.0, "t", 1) is False
    assert halt.evaluate(96.9, "t", 2) is True  # -3.1% trips the kill-switch
    df = _fixture_df()
    recs = _walk(_runner(df, tmp_path / "o", 439150, 440700), tmp_path / "o")
    by_id = {r["bar_id"]: r for r in recs}
    assert by_id[439200]["action"] == "LONG"  # signal observed
    latched = [r for r in recs if r["reason"] == "DIVERGENCE_LATCH"]
    assert latched and latched[0]["bar_id"] == 440640  # kill blocks the later signal
    alerts = [json.loads(l) for l in open(tmp_path / "o" / "alerts.jsonl", encoding="utf-8")]
    kinds = json.dumps(alerts)
    assert "DAILY_LOSS_HALT" in kinds and "DIVERGENCE_TRIP" in kinds


def test_expiry_path(tmp_path):
    df = _fixture_df()
    recs = _walk(_runner(df, tmp_path / "o", 440600, 441099), tmp_path / "o")
    by_id = {r["bar_id"]: r for r in recs}
    assert by_id[440640]["action"] == "LONG"
    fills = [json.loads(l) for l in open(tmp_path / "o" / "fills.jsonl", encoding="utf-8")]
    armed = [f for f in fills if f["event"] == "INTENT_ARMED"]
    expired = [f for f in fills if f["event"] == "PENDING_EXPIRED"]
    assert len(armed) == 1 and len(expired) == 1
    assert expired[0]["signal_bar"] == 440640
    assert by_id[440640]["expiry_bar"] == 440652


def test_restart_parity(tmp_path):
    df = _fixture_df()
    s, m, e = 439150, 440200, 441099
    r1 = _runner(df, tmp_path / "p1", s, m)
    d1 = _walk(r1, tmp_path / "p1")
    snap = json.loads((tmp_path / "p1" / "state.json").read_text())
    r2 = _runner(df, tmp_path / "p2", s, e)
    r2.strategy.restore_state(snap)
    r2.n_flushed_alerts = len(r2.strategy.alerts)
    m1_pos = list(df.index).index(m) + 1
    d2 = _walk(r2, tmp_path / "p2", from_pos=m1_pos)
    r3 = _walk(_runner(df, tmp_path / "full", s, e), tmp_path / "full")
    h = lambda ds: hashlib.sha256(json.dumps(ds, sort_keys=True).encode()).hexdigest()
    assert h(d1 + d2) == h(r3)
    f1 = open(tmp_path / "p1" / "fills.jsonl", encoding="utf-8").read()
    f2 = open(tmp_path / "p2" / "fills.jsonl", encoding="utf-8").read()
    f3 = open(tmp_path / "full" / "fills.jsonl", encoding="utf-8").read()
    assert f1 + f2 == f3


def test_rehearsal_vs_fresh_labeling(tmp_path):
    df = _fixture_df()
    recs = _walk(_runner(df, tmp_path / "o", 440940, 440960), tmp_path / "o")
    assert all(r["freshness"] == sh.REHEARSAL_LABEL for r in recs)
    assert all(r["label"] == "SIMULATED/PAPER-research-shadow" for r in recs)
    # fresh: stubbed public-klines fetch (no network), forming candle dropped
    klines = [[1700000000000 + i * 300000, "1", "2", "0.5", "1.5", "10", 1700000299999 + i * 300000,
               "x", "x", "x", "x", "x"] for i in range(4)]

    class _Resp:
        def read(self):
            return json.dumps(klines).encode()

        def close(self):
            pass

    now = pd.Timestamp(klines[-1][6], unit="ms", tz="UTC") + pd.Timedelta(minutes=10)
    fdf, meta = sh.fetch_public_klines("BTCUSDT", "5m", 4, "https://x.test", 5,
                                       now=now.to_pydatetime(),
                                       opener=lambda req, timeout=None: _Resp())
    assert meta["rows_raw"] == 4 and meta["rows_closed"] == 4
    recs2 = _walk(_runner(fdf, tmp_path / "f", 0, 3, freshness=sh.FRESH_LABEL), tmp_path / "f")
    assert all(r["freshness"] == sh.FRESH_LABEL for r in recs2)
    assert all(r["reason"] == "NO_SIGNAL" for r in recs2)  # no frozen rows match fresh ids


def test_live_refuses_resume(tmp_path):
    sys.argv = ["prog", "--config", str(_ROOT / "configs/opencode_r75_shadow.json"),
                "--candles", "live", "--out", str(tmp_path), "--resume"]
    with pytest.raises(SystemExit):
        sh.main()
