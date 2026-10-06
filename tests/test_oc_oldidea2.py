"""Tests for oc_oldidea2 (fast: verdict transcription vs audited v417 sources)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_oldidea2"
V417 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2" / "v417"


def _load(p):
    return json.loads(Path(p).read_text())


def test_results_transcribes_v417_x_row():
    res = _load(HERE / "results.json")
    assert res["judged_in_full_engine"] is True
    assert res["engine"] == "v417"
    v417 = _load(V417 / "v417_result.json")
    mani = _load(V417 / "result_manifest.json")
    for row in ("R2B1D17BF", "R2B1D17BFX", "R2B1D17BFC", "R2B1D17BFCX"):
        for k in ("R", "W", "DD", "full_path_dd", "losing"):
            assert res["rows"][row][k] == v417["rows"][row][k], (row, k)
            assert res["rows"][row][k] == mani["result"]["rows"][row][k], (row, k)
    # the judged variant is the fixed oc_idea2 V leg
    assert res["rows"]["R2B1D17BFX"]["R"] == 5.574
    assert res["rows"]["R2B1D17BFX"]["DD"] == 18.37
    assert res["rows"]["R2B1D17BFX"]["full_path_dd"] == 16.89
    assert mani["status"] == "rejected"
    assert mani["audit"]["passed"] is True
    assert v417["transfer"] is False


def test_report_states_verdict_and_sources():
    txt = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("R2B1D17BFX", "REJECTED", "v417_cascade.py",
                   "result_manifest.json", "oc_idea2_dipstop", "Tom tat tieng Viet"):
        assert needle in txt, needle
    # first branch of the assignment: report the existing verdict and stop (no run)
    low = txt.lower()
    assert "no engine run" in low or "no\nre-simulation" in low or "no re-simulation" in low


def test_v417_prereg_matches_oc_idea2_variant():
    src = (V417 / "v417_cascade.py").read_text(encoding="utf-8")
    assert "XRPUSDT 5.5 sigma, other majors" in src
    assert "sleeve_sl_coin" in src
    assert 'xrp=5.5' in src
