"""Test oc_rolling17 deliverables (light, no simulation)."""
import json
from pathlib import Path

HERE = Path("research/tournament/oc_rolling17/results.json")


def _load():
    return json.loads(HERE.read_text())


def test_files_exist():
    base = Path("research/tournament/oc_rolling17")
    assert (base / "PLAN.md").exists()
    assert (base / "run_rolling17.py").exists()
    assert (base / "results.json").exists()
    assert (base / "REPORT.md").exists()


def test_windows_and_repro():
    d = _load()
    assert d["grid"]["n_windows"] == 49
    assert d["scored"] == ["R2B1D17BF", "R2B1D16"]
    assert d["r2_4p_present"] is False
    assert d["repro_max_abs_diff"]["vs_year_reset_R"] <= 1e-3
    assert d["repro_max_abs_diff"]["vs_year_reset_DD"] <= 1e-3
    assert d["repro_max_abs_diff"]["vs_result_json"] <= 1e-3
    for st in d["scored"]:
        rows = d["windows"][st]
        assert len(rows) == 49
        starts = [r["start"] for r in rows]
        assert starts == sorted(starts)
        assert starts[0] == "2021-09-24" and starts[-1] == "2025-09-24"
        for r in rows:
            assert r["DD"] >= 0
            assert r["losing"] == int(r["R"] < 0)
            assert r["end_eq"] > 0
        s = d["summary"][st]
        assert s["n_windows"] == 49
        assert s["n_losing"] == sum(r["losing"] for r in rows)
        assert s["worst_R_date"] == min(rows, key=lambda r: (r["R"], r["start"]))["start"]
