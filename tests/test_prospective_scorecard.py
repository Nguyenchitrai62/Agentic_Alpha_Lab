"""Synthetic-fixture tests for scripts/prospective_scorecard.py (no network, no real DB)."""
import json
import sqlite3

import numpy as np
import pandas as pd

import scripts.prospective_scorecard as sc


def test_research_expect_matches_v421_v422():
    assert sc.RESEARCH_EXPECT["bot_paper_d17bfg2"]["monthly_pct"] == 5.41
    assert sc.RESEARCH_EXPECT["bot_paper_d17bfg2"]["max_yearly_dd"] == 16.91
    assert "v421" in sc.RESEARCH_EXPECT["bot_paper_d17bfg2"]["variant"]
    assert "--dip-gross-cap 2.0" in sc.RESEARCH_EXPECT["bot_paper_d17bfg2"]["config"]
    assert "17:51" in sc.RESEARCH_EXPECT["bot_paper_d17bfg2"]["started"]
    assert sc.RESEARCH_EXPECT["bot_paper_g2k20"]["monthly_pct"] == 5.87
    assert sc.RESEARCH_EXPECT["bot_paper_g2k20"]["max_yearly_dd"] == 17.79
    assert "v422" in sc.RESEARCH_EXPECT["bot_paper_g2k20"]["variant"]
    assert "--dip-mult 2.0" in sc.RESEARCH_EXPECT["bot_paper_g2k20"]["config"]
    assert "17:38" in sc.RESEARCH_EXPECT["bot_paper_g2k20"]["started"]


def test_names_and_thresholds_match_d17bf_bar():
    assert "bot_paper_d17bfg2" in sc.NAMES and "bot_paper_g2k20" in sc.NAMES
    assert "bot_paper" in sc.NAMES and "bot_paper_d17bf" in sc.NAMES  # existing rows kept
    for needle in ("pct>=20", "DD<=15%", "1.5", "cycle_error", "stop"):
        assert needle in sc.GO_LIVE
    for needle in ("DD>20%", "10%", "pct<5", "8w"):
        assert needle in sc.STOP_RULE
    keys = [k for k, _ in sc.BOT_DIRS]
    assert keys[:4] == ["bot_paper", "bot_paper_d17bf", "bot_paper_d17bfg2", "bot_paper_g2k20"]
    assert set(keys[4:]) == {"bot_paper_d17bfg2c", "bot_paper_g2k20c"}  # G2 + carry runners (ops_scorecardfix 2026-10-07)
    assert keys[:2] == ["bot_paper", "bot_paper_d17bf"]  # existing order unchanged


def test_bootstrap_deterministic_synthetic():
    daily = np.array([0.001, -0.002, 0.003, -0.001, 0.002] * 60)
    b1 = sc.bootstrap(daily, 3, draws=200)
    b2 = sc.bootstrap(daily, 3, draws=200)
    assert len(b1) == 200 and (b1 == b2).all()
    assert np.isfinite(b1).all()


def test_research_daily_filters_dev_window_synthetic():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE equity (t INTEGER, equity REAL, source TEXT)")
    idx = pd.date_range("2021-09-24", periods=200, freq="D", tz="UTC")
    for t, i in zip(idx, range(200)):
        con.execute("INSERT INTO equity VALUES (?,?,?)", (int(t.value // 1_000_000), 100.0 + i, "tm_v376"))
    out = con.execute("SELECT t, equity FROM equity WHERE source='tm_vXXX'").fetchall()
    assert out == []
    daily = sc.research_daily(con, "v376")
    assert daily is not None and len(daily) == 199
    con.close()


def test_main_collects_new_bots_on_synthetic_fixtures(tmp_path, monkeypatch):
    plans = tmp_path / "plans"
    plans.mkdir()
    curve = [["2026-10-05 17:00:00+00:00", 5000.0], ["2026-10-05 19:00:00+00:00", 5050.0]]
    (plans / "trade_plan_v999.json").write_text(json.dumps({"equity_curve": curve}))
    bots = {}
    for key in ("bot_paper", "bot_paper_d17bf", "bot_paper_d17bfg2", "bot_paper_g2k20"):
        d = tmp_path / key
        d.mkdir()
        p = d / "exchange.json"
        p.write_text(json.dumps({"equity_curve": curve}))
        bots[key] = p
    db = tmp_path / "app.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE equity (t INTEGER, equity REAL, source TEXT)")
    idx = pd.date_range("2021-09-24", periods=200, freq="D", tz="UTC")
    for t, i in zip(idx, range(200)):
        con.execute("INSERT INTO equity VALUES (?,?,?)", (int(t.value // 1_000_000), 100.0 + i, "tm_v999"))
        con.execute("INSERT INTO equity VALUES (?,?,?)", (int(t.value // 1_000_000), 100.0 + i, "tm_v376"))
    con.commit()
    con.close()
    monkeypatch.setattr(sc, "PLANS", plans)
    monkeypatch.setattr(sc, "DB", db)
    monkeypatch.setattr(sc, "BOT_DIRS", tuple((k, bots[k]) for k in ("bot_paper", "bot_paper_d17bf", "bot_paper_d17bfg2", "bot_paper_g2k20")))
    sc.main()
    rows = json.loads((plans / "prospective_scorecard.json").read_text())["rows"]
    by_pipe = {r["pipeline"]: r for r in rows}
    assert set(("v999", "bot_paper", "bot_paper_d17bf", "bot_paper_d17bfg2", "bot_paper_g2k20")) <= set(by_pipe)
    # existing rows keep old key set (no research/threshold keys leak onto them)
    for old in ("v999", "bot_paper", "bot_paper_d17bf"):
        for forbidden in ("research_monthly_pct", "research_max_yearly_dd", "go_live", "stop", "config"):
            assert forbidden not in by_pipe[old]
    # new rows carry research expectation + d17bf thresholds, same live math as old rows
    for new in ("bot_paper_d17bfg2", "bot_paper_g2k20"):
        r = by_pipe[new]
        assert r["live_pct"] == round(100 * (5050.0 / 5000.0 - 1), 3) == 1.0
        assert r["research_monthly_pct"] == sc.RESEARCH_EXPECT[new]["monthly_pct"]
        assert r["research_max_yearly_dd"] == sc.RESEARCH_EXPECT[new]["max_yearly_dd"]
        assert r["go_live"] == sc.GO_LIVE and r["stop"] == sc.STOP_RULE
