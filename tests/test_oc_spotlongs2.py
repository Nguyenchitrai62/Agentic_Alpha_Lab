"""Tests for oc_spotlongs2 (honest spot fees on spot-routed book longs).

Phase 1 (pre-engine, fast): patch structure/defaults, rule causality and
hand-checked synthetics. Phase 2 (post-engine) headline + accounting-identity
assertions are appended after the engine runs (same pattern as oc_spotlongs).
"""

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_spotlongs2"

import sys

sys.path.insert(0, str(HERE))
import spot_patch2  # noqa: E402
import spot_rule2  # noqa: E402


def test_fee_constants_frozen():
    assert spot_rule2.SPOT_F10_MAKER == 0.001
    assert spot_rule2.SPOT_F10_TAKER == 0.001
    assert spot_rule2.SPOT_F06_MAKER == 0.0006
    assert spot_rule2.SPOT_F06_TAKER == 0.0006
    assert spot_rule2.GATE_MAKER == 0.0002
    assert spot_rule2.GATE_TAKER == 0.00055
    assert spot_rule2.BORROW_APR == 0.10


def test_spot_patch_verbatim_and_defaults():
    src = spot_patch2.EU_PATH.read_text(encoding="utf-8")
    for anchor in (spot_patch2._ANCHOR_SIG, spot_patch2._ANCHOR_HERE,
                   spot_patch2._ANCHOR_FUND_A, spot_patch2._ANCHOR_FUND_B,
                   spot_patch2._ANCHOR_ASSET, spot_patch2._ANCHOR_LOOP_END,
                   spot_patch2._ANCHOR_BARS, spot_patch2._ANCHOR_STATS,
                   spot_patch2._ANCHOR_TRADE_OPEN, spot_patch2._ANCHOR_ENTRY,
                   spot_patch2._ANCHOR_TP, spot_patch2._ANCHOR_ADD,
                   spot_patch2._ANCHOR_REDUCE, spot_patch2._ANCHOR_PARTIAL):
        assert src.count(anchor) == 1, anchor
    assert src.count(spot_patch2._ANCHOR_STOP) == 2
    m = spot_patch2.load()
    sig = inspect.signature(m.simulate)
    assert sig.parameters["spot_route"].default is None
    assert sig.parameters["borrow_apr"].default == 0.0
    assert sig.parameters["spot_maker"].default == m.MAKER == 0.0002
    assert sig.parameters["spot_taker"].default == m.TAKER == 0.00055
    assert m.FUND_LONG == 0.0001


def test_fee_switch_sites_present_once_each():
    src = spot_patch2.patched_source()
    # one rate decision per book fee site (entry/2x stop/TP/add/reduce/partial)
    assert src.count("_rtE = _bkfee(ps > 0, False)") == 1
    assert src.count("_rtS = _bkfee(cur_q > 0, True)") == 2
    assert src.count("_rtT = _bkfee(cur_q > 0, False)") == 1
    assert src.count("_rtA = _bkfee(cur_q > 0, False)") == 1
    assert src.count("_rtR = _bkfee(cur_q > 0, False)") == 1
    assert src.count("_rtP = _bkfee(cur_q > 0, False)") == 1
    # dip-sleeve fee math is untouched (still raw MAKER/TAKER in rung returns)
    assert "ret = _slip(fm_lv, 1, La[f], Ha[f]) / lv - 1 - MAKER - TAKER" in src
    assert "ret = tp / lv - 1 - 2 * MAKER" in src
    # non-trade branch (trade=None) left byte-identical: variable fee vars kept
    assert "carr[fill_min:] -= dq * fill_px + abs(dq) * fill_px * fill_fee" in src
    assert "mm, px, fee, kind = ev" in src


def _synth_fund():
    base = pd.Timestamp("2021-01-01", tz="UTC")
    # settlements every 8h, rate 0.0002, plus one stamped EXACTLY at T0
    T0 = base + pd.Timedelta(days=10)
    cs = [base + pd.Timedelta(hours=8 * k) for k in range(40)] + [T0]
    df = pd.DataFrame({"c": pd.to_datetime(sorted(cs), utc=True),
                       "r": [0.0002] * 40 + [0.09]})
    return {"T": df}, T0


