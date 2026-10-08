"""Tests for oc_spotlongs (gate, headlines, causality, synthetics)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_spotlongs"
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"

import sys

sys.path.insert(0, str(HERE))
import spot_patch  # noqa: E402
import spot_rule  # noqa: E402


def _res():
    return json.loads((HERE / "results.json").read_text())


def _tab():
    return json.loads((HERE / "tmp/spotlongs_table.json").read_text())


def test_v0_reproduces_v421_dev_to_digit():
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = _tab()["table"]["V0"]
    assert got["years_R"] == [r for r, _ in exp["years"][:4]]
    assert got["years_DD"] == [d for _, d in exp["years"][:4]]
    assert got["Rdev4"] == 5.601 and got["Wdev4"] == 2.588
    assert _tab()["pick"] == "V1"


def test_dev_headlines():
    t = _tab()["table"]
    assert (t["V1"]["Rdev4"], t["V1"]["Wdev4"], t["V1"]["DDmax_full"],
            t["V1"]["losing_dev4"]) == (5.859, 2.664, 16.68, 0)
    assert (t["V2"]["Rdev4"], t["V2"]["Wdev4"], t["V2"]["DDmax_full"],
            t["V2"]["losing_dev4"]) == (5.694, 2.594, 16.97, 0)
    # V1 wins the frozen robust rule (both eligible, both mean>=5, highest WORST)
    assert t["V1"]["Wdev4"] > t["V2"]["Wdev4"]


def test_full_window_gate_legs():
    t = _tab()["table"]
    v1 = t["V1_full"]
    assert v1["years_R"] == [2.664, 3.515, 6.401, 11.055, 4.876]
    assert v1["R5y"] == 5.661 and v1["W5y"] == 2.664
    assert v1["losing_5y"] == 0 and v1["full_path_dd"] == 16.62
    assert v1["DDmax_full"] == 16.68
    ref = t["REF_stored"]
    assert (ref["R5y"], ref["full_path_dd"]) == (5.41, 16.82)
    assert v1["years_R"][4] == 4.876  # scored once; below the 5 floor
    assert ref["years_R"][4] == 4.648


def test_ctrl_and_stress_attribution():
    t = _tab()["table"]
    assert t["V1_CTRL_full"]["R5y"] == 5.433  # ~REF 5.41 (+0.023 overlay residue)
    assert round(t["V1_full"]["R5y"] - t["V1_CTRL_full"]["R5y"], 3) == 0.228
    assert t["V1_APR15_full"]["R5y"] < t["V1_full"]["R5y"]  # more borrow hurts
    assert t["V1_full"]["R5y"] - t["V1_APR15_full"]["R5y"] < 0.01  # immaterial


def test_s5_gap_preserved():
    t = _tab()["table"]
    assert t["V1_S5"]["Rdev4"] == 5.207
    assert t["REF_S5_side"]["Rdev4"] == 4.994
    assert round(t["V1_S5"]["Rdev4"] - t["REF_S5_side"]["Rdev4"], 3) == 0.213


def test_spot_patch_verbatim_and_defaults():
    import inspect
    src = spot_patch.EU_PATH.read_text(encoding="utf-8")
    for anchor in (spot_patch._ANCHOR_SIG, spot_patch._ANCHOR_HERE,
                   spot_patch._ANCHOR_FUND_A, spot_patch._ANCHOR_FUND_B,
                   spot_patch._ANCHOR_ASSET, spot_patch._ANCHOR_LOOP_END,
                   spot_patch._ANCHOR_BARS):
        assert src.count(anchor) == 1, anchor
    m = spot_patch.load()
    sig = inspect.signature(m.simulate)
    assert sig.parameters["spot_route"].default is None
    assert sig.parameters["borrow_apr"].default == 0.0
    assert m.FUND_LONG == 0.0001 and m.MAKER == 0.0002 and m.TAKER == 0.00055


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
    f7 = spot_rule.f7_at(Tn, c_ns, fund["T"]["r"].to_numpy())
    # the 0.09 settlement stamped exactly at T0 is excluded; window holds 21
    # settlements of 0.0002 -> mean 0.0002
    assert abs(f7[0] - 0.0002) < 1e-12
    # far-away T with < 14 settlements in window -> NaN, never routed
    Tfar = np.array([(pd.Timestamp("2020-01-02", tz="UTC")).value])
    assert np.isnan(spot_rule.f7_at(Tfar, c_ns, fund["T"]["r"].to_numpy())[0])


def test_median_embargo_and_route():
    fund, _ = _synth_fund()
    meds = spot_rule.medians(fund)
    # truncated panel (drop everything >= A0 - 7d) gives identical medians
    cut = pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(days=7)
    trunc = {s: df[df["c"] < cut] for s, df in fund.items()}
    meds2 = spot_rule.medians(trunc)
    assert meds == meds2
    # route: finite F7 above median -> True; NaN -> False
    T_list = [pd.Timestamp("2021-06-01", tz="UTC")]
    y_of = np.array([0])
    meds3 = {"2021-09-24": {"T": 0.0001}, "2022-09-24": {"T": 0.0},
             "2023-09-24": {"T": 0.0}, "2024-09-24": {"T": 0.0},
             "2025-09-24": {"T": 0.0}}
    r = spot_rule.route_matrix(T_list, ["T"], y_of, meds3, fund)
    assert r.shape == (1, 1) and r[0, 0] in (True, False)


def test_borrow_bar_hand_values():
    assert spot_rule.borrow_bar(1.5, 0.10) == 0.5 * 0.10 * 4.0 / 8760.0
    assert spot_rule.borrow_bar(1.0, 0.10) == 0.0
    assert spot_rule.borrow_bar(0.2, 0.10) == 0.0
    assert spot_rule.borrow_bar(2.0, 0.0) == 0.0
    assert spot_rule.borrow_bar(float("nan"), 0.10) == 0.0


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("5.859", "5.694", "5.661", "4.876", "4.648", "16.68",
                   "16.62", "5.207", "4.994", "0.213", "0.228",
                   "Reproduction gate", "KHÔNG deploy", "Post-hoc log",
                   "win_start=5", "stop-first"):
        assert needle in rep, needle
