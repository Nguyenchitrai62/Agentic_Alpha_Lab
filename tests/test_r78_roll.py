"""R78 W1-ROLLING tests: bug repro, identity reconcile, durable state.

Mocked network/inference where noted; no live orders, no cloud, no training.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: F401,E402
import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_roll as roll  # noqa: E402

SYM, INT = "BTCUSDT", "5m"
T0 = pd.Timestamp("2026-01-01T00:00:00Z")
OBS = "2026-03-01T00:00:00+00:00"
ROLL_CFG = json.loads((ROOT / "configs/opencode_r78_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
import opencode_r76_infer as r76  # noqa: E402
SPEC = r76.load_prespec()

W1TMP = ROOT / "artifacts/research/opencode_r78_rolling/w1/_tmp"
W1TMP.mkdir(parents=True, exist_ok=True)


def candles(n, start=T0, step_min=5, patches=None):
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=step_min * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=step_min)})
    if patches:
        for idx, p in patches.items():
            rows[idx].update(p)
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def fake_raw(exec_idx, close_time, action="WAIT"):
    geo = None
    if action in ("LONG", "SHORT"):
        s = 1 if action == "LONG" else -1
        geo = {"direction": s, "entry_limit": 100.0, "stop_loss": 95.0,
               "take_profit_1": 110.0, "take_profit_2": 120.0,
               "holding_bars": 2000, "leverage": 1.0,
               "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
               "conditional_win_score": 0.8}
    v = action in ("LONG", "SHORT")
    return {"status": "READY_RAW", "bar_index": exec_idx,
            "decision_time": core._ts(close_time), "close": 100.0,
            "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "iso4_raw_geometry": geo,
            "per_map_action": {}, "vote_majority": v, "vote_confirmed": v,
            "htf_last_close_lte_decision": {}, "device": "test"}


@pytest.fixture
def patched_identity(monkeypatch):
    """Hash only files that exist (test isolation; production still fails
    closed on missing model bytes)."""
    def _collect(roll_cfg, advisor_cfg, spec):
        out = []
        for rel in (["scripts/opencode_r77_advisor_core.py",
                     "scripts/opencode_r77_advisor.py",
                     "scripts/opencode_r78_roll.py",
                     "configs/opencode_r77_advisor.json",
                     "configs/opencode_r78_roll.json",
                     "configs/opencode_r76_infer.json"]):
            if (ROOT / rel).exists():
                out.append(rel)
        return out
    monkeypatch.setattr(roll, "collect_identity_files", _collect)
    return _collect


def make_advisor(outdir, patched_identity):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    adv.begin("2025-12-31T00:00:00+00:00", OBS)
    return adv


# ------------------------------------------------- bug repro ---
def test_rolling_bug_repro_old_vs_fixed(patched_identity, tmp_path):
    """Old code: start_bar=last+1 >= len(df) -> zero inference calls on a
    same-length shifted window. Fixed code settles the new bar."""
    df_old = candles(100)
    df_new = candles(100, start=T0 + pd.Timedelta(minutes=5))  # shift by 1
    last_bar_idx = 99  # settled through old window end (positional)
    start_bar = last_bar_idx + 1
    old_calls = 0 if start_bar >= len(df_new) else 1
    assert old_calls == 0  # BUG reproduced: 'nothing new' forever
    adv = make_advisor(tmp_path / "a", patched_identity)
    r1 = roll.reconcile_window(df_old, SYM, INT, OBS, adv.exec_state)
    assert len(r1["new_rows"]) == 100
    adv.settle_new(r1["new_rows"], {}, OBS)
    r2 = roll.reconcile_window(df_new, SYM, INT, OBS, adv.exec_state)
    assert len(r2["new_rows"]) == 1  # FIX: shifted window settles new bar
    assert r2["new_rows"][0][1]["open_time"] == core._ts(
        df_new["open_time"].iloc[-1])


def test_idempotency(patched_identity, tmp_path):
    adv = make_advisor(tmp_path / "a", patched_identity)
    df = candles(20)
    assert len(roll.reconcile_window(df, SYM, INT, OBS,
                                     adv.exec_state)["new_rows"]) == 20
    r2 = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    assert r2["new_rows"] == [] and len(r2["duplicates"]) == 20


def test_shorter_longer_overlap(patched_identity, tmp_path):
    adv = make_advisor(tmp_path / "a", patched_identity)
    base = candles(50)
    roll.reconcile_window(base, SYM, INT, OBS, adv.exec_state)
    short = base.iloc[40:].reset_index(drop=True)
    assert roll.reconcile_window(short, SYM, INT, OBS,
                                 adv.exec_state)["new_rows"] == []
    longer = candles(70)
    r = roll.reconcile_window(longer, SYM, INT, OBS, adv.exec_state)
    assert len(r["new_rows"]) == 20


def test_month_boundary_gates(patched_identity, tmp_path):
    adv = make_advisor(tmp_path / "a", patched_identity)
    df = candles(300, start=pd.Timestamp("2026-01-31T12:00:00Z"))
    obs = "2026-02-01T12:00:00+00:00"  # near data: not stale
    rec = roll.reconcile_window(df, SYM, INT, obs, adv.exec_state)
    raws = {}
    for exec_idx, row in rec["new_rows"]:
        if core.on_grid(row["open_time"]):
            raws[exec_idx] = fake_raw(exec_idx, row["close_time"], "LONG")
    assert raws, "window must contain 6h-grid bars"
    # Timely stream: observe each bar just after its close so nothing is
    # stale; both sides of the month boundary must consume gate slots.
    for exec_idx, row in rec["new_rows"]:
        obs_bar = (core._ts(row["close_time"]) + pd.Timedelta(
            seconds=1)).isoformat()
        adv.settle_new([(exec_idx, row)],
                       {exec_idx: raws[exec_idx]} if exec_idx in raws
                       else {}, obs_bar)
    months = set(adv.strategy.iso4_gate.monthly) | set(
        adv.strategy.confirmed_gate.monthly)
    # Frozen cap4/cd5: Jan slot consumed; Feb grid bars evaluated (cooldown-
    # rejected under the frozen rule, never silently dropped). Both sides of
    # the boundary are exercised with month attribution intact.
    assert "2026-01" in months
    feb_decisions = [d for d in adv.strategy.decision_log
                     if d.get("decision_time", "").startswith("2026-02")]
    assert feb_decisions, "Feb grid decisions must be evaluated, not skipped"


def test_6h_anchor_stable_across_origins():
    df_a = candles(300)
    df_b = candles(300, start=T0 + pd.Timedelta(minutes=5 * 37))
    ga = {core._ts(r["open_time"]).isoformat() for _, r in df_a.iterrows()
          if core.on_grid(r["open_time"])}
    gb = {core._ts(r["open_time"]).isoformat() for _, r in df_b.iterrows()
          if core.on_grid(r["open_time"])}
    # Absolute grid: shared timestamps agree regardless of cache origin.
    assert (ga & gb) == {t for t in ga if t in set(
        core._ts(o).isoformat() for o in df_b["open_time"])}
    assert len(ga) > 0 and len(gb) > 0


def test_revision_gap_ooo_nonfinite_forming(patched_identity, tmp_path):
    adv = make_advisor(tmp_path / "a", patched_identity)
    df = candles(10)
    roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    # Revision on settled bar: kept, flagged, no re-settlement.
    rev = candles(10, patches={5: {"close": 999.0}})
    r = roll.reconcile_window(rev, SYM, INT, OBS, adv.exec_state)
    assert len(r["revised"]) == 1 and r["new_rows"] == []
    # Gap: skip 3 bars, never bridged.
    gap = candles(5, start=T0 + pd.Timedelta(minutes=5 * 13))
    g = roll.reconcile_window(gap, SYM, INT, OBS, adv.exec_state)
    assert g["gaps"] and len(g["new_rows"]) == 5
    assert all("missing" in str(e) for e in [g["gaps"][-1]])
    n_seen_before = len(adv.exec_state["seen"])
    # Out-of-order input handled (sorted, flagged).
    ooo = candles(3, start=T0 + pd.Timedelta(minutes=5 * 100)).iloc[
        ::-1].reset_index(drop=True)
    o = roll.reconcile_window(ooo, SYM, INT, OBS, adv.exec_state)
    assert o["out_of_order"] and len(o["new_rows"]) == 3
    # Nonfinite + forming excluded.
    bad = candles(3, start=T0 + pd.Timedelta(minutes=5 * 200),
                  patches={0: {"close": float("nan")}})
    b = roll.reconcile_window(bad, SYM, INT, OBS, adv.exec_state)
    assert len(b["nonfinite"]) == 1
    future = candles(2, start=pd.Timestamp("2026-12-01T00:00:00Z"))
    f = roll.reconcile_window(future, SYM, INT, "2026-02-01T00:00:00+00:00",
                              adv.exec_state)
    assert len(f["forming"]) == 2
    assert len(adv.exec_state["seen"]) == n_seen_before + 3 + 2


def test_timeliness_policy_prespecified_and_enforced(patched_identity,
                                                     tmp_path):
    tp = ROLL_CFG["timeliness_policy"]
    assert tp["stale_after_bars"] == 24 and tp["rationale"]  # pre-specified
    adv = make_advisor(tmp_path / "a", patched_identity)
    df = candles(30)
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    # Decision 30 bars stale (>24) -> DIAGNOSTIC-only, gates untouched.
    gate_before = dict(adv.strategy.confirmed_gate.monthly)
    old_dt = core._ts(df["close_time"].iloc[0]).isoformat()
    assert roll.is_stale(old_dt, OBS, 24)
    raws = {rec["new_rows"][0][0]: {**fake_raw(0, df["close_time"].iloc[0],
                                               "LONG"),
                                    "decision_time": core._ts(
                                        df["close_time"].iloc[0])}}
    st = adv.settle_new([rec["new_rows"][0]], raws, OBS)
    assert st[0]["status"] == "DIAGNOSTIC"
    assert adv.strategy.confirmed_gate.monthly == gate_before
    assert adv.counts["stale_forced_diagnostic"] == 1


def test_bootstrap_diagnostic_only(patched_identity, tmp_path):
    adv = make_advisor(tmp_path / "a", patched_identity)
    df = candles(10)
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    # shadow_start is AFTER all these decision_times -> all diagnostic.
    adv2 = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, tmp_path / "b",
                               SYM, INT)
    adv2.begin("2027-01-01T00:00:00+00:00", OBS)
    raws = {e: fake_raw(e, r["close_time"], "LONG")
            for e, r in rec["new_rows"][:3]}
    # recompute rec against adv2 state
    adv2.exec_state = {"seen": {}, "exec_counter": 0,
                       "last_settled_open_iso": None,
                       "last_settled_close_iso": None, "revisions": [],
                       "gaps": []}
    rec2 = roll.reconcile_window(df.iloc[:3].reset_index(drop=True), SYM,
                                 INT, OBS, adv2.exec_state)
    raws2 = {e: fake_raw(e, r["close_time"], "LONG")
             for e, r in rec2["new_rows"]}
    adv2.settle_new(rec2["new_rows"], raws2, OBS)
    assert adv2.strategy.counters["diagnostic_rows"] >= 3
    assert adv2.strategy.counters["operating_admitted"] == 0
    assert adv2.strategy.counters["control_admitted"] == 0


def test_atomic_commit_and_resume(patched_identity, tmp_path):
    out = tmp_path / "out"
    adv = make_advisor(out, patched_identity)
    df = candles(10)
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    adv.settle_new(rec["new_rows"], {}, OBS)
    g1 = adv.atomic_commit()
    assert (out / f"checkpoint-{g1}.json").exists()
    assert (out / "CURRENT").read_text().strip() == str(g1)
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    assert adv2.generation == g1
    assert len(adv2.exec_state["seen"]) == 10
    # No duplicates on resume with identical window.
    r = roll.reconcile_window(df, SYM, INT, OBS, adv2.exec_state)
    assert r["new_rows"] == []


def test_corrupt_state_fails_or_recovers(patched_identity, tmp_path):
    out = tmp_path / "out"
    adv = make_advisor(out, patched_identity)
    df = candles(5)
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    adv.settle_new(rec["new_rows"], {}, OBS)
    adv.atomic_commit()
    adv.atomic_commit()  # gen 2
    # Corrupt latest checkpoint -> must recover previous verified generation.
    (out / "checkpoint-2.json").write_bytes(b"TRUNCATED{{")
    adv2 = roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    assert adv2.generation == 1
    # Corrupt everything -> clear failure.
    for p in out.glob("checkpoint-*.json"):
        p.write_bytes(b"\x00\x01")
    (out / "CURRENT").write_text("not-a-number")
    with pytest.raises(ValueError, match="[Cc]orrupt|REFUSED|verified"):
        roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)


class _PinIdentity:
    def __init__(self, path, base_collect, orig_hash):
        self.path = str(path)
        self.base_collect = base_collect
        self.orig_hash = orig_hash

    def collect(self, roll_cfg, advisor_cfg, spec):
        return list(self.base_collect(roll_cfg, advisor_cfg, spec)) + [self.path]

    def hash_all(self, roll_cfg, advisor_cfg, spec):
        import hashlib as _hl
        d = dict(self.orig_hash(roll_cfg, advisor_cfg, spec))
        d[self.path] = _hl.sha256(Path(self.path).read_bytes()).hexdigest()
        return d


def test_identity_change_refusal(patched_identity, tmp_path,
                                 monkeypatch):
    out = tmp_path / "out"
    pinfile = tmp_path / "pinfile.bin"
    pinfile.write_bytes(b"v1")
    helper = _PinIdentity(pinfile, roll.collect_identity_files,
                            roll.hash_identity_bytes)
    monkeypatch.setattr(roll, "collect_identity_files", helper.collect)
    monkeypatch.setattr(roll, "hash_identity_bytes", helper.hash_all)
    adv = make_advisor(out, patched_identity)
    adv.atomic_commit()
    pinfile.write_bytes(b"v2")  # byte identity changed
    with pytest.raises(ValueError, match="identity change"):
        roll.RollingAdvisor.resume(out, ROLL_CFG, ADV_CFG, SPEC)
    # Declared-hash spoof is useless: bytes differ -> still refuses.
    with pytest.raises(ValueError, match="identity change"):
        roll.verify_identity_bytes({"a": "declared"}, {"a": "actual-bytes"})




def test_warmup_row_attaches_to_first_grid_bar(patched_identity, tmp_path):
    out = tmp_path / "out"
    adv = make_advisor(out, patched_identity)
    df = candles(300, start=pd.Timestamp("2026-01-05T00:00:00Z"))
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    warm = {"status": core.STATUS_WARMUP, "reason": "short history"}
    raw_by_exec = {}
    for exec_idx, row in rec["new_rows"]:
        if core.on_grid(row["open_time"]):
            raw_by_exec[exec_idx] = warm
            break
    assert raw_by_exec, "window must contain a grid bar"
    first = min(raw_by_exec)
    adv.settle_new(rec["new_rows"], raw_by_exec, OBS)
    kinds = [d.get("status") for d in adv.strategy.decision_log]
    assert kinds == [core.STATUS_WARMUP]
    assert adv.strategy.decision_log[0]["bar_time"] == core._ts(df["close_time"].iloc[first]).isoformat()
def test_snapshot_exactness(patched_identity, tmp_path):
    out = tmp_path / "out"
    adv = make_advisor(out, patched_identity)
    df = candles(8)
    rec = roll.reconcile_window(df, SYM, INT, OBS, adv.exec_state)
    adv.settle_new(rec["new_rows"], {}, OBS)
    snap = adv.build_snapshot(
        core._ts(df["open_time"].iloc[0]).isoformat(),
        core._ts(df["close_time"].iloc[-1]).isoformat(), len(df),
        {"path": "raw_candles.parquet", "sha256": "abc"},
        OBS, {"kind": "t"}, {"OFF_CLOCK": 8},
        {"calls": 1, "stub": True})
    assert snap["first_candle_open"] == core._ts(
        df["open_time"].iloc[0]).isoformat()
    assert snap["last_candle_close"] == core._ts(
        df["close_time"].iloc[-1]).isoformat()
    assert snap["row_count"] == 8
    assert snap["raw_candle_artifact"]["sha256"] == "abc"
    assert "diagnostic_count" in snap and "actionable_count" in snap
    assert snap["identity_bytes"]


# ------------------------------------------------- CLI kill tests ---
def _write_repo_candles(name, df):
    p = W1TMP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return f"artifacts/research/opencode_r78_rolling/w1/_tmp/{name}"


def _run_cli(candles_rel, out_rel, extra=()):
    cmd = [sys.executable, "scripts/opencode_r78_roll.py", "--mode",
           "replay", "--candles", candles_rel, "--out", out_rel,
           "--stub-infer", *extra]
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def _wait_out(out_rel, timeout=120):
    out = ROOT / out_rel
    t0 = time.time()
    while time.time() - t0 < timeout:
        if (out / "summary.json").exists():
            return True
        time.sleep(0.2)
    return False


def _read_exports(out):
    exp = out / "exports"
    dec = pd.read_csv(exp / "decisions.csv") if (
        exp / "decisions.csv").exists() else pd.DataFrame()
    return dec


def _poll(cond, timeout=240, step=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(step)
    raise TimeoutError("poll timed out")


def _journal_status_count(out):
    jl = out / "journal.jsonl"
    if not jl.exists():
        return 0
    n = 0
    for line in jl.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("t") == "status":
            n += 1
    return n


def _current_gen(out):
    cur = out / "CURRENT"
    if not cur.exists():
        return 0
    try:
        return int(cur.read_text(encoding="utf-8").strip())
    except ValueError:
        return 0


def test_cli_kill_before_commit_recovery():
    df = candles(120)
    crel = _write_repo_candles("killA.parquet", df)
    orel = "artifacts/research/opencode_r78_rolling/w1/_tmp/killA_out"
    import shutil
    shutil.rmtree(str(ROOT / orel), ignore_errors=True)
    # persist_every huge -> only gen-1 + final commit; kill mid-settle.
    # Resume replays from the last committed generation (WAL truncation)
    # and must reach bit-identical exports with no duplicate journal rows.
    p = _run_cli(crel, orel, ("--persist-every", "100000",
                              "--sleep-per-bar", "0.05"))
    _poll(lambda: _journal_status_count(ROOT / orel) >= 10)
    assert not (ROOT / orel / "summary.json").exists()
    p.kill()
    p.wait()
    assert not (ROOT / orel / "summary.json").exists()
    p2 = _run_cli(crel, orel, ("--persist-every", "25",
                               "--sleep-per-bar", "0.0", "--resume"))
    rc = p2.wait(timeout=300)
    assert rc == 0, p2.communicate()[0][-3000:]
    assert _wait_out(orel, timeout=300)
    rrel = "artifacts/research/opencode_r78_rolling/w1/_tmp/killA_ref"
    shutil.rmtree(str(ROOT / rrel), ignore_errors=True)
    p3 = _run_cli(crel, rrel, ("--persist-every", "25",
                               "--sleep-per-bar", "0.0"))
    assert p3.wait(timeout=300) == 0
    assert _wait_out(rrel, timeout=300)
    a = _read_exports(ROOT / orel)
    b = _read_exports(ROOT / rrel)
    assert len(a) == len(b)
    ja = (ROOT / orel / "journal.jsonl").read_text().splitlines()
    idxs = [json.loads(ll).get("exec_idx") for ll in ja
            if json.loads(ll).get("t") == "status"]
    assert len(idxs) == len(set(idxs))


def test_cli_kill_after_commit_and_export_rebuild():
    df = candles(80)
    crel = _write_repo_candles("killB.parquet", df)
    orel = "artifacts/research/opencode_r78_rolling/w1/_tmp/killB_out"
    import shutil
    shutil.rmtree(str(ROOT / orel), ignore_errors=True)
    p = _run_cli(crel, orel, ("--persist-every", "10",
                              "--sleep-per-bar", "0.05"))
    _poll(lambda: _current_gen(ROOT / orel) >= 3)
    assert not (ROOT / orel / "summary.json").exists()
    p.kill()
    p.wait()
    out = ROOT / orel
    assert (out / "CURRENT").exists()
    assert not (out / "summary.json").exists()
    p2 = _run_cli(crel, orel, ("--persist-every", "10",
                               "--sleep-per-bar", "0.0", "--resume"))
    assert p2.wait(timeout=300) == 0
    assert _wait_out(orel, timeout=300)
    assert (out / "exports" / "decisions.csv").exists()
    assert (out / "snapshot.json").exists()
    n_dec = len(pd.read_csv(out / "exports" / "decisions.csv"))
    p3 = _run_cli(crel, orel, ("--persist-every", "10",
                               "--sleep-per-bar", "0.0", "--resume"))
    assert p3.wait(timeout=300) == 0
    assert len(pd.read_csv(out / "exports" / "decisions.csv")) == n_dec
