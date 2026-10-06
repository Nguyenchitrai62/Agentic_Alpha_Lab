"""Lightweight check for the oc_freeze manifest (no market data, no heavy I/O)."""
import json
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "artifacts/research/freeze_d17bf"


def test_manifest_complete():
    for f in ("PLAN.md", "make_freeze.py", "results.json", "FREEZE.json", "FREEZE.md", "REPORT.md"):
        assert (D / f).is_file(), f
    m = json.loads((D / "FREEZE.json").read_text(encoding="utf-8"))
    assert m["pick"] == "R2B1D17BF"
    assert m["verdict"] == "FROZEN", m["missing"]
    assert m["missing"] == []
    assert len(m["files"]) >= 40
    assert len(m["git_head"]) == 40 and m["freeze_time_utc"] and "--bear-book" in m["bot_command_paper"]
    kinds = {r["kind"] for r in m["files"]}
    assert {"module", "r2_table", "book_cache", "bot_path", "runner", "reference"} <= kinds
    for r in m["files"]:
        assert len(r["sha256"]) == 64 and r["bytes"] > 0
