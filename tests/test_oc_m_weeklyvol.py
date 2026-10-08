"""Tests for oc_m_weeklyvol (IDEAS9 #5 weekly-frozen vol table, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_weeklyvol/results.json exists.
"""

import importlib.util
import json
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_weeklyvol"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_weeklyvol", HERE / "compute_m_weeklyvol.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


HAS_RESULTS = (HERE / "results.json").exists()
needs_results = pytest.mark.skipif(not HAS_RESULTS, reason="post-heavy")


# ---- pre-registered constants -------------------------------------------
def test_prereg_constants():
    m = _mod()
    assert m.WIN_START == 15 and m.SLEEVE_START == 16
    assert m.MAJORS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert m.TICKS == {"BTCUSDT": 0.10, "ETHUSDT": 0.01, "SOLUSDT": 0.01,
                       "BNBUSDT": 0.10, "XRPUSDT": 0.0001}
    assert m.TICK_STEP == {"BTCUSDT": 0.50, "ETHUSDT": 0.05, "SOLUSDT": 0.05,
                           "BNBUSDT": 0.50, "XRPUSDT": 0.0005}
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1_WEEKLY", "V2_WEEKLY5T"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1_WEEKLY": "v1",
                             "V2_WEEKLY5T": "v2"}
    assert m.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")


def test_helpers_geo_and_anchor():
    m = _mod()
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_week_start_sunday_boundaries():
    m = _mod()
    sun = pd.Timestamp("2022-01-02 00:00", tz="UTC")  # a Sunday
    assert sun.weekday() == 6
    assert m.week_start_of(sun) == sun  # print usable from Sunday 00:00
    assert m.week_start_of(sun + pd.Timedelta(hours=3)) == sun
    assert m.week_start_of(sun + pd.Timedelta(days=6, hours=23)) == sun
    nxt = sun + pd.Timedelta(days=7)
    assert m.week_start_of(nxt) == nxt  # next Sunday starts a new table
    assert m.week_start_of(sun - pd.Timedelta(minutes=1)) == sun - pd.Timedelta(days=7)
    assert m.week_start_of(pd.Timestamp("2022-01-05 12:00", tz="UTC")) == sun  # Wednesday


def test_synthetic_weekly_freeze_uses_sunday_print_only():
    m = _mod()
    # 4h grid from Saturday 2022-01-01 00:00 UTC, one coin, rising sigma
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2022-01-01", tz="UTC") + i * pd.Timedelta(hours=4)
         for i in range(30)])
    sig = (np.arange(30, dtype=float).reshape(-1, 1) + 1.0) / 1000.0
    out, diag = m.build_weekly_sig4(idx, sig)
    assert out.shape == (30, 1)
    # Sunday 2022-01-02 00:00 print: last T <= Sun 00 is Sun 00 itself
    # (i=5, T=idx+4h); bars with T in [Sun 00, next Sun 00) freeze sig4[5].
    sun = pd.Timestamp("2022-01-02 00:00", tz="UTC")
    T = idx + pd.Timedelta(hours=4)
    week = (T >= sun)
    assert week.sum() == 30 - 5  # T[5] = Sun 00:00 is the print bar
    assert (out[week, 0] == sig[5, 0]).all()  # frozen at the Sunday print
    assert (out[~week, 0] == sig[~week, 0]).all()  # pre-Sunday: per-bar fallback
    assert diag["n_weeks"] == 2
    assert 0.0 < diag["frozen_frac"] <= 1.0
    assert diag["fallback_frac"] == pytest.approx(0.166667)


def test_synthetic_weekly_fallback_nan_warmup():
    m = _mod()
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2022-01-05", tz="UTC") + i * pd.Timedelta(hours=4)
         for i in range(6)])  # Wednesday week, jw exists
    sig = np.full((6, 2), 0.01)
    sig[0, 0] = np.nan  # warmup NaN at the print bar
    out, diag = m.build_weekly_sig4(idx, sig)
    assert out[2, 0] == pytest.approx(0.01)  # fallback to per-bar
    assert out[2, 1] == pytest.approx(0.01)
    assert diag["fallback_frac"] > 0.0


