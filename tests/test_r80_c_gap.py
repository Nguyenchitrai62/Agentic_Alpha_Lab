"""R80 Track-C: Codex gap-case regressions (fail BEFORE Track-A fix).

MOCK-mechanics only, explicitly labeled: synthetic flat candles (no network),
deterministic READY_RAW fixture (NOT model weights), controlled observation
clocks. Uses the ACTUAL settle path (roll.reconcile_window +
apply_validity_pause + RollingAdvisor.settle_new).

Post-fix expectations asserted here; both tests FAIL on current code
(see artifacts/research/opencode_r80/c_fails_before/c_fails_before.json).
Track C must NOT edit source; honest status now is FAIL-BEFORE-FIX.
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import json
from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_roll as roll  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402

SYM, INT = "BTCUSDT", "5m"
T0 = pd.Timestamp("2026-09-10T00:00:00Z")  # fixed MOCK clock base
LABEL = "MOCK-mechanics regression (synthetic candles + raw fixture)"

ROLL_CFG = json.loads((ROOT / "configs/opencode_r79_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()


@pytest.fixture
def patched_identity(monkeypatch):
    def _collect(roll_cfg, advisor_cfg, spec):
        return [rel for rel in (
            "scripts/opencode_r77_advisor_core.py",
            "scripts/opencode_r77_advisor.py",
            "scripts/opencode_r78_roll.py",
            "configs/opencode_r77_advisor.json",
            "configs/opencode_r79_roll.json",
            "configs/opencode_r76_infer.json")
            if (ROOT / rel).exists()]
    monkeypatch.setattr(roll, "collect_identity_files", _collect)
    return _collect


def candles(n, start=T0):
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=5)})
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def mock_raw(close_time, action="LONG"):
    s = 1 if action == "LONG" else -1
    return {"status": "READY_RAW", "bar_index": -1,
            "decision_time": core._ts(close_time), "close": 100.1,
            "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "vote_majority": True,
            "vote_confirmed": True,
            "iso4_raw_geometry": {
                "direction": s, "entry_limit": 100.0, "stop_loss": 95.0,
                "take_profit_1": 110.0, "take_profit_2": 120.0,
                "holding_bars": 2000, "leverage": 1.0,
                "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
                "conditional_win_score": 0.8},
            "per_map_action": {}, "htf_last_close_lte_decision": {},
            "device": "test-mock-r80", "MOCK": LABEL}


def fresh_adv(out, df, observed_at):
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    adv.begin(core._ts(df["close_time"].iloc[0]).isoformat(), observed_at)
    return adv


def settle_ingest(adv, df, observed_at, raws=None):
    """One ingest exactly like roll.main(). Returns (rec, paused)."""
    gaps_before = len(adv.exec_state.get("gaps", []))
    rec = roll.reconcile_window(df, SYM, INT, observed_at, adv.exec_state)
    paused = roll.apply_validity_pause(
        adv, rec, rec["gaps"][gaps_before:], observed_at)
    latest = (max(core._ts(r["close_time"])
                  for _, r in rec["new_rows"]).isoformat()
              if rec["new_rows"] else None)
    for exec_idx, row in rec["new_rows"]:
        adv.settle_new([(exec_idx, row)],
                       {exec_idx: raws[exec_idx]}
                       if raws and exec_idx in raws else {},
                       observed_at, batch_latest_close_iso=latest,
                       paused_exec=set(paused))
    return rec, paused


def op_state(adv):
    op = adv.strategy.operating
    return {"equity": float(op.equity),
            "pending": op.pending is not None,
            "open": op.open is not None,
            "entry_bar": (op.open or {}).get("entry_bar") if op.open else None}


OBS1 = "2026-09-10T00:55:00+00:00"
OBS2 = "2026-09-10T02:35:00+00:00"
OBS3 = "2026-09-10T03:05:00+00:00"


def run_reference(tmp_path):
    full = candles(30)
    out = tmp_path / "ref"
    out.mkdir(parents=True)
    adv = fresh_adv(out, full.iloc[:10], OBS1)
    rec, _ = settle_ingest(adv, full.iloc[:10].reset_index(drop=True), OBS1)
    assert adv.strategy.operating.pending is None  # no raw -> no intent
    # Fresh advisor armed deterministically with the raw on the latest bar
    # (bar9 == latest -> actionable).
    out2 = tmp_path / "ref2"
    out2.mkdir(parents=True)
    adv = fresh_adv(out2, full.iloc[:10], OBS1)
    rec = roll.reconcile_window(full.iloc[:10].reset_index(drop=True),
                                SYM, INT, OBS1, adv.exec_state)
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"], OBS1)
    rows = dict(rec["new_rows"])
    latest = max(rows)
    raw = mock_raw(rows[latest]["close_time"])
    latest_iso = max(core._ts(r["close_time"])
                     for _, r in rec["new_rows"]).isoformat()
    for exec_idx, row in rec["new_rows"]:
        adv.settle_new([(exec_idx, row)],
                       {exec_idx: raw} if exec_idx == latest else {},
                       OBS1, batch_latest_close_iso=latest_iso,
                       paused_exec=set(paused))
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    settle_ingest(adv, full.reset_index(drop=True), OBS2)
    return adv


def run_gap_backfill(tmp_path):
    full = candles(30)
    gapped = pd.concat([full.iloc[:10],
                        full.iloc[13:]]).reset_index(drop=True)
    out = tmp_path / "gap"
    out.mkdir(parents=True)
    adv = fresh_adv(out, full.iloc[:10], OBS1)
    rec = roll.reconcile_window(full.iloc[:10].reset_index(drop=True),
                                SYM, INT, OBS1, adv.exec_state)
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"], OBS1)
    rows = dict(rec["new_rows"])
    latest = max(rows)
    raw = mock_raw(rows[latest]["close_time"])
    latest_iso = max(core._ts(r["close_time"])
                     for _, r in rec["new_rows"]).isoformat()
    for exec_idx, row in rec["new_rows"]:
        adv.settle_new([(exec_idx, row)],
                       {exec_idx: raw} if exec_idx == latest else {},
                       OBS1, batch_latest_close_iso=latest_iso,
                       paused_exec=set(paused))
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    settle_ingest(adv, gapped, OBS2)
    adv.atomic_commit()
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    settle_ingest(adv, full.reset_index(drop=True), OBS3)
    return adv


def exec_time_map(adv):
    return {k.rsplit("|", 1)[1]: int(v["exec_idx"])
            for k, v in adv.exec_state.get("seen", {}).items()}


def test_full_backfill_matches_uninterrupted(patched_identity, tmp_path):
    """Codex case 1: identical candle times must settle identically whether
    consumed uninterrupted or gapped-then-backfilled (stable economic clock,
    no double-consumed expiry indices). FAILS before Track-A fix."""
    ref = run_reference(tmp_path / "a")
    bf = run_gap_backfill(tmp_path / "b")
    assert op_state(bf) == op_state(ref)
    assert exec_time_map(bf) == exec_time_map(ref)


def test_partial_backfill_preserves_pause(patched_identity, tmp_path):
    """Codex case 2: restoring only bar10 of missing {10,11,12} must keep
    the gap unresolved (paused=True) until EVERY expected valid close is
    available. FAILS before Track-A fix (ANY-seen clears validity)."""
    full = candles(30)
    gapped = pd.concat([full.iloc[:10],
                        full.iloc[13:]]).reset_index(drop=True)
    out = tmp_path / "part"
    out.mkdir(parents=True)
    adv = fresh_adv(out, full.iloc[:10], OBS1)
    settle_ingest(adv, full.iloc[:10].reset_index(drop=True), OBS1)
    adv.atomic_commit()
    _, paused = settle_ingest(adv, gapped, OBS2)
    assert paused, "gapped ingest must pause"
    adv.atomic_commit()
    only10 = full.iloc[:11].reset_index(drop=True)
    _, paused = settle_ingest(adv, only10, OBS3)
    validity = adv.exec_state.get("validity", {})
    assert validity.get("paused") is True
    assert len(validity.get("unresolved_gaps", [])) == 1
    assert paused, "bars after a still-missing price path must stay paused"
