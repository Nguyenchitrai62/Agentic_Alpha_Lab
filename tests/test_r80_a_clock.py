"""R80 Track-A: timestamp-stable economic clock (Codex counterexample 1).

MOCK-mechanics only (synthetic candles + stub-like raw fixtures, no
network/model/training). Rule under test (r80_roll/1):

- Pending expiry, holding timeout, funding, cooldown and control exits
  follow ACTUAL candle times (origin-anchored absolute 5m grid steps),
  stable across uninterrupted / chunked / duplicated / gapped-backfilled /
  restarted consumption of identical data. Same candle time -> same
  economic position in time. No fresh elapsed-time indices, no
  reset/re-arm of pending.

FAIL-BEFORE (r79): arm LONG at bar9 over 30 bars; uninterrupted fills at
bar10 (equity 99.98, position open). Hide bars 10,11,12 -> pause,
commit+resume with COMPLETE data: pending rejected-expired, equity 100.
Post-gap bars consumed fresh exec indices; backfilled candle-times replay
at NEW indices beyond the elapsed-index expiry.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_roll as roll  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402

SYM, INT = "BTCUSDT", "5m"
T0 = pd.Timestamp("2026-09-10T00:00:00Z")
ROLL_CFG = json.loads((ROOT / "configs/opencode_r80_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()


def candles(n, start=T0, patches=None):
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=5)})
    if patches:
        for idx, p in patches.items():
            rows[idx].update(p)
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def mock_raw(close_time, action, entry=100.0, holding=2000):
    s = 1 if action == "LONG" else -1
    if action == "LONG":
        geo = {"direction": s, "entry_limit": entry, "stop_loss": 95.0,
               "take_profit_1": 110.0, "take_profit_2": 120.0,
               "holding_bars": holding, "leverage": 1.0,
               "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
               "conditional_win_score": 0.8}
    else:
        geo = {"direction": s, "entry_limit": entry, "stop_loss": 105.0,
               "take_profit_1": 90.0, "take_profit_2": 80.0,
               "holding_bars": holding, "leverage": 1.0,
               "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
               "conditional_win_score": 0.8}
    return {"status": "READY_RAW", "bar_index": -1,
            "decision_time": core._ts(close_time), "close": 100.1,
            "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "iso4_raw_geometry": geo,
            "per_map_action": {}, "vote_majority": True,
            "vote_confirmed": True,
            "htf_last_close_lte_decision": {}, "device": "test-mock"}


@pytest.fixture
def patched_identity(monkeypatch):
    def _collect(roll_cfg, advisor_cfg, spec):
        return [rel for rel in (
            "scripts/opencode_r77_advisor_core.py",
            "scripts/opencode_r77_advisor.py",
            "scripts/opencode_r78_roll.py",
            "configs/opencode_r77_advisor.json",
            "configs/opencode_r80_roll.json",
            "configs/opencode_r76_infer.json")
            if (ROOT / rel).exists()]
    monkeypatch.setattr(roll, "collect_identity_files", _collect)
    return _collect


def fresh_adv(out, df, observed_at):
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    adv.begin(roll.fresh_shadow_start(df, observed_at), observed_at)
    return adv


def settle_all(adv, new_rows, raws, observed_at, paused=frozenset(),
               revision=False):
    latest = max(core._ts(r["close_time"]) for _, r in
                 new_rows).isoformat() if new_rows else None
    out = []
    for exec_idx, row in new_rows:
        out.extend(adv.settle_new(
            [(exec_idx, row)],
            {exec_idx: raws[exec_idx]} if exec_idx in raws else {},
            observed_at, batch_latest_close_iso=latest,
            paused_exec=set(paused), revision_contaminated=revision))
    return out


def arm_at_bar9(out, full, action="LONG", entry=100.0, holding=2000):
    """Bootstrap 0..8 (diagnostic) then arm intent on bar9 (latest new)."""
    obs1a = "2026-09-10T00:46:00+00:00"
    obs1b = "2026-09-10T00:51:00+00:00"
    adv = fresh_adv(out, full.iloc[:9], obs1a)
    rec = roll.reconcile_window(full.iloc[:9].reset_index(drop=True),
                                SYM, INT, obs1a, adv.exec_state)
    settle_all(adv, rec["new_rows"], {}, obs1a)
    adv.atomic_commit()
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec = roll.reconcile_window(full.iloc[:10].reset_index(drop=True),
                                SYM, INT, obs1b, adv.exec_state)
    assert len(rec["new_rows"]) == 1
    rows = dict(rec["new_rows"])
    latest = max(rows)
    raws = {latest: mock_raw(rows[latest]["close_time"], action,
                             entry=entry, holding=holding)}
    settle_all(adv, rec["new_rows"], raws, obs1b)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    return adv


def op_state(adv):
    op = adv.strategy.operating
    return {"equity": op.equity, "pending": op.pending, "open": op.open,
            "exits": op.exits, "rejected": op.rejected,
            "events": op.events}


def drop_gap(df, lo=10, hi=12):
    drop = [i for i in range(lo, hi + 1)]
    return df.drop(index=drop).reset_index(drop=True)


def run_reference(out, full, action="LONG", entry=100.0, holding=2000,
                  obs="2026-09-10T02:35:00+00:00"):
    adv = arm_at_bar9(out, full, action=action, entry=entry,
                      holding=holding)
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                obs, adv.exec_state)
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"], obs)
    assert paused == set()
    settle_all(adv, rec["new_rows"], {}, obs, paused=paused)
    adv.atomic_commit()
    return adv


def run_gapped_backfill(out, full, action="LONG", entry=100.0,
                        holding=2000, obs2="2026-09-10T02:35:00+00:00",
                        obs3="2026-09-10T02:36:00+00:00"):
    adv = arm_at_bar9(out, full, action=action, entry=entry,
                      holding=holding)
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    gaps_before = len(adv.exec_state.get("gaps", []))
    gapped = drop_gap(full)
    rec = roll.reconcile_window(gapped, SYM, INT, obs2, adv.exec_state)
    assert len(rec["gaps"]) > gaps_before
    paused = roll.apply_validity_pause(
        adv, rec, rec["gaps"][gaps_before:], obs2)
    assert len(paused) > 0  # post-gap bars pause; pending preserved
    assert adv.strategy.operating.pending is not None
    settle_all(adv, rec["new_rows"], {}, obs2, paused=paused)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec2 = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                 obs3, adv.exec_state)
    paused2 = roll.apply_validity_pause(adv, rec2, [], obs3)
    assert paused2 == set()
    settle_all(adv, rec2["new_rows"], {}, obs3, paused=paused2)
    adv.atomic_commit()
    return adv


def assert_same_economics(ref, got):
    r, g = op_state(ref), op_state(got)
    assert g["equity"] == pytest.approx(r["equity"])
    assert g["rejected"] == r["rejected"]
    assert g["exits"] == r["exits"]
    assert (g["pending"] is None) == (r["pending"] is None)
    assert (g["open"] is None) == (r["open"] is None)
    if r["open"] is not None:
        assert g["open"]["entry_price"] == pytest.approx(
            r["open"]["entry_price"])
        assert g["open"]["entry_bar"] == r["open"]["entry_bar"]
        for k in ("remaining", "tp1_done", "gross", "fees", "funding"):
            assert g["open"][k] == pytest.approx(r["open"][k])
        # Same candle time -> same economic position in time.
        assert got.strategy.bar_close_by_idx[
            got.strategy.operating.open["entry_bar"]] == \
            ref.strategy.bar_close_by_idx[
                ref.strategy.operating.open["entry_bar"]]
    assert len(g["events"]) == len(r["events"])
    for ge, re_ in zip(g["events"], r["events"]):
        assert ge["reason"] == re_["reason"]
        assert ge["price"] == pytest.approx(re_["price"])
    # Deterministic fill/intent IDs derive from candle times + prices.
    assert got.strategy.fills == ref.strategy.fills
    assert got.strategy.intents == ref.strategy.intents


@pytest.mark.parametrize("action", ["LONG", "SHORT"])
def test_full_backfill_matches_uninterrupted(action, patched_identity,
                                             tmp_path):
    """Codex counterexample 1, LONG and SHORT with an open position."""
    full = candles(30)
    entry = 100.0 if action == "LONG" else 100.1
    ref = run_reference(tmp_path / f"ref_{action}", full, action=action,
                        entry=entry)
    assert ref.strategy.operating.open is not None  # filled on bar10
    assert ref.strategy.operating.equity == pytest.approx(99.98)
    got = run_gapped_backfill(tmp_path / f"gap_{action}", full,
                              action=action, entry=entry)
    assert_same_economics(ref, got)


def test_pending_preserved_through_backfill(patched_identity, tmp_path):
    """Far-entry pending never fills: preserved intact, no expiry."""
    full = candles(20)  # through bar19: inside the 12-bar window (last=21)
    ref = run_reference(tmp_path / "ref_pend", full, entry=50.0,
                        obs="2026-09-10T01:45:00+00:00")
    assert ref.strategy.operating.pending is not None
    assert ref.strategy.operating.open is None
    got = run_gapped_backfill(tmp_path / "gap_pend", full, entry=50.0,
                              obs2="2026-09-10T01:45:00+00:00",
                              obs3="2026-09-10T01:46:00+00:00")
    assert_same_economics(ref, got)
    assert got.strategy.operating.pending is not None


def test_tp1_partial_matches_through_backfill(patched_identity, tmp_path):
    """TP1 50% partial after a post-entry gap resolves identically."""
    patches = {16: {"high": 115.0, "close": 112.0},
               17: {"high": 115.0, "close": 112.0}}
    full = candles(30, patches=patches)
    ref = run_reference(tmp_path / "ref_tp1", full)
    # TP1 50% partials are non-final (no EXIT event record) but visible
    # on the open position + equity.
    assert ref.strategy.operating.open is not None
    assert ref.strategy.operating.open["tp1_done"] is True
    assert ref.strategy.operating.open["remaining"] == pytest.approx(0.5)
    # Gap AFTER entry, before TP1: hide bars 13,14,15.
    out = tmp_path / "gap_tp1"
    adv = arm_at_bar9(out, full)
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    obs2 = "2026-09-10T02:35:00+00:00"
    gapped = full.drop(index=[13, 14, 15]).reset_index(drop=True)
    gaps_before = len(adv.exec_state.get("gaps", []))
    rec = roll.reconcile_window(gapped, SYM, INT, obs2, adv.exec_state)
    assert len(rec["gaps"]) > gaps_before
    paused = roll.apply_validity_pause(
        adv, rec, rec["gaps"][gaps_before:], obs2)
    settle_all(adv, rec["new_rows"], {}, obs2, paused=paused)
    adv.atomic_commit()
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    obs3 = "2026-09-10T02:36:00+00:00"
    rec2 = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                 obs3, adv.exec_state)
    paused2 = roll.apply_validity_pause(adv, rec2, [], obs3)
    assert paused2 == set()
    settle_all(adv, rec2["new_rows"], {}, obs3, paused=paused2)
    assert_same_economics(ref, adv)


def test_expiry_boundary_matches(patched_identity, tmp_path):
    """Entry window signal+1..signal+12: CANCEL lands on the same bar."""
    full = candles(40)
    ref = run_reference(tmp_path / "ref_exp", full, entry=50.0,
                        obs="2026-09-10T03:25:00+00:00")
    assert ref.strategy.operating.pending is None
    assert ref.strategy.operating.rejected == 1
    cancel_bar = [e.get("bar_time") for e in
                  ref.strategy.operating.events
                  if e.get("reason") == "expired"]
    got = run_gapped_backfill(tmp_path / "gap_exp", full, entry=50.0,
                              obs2="2026-09-10T03:25:00+00:00",
                              obs3="2026-09-10T03:26:00+00:00")
    # Extend both through bar39 so expiry CANCEL is reached identically.
    assert_same_economics(ref, got)


def test_timeout_boundary_matches(patched_identity, tmp_path):
    """holding=5: timeout exit lands on the same candle time."""
    full = candles(30)
    ref = run_reference(tmp_path / "ref_to", full, holding=5)
    reasons = [e.get("reason") for e in
               ref.strategy.operating.events]
    assert "time" in reasons
    got = run_gapped_backfill(tmp_path / "gap_to", full, holding=5)
    assert_same_economics(ref, got)


def test_chunked_duplicated_restarted_matches(patched_identity, tmp_path):
    """Identical data chunked, duplicated and restarted == one-shot."""
    full = candles(30)
    obs = "2026-09-10T02:35:00+00:00"
    one = tmp_path / "one"
    adv = fresh_adv(one, full, obs)
    rec = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                obs, adv.exec_state)
    settle_all(adv, rec["new_rows"], {}, obs)
    adv.atomic_commit()
    ref_state = op_state(adv)
    ref_idx = dict(adv.strategy.bar_close_by_idx)

    out = tmp_path / "chunk"
    adv2 = fresh_adv(out, full.iloc[:10], obs)
    for end in (10, 20, 30):
        start = end - 10
        chunk = full.iloc[start:end].reset_index(drop=True)
        if end > 10:
            adv2 = roll.RollingAdvisor.resume(
                out, ROLL_CFG, ADV_CFG, SPEC)
        rec2 = roll.reconcile_window(chunk, SYM, INT, obs,
                                     adv2.exec_state)
        settle_all(adv2, rec2["new_rows"], {}, obs)
        adv2.atomic_commit()
        # Duplicated delivery of the same chunk: clean noop.
        adv_d = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
        recd = roll.reconcile_window(chunk, SYM, INT, obs,
                                     adv_d.exec_state)
        assert recd["new_rows"] == []
    got_state = op_state(adv2)
    assert got_state["equity"] == pytest.approx(ref_state["equity"])
    assert got_state["exits"] == ref_state["exits"]
    assert dict(adv2.strategy.bar_close_by_idx) == ref_idx
