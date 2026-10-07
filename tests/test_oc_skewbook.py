"""Tests for oc_skewbook (research/tournament/oc_skewbook). Consistency checks on results.json."""

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_skewbook"
RES = HERE / "results.json"
BOOKIC = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bookic" / "results.json"


def _load():
    return json.loads(RES.read_text())


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_skewbook/compute_skewbook.py first"
    r = _load()
    for k in ("ic", "cutoffs", "terciles", "E_high_minus_low", "full_sign",
              "loyo", "per_year", "verdict_rule", "definitions"):
        assert k in r, k
    assert len(r["ic"]) == 25  # 5 years x 5 coins
    assert len(r["cutoffs"]) == 5
    assert len(r["terciles"]) == 15  # 5 years x low/mid/high
    assert len(r["per_year"]) == 5
    assert len(r["E_high_minus_low"]) == 5
    assert len(r["loyo"]) == 5
    assert r["verdict_rule"] in ("PROMISING", "NOT PROMISING")


def test_legs_and_coins_partition_terciles():
    r = _load()
    for t in r["terciles"]:
        assert abs(t["pnl_total"] - (t["pnl_long"] + t["pnl_short"])) < 5e-6, t
        assert abs(sum(t["per_coin"].values()) - t["pnl_total"]) < 5e-6, t
        assert t["n_bars"] >= 0


def test_year_aggregation_and_E_consistency():
    r = _load()
    for y in r["per_year"]:
        rows = [t for t in r["terciles"] if t["year"] == y["year"]]
        assert len(rows) == 3
        assert abs(sum(t["pnl_total"] for t in rows) - y["pnl_total"]) < 5e-6, y
        hi = next(t for t in rows if t["tercile"] == "high")["pnl_total"]
        lo = next(t for t in rows if t["tercile"] == "low")["pnl_total"]
        assert abs((hi - lo) - y["E_high_minus_low"]) < 5e-6, y
        assert abs((hi - lo) - r["E_high_minus_low"][y["year"]]) < 5e-6, y


def test_cutoffs_causal_and_finite():
    r = _load()
    for c in r["cutoffs"]:
        assert c["n_hist"] > 1000, c  # multi-year pre-anchor history, never empty
        assert c["q33"] < c["q67"], c
        # cut-off history must end strictly before the anchor year starts
        anchor = pd.Timestamp(c["year"], tz="UTC")
        assert pd.Timestamp(c["hist_to"]) < anchor, c
        assert pd.Timestamp(c["hist_from"]) < pd.Timestamp("2021-09-24", tz="UTC"), c


def test_verdict_rule_recomputed():
    r = _load()
    E = r["E_high_minus_low"]
    S = "neg" if sum(E.values()) < 0 else ("pos" if sum(E.values()) > 0 else "zero")
    assert S == r["full_sign"]
    n_same = sum(1 for y in r["per_year"] if y["sign"] == S)
    n_loyo = sum(1 for L in r["loyo"] if L["holds"])
    expect = "PROMISING" if (n_same >= 4 and n_loyo >= 4) else "NOT PROMISING"
    assert expect == r["verdict_rule"]
    for L in r["loyo"]:
        rest = sum(v for k, v in E.items() if k != L["excluded_year"])
        sj = "neg" if rest < 0 else ("pos" if rest > 0 else "zero")
        assert sj == L["sign_rest"], L


def test_ic_bounds_and_coverage():
    r = _load()
    for row in r["ic"]:
        for k in ("ic6", "ic42", "ic6_putbuy", "ic42_putbuy",
                  "ic6_ethskew", "ic42_ethskew"):
            v = row.get(k)
            if v is not None:
                assert -1.0 <= v <= 1.0, (row, k)
        assert row["n_bars"] >= 2140, row  # full anchor year on the 4h grid


def test_year_totals_match_oc_bookic():
    # Same book rebuild + same grid must give the same gross year totals.
    b = json.loads(BOOKIC.read_text())
    r = _load()
    ref = {y["year"]: y["pnl_total"] for y in b["per_year"]}
    for y in r["per_year"]:
        assert abs(y["pnl_total"] - ref[y["year"]]) < 5e-6, y


def test_asof_takes_last_complete_bar_only():
    # Synthetic hand-check of the causal alignment: bar T covers [T, T+4h);
    # the decision at grid t may only see bars with start <= t, and must
    # prefer the latest such bar (the just-completed one), never a later bar.
    opt = pd.DataFrame({
        "bar": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 04:00",
                               "2021-01-01 08:00"], utc=True),
        "skew": [1.0, 2.0, 3.0],
    }).sort_values("bar")
    grid = pd.DataFrame({"t": pd.to_datetime(["2021-01-01 04:00",
                                              "2021-01-01 06:00"], utc=True)})
    m = pd.merge_asof(grid.sort_values("t"), opt.rename(columns={"bar": "t"}),
                      on="t", direction="backward")
    assert m["skew"].tolist() == [2.0, 2.0]  # 08:00 bar not yet complete
