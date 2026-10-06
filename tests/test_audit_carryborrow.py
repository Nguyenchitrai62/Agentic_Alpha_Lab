"""Blind audit test for oc_carryborrow f=0.5 + borrow cost.

Compares research/tournament/audit_carryborrow/replication.json (built blind)
against the published oc_carryborrow REPORT.md values within tolerance
0.01 %/mo (R) and 0.05 pp (DD). No engine reruns, no REPORT read at build time.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent.parent / "research/tournament/audit_carryborrow"
REPORT_EXPECTED = {
    ("base", "f=0.5_apr10"): {
        "years": [
            (2.658, 10.86), (3.272, 16.93), (6.735, 15.60),
            (10.797, 8.15), (4.586, 12.53),
        ],
        "R_5y": 5.569, "W": 2.658, "DD_maxyearly": 16.93,
        "full": 16.84, "losing": 0,
    },
    ("base", "f=0.5_apr15"): {
        "years": [
            (2.503, 10.86), (3.195, 17.10), (6.538, 15.60),
            (10.577, 8.16), (4.504, 12.59),
        ],
        "R_5y": 5.424, "W": 2.503, "DD_maxyearly": 17.10,
        "full": 17.01, "losing": 0,
    },
    ("S1", "f=0.5_apr10"): {
        "years": [
            (2.009, 11.18), (2.560, 17.47), (5.495, 15.78),
            (9.778, 8.19), (3.822, 13.25),
        ],
        "R_5y": 4.696, "W": 2.009, "DD_maxyearly": 17.47,
        "full": 17.39, "losing": 0,
    },
    ("S1", "f=0.5_apr15"): {
        "years": [
            (1.853, 11.18), (2.482, 17.64), (5.297, 15.78),
            (9.557, 8.19), (3.740, 13.79),
        ],
        "R_5y": 4.550, "W": 1.853, "DD_maxyearly": 17.64,
        "full": 17.56, "losing": 0,
    },
}

TOL_R = 0.01 + 1e-9
TOL_DD = 0.05 + 1e-9


def _load_rep():
    rep = json.loads((HERE / "replication.json").read_text())
    return {(c["scen"], c["label"]): c for c in rep["combos"]}


def test_replication_matches_report_within_tolerance():
    got = _load_rep()
    for key, exp in REPORT_EXPECTED.items():
        c = got[key]
        assert abs(c["R_5y"] - exp["R_5y"]) <= TOL_R, (key, c["R_5y"], exp["R_5y"])
        assert abs(c["W"] - exp["W"]) <= TOL_R, (key, c["W"], exp["W"])
        assert abs(c["DD_maxyearly"] - exp["DD_maxyearly"]) <= TOL_DD, key
        assert abs(c["full_path_dd"]["full"] - exp["full"]) <= TOL_DD, key
        assert c["losing_years"] == exp["losing"], key
        for yy, (er, edd) in zip(c["years"], exp["years"]):
            assert abs(yy["R"] - er) <= TOL_R, (key, yy, er)
            assert abs(yy["DD"] - edd) <= TOL_DD, (key, yy, edd)


def test_f025_reproduces_carrycompound_to_digit():
    root = Path(__file__).parent.parent
    cmp_rows = json.loads((root / "research/tournament/oc_carrycompound/results.json").read_text())["rows"]
    ref = cmp_rows["G2_f0.25"]
    got = _load_rep()[("base", "f=0.25")]
    assert [y["R"] for y in got["years"]] == [y["R"] for y in ref["years"]]
    assert [y["DD"] for y in got["years"]] == [y["DD"] for y in ref["years"]]
    assert got["R_5y"] == ref["R"] and got["W"] == ref["W"]
    assert got["DD_maxyearly"] == ref["DD"]
    assert got["full_path_dd"]["full"] == ref["full_path_dd"]["full"]


def test_borrow_economics_sane():
    got = _load_rep()
    # no borrow on f=0.25 legs
    assert all(v == 0.0 for v in got[("base", "f=0.25")]["borrow_paid_year_acct"])
    # borrow paid positive and ~1.5x from 10% to 15% APR
    for scen in ("base", "S1"):
        b10 = got[(scen, "f=0.5_apr10")]["borrow_paid_year_acct"]
        b15 = got[(scen, "f=0.5_apr15")]["borrow_paid_year_acct"]
        assert all(v > 0 for v in b10) and all(v > 0 for v in b15)
        for a, b in zip(b10, b15):
            assert abs(b / a - 1.5) < 0.02, (scen, a, b)
        # borrow drags return below f=0.25 in both scens
        r25 = got[(scen, "f=0.25")]["R_5y"]
        assert got[(scen, "f=0.5_apr10")]["R_5y"] < r25
        assert got[(scen, "f=0.5_apr15")]["R_5y"] < got[(scen, "f=0.5_apr10")]["R_5y"]


def test_grid_capped_and_causal_spec():
    rep = json.loads((HERE / "replication.json").read_text())
    assert rep["meta"]["grid"][1].startswith("2026-09-23 12:00")
    src = (HERE / "replicate.py").read_text()
    # causal last-CLOSED-bar helper and strict inside-window borrow
    assert 'side="left") - 1' in src
    assert "tnow > trades[k][\"tc_ns\"] and tnow < trades[k][\"ts_ns\"]" in src
    assert "APR/8760" in src or "apr / HRS_YR" in src
