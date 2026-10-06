"""disk_growth: read-only report helpers. No network, no bot writes."""
import json
import subprocess
import sys
from pathlib import Path

import scripts.disk_growth as dg

ROOT = Path(__file__).resolve().parents[1]


def test_project_math():
    assert dg.project(100, 10.0, 30) == 400
    assert dg.project(100, None, 30) is None
    assert dg.project(0, 1.5, 365) == 1.5 * 365


def test_parse_ts():
    assert dg.parse_ts(None) is None
    assert dg.parse_ts("not-a-date") is None
    t = dg.parse_ts("2026-10-05 04:50:03.232811+00:00")
    assert t is not None and t.year == 2026
    assert dg.parse_ts("2026-10-06T22:20:47Z") is not None


def test_jsonl_rate_tmp(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text(
        '{"t": "2026-10-05T00:00:00+00:00", "op": "place"}\n'
        '{"t": "2026-10-06T00:00:00+00:00", "op": "cancel"}\n',
        encoding="utf-8",
    )
    r = dg.jsonl_bytes_per_day(p)
    assert r["n"] == 2 and r["span_h"] == 24.0
    assert r["bytes_per_day"] is not None and r["bytes_per_day"] > 0
    assert dg.jsonl_bytes_per_day(tmp_path / "missing.jsonl")["bytes_per_day"] is None


def test_whole_rewrite_heuristic(tmp_path):
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert dg.is_whole_rewrite_json(d) is True
    j = tmp_path / "j.jsonl"
    j.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    assert dg.is_whole_rewrite_json(j) is False


def test_collect_readonly_keys():
    data = dg.collect()
    assert set(data) >= {"items", "disk", "topbook_daily", "liquidations_daily"}
    assert data["disk"]["free"] and data["disk"]["free"] > 0
    paths = {i["path"] for i in data["items"]}
    for want in ("artifacts/bot/paper/state.json",
                 "artifacts/bot/paper/actions.jsonl",
                 "artifacts/web/app.db",
                 "data/raw/topbook_live",
                 "data/raw/liquidations_live",
                 "artifacts/research/advisor_shadow/shadow.jsonl",
                 "artifacts/backend_logs/uvicorn_local.log"):
        assert want in paths, want
    for i in data["items"]:
        assert set(i) >= {"path", "exists", "size", "bytes_per_day", "projection"}


def test_cli_json_runs_readonly():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/disk_growth.py"), "--json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "items" in data and "disk" in data
