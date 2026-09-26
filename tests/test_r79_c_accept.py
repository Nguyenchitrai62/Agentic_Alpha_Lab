"""R79 Track-C: independent integrated acceptance (actual CLI + real settle path).

MOCK-mechanics only, explicitly labeled: synthetic candles (no network),
deterministic raw-inference fixtures (NOT model weights), controlled
observation clocks (stand-in for wall-clock availability instants).
Fails-before provenance: Codex leader_r78_bootstrap_repro (fresh backdate:
actionable LONG + historical fill + equity 99.98 on r78_roll/2 code) and
commit e0e79b6 (4/4 bootstrap tests failing pre-fix). These tests pin the
FIXED behavior and fail on reintroduction.

Scope: bootstrap LONG/SHORT, delayed catch-up (no retroactive fill, pending
preserved), gaps fail-closed (empty AND open portfolios) + backfill recovery
without duplication, per-ingest provenance on two shifted windows, pending
-> partial across restart with NONEMPTY decisions, revision contamination
with open portfolio. Real-checkpoint bounded anchors are PENDING-B (Track B
declared them; this file uses MOCK inference only).
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

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
T0 = pd.Timestamp("2026-09-10T00:00:00Z")  # fixed MOCK clock base
ROLL_CFG = json.loads((ROOT / "configs/opencode_r79_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()
ACC_DIR = Path("artifacts/research/opencode_r79/c_accept")


def candles(n, start=T0):
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "quote_volume": 1001.0,
                     "close_time": o + pd.Timedelta(minutes=5)})
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def mock_raw(close_time, action, entry=100.0, tp1=110.0):
    """MOCK-mechanics deterministic raw row (NOT model inference)."""
    s = 1 if action == "LONG" else -1
    geo = {"direction": s, "entry_limit": entry, "stop_loss": 40.0,
           "take_profit_1": tp1, "take_profit_2": 120.0,
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
            "htf_last_close_lte_decision": {}, "device": "test-mock-c"}


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


def settle_batch(adv, new_rows, raws, observed_at, paused=frozenset(),
                 rev=False):
    """Settle exactly like main(): one shared batch-latest anchor."""
    latest = (max(core._ts(r["close_time"]) for _, r in new_rows).isoformat()
              if new_rows else None)
    out = []
    for exec_idx, row in new_rows:
        out.extend(adv.settle_new(
            [(exec_idx, row)],
            {exec_idx: raws[exec_idx]} if exec_idx in raws else {},
            observed_at, batch_latest_close_iso=latest,
            paused_exec=set(paused), revision_contaminated=rev))
    return out


def reconcile(adv, df, observed_at):
    return roll.reconcile_window(df, SYM, INT, observed_at, adv.exec_state)


def snapshot(adv, n, observed_at):
    return adv.build_snapshot("mock", "mock", n, {}, observed_at,
                              {"kind": "MOCK"}, {}, {})


# ------------------------------------------------- CLI-level runs ---
def run_cli(monkeypatch, candles_path, out_rel, resume, fixture):
    """ACTUAL roll.main entry point; ONLY inference input is mocked."""
    import opencode_r78_roll as _roll_cli
    monkeypatch.setattr(core, "infer_full", fixture)
    argv = ["opencode_r78_roll.py", "--mode", "replay",
            "--config", "configs/opencode_r79_roll.json",
            "--candles", candles_path, "--out", out_rel]
    if resume:
        argv.append("--resume")
    old = sys.argv
    sys.argv = argv
    try:
        _roll_cli.main()
    finally:
        sys.argv = old
    return json.loads((ROOT / out_rel / "summary.json").read_text())


def recent_windows():
    now = pd.Timestamp.now(tz="UTC")
    end_close = now.floor("5min") - pd.Timedelta(minutes=10)
    start = end_close - pd.Timedelta(seconds=30 * 300)
    win_a = candles(30, start)
    extra = start + pd.Timedelta(seconds=30 * 300)
    last = {"open_time": extra, "open": 100.0, "high": 100.5, "low": 99.8,
            "close": 100.4, "volume": 10.0, "quote_volume": 1004.0,
            "close_time": extra + pd.Timedelta(minutes=5)}
    win_b = pd.concat([win_a.iloc[1:].reset_index(drop=True),
                       pd.DataFrame([last])], ignore_index=True)
    win_b["open_time"] = pd.to_datetime(win_b["open_time"], utc=True)
    win_b["close_time"] = pd.to_datetime(win_b["close_time"], utc=True)
    return win_a, win_b


def fake_fixture(decision_idx, side, **geo_kw):
    def _fake(df, spec=None, device=None, max_decisions=None):
        df = df.sort_values("open_time").reset_index(drop=True)
        if decision_idx is None:
            return []
        close_t = pd.to_datetime(df["close_time"], utc=True).iloc[
            decision_idx]
        return [{**mock_raw(close_t, side, **geo_kw),
                 "bar_index": int(decision_idx)}]
    return _fake


def ckpt_strategy(out_rel):
    out = ROOT / out_rel
    gen = int((out / "CURRENT").read_text().strip())
    return json.loads((out / f"checkpoint-{gen}.json").read_text())[
        "strategy"]


def test_c1_cli_bootstrap_long_diagnostic_only(monkeypatch, tmp_path):
    win_a, _ = recent_windows()
    acc = ROOT / ACC_DIR
    acc.mkdir(parents=True, exist_ok=True)
    rel = f"{ACC_DIR}/c_winA.parquet"
    win_a.to_parquet(ROOT / rel, index=False)
    out = f"{ACC_DIR}/c_boot_long"
    import shutil
    shutil.rmtree(ROOT / out, ignore_errors=True)
    summary = run_cli(monkeypatch, rel, out, False,
                      fake_fixture(27, "LONG"))
    assert summary["actionable_count"] == 0
    assert summary["diagnostic_count"] > 0
    assert summary["counts"].get("fills", 0) == 0 if "fills" in summary[
        "counts"] else True
    st = ckpt_strategy(out)
    assert st["intents"] == {}
    assert st["fills"] == {}
    assert st["operating"]["equity"] == pytest.approx(100.0)
    assert st["control"]["equity"] == pytest.approx(100.0)


def test_c2_cli_bootstrap_short_diagnostic_only(monkeypatch):
    rel = f"{ACC_DIR}/c_winA.parquet"
    out = f"{ACC_DIR}/c_boot_short"
    import shutil
    shutil.rmtree(ROOT / out, ignore_errors=True)
    summary = run_cli(monkeypatch, rel, out, False,
                      fake_fixture(27, "SHORT"))
    assert summary["actionable_count"] == 0
    st = ckpt_strategy(out)
    assert st["intents"] == {}
    assert st["operating"]["equity"] == pytest.approx(100.0)


def test_c3_cli_provenance_two_shifted_windows(monkeypatch):
    win_a, win_b = recent_windows()
    acc = ROOT / ACC_DIR
    acc.mkdir(parents=True, exist_ok=True)
    rel_a, rel_b = f"{ACC_DIR}/c_winA.parquet", f"{ACC_DIR}/c_winB.parquet"
    win_a.to_parquet(ROOT / rel_a, index=False)
    win_b.to_parquet(ROOT / rel_b, index=False)
    out = f"{ACC_DIR}/c_prov"
    import shutil
    shutil.rmtree(ROOT / out, ignore_errors=True)
    s1 = run_cli(monkeypatch, rel_a, out, False, fake_fixture(27, "LONG"))
    snaps1 = sorted((ROOT / out).glob("raw_ingest_*.parquet"))
    assert len(snaps1) == 1
    h1 = roll.sha_file(snaps1[0])
    assert s1["raw_candle_artifact"]["sha256"] == h1
    s2 = run_cli(monkeypatch, rel_b, out, True, fake_fixture(27, "LONG"))
    snaps2 = sorted((ROOT / out).glob("raw_ingest_*.parquet"))
    assert len(snaps2) == 2  # immutable per-ingest: never reused
    assert roll.sha_file(snaps1[0]) == h1  # first snapshot untouched
    new_snap = [p for p in snaps2 if p != snaps1[0]][0]
    assert s2["raw_candle_artifact"]["sha256"] == roll.sha_file(new_snap)
    assert s2["raw_candle_artifact"]["sha256"] != h1  # distinct bytes
    assert s2["raw_candle_artifact"]["first_open"] == core._ts(
        win_b["open_time"].iloc[0]).isoformat()
    assert s2["raw_candle_artifact"]["last_close"] == core._ts(
        win_b["close_time"].iloc[-1]).isoformat()
    manifest = (ROOT / out / "ingest_manifest.jsonl").read_text().splitlines()
    assert len(manifest) == 2
    m1, m2 = (json.loads(m) for m in manifest)
    assert m2["prev_sha256"] == m1["sha256"]
    assert m2["sha256"] == s2["raw_candle_artifact"]["sha256"]


def test_c4_cli_gap_pause_and_backfill(monkeypatch):
    win_a, _ = recent_windows()
    gapped = win_a.drop(index=[15]).reset_index(drop=True)
    acc = ROOT / ACC_DIR
    acc.mkdir(parents=True, exist_ok=True)
    rel_g, rel_f = (f"{ACC_DIR}/c_gap.parquet", f"{ACC_DIR}/c_gapfull.parquet")
    gapped.to_parquet(ROOT / rel_g, index=False)
    win_a.to_parquet(ROOT / rel_f, index=False)
    out = f"{ACC_DIR}/c_gap"
    import shutil
    shutil.rmtree(ROOT / out, ignore_errors=True)
    s1 = run_cli(monkeypatch, rel_g, out, False, fake_fixture(27, "LONG"))
    assert s1["status_counts"].get("PAUSED", 0) > 0
    assert s1["counts"].get("paused_bars", 0) > 0
    assert s1["actionable_count"] == 0
    assert s1["validity"]["paused"] is True
    s2 = run_cli(monkeypatch, rel_f, out, True, fake_fixture(29, "LONG"))
    assert s2["validity"]["paused"] is False
    dec = list((ROOT / out / "exports").glob("decisions.csv"))
    assert dec, "exports must exist after backfill"
    import csv
    with open(dec[0], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    bars = [r.get("bar_time") for r in rows]
    assert len(bars) == len(set(bars))  # no duplicated outputs
    st = ckpt_strategy(out)
    assert st["fills"] == {}


# --------------------------------------------- white-box clock ---
def test_c5_missed_clock_and_pending_preserved(patched_identity, tmp_path):
    """Delayed catch-up: earlier bars diagnostic (no retroactive fill);
    latest-bar LONG arms exactly one pending; pending survives restart."""
    full = candles(40)
    obs1 = "2026-09-10T01:20:00+00:00"
    obs2 = "2026-09-10T01:45:00+00:00"
    obs3 = "2026-09-10T03:25:00+00:00"

    def stream(out, do_resume):
        adv = fresh_adv(out, full.iloc[:15], obs1)
        rec = reconcile(adv, full.iloc[:15].reset_index(drop=True), obs1)
        settle_batch(adv, rec["new_rows"], {}, obs1)
        adv.atomic_commit()
        if do_resume:
            adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
        w2 = full.iloc[:20].reset_index(drop=True)
        rec = reconcile(adv, w2, obs2)
        rows = dict(rec["new_rows"])
        latest = max(rows)
        raws = {e: mock_raw(r["close_time"], "LONG", entry=100.0)
                for e, r in rows.items() if e != latest}
        raws[latest] = mock_raw(rows[latest]["close_time"], "LONG",
                                entry=50.0)
        settle_batch(adv, rec["new_rows"], raws, obs2)
        # 4 earlier new bars refused as missed-clock (entry 100 would fill).
        assert adv.counts["missed_clock_diagnostic"] == len(rows) - 1
        assert adv.strategy.operating.pending is not None
        assert adv.strategy.fills == {}
        adv.atomic_commit()
        if do_resume:
            adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
            assert adv.strategy.operating.pending is not None
        rec = reconcile(adv, full.reset_index(drop=True), obs3)
        settle_batch(adv, rec["new_rows"], {}, obs3)
        return adv

    ref = stream(tmp_path / "ref", False)
    rst = stream(tmp_path / "rst", True)
    assert rst.strategy.intents == ref.strategy.intents
    assert len(rst.strategy.intents) == 2  # control + operating, latest only
    assert rst.strategy.fills == ref.strategy.fills == {}
    assert rst.strategy.decision_log == ref.strategy.decision_log
    assert rst.strategy.operating.equity == pytest.approx(100.0)


def test_c6_partial_across_restart_nonempty(patched_identity, tmp_path):
    """Pending -> TP1 partial across a kill/restart: NONEMPTY decisions,
    exact parity with the uninterrupted run, no duplicated intents."""
    full = candles(40)
    obs1 = "2026-09-10T01:20:00+00:00"
    obs2 = "2026-09-10T01:45:00+00:00"  # after bar19 close
    obs3 = "2026-09-10T02:10:00+00:00"  # after bar24 close

    def stream(out, kill_before_tail):
        adv = fresh_adv(out, full.iloc[:15], obs1)
        rec = reconcile(adv, full.iloc[:15].reset_index(drop=True), obs1)
        settle_batch(adv, rec["new_rows"], {}, obs1)
        adv.atomic_commit()
        w2 = full.iloc[:20].reset_index(drop=True)
        rec = reconcile(adv, w2, obs2)
        rows = dict(rec["new_rows"])
        latest = max(rows)
        # Near-entry LONG (fills next bar) + TP1 inside the flat range so
        # the position goes partial on the following bars.
        raws = {latest: mock_raw(rows[latest]["close_time"], "LONG",
                                 entry=100.0, tp1=100.05)}
        settle_batch(adv, rec["new_rows"], raws, obs2)
        assert adv.strategy.operating.pending is not None
        adv.atomic_commit()
        if kill_before_tail:
            adv = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
            assert adv.strategy.operating.pending is not None
        rec = reconcile(adv, full.iloc[:25].reset_index(drop=True), obs3)
        settle_batch(adv, rec["new_rows"], {}, obs3)
        return adv

    ref = stream(tmp_path / "ref", False)
    rst = stream(tmp_path / "rst", True)
    # Non-vacuous: TP1 partial happened economically (fills journal only
    # records EXIT-kind account events, so assert on position state).
    assert ref.strategy.operating.open is not None
    assert ref.strategy.operating.open["tp1_done"] is True
    assert ref.strategy.operating.open["remaining"] == pytest.approx(0.5)
    assert ref.strategy.operating.open["entry_bar"] == 20
    assert rst.strategy.operating.open == ref.strategy.operating.open
    assert rst.strategy.intents == ref.strategy.intents
    assert len(rst.strategy.intents) == 2
    assert rst.strategy.decision_log == ref.strategy.decision_log
    assert rst.strategy.operating.equity == pytest.approx(
        ref.strategy.operating.equity)
    assert rst.strategy.control.equity == pytest.approx(
        ref.strategy.control.equity)


def test_c7_gap_open_pending_then_backfill(patched_identity, tmp_path):
    """Open pending + gap ingest: PAUSED, pending intact, no exits across
    the unobserved path; verified backfill clears validity, no duplicates."""
    out = tmp_path / "gapopen"
    full = candles(40)
    obs1 = "2026-09-10T01:20:00+00:00"
    obs2 = "2026-09-10T01:45:00+00:00"
    obs3 = "2026-09-10T02:10:00+00:00"
    obs4 = "2026-09-10T02:40:00+00:00"
    adv = fresh_adv(out, full.iloc[:15], obs1)
    rec = reconcile(adv, full.iloc[:15].reset_index(drop=True), obs1)
    settle_batch(adv, rec["new_rows"], {}, obs1)
    adv.atomic_commit()
    # Arm a far-entry pending on the latest bar of phase 2.
    w2 = full.iloc[:20].reset_index(drop=True)
    rec = reconcile(adv, w2, obs2)
    rows = dict(rec["new_rows"])
    latest = max(rows)
    settle_batch(adv, rec["new_rows"],
                 {latest: mock_raw(rows[latest]["close_time"], "LONG",
                                   entry=50.0)}, obs2)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    # Phase 3: gap ingest (drop one bar) with the pending open.
    w3 = full.iloc[:25].reset_index(drop=True)
    w3g = w3.drop(index=[22]).reset_index(drop=True)
    rec = reconcile(adv, w3g, obs3)
    new_gaps = [g for g in rec["gaps"]]
    paused = roll.apply_validity_pause(adv, rec, new_gaps, obs3)
    assert paused, "post-gap bars must pause with an open pending"
    st = settle_batch(adv, rec["new_rows"], {}, obs3, paused=paused)
    assert any(s["status"] == "PAUSED" for s in st)
    assert adv.strategy.operating.pending is not None  # intact
    assert adv.strategy.fills == {}  # no exits across unobserved path
    intents_before = dict(adv.strategy.intents)
    adv.atomic_commit()
    # Phase 4: verified backfill clears validity; no duplicated outputs.
    rec = reconcile(adv, w3, obs4)
    paused = roll.apply_validity_pause(adv, rec, [], obs4)
    st = settle_batch(adv, rec["new_rows"], {}, obs4, paused=paused)
    assert adv.strategy.operating.pending is not None
    assert adv.strategy.intents == intents_before
    assert adv.strategy.fills == {}
    snap = snapshot(adv, len(w3), obs4)
    assert snap["validity"]["paused"] is False


def test_c8_revision_open_pending_forces_diagnostic(patched_identity,
                                                   tmp_path):
    """Ingest carrying an OHLC revision on a settled bar: whole ingest
    diagnostic-only; open pending preserved; revised bytes never settle."""
    out = tmp_path / "revopen"
    full = candles(40)
    obs1 = "2026-09-10T01:20:00+00:00"
    obs2 = "2026-09-10T01:45:00+00:00"
    obs3 = "2026-09-10T02:10:00+00:00"
    adv = fresh_adv(out, full.iloc[:15], obs1)
    rec = reconcile(adv, full.iloc[:15].reset_index(drop=True), obs1)
    settle_batch(adv, rec["new_rows"], {}, obs1)
    adv.atomic_commit()
    w2 = full.iloc[:20].reset_index(drop=True)
    rec = reconcile(adv, w2, obs2)
    rows = dict(rec["new_rows"])
    latest = max(rows)
    settle_batch(adv, rec["new_rows"],
                 {latest: mock_raw(rows[latest]["close_time"], "LONG",
                                   entry=50.0)}, obs2)
    assert adv.strategy.operating.pending is not None
    adv.atomic_commit()
    # Phase 3: same window shifted +1 with a revised overlap bar + a MOCK
    # on the newest bar (would be actionable if the ingest were clean).
    w3 = full.iloc[1:26].reset_index(drop=True)
    w3.loc[10, "close"] = 101.7  # OHLC revision on a settled bar
    rec = reconcile(adv, w3, obs3)
    assert rec["revised"], "fixture must trigger the revision path"
    rows = dict(rec["new_rows"])
    latest = max(rows)
    st = settle_batch(adv, rec["new_rows"],
                      {latest: mock_raw(rows[latest]["close_time"], "LONG")},
                      obs3, rev=True)
    assert adv.counts.get("revision_forced_diagnostic", 0) >= 1
    assert adv.strategy.operating.pending is not None
    assert adv.strategy.fills == {}
    snap = snapshot(adv, len(w3), obs3)
    assert snap["actionable_count"] == 1  # only the phase-2 LONG ever armed