def test_f7_strictly_before_T_and_min_settle():
    fund, T0 = _synth_fund()
    Tn = np.array([T0.value])
    c_ns = fund["T"]["c"].values.astype("datetime64[ns]").astype(np.int64)
    f7 = spot_rule2.f7_at(Tn, c_ns, fund["T"]["r"].to_numpy())
    # the 0.09 settlement stamped exactly at T0 is excluded; window holds 21
    # settlements of 0.0002 -> mean 0.0002
    assert abs(f7[0] - 0.0002) < 1e-12
    # far-away T with < 14 settlements in window -> NaN, never routed
    Tfar = np.array([(pd.Timestamp("2020-01-02", tz="UTC")).value])
    assert np.isnan(spot_rule2.f7_at(Tfar, c_ns, fund["T"]["r"].to_numpy())[0])


def test_median_embargo_truncation_identical():
    fund, _ = _synth_fund()
    meds = spot_rule2.medians(fund)
    # truncated panel (drop everything >= A0 - 7d) gives identical medians
    cut = pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(days=7)
    trunc = {s: df[df["c"] < cut] for s, df in fund.items()}
    meds2 = spot_rule2.medians(trunc)
    assert meds == meds2


def test_borrow_bar_hand_values():
    assert spot_rule2.borrow_bar(1.5, 0.10) == 0.5 * 0.10 * 4.0 / 8760.0
    assert spot_rule2.borrow_bar(1.0, 0.10) == 0.0
    assert spot_rule2.borrow_bar(0.2, 0.10) == 0.0
    assert spot_rule2.borrow_bar(2.0, 0.0) == 0.0
    assert spot_rule2.borrow_bar(float("nan"), 0.10) == 0.0


def _tab():
    return json.loads((HERE / "tmp/spotlongs2_table.json").read_text())


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_ref_reproduces_v421_dev_to_digit():
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = _tab()["table"]["REF"]
    assert got["years_R"] == [r for r, _ in exp["years"][:4]]
    assert got["years_DD"] == [d for _, d in exp["years"][:4]]
    assert got["Rdev4"] == 5.601 and got["Wdev4"] == 2.588
    assert _tab()["pick"] == "REF"
    assert (HERE / "tmp/spotlongs2_table.json").exists()


def test_dev_headlines_and_robust_pick():
    t = _tab()["table"]
    assert (t["SPOT_F10"]["Rdev4"], t["SPOT_F10"]["Wdev4"],
            t["SPOT_F10"]["DDmax_full"], t["SPOT_F10"]["losing_dev4"]) == (5.675, 2.56, 16.94, 0)
    assert (t["SPOT_F06"]["Rdev4"], t["SPOT_F06"]["Wdev4"],
            t["SPOT_F06"]["DDmax_full"]) == (5.73, 2.613, 17.03)
    # Frozen robust rule on dev4 (REF vs SPOT_F10): both eligible, both mean>=5
    # -> highest WORST wins -> REF (2.588 > 2.560). SPOT_F06 is sensitivity-only.
    assert t["REF"]["Wdev4"] > t["SPOT_F10"]["Wdev4"]
    assert t["REF"]["Rdev4"] == 5.601


def test_honest_fees_erase_the_v1_edge():
    t = _tab()["table"]
    # V1 at perp fees: +0.258 dev4 (5.859 vs 5.601). At honest 0.001 fees the
    # dev4 gap shrinks to +0.074 with a WORSE worst year — no selectable edge.
    assert round(t["SPOT_F10"]["Rdev4"] - t["REF"]["Rdev4"], 3) == 0.074
    assert round(t["SPOT_F06"]["Rdev4"] - t["REF"]["Rdev4"], 3) == 0.129


