"""R79 Track-A: gaps / revisions / invalid bars fail closed.

MOCK-mechanics only (synthetic candles + stub-like raw fixtures, no
network/model/training). Rules under test (r79_roll/1):

- Gaps: fail closed with pause. New rows at/after an unresolved gap
  boundary are PAUSED (no economic settlement, no actionable intents, no
  gate consumption); the pause persists until verified backfill (a seen
  open strictly inside the missing range). Missing bars are NEVER
  synthesized; positions NEVER settle through unobserved price paths.
  Covers empty AND open portfolios; backfill recovers without duplicates.
- Revisions: settled records kept (no silent overwrite, no re-settlement);
  an ingest carrying revisions forces the whole ingest diagnostic-only
  (revised bytes never reach inference silently).
- Invalid bars (non-finite, forming, empty): excluded from settlement AND
  from the inference frame; empty ingests are clean noops.
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
    geo = {"direction": s, "entry_limit": entry, "stop_loss": 95.0,
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


def fresh_adv(out, df, observed_at):
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    adv.begin(roll.fresh_shadow_start(df, observed_at), observed_at)
    return adv


def settle(adv, new_rows, raws, observed_at, paused=frozenset(),
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


def journal_t(out, adv, kind):
    _ = out  # journal lives under adv.out; scan in-memory via file
    recs = []
    jl = adv.out / "journal.jsonl"
    if jl.exists():
        for line in jl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("t") == kind:
                recs.append(r)
    return recs


def drop_full_gap(df):
    """Remove bars 10,11,12 -> a 4-bar step (gap of 3 missing bars)."""
    return df.drop(index=[10, 11, 12]).reset_index(drop=True)


def test_gap_empty_portfolio_pauses_and_recovers(patched_identity, tmp_path):
    out = tmp_path / "gap_empty"
    full = candles(20)
    gapped = drop_full_gap(full)
    obs = "2026-09-10T01:45:00+00:00"
    adv = fresh_adv(out, gapped, obs)
    gaps_before = 0
    rec = roll.reconcile_window(gapped, SYM, INT, obs, adv.exec_state)
    assert len(rec["gaps"]) == 1 and rec["gaps"][0]["missing_bars"] == 3
    paused = roll.apply_validity_pause(
        adv, rec, rec["gaps"][gaps_before:], obs)
    # Post-gap bars paused; pre-gap bars settle economically (empty book:
    # nothing can move, but no intent may arm across the gap either).
    rows = dict(rec["new_rows"])
    latest = max(rows)
    raws = {latest: mock_raw(rows[latest]["close_time"], "LONG")}
    statuses = settle(adv, rec["new_rows"], raws, obs, paused=paused)
    by_status = {}
    for s in statuses:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    assert by_status.get("PAUSED", 0) == len(paused) == 7
    assert adv.counts["paused_bars"] == 7
    assert len(adv.strategy.intents) == 0
    assert len(adv.strategy.fills) == 0
    assert adv.strategy.operating.equity == pytest.approx(100.0)
    assert adv.strategy.counters["operating_admitted"] == 0
    v = adv.exec_state["validity"]
    assert v["paused"] is True and len(v["unresolved_gaps"]) == 1
    settled_idx = set(adv.strategy.bar_close_by_idx)
    assert not (set(paused) & settled_idx)  # paused never settled
    adv.atomic_commit()
    # Verified backfill: resume with the COMPLETE window.
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec2 = roll.reconcile_window(full, SYM, INT, obs, adv2.exec_state)
    assert len(rec2["new_rows"]) == 3 + 7  # missing + replay, original idx
    paused2 = roll.apply_validity_pause(adv2, rec2, [], obs)
    assert paused2 == set()
    assert adv2.exec_state["validity"]["paused"] is False
    settle(adv2, rec2["new_rows"], {}, obs, paused=paused2)
    assert len(adv2.strategy.intents) == 0
    assert adv2.strategy.operating.equity == pytest.approx(100.0)
    # Exactly-once: journal status/diagnostic exec_idx unique, no dupes.
    idxs = ([r.get("exec_idx") for r in
             journal_t(out, adv2, "status")]
            + [r.get("exec_idx") for r in
               journal_t(out, adv2, "diagnostic")])
    assert len(idxs) == len(set(idxs)) == 20
    assert len(adv2.strategy.bar_close_by_idx) == 20


def test_gap_open_portfolio_never_settles_through(patched_identity,
                                                 tmp_path):
    out = tmp_path / "gap_open"
    full = candles(20)
    obs1a = "2026-09-10T00:46:00+00:00"  # after bar8 close (fresh bootstrap)
    obs1b = "2026-09-10T00:51:00+00:00"  # after bar9 close (streaming arm)
    # Phase 1: fresh bootstrap on bars 0..8 (all diagnostic by design).
    adv = fresh_adv(out, full.iloc[:9], obs1a)
    w1a = full.iloc[:9].reset_index(drop=True)
    rec1a = roll.reconcile_window(w1a, SYM, INT, obs1a, adv.exec_state)
    settle(adv, rec1a["new_rows"], {}, obs1a)
    adv.atomic_commit()
    # Phase 2: resume with bar 9 as the single latest new bar -> actionable
    # MOCK LONG (entry 100.0 fills on the next bar) arms a pending.
    adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    w1b = full.iloc[:10].reset_index(drop=True)
    rec1b = roll.reconcile_window(w1b, SYM, INT, obs1b, adv.exec_state)
    assert len(rec1b["new_rows"]) == 1
    rows1 = dict(rec1b["new_rows"])
    latest1 = max(rows1)
    raws1 = {latest1: mock_raw(rows1[latest1]["close_time"], "LONG")}
    settle(adv, rec1b["new_rows"], raws1, obs1b)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    # Phase 2: window jumps over bars 10..12 (gap of 3). The pending would
    # fill on bar10 in a complete feed; through the gap NOTHING may settle.
    gapped = pd.concat([full.iloc[:10], full.iloc[13:20]],
                       ignore_index=True)
    obs2 = "2026-09-10T01:45:00+00:00"
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    gaps_before = len(adv2.exec_state.get("gaps", []))
    rec2 = roll.reconcile_window(gapped, SYM, INT, obs2, adv2.exec_state)
    assert len(rec2["gaps"]) > gaps_before
    paused2 = roll.apply_validity_pause(
        adv2, rec2, rec2["gaps"][gaps_before:], obs2)
    assert len(paused2) == 7  # bars 13..19 all paused
    rows2 = dict(rec2["new_rows"])
    latest2 = max(rows2)
    raws2 = {latest2: mock_raw(rows2[latest2]["close_time"], "SHORT")}
    settle(adv2, rec2["new_rows"], raws2, obs2, paused=paused2)
    # Pending preserved untouched; no exit/fill across unobserved bars;
    # the post-gap SHORT never armed; equity untouched.
    assert adv2.strategy.operating.pending is not None
    assert adv2.strategy.operating.open is None
    assert len(adv2.strategy.fills) == 0
    assert len(adv2.strategy.intents) == 2  # phase-1 arms only
    assert adv2.strategy.operating.equity == pytest.approx(100.0)
    for ev in adv2.strategy.operating.events:
        bar_t = core._ts(ev.get("bar_time", "1970-01-01T00:00:00Z"))
        assert not (core._ts("2026-09-10T00:50:00+00:00") < bar_t
                    < core._ts("2026-09-10T01:05:00+00:00")), \
            "settled through the unobserved gap"
    adv2.atomic_commit()
    # Phase 3: backfill completes the window; pending fills on bar10, stays
    # open (flat bars hit no stop/TP); exactly-once, pause lifted.
    adv3 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec3 = roll.reconcile_window(full, SYM, INT, obs2, adv3.exec_state)
    paused3 = roll.apply_validity_pause(adv3, rec3, [], obs2)
    assert paused3 == set()
    settle(adv3, rec3["new_rows"], {}, obs2, paused=paused3)
    assert adv3.exec_state["validity"]["paused"] is False
    assert adv3.strategy.operating.pending is None
    assert adv3.strategy.operating.open is not None  # filled on bar10
    # Time-correctness (not counter-correctness: exec_idx is first-seen
    # order, so the backfilled time-bar10 carries a later counter value):
    # the fill landed on the now-observed time-bar10 at the limit price.
    inv = {v: k for k, v in adv3.strategy.bar_close_by_idx.items()}
    assert adv3.strategy.operating.open["entry_bar"] == inv[
        "2026-09-10T00:55:00+00:00"]
    assert adv3.strategy.operating.open["entry_price"] == pytest.approx(
        100.0)
    idxs = ([r.get("exec_idx") for r in journal_t(out, adv3, "status")]
            + [r.get("exec_idx") for r in journal_t(out, adv3,
                                                   "diagnostic")])
    assert len(idxs) == len(set(idxs))
    assert len(adv3.strategy.bar_close_by_idx) == 20


def test_revision_forces_ingest_diagnostic(patched_identity, tmp_path):
    out = tmp_path / "rev"
    df = candles(10)
    obs1 = "2026-09-10T01:00:00+00:00"
    adv = fresh_adv(out, df, obs1)
    rec = roll.reconcile_window(df, SYM, INT, obs1, adv.exec_state)
    settle(adv, rec["new_rows"], {}, obs1)
    adv.atomic_commit()
    # Revised window: bar5 OHLC changed + 2 genuinely new bars. The new-bar
    # MOCK LONG is timely and latest, yet the ingest is contaminated.
    rev = candles(12, patches={5: {"close": 999.0, "high": 999.0}})
    obs2 = "2026-09-10T01:05:00+00:00"
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    rec2 = roll.reconcile_window(rev, SYM, INT, obs2, adv2.exec_state)
    assert len(rec2["revised"]) == 1 and len(rec2["new_rows"]) == 2
    rows = dict(rec2["new_rows"])
    latest = max(rows)
    raws = {latest: mock_raw(rows[latest]["close_time"], "LONG")}
    statuses = settle(adv2, rec2["new_rows"], raws, obs2, revision=True)
    raw_status = [s["status"] for s in statuses]
    # The decision bar refuses as revision-contaminated; the decision-less
    # bar settles OFF_CLOCK economically (no intent possible there).
    assert raw_status.count(core.STATUS_DIAGNOSTIC) == 1
    assert raw_status.count(core.STATUS_OFF_CLOCK) == 1
    assert adv2.counts["revision_forced_diagnostic"] == 1
    snap = adv2.build_snapshot("mock", "mock", len(rev), {}, obs2,
                               {"kind": "MOCK"}, {}, {})
    assert snap["actionable_count"] == 0
    # Settled record kept: no re-settlement, no fills, no new intents.
    assert len(adv2.strategy.intents) == 0
    assert len(adv2.strategy.fills) == 0
    assert adv2.strategy.operating.equity == pytest.approx(100.0)


def test_invalid_bars_excluded_and_empty_noop(patched_identity, tmp_path):
    out = tmp_path / "invalid"
    df = candles(6, patches={2: {"close": float("nan")}})
    # Forming tail: close beyond observed_at.
    df.loc[5, "close_time"] = pd.Timestamp("2026-09-10T05:00:00Z")
    obs = "2026-09-10T00:30:00+00:00"
    adv = fresh_adv(out, df, obs)
    rec = roll.reconcile_window(df, SYM, INT, obs, adv.exec_state)
    assert len(rec["nonfinite"]) == 1 and len(rec["forming"]) == 1
    assert len(rec["new_rows"]) == 4
    clean, report = roll.sanitize_inference_frame(df, obs)
    assert report["nonfinite_dropped"] == 1
    assert report["forming_dropped"] == 1
    assert len(clean) == 4
    settle(adv, rec["new_rows"], {}, obs)
    assert adv.strategy.operating.equity == pytest.approx(100.0)
    # Empty frame: clean noop, no crash, nothing settled.
    empty = df.iloc[0:0].reset_index(drop=True)
    rec0 = roll.reconcile_window(empty, SYM, INT, obs, adv.exec_state)
    assert rec0["new_rows"] == [] and rec0["gaps"] == adv.exec_state["gaps"]
    clean0, rep0 = roll.sanitize_inference_frame(empty, obs)
    assert rep0["output_rows"] == 0 and len(clean0) == 0
