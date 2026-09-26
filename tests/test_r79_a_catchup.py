"""R79 Track-A: resume/catch-up missed-clock + pending/open preservation.

MOCK-mechanics only (synthetic candles + stub-like raw fixtures, no
network/model/training). Rules under test (r79_roll/1, diagnostic-only
choice -- NO delayed-entry policy shipped):

- Only decisions ON the latest new bar of an ingest may be actionable.
  Earlier catch-up decisions are missed-clock DIAGNOSTIC-only, independently
  of the 24-bar staleness outer bound (a 2h age rule alone cannot authorize
  retroactive next-bar fills).
- Already-observed pending/open positions settle causally through catch-up
  bars (observe_bar with raw=None); historical fills never rewritten.
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
ROLL_CFG = json.loads((ROOT / "configs/opencode_r79_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()


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


def mock_raw(close_time, action, entry=100.0):
    s = 1 if action == "LONG" else -1
    geo = {"direction": s, "entry_limit": entry, "stop_loss": 40.0,
           "take_profit_1": 110.0, "take_profit_2": 120.0,
           "holding_bars": 2000, "leverage": 1.0,
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
            "configs/opencode_r79_roll.json",
            "configs/opencode_r76_infer.json")
            if (ROOT / rel).exists()]
    monkeypatch.setattr(roll, "collect_identity_files", _collect)
    return _collect


def settle_batch(adv, new_rows, raws, observed_at):
    """Settle like main(): one shared batch-latest anchor for the ingest."""
    latest = max(core._ts(r["close_time"]) for _, r in
                 new_rows).isoformat() if new_rows else None
    out = []
    for exec_idx, row in new_rows:
        out.extend(adv.settle_new(
            [(exec_idx, row)],
            {exec_idx: raws[exec_idx]} if exec_idx in raws else {},
            observed_at, batch_latest_close_iso=latest,
            paused_exec=set(), revision_contaminated=False))
    return out


def test_missed_clock_only_latest_actionable(patched_identity, tmp_path):
    out = tmp_path / "catchup"
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    df1 = candles(30)
    obs1 = "2026-09-10T02:35:00+00:00"
    adv.begin(roll.fresh_shadow_start(df1, obs1), obs1)
    rec1 = roll.reconcile_window(df1, SYM, INT, obs1, adv.exec_state)
    settle_batch(adv, rec1["new_rows"], {}, obs1)
    adv.atomic_commit()
    # Catch-up: 5 new bars, MOCK LONG on EVERY new bar (all timely: <30min
    # old, so staleness cannot mask the missed-clock rule).
    df2 = candles(35)
    obs2 = "2026-09-10T02:56:00+00:00"
    rec2 = roll.reconcile_window(df2, SYM, INT, obs2, adv.exec_state)
    assert len(rec2["new_rows"]) == 5
    row_by_exec = {e: r for e, r in rec2["new_rows"]}
    raws = {e: mock_raw(r["close_time"], "LONG")
            for e, r in row_by_exec.items()}
    statuses = settle_batch(adv, rec2["new_rows"], raws, obs2)
    diags = [s for s in statuses if s["status"] == core.STATUS_DIAGNOSTIC]
    assert len(diags) == 4
    assert adv.counts["missed_clock_diagnostic"] == 4
    snap = adv.build_snapshot("mock", "mock", len(df2), {}, obs2,
                              {"kind": "MOCK"}, {}, {})
    # Only the latest new bar armed: exactly one actionable LONG.
    assert snap["actionable_count"] == 1
    assert len(adv.strategy.intents) == 2  # control + operating, latest only
    latest_close = core._ts(
        row_by_exec[max(row_by_exec)]["close_time"]).isoformat()
    for intent in adv.strategy.intents.values():
        assert intent["signal_time"] == latest_close
    # No retroactive fills from missed-clock bars (latest arms a pending
    # with no later bar in-window): no fills, equity untouched.
    assert len(adv.strategy.fills) == 0
    assert adv.strategy.operating.equity == pytest.approx(100.0)
    assert adv.strategy.control.equity == pytest.approx(100.0)
    assert any("missed-clock" in (d.get("note") or "")
               for d in adv.strategy.diagnostics)


def test_stale_outer_bound_still_binds(patched_identity, tmp_path):
    out = tmp_path / "stale"
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    df1 = candles(10)
    obs1 = "2026-09-10T01:00:00+00:00"
    adv.begin(roll.fresh_shadow_start(df1, obs1), obs1)
    rec1 = roll.reconcile_window(df1, SYM, INT, obs1, adv.exec_state)
    settle_batch(adv, rec1["new_rows"], {}, obs1)
    # One new bar observed 3h after its close: it IS the latest (no
    # missed-clock) but is older than 24 bars -> stale diagnostic.
    df2 = candles(11)
    new_close = core._ts(df2["close_time"].iloc[-1])
    obs2 = (new_close + pd.Timedelta(hours=3)).isoformat()
    rec2 = roll.reconcile_window(df2, SYM, INT, obs2, adv.exec_state)
    assert len(rec2["new_rows"]) == 1
    e, r = rec2["new_rows"][0]
    st = settle_batch(adv, [(e, r)], {e: mock_raw(r["close_time"], "LONG")},
                      obs2)
    assert st[0]["status"] == core.STATUS_DIAGNOSTIC
    assert adv.counts["stale_forced_diagnostic"] == 1
    assert adv.counts["missed_clock_diagnostic"] == 0
    assert len(adv.strategy.intents) == 0


def _phase(adv, df, observed_at, raws):
    rec = roll.reconcile_window(df, SYM, INT, observed_at, adv.exec_state)
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"][0:0],
                                       observed_at)
    assert paused == set()
    return settle_batch(adv, rec["new_rows"], raws, observed_at)


def test_pending_preserved_through_catchup_with_parity(patched_identity,
                                                      tmp_path):
    """r79 end-to-end: fresh bootstrap (all diagnostic) -> resume catch-up
    arms ONE pending on the latest bar -> resume catch-up settles it to
    expiry CANCEL. Restarted run must equal the uninterrupted run."""
    full = candles(40)
    obs1 = "2026-09-10T01:20:00+00:00"    # after bar14 close 01:15
    obs2 = "2026-09-10T01:45:00+00:00"    # after bar19 close 01:40
    obs3 = "2026-09-10T03:25:00+00:00"    # after bar39 close 03:20

    def run_stream(out, do_resume):
        adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
        adv.begin(roll.fresh_shadow_start(full.iloc[:15], obs1), obs1)
        _phase(adv, full.iloc[:15].reset_index(drop=True), obs1, {})
        adv.atomic_commit()
        if do_resume:
            adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
        # Only the latest new bar (19) carries a MOCK: far-entry LONG stays
        # pending (entry 50 never touched), earlier new bars are missed-clock.
        w2 = full.iloc[:20].reset_index(drop=True)
        rec = roll.reconcile_window(w2, SYM, INT, obs2, adv.exec_state)
        latest = max(e for e, _ in rec["new_rows"])
        rows = dict(rec["new_rows"])
        # Earlier new bars carry fill-guaranteed MOCK LONGs: they must ALL
        # refuse as missed-clock (no retroactive fills). Only the latest
        # new bar (19) carries the far-entry LONG that arms a pending.
        raws = {e: mock_raw(r["close_time"], "LONG", entry=100.0)
                for e, r in rows.items() if e != latest}
        raws[latest] = mock_raw(rows[latest]["close_time"], "LONG",
                                entry=50.0)
        settle_batch(adv, rec["new_rows"], raws, obs2)
        assert adv.counts["missed_clock_diagnostic"] == len(rows) - 1
        assert adv.strategy.operating.pending is not None
        adv.atomic_commit()
        if do_resume:
            adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
            assert adv.strategy.operating.pending is not None
        _phase(adv, full.reset_index(drop=True), obs3, {})
        return adv

    ref = run_stream(tmp_path / "ref", do_resume=False)
    restarted = run_stream(tmp_path / "rst", do_resume=True)
    # Expiry CANCEL preserved through the restart (entry window 12 bars).
    assert ref.strategy.control.rejected == 1
    assert restarted.strategy.control.rejected == 1
    assert restarted.strategy.intents == ref.strategy.intents
    assert restarted.strategy.fills == ref.strategy.fills
    assert restarted.strategy.decision_log == ref.strategy.decision_log
    assert restarted.strategy.counters == ref.strategy.counters
    assert restarted.strategy.operating.equity == pytest.approx(
        ref.strategy.operating.equity)
    assert restarted.strategy.control.equity == pytest.approx(
        ref.strategy.control.equity)
    assert restarted.counts["missed_clock_diagnostic"] == ref.counts[
        "missed_clock_diagnostic"] > 0
    snap = restarted.build_snapshot("mock", "mock", len(full), {}, obs3,
                                    {"kind": "MOCK"}, {}, {})
    assert snap["actionable_count"] == 1  # only bar-19 LONG ever armed
