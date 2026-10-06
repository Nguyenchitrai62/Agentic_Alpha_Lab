"""cycle_stats: sampler stats + actions summary. No network, no bot dirs, no processes."""
import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.cycle_stats as cs


def _mk_state(d: Path, cycle_ms, stages=None, lock_wait=0.0):
    d.mkdir(parents=True, exist_ok=True)
    s = {"ledger": {}, "links": {}, "last_cycle_ms": cycle_ms,
         "last_cycle_stages_ms": stages or {"plan_ms": 1.0, "kline_ms": 5.0, "sync_ms": 0.5,
                                            "decide_ms": 2.0, "order_ms": 0.5, "state_ms": 3.0},
         "last_cycle_lock_wait_ms": lock_wait}
    (d / "state.json").write_text(json.dumps(s), encoding="utf-8")


def test_read_state(tmp_path):
    d = tmp_path / "paper"
    _mk_state(d, 417.8)
    snap = cs.read_state(d)
    assert snap["ok"] and snap["cycle_ms"] == 417.8
    assert snap["stages"]["kline_ms"] == 5.0
    assert snap["mtime"] is not None


def test_read_state_missing(tmp_path):
    snap = cs.read_state(tmp_path / "nodoc")
    assert snap["cycle_ms"] is None and snap["mtime"] is None


def test_percentile_and_dominant_stage():
    assert cs.percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert cs.percentile([7.0], 0.95) == 7.0
    assert cs.percentile([], 0.5) is None
    samples = [
        {"tick": 0, "dir": "a", "cycle_ms": 100.0, "gap_s": 20.0,
         "stages": {"plan_ms": 1, "kline_ms": 80, "sync_ms": 1, "decide_ms": 5, "order_ms": 1, "state_ms": 2},
         "free_mem_kb": 1000},
        {"tick": 1, "dir": "a", "cycle_ms": 300.0, "gap_s": 150.0,
         "stages": {"plan_ms": 1, "kline_ms": 250, "sync_ms": 1, "decide_ms": 5, "order_ms": 1, "state_ms": 2},
         "free_mem_kb": 1000},
    ]
    stats, _ = cs.summarize_samples(samples, ["a"])
    s = stats["a"]
    assert s["median_ms"] == 200.0 and s["max_ms"] == 300.0
    assert s["dominant_stage"] == "kline_ms"
    assert s["gaps_over_2min"] == 1 and s["max_gap_s"] == 150.0


def test_pearson_none_on_constant():
    assert cs.pearson([1, 1, 1], [2, 3, 4]) is None
    assert cs.pearson([1, 2], [3, 4]) is None
    r = cs.pearson([1, 2, 3, 4], [2, 4, 6, 8])
    assert r is not None and abs(r - 1.0) < 1e-9


def test_summarize_actions_counts(tmp_path):
    d = tmp_path / "paper"
    d.mkdir()
    rows = [
        {"t": "2026-10-06T06:39:00+00:00", "op": "slow_cycle", "total_ms": 61000},
        {"t": "2026-10-06T06:41:00+00:00", "op": "slow_cycle", "total_ms": 62000},
        {"t": "2026-10-06T06:42:00+00:00", "op": "lock_wait", "lock_wait_ms": 11000},
        {"t": "2026-10-06T06:43:00+00:00", "op": "cycle_error",
         "note": "BybitError('10006: Too many visits.')"},
        {"t": "2026-10-06T06:44:00+00:00", "op": "place"},
    ]
    (d / "actions.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    since = datetime(2026, 10, 6, 6, 40, tzinfo=timezone.utc)
    out = cs.summarize_actions([str(d)], since)
    r = out[str(d)]
    assert r == {"slow_cycle": 1, "lock_wait": 1, "rate_limit": 1, "errors": 1, "scanned": 4}


def test_sampler_read_only_and_no_ram(tmp_path):
    d = tmp_path / "paper"
    _mk_state(d, 250.0)
    before = (d / "state.json").read_text(encoding="utf-8")
    samples = cs.run_sampler([str(d)], 3, 0.0, no_ram=True, sleep_fn=lambda s: None)
    assert len(samples) == 3
    assert all(s["cycle_ms"] == 250.0 and s["free_mem_kb"] is None for s in samples)
    assert (d / "state.json").read_text(encoding="utf-8") == before  # untouched
