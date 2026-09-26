"""R80 Track-A: complete validity recovery (Codex counterexample 2 + scope).

MOCK-mechanics only (synthetic candles + stub-like raw fixtures, no
network/model/training). Rules under test (r80_roll/1):

- A gap stays unresolved until EVERY expected valid closed candle on the
  absolute 5m grid is available (or the run is censored/invalid).
  Partial / out-of-order / overlapping backfills, repeated pauses and
  multiple restarts preserve the missing set + positions. Never settle
  past a still-missing price path.
- Invalid OHLC/grid/close-time data is NEVER marked seen/settled nor
  silently counted as settled.
- Revisions get a persistent validity decision; a diagnostic marker never
  erases uncertainty in an open position.
- Missed next-bar entry on stale/late feeds stays diagnostic-only (no
  delayed-execution policy shipped).

FAIL-BEFORE (r79): missing bars 10,11,12; receiving only bar10 sets
paused=False and unresolved_gaps=[], because apply_validity_pause tests
ANY seen open inside a gap instead of ALL expected valid timestamps.
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


def mock_raw(close_time, action, entry=100.0):
    s = 1 if action == "LONG" else -1
    if action == "LONG":
        geo = {"direction": s, "entry_limit": entry, "stop_loss": 95.0,
               "take_profit_1": 110.0, "take_profit_2": 120.0,
               "holding_bars": 2000, "leverage": 1.0,
               "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
               "conditional_win_score": 0.8}
    else:
        geo = {"direction": s, "entry_limit": entry, "stop_loss": 105.0,
               "take_profit_1": 90.0, "take_profit_2": 80.0,
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


def gap_scenario(out, obs="2026-09-10T01:45:00+00:00"):
    """Bars 0..19 less 10,11,12 -> paused gap ingest. Returns (adv, rec)."""
    full = candles(20)
    gapped = full.drop(index=[10, 11, 12]).reset_index(drop=True)
    adv = fresh_adv(out, gapped, obs)
    rec = roll.reconcile_window(gapped, SYM, INT, obs, adv.exec_state)
    assert len(rec["gaps"]) == 1 and rec["gaps"][0]["missing_bars"] == 3
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"], obs)
    return adv, rec, paused, full, obs


def test_partial_backfill_keeps_pause(patched_identity, tmp_path):
    """Codex counterexample 2: only bar10 of {10,11,12} -> still paused."""
    adv, rec, paused, full, obs = gap_scenario(tmp_path / "partial")
    assert len(paused) == 7
    settle_all(adv, rec["new_rows"], {}, obs, paused=paused)
    adv.atomic_commit()
    adv2 = roll.RollingAdvisor.resume(
        tmp_path / "partial", ROLL_CFG, ADV_CFG, SPEC)
    # Partial backfill: only bar10 returns.
    part = pd.concat([full.iloc[:11], full.iloc[13:]],
                     ignore_index=True)
    rec2 = roll.reconcile_window(part, SYM, INT, obs, adv2.exec_state)
    paused2 = roll.apply_validity_pause(adv2, rec2, [], obs)
    v = adv2.exec_state["validity"]
    assert v["paused"] is True
    assert len(v["unresolved_gaps"]) == 1
    missing = v["unresolved_gaps"][0].get("missing_opens", [])
    assert len(missing) == 2  # bars 11,12 still absent
    assert len(paused2) > 0  # post-gap bars stay paused
    settled = set(adv2.strategy.bar_close_by_idx)
    assert not (set(paused2) & settled)
    # Post-gap SHORT must not arm through the still-missing path.
    rows = dict(rec2["new_rows"])
    if rows:
        latest = max(rows)
        raws = {latest: mock_raw(rows[latest]["close_time"], "SHORT")}
        settle_all(adv2, rec2["new_rows"], raws, obs, paused=paused2)
    assert len(adv2.strategy.intents) == 0
    assert adv2.strategy.operating.equity == pytest.approx(100.0)


def test_out_of_order_backfill_resolves_only_when_complete(
        patched_identity, tmp_path):
    adv, rec, paused, full, obs = gap_scenario(tmp_path / "ooo")
    settle_all(adv, rec["new_rows"], {}, obs, paused=paused)
    adv.atomic_commit()
    out = tmp_path / "ooo"
    # Backfill 12 alone, then 10 alone: still paused each time.
    for keep in ([12], [10]):
        adv_r = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
        idx = [i for i in range(20) if i in keep or i < 10 or i >= 13]
        part = full.iloc[idx].reset_index(drop=True)
        rec_r = roll.reconcile_window(part, SYM, INT, obs,
                                      adv_r.exec_state)
        paused_r = roll.apply_validity_pause(adv_r, rec_r, [], obs)
        assert adv_r.exec_state["validity"]["paused"] is True
        settle_all(adv_r, rec_r["new_rows"], {}, obs, paused=paused_r)
        adv_r.atomic_commit()
    # Final missing bar 11 completes the set -> pause lifts.
    adv_f = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec_f = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                  obs, adv_f.exec_state)
    paused_f = roll.apply_validity_pause(adv_f, rec_f, [], obs)
    assert paused_f == set()
    assert adv_f.exec_state["validity"]["paused"] is False
    settle_all(adv_f, rec_f["new_rows"], {}, obs, paused=paused_f)
    assert len(adv_f.strategy.bar_close_by_idx) == 20


def test_overlapping_gaps_and_restarts_preserve_missing(
        patched_identity, tmp_path):
    out = tmp_path / "overlap"
    full = candles(30)
    obs = "2026-09-10T02:35:00+00:00"
    # Ingest 1: bars 0..19 less 10,11,12 -> gap A (pause 13..19).
    g1 = full.iloc[:20].drop(index=[10, 11, 12]).reset_index(drop=True)
    adv = fresh_adv(out, g1, obs)
    rec = roll.reconcile_window(g1, SYM, INT, obs, adv.exec_state)
    paused = roll.apply_validity_pause(adv, rec, rec["gaps"], obs)
    settle_all(adv, rec["new_rows"], {}, obs, paused=paused)
    adv.atomic_commit()
    # Ingest 2 (restart): extend to bar29 while hiding never-seen 20,21
    # alongside the still-missing 10,11,12 -> genuine second gap B.
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    g2 = full.drop(index=[10, 11, 12, 20, 21]).reset_index(drop=True)
    gaps_before = len(adv2.exec_state.get("gaps", []))
    rec2 = roll.reconcile_window(g2, SYM, INT, obs, adv2.exec_state)
    assert len(rec2["gaps"]) > gaps_before
    paused2 = roll.apply_validity_pause(
        adv2, rec2, rec2["gaps"][gaps_before:], obs)
    assert adv2.exec_state["validity"]["paused"] is True
    assert len(adv2.exec_state["validity"]["unresolved_gaps"]) == 2
    settle_all(adv2, rec2["new_rows"], {}, obs, paused=paused2)
    adv2.atomic_commit()
    # Ingest 3 (restart): backfill gap A only -> gap B persists.
    adv3 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    g3 = full.drop(index=[20, 21]).reset_index(drop=True)
    rec3 = roll.reconcile_window(g3, SYM, INT, obs, adv3.exec_state)
    paused3 = roll.apply_validity_pause(adv3, rec3, [], obs)
    assert adv3.exec_state["validity"]["paused"] is True
    assert len(adv3.exec_state["validity"]["unresolved_gaps"]) == 1
    settle_all(adv3, rec3["new_rows"], {}, obs, paused=paused3)
    adv3.atomic_commit()
    # Ingest 4: complete window -> all resolved, 30 bars settled once.
    adv4 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec4 = roll.reconcile_window(full.reset_index(drop=True), SYM, INT,
                                 obs, adv4.exec_state)
    paused4 = roll.apply_validity_pause(adv4, rec4, [], obs)
    assert paused4 == set()
    assert adv4.exec_state["validity"]["paused"] is False
    settle_all(adv4, rec4["new_rows"], {}, obs, paused=paused4)
    assert len(adv4.strategy.bar_close_by_idx) == 30


def test_invalid_bars_never_seen_or_settled(patched_identity, tmp_path):
    out = tmp_path / "invalid"
    obs = "2026-09-10T00:30:00+00:00"
    df = candles(8)
    # Corrupt one bar each way: OHLC inconsistency, off-grid open,
    # wrong close-time, non-finite, NaT open.
    df.loc[2, "high"] = 50.0  # high < low/open/close
    df.loc[3, "open_time"] = pd.Timestamp("2026-09-10T00:16:30Z")  # off-grid
    df.loc[4, "close_time"] = pd.Timestamp("2026-09-10T00:26:00Z")  # != +5m
    df.loc[5, "close"] = float("nan")
    df.loc[6, "open_time"] = pd.NaT
    adv = fresh_adv(out, df, obs)
    rec = roll.reconcile_window(df, SYM, INT, obs, adv.exec_state)
    n_invalid = len(rec.get("invalid", [])) + len(rec["nonfinite"])
    assert n_invalid >= 4
    seen_opens = {k.rsplit("|", 1)[1] for k in adv.exec_state["seen"]}
    for bad_open in ("2026-09-10T00:10:00+00:00",  # row2 OHLC-bad
                     "2026-09-10T00:16:30+00:00",  # row3 off-grid
                     "2026-09-10T00:20:00+00:00"):  # row4 close-time-bad
        assert bad_open not in seen_opens
    assert len(rec["new_rows"]) <= 3  # only genuinely valid bars
    clean, report = roll.sanitize_inference_frame(df, obs)
    assert report["output_rows"] <= 3
    settle_all(adv, rec["new_rows"], {}, obs)
    assert adv.strategy.operating.equity == pytest.approx(100.0)
    assert adv.counts["settled"] == len(rec["new_rows"])


def test_revision_with_open_position_persists(patched_identity, tmp_path):
    out = tmp_path / "revopen"
    full = candles(20)
    # Two-phase arm (fresh bootstrap is diagnostic-only by design):
    # bootstrap 0..8, then resume with bar9 as the single latest new bar.
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
    rows = dict(rec["new_rows"])
    latest = max(rows)
    raws = {latest: mock_raw(rows[latest]["close_time"], "LONG")}
    settle_all(adv, rec["new_rows"], raws, obs1b)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    # Settle through bar13 so the LONG fills on bar10 and is OPEN.
    obs2 = "2026-09-10T01:10:00+00:00"
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec2 = roll.reconcile_window(full.iloc[:14].reset_index(drop=True),
                                 SYM, INT, obs2, adv2.exec_state)
    settle_all(adv2, rec2["new_rows"], {}, obs2)
    assert adv2.strategy.operating.open is not None
    open_before = dict(adv2.strategy.operating.open)
    adv2.atomic_commit()
    # Revision ingest: bar5 OHLC changed + 2 new bars. Settled record kept,
    # whole ingest diagnostic-only, OPEN position untouched by the marker.
    rev = candles(16, patches={5: {"close": 999.0, "high": 999.0}})
    obs3 = "2026-09-10T01:20:00+00:00"
    adv3 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec3 = roll.reconcile_window(rev, SYM, INT, obs3, adv3.exec_state)
    assert len(rec3["revised"]) == 1
    assert len(adv3.exec_state["revisions"]) >= 1
    rows3 = dict(rec3["new_rows"])
    latest3 = max(rows3)
    raws3 = {latest3: mock_raw(rows3[latest3]["close_time"], "SHORT")}
    statuses = settle_all(adv3, rec3["new_rows"], raws3, obs3,
                          revision=True)
    assert core.STATUS_DIAGNOSTIC in [s["status"] for s in statuses]
    assert adv3.strategy.operating.open is not None
    assert adv3.strategy.operating.open["entry_price"] == pytest.approx(
        open_before["entry_price"])
    assert adv3.strategy.operating.open["entry_bar"] == \
        open_before["entry_bar"]
    # Revision decision persists in state (not erased by later ingests).
    adv3.atomic_commit()
    adv4 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    assert len(adv4.exec_state["revisions"]) >= 1


def test_stale_late_feed_stays_diagnostic(patched_identity, tmp_path):
    out = tmp_path / "stale"
    df1 = candles(10)
    obs1 = "2026-09-10T01:00:00+00:00"
    adv = fresh_adv(out, df1, obs1)
    rec1 = roll.reconcile_window(df1, SYM, INT, obs1, adv.exec_state)
    settle_all(adv, rec1["new_rows"], {}, obs1)
    # Late feed: 5 new bars arrive together; all but the latest are
    # missed-clock diagnostic even though all are within the 24-bar age
    # bound (latest-new-bar alone authorizes nothing backdated).
    df2 = candles(15)
    obs2 = "2026-09-10T01:16:00+00:00"
    rec2 = roll.reconcile_window(df2, SYM, INT, obs2, adv.exec_state)
    assert len(rec2["new_rows"]) == 5
    rows = {e: r for e, r in rec2["new_rows"]}
    raws = {e: mock_raw(r["close_time"], "LONG") for e, r in rows.items()}
    statuses = settle_all(adv, rec2["new_rows"], raws, obs2)
    diags = [s for s in statuses if s["status"] == core.STATUS_DIAGNOSTIC]
    assert len(diags) == 4
    assert adv.counts["missed_clock_diagnostic"] == 4
    assert len(adv.strategy.intents) == 2  # latest bar only
    # Far-stale single latest bar: stale outer bound binds independently.
    df3 = candles(16)
    obs3 = (core._ts(df3["close_time"].iloc[-1]) +
            pd.Timedelta(hours=3)).isoformat()
    rec3 = roll.reconcile_window(df3, SYM, INT, obs3, adv.exec_state)
    e, r = rec3["new_rows"][0]
    st = settle_all(adv, [(e, r)], {e: mock_raw(r["close_time"], "LONG")},
                    obs3)
    assert st[0]["status"] == core.STATUS_DIAGNOSTIC
    assert adv.counts["stale_forced_diagnostic"] == 1
