"""Ops scorecardfix tests: correction windows + two carry runners (no network, no bot state)."""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

import scripts.prospective_scorecard as sc

SPEC = importlib.util.spec_from_file_location(
    "paper_report_fix", Path(__file__).resolve().parents[1] / "scripts" / "paper_report.py")
pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pr)


def test_corrected_chain_matches_hand_computation():
    curve = [["2026-10-06 19:00:00+00:00", 100.0], ["2026-10-06 20:00:00+00:00", 110.0],
             ["2026-10-06 21:00:00+00:00", 121.0], ["2026-10-06 22:00:00+00:00", 133.1]]
    wins = [(pd.Timestamp("2026-10-06 20:00:00+00:00"), pd.Timestamp("2026-10-06 21:00:00+00:00"))]
    live, excl = sc.corrected_stats(curve, wins)
    assert live == pytest.approx(1.10 * 1.0 * 1.10 - 1.0)  # middle step zeroed
    assert excl == pytest.approx(1.0 / 24.0)
    raw, corr, _ = pr.corrected_return(curve, [(pr.parse_ts("2026-10-06T20:00:00+00:00"),
                                                pr.parse_ts("2026-10-06T21:00:00+00:00"))])
    assert raw == pytest.approx(33.1)
    assert corr == pytest.approx(21.0)


def test_missing_corrections_file_identical(tmp_path):
    assert sc.load_corrections(tmp_path / "nope.json") == []
    assert pr.load_corrections(tmp_path / "nope.json") == []
    assert sc.windows_for_runner([], "bot_paper") == []
    curve = [["2026-10-06 19:00:00+00:00", 100.0], ["2026-10-06 20:00:00+00:00", 110.0]]
    live, excl = sc.corrected_stats(curve, [])
    assert live == pytest.approx(0.10) and excl == 0.0
    raw, corr, excl2 = pr.corrected_return(curve, [])
    assert raw == pytest.approx(10.0) and corr == pytest.approx(10.0) and excl2 == 0.0


def test_new_carry_runners_appear():
    assert sc.NAMES["bot_paper_d17bfg2c"] == "G2 + carry f 0.25 (paper)"
    assert sc.NAMES["bot_paper_g2k20c"] == "G2K20 + carry f 0.25 (paper)"
    assert sc.RESEARCH_EXPECT["bot_paper_d17bfg2c"]["monthly_pct"] == 5.634
    assert sc.RESEARCH_EXPECT["bot_paper_d17bfg2c"]["max_yearly_dd"] == 16.75
    assert sc.RESEARCH_EXPECT["bot_paper_g2k20c"]["monthly_pct"] == 6.097
    assert sc.RESEARCH_EXPECT["bot_paper_g2k20c"]["max_yearly_dd"] == 17.64
    by_key = dict(sc.BOT_DIRS)
    assert Path(by_key["bot_paper_d17bfg2c"]).as_posix().endswith("paper_d17bfg2c/exchange.json")
    assert Path(by_key["bot_paper_g2k20c"]).as_posix().endswith("paper_g2k20c/exchange.json")
    assert json.loads((sc.CORRECTIONS).read_text())[0]["runners"] == "all"