def test_fee_funding_split_identities():
    t = _tab()["table"]
    ref = t["REF"]["split_dev_years"]
    f10 = t["SPOT_F10"]["split_dev_years"]
    for y in ("0", "1", "2", "3"):
        # REF pays perp fees + gate funding, never spot legs
        assert ref[y]["spot_fees"] == 0.0
        assert ref[y]["funding_saved"] == 0.0
        assert ref[y]["borrow"] == 0.0
        assert ref[y]["funding_paid"] > 0.0
        assert ref[y]["turnover"] > 30.0  # the book churns a lot: honest fees bite
        # SPOT_F10: longs spot-routed -> no perp funding paid, spot fees dominate
        assert f10[y]["funding_paid"] == 0.0
        assert f10[y]["spot_fees"] > 0.0
        assert f10[y]["perp_fees"] > 0.0  # short legs stay perp
        assert f10[y]["funding_saved"] > 0.0
        # same exposure -> funding saved ~= REF funding paid (second order only)
        assert abs(f10[y]["funding_saved"] - ref[y]["funding_paid"]) < 2e-4
    # Direct arithmetic nets to ~zero: extra book fees ~= funding saved
    # (yearly means across dev4), so the +0.074 residual is path second order.
    ref_fee = sum(ref[y]["perp_fees"] for y in ("0", "1", "2", "3")) / 4
    f10_fee = sum(f10[y]["spot_fees"] + f10[y]["perp_fees"] for y in ("0", "1", "2", "3")) / 4
    saved = sum(f10[y]["funding_saved"] for y in ("0", "1", "2", "3")) / 4
    assert abs((f10_fee - ref_fee) - saved) < 0.001


def test_stats_vs_bars_turnover_consistent():
    import pickle
    runs = pickle.loads((HERE / "tmp/runs_dev_base.pkl").read_bytes())
    for s in range(4):
        for v in ("REF", "SPOT_F10", "SPOT_F06"):
            bars_sum = sum(b["turnover"] for b in runs[s][v]["bars_lite"])
            assert abs(runs[s][v]["stats"]["book_turnover"] - bars_sum) < 1e-6
            assert abs(runs[s][v]["stats"]["book_spot_fees"]
                       - sum(b["spot_fees"] for b in runs[s][v]["bars_lite"])) < 1e-9
            assert abs(runs[s][v]["stats"]["book_perp_fees"]
                       - sum(b["perp_fees"] for b in runs[s][v]["bars_lite"])) < 1e-9
    # REF never touches a spot leg anywhere
    for s in range(4):
        assert runs[s]["REF"]["stats"]["book_spot_fees"] == 0.0


def test_no_y4_scoring_for_unpicked():
    t = _tab()["table"]
    # Pick is REF (stored row); SPOT rows stay dev-only: Y4 never scored.
    assert t["SPOT_F10"]["years_idx"] == [0, 1, 2, 3]
    assert t["SPOT_F10"]["R5y"] is None
    assert t["SPOT_F06"]["R5y"] is None
    ref = t["REF_stored"]
    assert (ref["R5y"], ref["W5y"], ref["full_path_dd"]) == (5.41, 2.588, 16.82)
    assert ref["years_R"][4] == 4.648
    assert t["REF_S5_side"]["Rdev4"] == 4.994


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("5.675", "5.601", "2.560", "2.588", "0.074", "16.94",
                   "Reproduction gate", "KHÔNG deploy", "Post-hoc log",
                   "win_start=5", "stop-first", "tpslOrder", "turnover"):
        assert needle in rep, needle


def test_honest_fee_multiple_hand_checked():
    """Synthetic: 2.0x annual book turnover at honest spot vs perp rates.

    Uses the REAL frozen constants. Perp round-trip 2x0.0002 on 2.0x turnover
    = 0.0008/yr drag; honest spot 2x0.001 = 0.0040/yr — a 5x fee multiple, or
    +0.0032/yr (+0.027 pp/mo) of extra drag per 2x turnover, before any
    stop-taker mix. The V1 funding save was ~0.4118/4yr = 0.103/yr, so the
    break-even turnover is ~0.103/0.0016 ~= 64x/yr — the engine decides.
    """
    m = spot_patch2.load()
    turn = 2.0
    perp_drag = turn * 2 * m.MAKER
    spot_drag = turn * 2 * spot_rule2.SPOT_F10_TAKER
    assert perp_drag == 2.0 * 2 * 0.0002 == 0.0008
    assert spot_drag == 2.0 * 2 * 0.001 == 0.0040
    assert round((spot_drag - perp_drag) * 100 / 12, 4) == round(0.0032 * 100 / 12, 4)
