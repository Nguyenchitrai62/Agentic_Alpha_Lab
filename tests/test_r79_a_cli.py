"""R79 Track-A: supported-CLI smoke via the REAL main() entry.

MOCK-mechanics only where labeled: replay parquet fixtures + --stub-infer
(WAIT-only settlement/recovery mechanics, never production inference). No
network (replay mode), no training, no orders. Identity hashing is patched
to repo-present files (production still fails closed on missing model
bytes); the patch is labeled explicitly.

Covers the r79 main() wiring: fresh_shadow_start, per-ingest immutable raw
snapshots + manifest lineage, batch-latest missed-clock anchor, validity
pause hook, [r79_roll/1] version stamp.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import gc
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r78_roll as roll  # noqa: E402

A_CLI = ROOT / "artifacts" / "research" / "opencode_r79" / "a_cli"
CFG = "configs/opencode_r79_roll.json"
T0 = pd.Timestamp("2026-09-10T00:00:00Z")


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
    """MOCK-mechanics identity patch (test-only; production fails closed)."""
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


def _rmtree_retry(path: Path, tries: int = 6, delay: float = 0.25) -> None:
    """Windows-robust rmtree for the test out dir.

    Cause of the intermittent PermissionError: on Windows a file with a
    still-open handle (unclosed parquet/CSV handle from a previous
    run_main in the same process, or a transient AV/indexer lock from a
    previous pytest process) cannot be deleted. The old
    shutil.rmtree(..., ignore_errors=True) masked the partial delete and
    left stale state that flaked the next run. Fix in the test: release
    straggler handles via gc.collect(), clear read-only bits via
    onerror, and retry with short sleeps; a genuine lock still raises
    loudly on the final attempt instead of being masked.
    """
    if not path.exists() and not path.is_symlink():
        return

    def _onerror(func, p, _exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(p)
        except OSError:
            pass

    for _ in range(tries):
        gc.collect()  # release any unclosed handles held by this process
        shutil.rmtree(path, onerror=_onerror)
        if not path.exists():
            return
        time.sleep(delay)
    shutil.rmtree(path)  # final attempt without masking: real errors raise


def run_main(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["opencode_r78_roll.py", *argv])
    roll.main()


def test_cli_fresh_resume_shifted_idempotent(patched_identity, monkeypatch):
    A_CLI.mkdir(parents=True, exist_ok=True)
    candles(30).to_parquet(A_CLI / "candles_30.parquet", index=False)
    out_rel = "artifacts/research/opencode_r79/a_cli/out_smoke"
    _rmtree_retry(ROOT / out_rel)
    run_main(["--mode", "replay", "--config", CFG,
              "--candles",
              "artifacts/research/opencode_r79/a_cli/candles_30.parquet",
              "--out", out_rel, "--stub-infer", "--persist-every", "10"],
             monkeypatch)
    out = ROOT / out_rel
    s1 = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s1["roll_version"] == "r80_roll/1"  # authorized R80 contract bump
    assert s1["actionable_count"] == 0  # WAIT stub + fresh replay: nothing
    assert s1["observation_times"]["bootstrap_observed_at"] is not None
    assert len(s1["lineage"]["ingest_ids"]) == 1
    snaps = sorted(out.glob("raw_ingest_*.parquet"))
    assert len(snaps) == 1  # exactly the bytes consumed
    assert not (out / "raw_candles.parquet").exists()  # never shared file
    man = (out / "ingest_manifest.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(man) == 1
    m1 = json.loads(man[0])
    assert m1["kind"] == "REHEARSAL-NOT-LIVE" and m1["prev_sha256"] is None
    assert m1["sha256"] == s1["raw_candle_artifact"]["sha256"]
    gen1 = (out / "CURRENT").read_text(encoding="utf-8").strip()
    # Shifted window (+1 bar): settles exactly the new bar.
    base = candles(30)
    shifted = pd.concat(
        [base.iloc[1:],
         candles(1, start=base["open_time"].iloc[-1]
                 + pd.Timedelta(minutes=5))], ignore_index=True)
    shifted.to_parquet(A_CLI / "candles_shift30.parquet", index=False)
    run_main(["--mode", "replay", "--config", CFG,
              "--candles",
              "artifacts/research/opencode_r79/a_cli/candles_shift30.parquet",
              "--out", out_rel, "--stub-infer", "--persist-every", "10",
              "--resume"], monkeypatch)
    s2 = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s2["last_candle_close"] == shifted["close_time"].iloc[
        -1].isoformat()
    assert (out / "CURRENT").read_text(
        encoding="utf-8").strip() != gen1  # generation advanced
    assert len(sorted(out.glob("raw_ingest_*.parquet"))) == 2
    man2 = (out / "ingest_manifest.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(man2) == 2
    m2 = json.loads(man2[1])
    assert m2["prev_sha256"] == m1["sha256"] and m2["sha256"] != m1["sha256"]
    assert m2["observed_at"] is not None and m2["kind"] == "REHEARSAL-NOT-LIVE"
    # Identical resume: nothing new, exports intact.
    dec_before = (out / "exports" / "decisions.csv").read_bytes()
    run_main(["--mode", "replay", "--config", CFG,
              "--candles",
              "artifacts/research/opencode_r79/a_cli/candles_shift30.parquet",
              "--out", out_rel, "--stub-infer", "--persist-every", "10",
              "--resume"], monkeypatch)
    assert (out / "exports" / "decisions.csv").read_bytes() == dec_before
    man3 = (out / "ingest_manifest.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(man3) == 3  # every ingest recorded, even zero-new ones