def test_synthetic_weekly_no_lookahead_first_week():
    m = _mod()
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2022-01-02 04:00", tz="UTC") + i * pd.Timedelta(hours=4)
         for i in range(4)])  # starts after the Sunday print week began
    sig = (np.arange(4, dtype=float).reshape(-1, 1) + 1.0) / 100.0
    out, _ = m.build_weekly_sig4(idx, sig)
    # jw for the first bars: last T <= Sun 00:00 -> none (index starts Sun 08:00
    # decision => T Sun 08? T[0] = Sun 08:00, ws = Sun 00, no T_j <= ws yet)
    assert (out[:, 0] == sig[:, 0]).all()  # pure per-bar fallback, no future use


def test_synthetic_round5_grid():
    m = _mod()
    assert m.round5(100.0, 0.5) == pytest.approx(100.0)
    assert m.round5(100.26, 0.5) == pytest.approx(100.5)  # nearest
    assert m.round5(100.24, 0.5) == pytest.approx(100.0)
    assert m.round5(3000.026, 0.05) == pytest.approx(3000.05)
    assert m.round5(2.00024, 0.0005) == pytest.approx(2.0)
    assert m.round5(2.00026, 0.0005) == pytest.approx(2.0005)
    assert np.isnan(m.round5(float("nan"), 0.5))
    assert m.round5(100.0, 0.0) == pytest.approx(100.0)


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    t = {"V1_WEEKLY": _row(3.0, 0.9, 15.0, 0),
         "V2_WEEKLY5T": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1_WEEKLY"
    t2 = {"V1_WEEKLY": _row(4.9, 1.5, 15.0, 0),
          "V2_WEEKLY5T": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2_WEEKLY5T"
    t3 = {"V1_WEEKLY": _row(6.0, 1.5, 21.0, 0),
          "V2_WEEKLY5T": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


def _stub_simulate(o1, sig_sl, cols, T, Oa, sgn, off, size, px, ps, m_sl, sdv,
                   mt, side, sd_a, P, k_t, amt, tg, cur_w, sg, _msl,
                   sleeve_tp, m_sleeve_tp, k, r, a, i, f, acts):
    out = {}
    lv = o1[i][a] * (1 - k * sig_sl[i][a])
    out["lv"] = lv
    tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None else float(sleeve_tp(i, a, r, f))) * sg)
    out["tp"] = tp
    sl = lv * (1 - _msl(a) * sg)
    out["sl"] = sl
    T["side"][a], T["px"][a], T["w"][a] = sgn, Oa[0] * (1 - sgn * off), size
    T["sl"][a], T["tp"][a], T["sd"][a] = px * (1 - ps * m_sl * sdv), px * (1 + ps * mt * sdv), sdv
    new = Oa[0] * (1 - side * P.get("tighten", 1.5) * sd_a)
    out["tpol"] = new
    new = Oa[0] * (1 - side * k_t * sd_a)
    out["tnp"] = new
    T["ak"][a], T["apx"][a], T["aw"][a] = 1, Oa[0] * (1 - side * off), amt.get("add") or abs(tg) - cur_w
    out["add"] = T["apx"][a]
    T["ak"][a], T["apx"][a], T["aw"][a] = -1, Oa[0] * (1 + side * off), 1.0 if "close" in acts else (amt.get("reduce") or P.get("reduce_frac", 0.5))
    out["red"] = T["apx"][a]
    T["ak"][a], T["apx"][a], T["aw"][a] = 1, Oa[0] * (1 - side * off), abs(tg) - cur_w
    T["ak"][a], T["apx"][a], T["aw"][a] = -1, Oa[0] * (1 + side * off), 1.0
    T["ak"][a], T["apx"][a], T["aw"][a] = -1, Oa[0] * (1 + side * off), P.get("reduce_frac", 0.5)
    return out


def _stub_eu():
    return types.SimpleNamespace(simulate=_stub_simulate)


def test_synthetic_v2_patch_rounds_all_sigma_prices():
    m = _mod()
    fn = m.make_weekly5t_simulate(_stub_eu())
    src = fn._patched_src
    assert src.count("_r5(") == 13  # 1+1+1+1+2+1+1+2+3 replacements
    assert "Oa[0] * (1 - sgn * off), size" not in src  # book px wrapped
    assert "lv * (1 - _msl(a) * sg), cols[a])" in src  # dip sl wrapped
    r5 = fn.__globals__["_r5"]
    assert r5(100.26, "BTCUSDT") == pytest.approx(100.5)
    assert r5(100.24, "BTCUSDT") == pytest.approx(100.0)
    assert r5(2.00026, "XRPUSDT") == pytest.approx(2.0005)
    assert fn._tick_step == m.TICK_STEP


def test_engine_anchor_counts_match_plan():
    m = _mod()
    src = (ROOT / "research/parallel/rounds/parallel-20260906-r2"
           / "engine_user" / "engine_user.py").read_text()
    assert src.count(m.DIP_LV) == 1
    assert src.count(m.DIP_TP) == 1
    assert src.count(m.DIP_SL) == 1
    assert src.count(m.BOOK_PX) == 1
    assert src.count(m.BOOK_SLTP) == 1
    assert src.count(m.TIGHTEN_POL) == 1
    assert src.count(m.TIGHTEN_NP) == 1
    assert src.count(m.SCALE_ADD) == 2
    assert src.count(m.SCALE_RED) == 3


# ---- causality / truncation -----------------------------------------------
def test_causality_builder_is_index_and_sig4_only():
    src = (HERE / "compute_m_weeklyvol.py").read_text()
    assert "build_weekly_sig4" in src
    assert "week_start_of" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute",
                "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_causality_v2_rounding_uses_price_and_tick_only():
    src = (HERE / "compute_m_weeklyvol.py").read_text()
    assert "_r5(" in src and "_TICK5" in src
    assert "def _slot_r5" in src
    # the rounding helper closes over nothing but price + frozen tick map
    helper = src.split("def _slot_r5")[1].split("def make_weekly5t_simulate")[0]
    for bad in ("La[", "Ha[", "Ca[", "Oa[", "sig4", "prep[", "events"):
        assert bad not in helper, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_weeklyvol.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_weeklyvol.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_script_is_ascii():
    src = (HERE / "compute_m_weeklyvol.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines())
           if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "V1_WEEKLY" in txt and "V2_WEEKLY5T" in txt and "M5_human" in txt
    assert "Sunday" in txt and "sigma360" in txt
    assert "POST-RELEASE" in txt
    assert "5-tick" in txt and "tick" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1_WEEKLY", "V2_WEEKLY5T"}
    assert out["meta"]["costs"] == {"maker": 0.0002, "taker": 0.00055,
                                    "fund_long_8h": 0.0001}
    assert out["meta"]["ticks"] == {"BTCUSDT": 0.10, "ETHUSDT": 0.01,
                                    "SOLUSDT": 0.01, "BNBUSDT": 0.10,
                                    "XRPUSDT": 0.0001}
    m5 = out["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)
    for row, v in out["rows"].items():
        assert len(v["years_R"]) == 5 and len(v["years_DD"]) == 5
        assert v["W"] == min(v["years_R"])
        assert v["maxDD"] == max(v["years_DD"])
        fac = 1.0
        for r in v["years_R"]:
            fac *= 1 + r / 100
        assert abs(fac ** (1 / 5) - 1 - v["R5"] / 100) < 5e-5
        assert v["book_win"] is not None and v["book_win"] >= 0
        assert v["rung_trades"] > 0
    assert out["rows"]["M5_human"]["frozen_frac"] == 0.0
    assert out["rows"]["V1_WEEKLY"]["frozen_frac"] > 0.0
    assert out["rows"]["V1_WEEKLY"]["frozen_frac"] == \
        out["rows"]["V2_WEEKLY5T"]["frozen_frac"]
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1_WEEKLY",
                                                   "V2_WEEKLY5T"}
    assert out["meta"]["pick_dev4"] in ("V1_WEEKLY", "V2_WEEKLY5T",
                                        "none-eligible")
    assert out["meta"]["weekly"]["0"]["n_weeks"] > 200


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1_WEEKLY" in rep and "V2_WEEKLY5T" in rep and "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
