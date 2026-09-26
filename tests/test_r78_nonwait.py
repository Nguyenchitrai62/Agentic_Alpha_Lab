"""R78 W2 tests: pre-spec frozen SHAs, no-replay audit, gate parity,
snapshot/restore roundtrip, summary schema. No training, no cloud."""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_nonwait as w2  # noqa: E402

SPEC = ROOT / "configs" / "opencode_r78_nonwait.json"
OUT = ROOT / "artifacts" / "research" / "opencode_r78_rolling" / "w2"


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_prespec_frozen_shas():
    spec = w2.load_prespec()
    assert w2.verify_frozen(spec)["runner"] == "ok"


def test_no_replay_audit_runner_sources():
    audit = w2.audit_runner_sources()
    assert audit["pass"], audit
    # Honest classification: naive pattern hits exist but are confined to
    # the deny-list constant, own-output writes and the uncalled legacy
    # replay branch of feedexec.main.
    assert audit["legacy_replay_calls_in_w2"] == []
    assert audit["non_checkpoint_loads_in_infer"] == []


def test_raw_path_order_denial_flag():
    # The harness flag exists and starts in the pre-raw state contract:
    # raw path must precede any harness reference load.
    assert w2._REFERENCE_LOADED["raw_done"] in (True, False)
    src = (ROOT / "scripts" / "opencode_r78_nonwait.py").read_text(
        encoding="utf-8")
    assert "REFUSED: reference section ran before the raw path" in src
    assert "REFUSED: raw path must run before the harness reference" in src


def test_gate_parity_core_vs_harness():
    cap, cd = 4, 5
    g_core = core.FrequencyGate(cap, cd)
    g_mine = w2._Gate(cap, cd)
    stamps = pd.to_datetime([
        "2024-01-06T00:05:00Z", "2024-01-08T00:05:00Z",  # 2nd in cooldown
        "2024-01-13T06:05:00Z", "2024-01-18T06:05:00Z",  # exact 5d boundary
        "2024-01-20T00:05:00Z", "2024-01-25T00:05:00Z",
        "2024-01-30T00:05:00Z",  # monthly cap (5th in Jan)
        "2024-02-05T00:05:00Z",
    ], utc=True)
    for ts in stamps:
        a1, _ = g_core.attempt(ts, True)
        a2, _ = g_mine.attempt(ts)
        assert bool(a1) == bool(a2), ts
    assert g_core.monthly == g_mine.monthly
    assert g_core.next_allowed == g_mine.next_allowed


def _tiny_config():
    cfg = json.loads(
        (ROOT / "configs" / "opencode_r77_advisor.json").read_text(
            encoding="utf-8"))
    return cfg


def _tiny_bars(n: int = 30):
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    rows = []
    for i in range(n):
        o = base + pd.Timedelta(minutes=5 * i)
        c = o + pd.Timedelta(minutes=4, seconds=59, milliseconds=999)
        rows.append({"open_time": o, "close_time": c, "open": 100.0,
                     "high": 101.0, "low": 99.0, "close": 100.5,
                     "volume": 10.0})
    return pd.DataFrame(rows)


def test_snapshot_restore_roundtrip():
    import opencode_r76_infer as r76
    cfg = _tiny_config()
    df = _tiny_bars()
    rspec = r76.load_prespec()
    s1 = core.AdvisorStrategy(cfg, n_bars=len(df))
    ident = s1.identity_block(cfg, rspec)
    s1._identity = ident
    s1.begin_observation(df["close_time"].iloc[0].isoformat(),
                         "2024-01-01T00:00:01Z")
    for pos in range(len(df)):
        row = df.iloc[pos]
        bar = {"open_time": row["open_time"], "close_time": row["close_time"],
               "open": float(row["open"]), "high": float(row["high"]),
               "low": float(row["low"]), "close": float(row["close"]),
               "volume": float(row["volume"])}
        s1.observe_bar(pos, bar, None, "2024-01-01T00:00:01Z")
    snap = s1.snapshot_state(ident)
    s2 = core.AdvisorStrategy(cfg, n_bars=len(df))
    s2._identity = ident
    s2.restore_state(snap, ident)
    snap2 = s2.snapshot_state(ident)
    assert snap2["operating"]["equity"] == snap["operating"]["equity"]
    assert snap2["control"]["equity"] == snap["control"]["equity"]
    assert snap2["counters"] == snap["counters"]
    assert snap2["last_bar_idx"] == snap["last_bar_idx"]


def test_summary_schema_after_run():
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    for key in ("verdict", "interval", "frozen", "raw_inference_proof",
                "stream_full_prefix", "batch_reference",
                "score_comparison_slice",
                "portfolio_deltas_stream_vs_batch1x", "restart", "blocked"):
        assert key in summary, key
    assert summary["verdict"] in ("PASS", "BLOCKED", "MISMATCH-DIAGNOSE")
    assert summary["raw_inference_proof"]["ready_raw_rows"] >= 1
