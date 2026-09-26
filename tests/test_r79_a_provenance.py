"""R79 Track-A: per-ingest immutable raw provenance.

MOCK-mechanics only (synthetic candles, no network/model/training). Rules
under test (r79_roll/1):

- Every ingest writes its OWN immutable snapshot (never a
  write-once-shared file); each commit associates EXACTLY the bytes
  consumed (sha256 + first_open/last_close/row_count).
- The append-only ingest_manifest.jsonl carries bootstrap/resume
  observation times + lineage (prev_sha256 chain, generation).
- Hash/range consistency verified on two shifted windows with distinct
  bytes; the snapshot's raw_artifact (hash + range) matches recomputation
  from the stored file bytes.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import hashlib
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


def test_two_shifted_windows_hash_range_consistency(patched_identity,
                                                   tmp_path):
    out = tmp_path / "prov"
    out.mkdir(parents=True, exist_ok=True)
    # Two shifted windows with DISTINCT bytes (second starts one bar later
    # with a different close on its last bar).
    df_a = candles(30, start=T0)
    df_b = candles(30, start=T0 + pd.Timedelta(minutes=5))
    df_b.loc[29, "close"] = 101.5
    obs_a = "2026-09-10T02:35:00+00:00"   # bootstrap observation
    obs_b = "2026-09-10T02:40:00+00:00"   # resume observation
    snap_a = roll.write_raw_snapshot(df_a, out, obs_a, "bootstrap", None, 1)
    snap_b = roll.write_raw_snapshot(df_b, out, obs_b, "resume",
                                     snap_a["sha256"], 2)
    # Immutable + distinct: two files, both still on disk, distinct bytes.
    assert snap_a["path"] != snap_b["path"]
    assert snap_a["sha256"] != snap_b["sha256"]
    pa, pb = out / snap_a["path"], out / snap_b["path"]
    assert pa.exists() and pb.exists()
    assert (pa.read_bytes() != pb.read_bytes())
    # Legacy write-once shared file is NEVER created by r79.
    assert not (out / "raw_candles.parquet").exists()
    # Hash/range consistency: recompute from the stored bytes.
    for snap, df, obs in ((snap_a, df_a, obs_a), (snap_b, df_b, obs_b)):
        p = out / snap["path"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == snap["sha256"]
        back = pd.read_parquet(p)
        assert len(back) == snap["row_count"] == len(df)
        assert core._ts(back["open_time"].iloc[0]).isoformat() == snap[
            "first_open"] == core._ts(df["open_time"].iloc[0]).isoformat()
        assert core._ts(back["close_time"].iloc[-1]).isoformat() == snap[
            "last_close"] == core._ts(df["close_time"].iloc[-1]).isoformat()
        _ = obs
    # Manifest lineage: append-only, prev-chain, observation times, kinds.
    lines = (out / "ingest_manifest.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == 2
    ma, mb = (json.loads(lines[0]), json.loads(lines[1]))
    assert ma["kind"] == "bootstrap" and mb["kind"] == "resume"
    assert ma["observed_at"] == core._ts(obs_a).isoformat()
    assert mb["observed_at"] == core._ts(obs_b).isoformat()
    assert ma["prev_sha256"] is None
    assert mb["prev_sha256"] == ma["sha256"] == snap_a["sha256"]
    assert mb["sha256"] == snap_b["sha256"]
    assert ma["generation"] == 1 and mb["generation"] == 2
    assert ma["row_count"] == mb["row_count"] == 30
    assert ma["first_open"] != mb["first_open"]  # shifted ranges recorded


def test_snapshot_binds_exact_bytes_and_times(patched_identity, tmp_path):
    out = tmp_path / "snap"
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    df = candles(12)
    obs = "2026-09-10T01:05:00+00:00"
    adv.begin(roll.fresh_shadow_start(df, obs), obs)
    snap_rec = roll.write_raw_snapshot(df, out, obs, "bootstrap", None, 1)
    adv.exec_state.setdefault("ingest_ids", []).append(
        snap_rec["ingest_id"])
    rec = roll.reconcile_window(df, SYM, INT, obs, adv.exec_state)
    adv.settle_new(rec["new_rows"], {}, obs)
    snap = adv.build_snapshot(
        core._ts(df["open_time"].iloc[0]).isoformat(),
        core._ts(df["close_time"].iloc[-1]).isoformat(), len(df),
        {"kind": "REHEARSAL-MOCK", **snap_rec},
        observed_at=obs, source={"kind": "MOCK", "fetched_at": None},
        status_counts={}, inference_evidence={},
        observation_times={
            "bootstrap_observed_at": adv.exec_state[
                "bootstrap_observed_at"],
            "observed_at": core._ts(obs).isoformat()},
        lineage={"ingest_ids": list(adv.exec_state["ingest_ids"]),
                 "ingest_id": snap_rec["ingest_id"],
                 "prev_sha256": snap_rec["prev_sha256"]},
        validity=dict(adv.exec_state["validity"]),
        inference_sanitized={"output_rows": len(df)})
    art = snap["raw_candle_artifact"]
    assert art["sha256"] == snap_rec["sha256"]
    assert art["row_count"] == len(df) == 12
    assert art["first_open"] == core._ts(
        df["open_time"].iloc[0]).isoformat()
    assert art["last_close"] == core._ts(
        df["close_time"].iloc[-1]).isoformat()
    assert hashlib.sha256(
        (out / art["path"]).read_bytes()).hexdigest() == art["sha256"]
    assert snap["observation_times"]["bootstrap_observed_at"] == core._ts(
        obs).isoformat()
    assert snap["observation_times"]["observed_at"] == core._ts(
        obs).isoformat()
    assert snap["lineage"]["ingest_id"] == snap_rec["ingest_id"]
    assert snap["roll_version"] == roll.ROLL_VERSION == "r80_roll/1"  # authorized R80 contract bump
