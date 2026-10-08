"""Tests for research/tournament/oc_booktrim (assignment OPENCODE_W_oc_booktrim)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_booktrim"

VARIANTS = ("REF", "BT08", "BT06")


def _load_compute():
    spec = importlib.util.spec_from_file_location(
        "oc_booktrim_mod", str(OC / "compute_booktrim_engine.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _table():
    return json.loads((OC / "tmp" / "booktrim_table.json").read_text())


def _results():
    return json.loads((OC / "results.json").read_text())


def test_results_exists_and_schema():
    t = _table()
    assert t["pick"] == "REF"
    assert set(t["dev"]) == {"base", "S5"}
    assert set(t["last"]) == {"base", "S5"}
    for fric in ("base", "S5"):
        assert set(t["dev"][fric]) == set(VARIANTS)
        assert set(t["last"][fric]) == {"REF"}  # pick==REF collapses last stage
    for stage in ("dev", "last"):
        for fric, rows in t[stage].items():
            for v, d in rows.items():
                for k in ("years_R", "years_DD", "Rdev4", "Wdev4", "DDdev4",
                          "losing_dev4", "full_path_dd", "DDmax_full", "wins",
                          "decomp"):
                    assert k in d, (stage, fric, v, k)
                dc = d["decomp"]
                for k in ("book", "dip", "fills", "wsum", "wmean", "near",
                          "over", "maxconc", "rungs", "book_share_dev4"):
                    assert k in dc, (stage, fric, v, k)
    r = _results()
    assert r["pick"] == "REF"
    assert r["dev_base"]["REF"]["Rdev4"] == 5.601


def test_reproduction_matches_v421_and_c2bybit():
    t = _table()
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    for y in range(4):
        er, ed = exp["years"][y]
        assert t["dev"]["base"]["REF"]["years_R"][y] == er
        assert t["dev"]["base"]["REF"]["years_DD"][y] == ed
    assert t["last"]["base"]["REF"]["R5y"] == exp["R"]
    assert t["last"]["base"]["REF"]["full_path_dd"] == exp["full_path_dd"]
    c2b = json.loads((ROOT / "research/tournament/oc_c2bybit/tmp/c2bybit_table.json").read_text())["table"]
    for y in range(5):
        assert t["last"]["S5"]["REF"]["years_R"][y] == c2b["REF_S5"]["years_R"][y]
        assert t["last"]["S5"]["REF"]["years_DD"][y] == c2b["REF_S5"]["years_DD"][y]
    assert t["last"]["S5"]["REF"]["full_path_dd"] == c2b["REF_S5"]["full_path_dd"]


def test_aggregates_consistent():
    t = _table()
    for stage in ("dev", "last"):
        for fric, rows in t[stage].items():
            for v, d in rows.items():
                Rs, DDs = d["years_R"], d["years_DD"]
                assert d["Wdev4"] == round(min(Rs[:4]), 3)
                assert d["DDdev4"] == round(max(DDs[:4]), 2)
                assert d["losing_dev4"] == sum(r < 0 for r in Rs[:4])
                g = 1.0
                for x in Rs[:4]:
                    g *= 1.0 + x / 100.0
                assert abs(100.0 * (g ** 0.25 - 1.0) - d["Rdev4"]) < 1e-2
                assert d["DDmax_full"] == round(max(max(DDs), d["full_path_dd"]), 2)
                for w in d["wins"]:
                    n = w["nb"] + w["nr"]
                    if n:
                        assert abs(w["all_win"] - round((w["wb"] + w["wr"]) / n, 4)) < 1e-9
                dc = d["decomp"]
                assert sum(dc["fills"][:4]) <= sum(dc["rungs"])
                assert all(nc <= f for nc, f in zip(dc["near"], dc["fills"]))
                assert all(o == 0 for o in dc["over"])  # engine cuts to room
                assert all(mc <= 2.0 + 1e-9 for mc in dc["maxconc"])
                for y in range(5):
                    if dc["fills"][y]:
                        assert abs(dc["wmean"][y] - round(dc["wsum"][y] / dc["fills"][y], 6)) < 1e-9


def test_pick_rule_matches_dev_base_only():
    t = _table()
    cands = {v: t["dev"]["base"][v] for v in VARIANTS}
    elig = [v for v in VARIANTS if cands[v]["DDdev4"] <= 20 and cands[v]["losing_dev4"] == 0]
    over5 = [v for v in elig if cands[v]["Rdev4"] >= 5]
    pool = over5 or elig
    pick = max(pool, key=lambda v: (cands[v]["Wdev4"], cands[v]["Rdev4"]))
    assert pick == "REF" == t["pick"]
    # trim loses monotonically on both price sources
    assert cands["BT08"]["Rdev4"] < cands["REF"]["Rdev4"]
    assert cands["BT06"]["Rdev4"] < cands["BT08"]["Rdev4"]
    s5 = {v: t["dev"]["S5"][v] for v in VARIANTS}
    assert s5["BT08"]["Rdev4"] < s5["REF"]["Rdev4"]
    assert s5["BT06"]["Rdev4"] < s5["BT08"]["Rdev4"]
    # BT variants' clean year was never computed
    assert "BT08" not in t["last"]["base"] and "BT06" not in t["last"]["base"]


def test_book_scale_wiring_present():
    src = (OC / "compute_booktrim_engine.py").read_text()
    assert 'trade["book_mult"] = BOOK_MULT[variant]' in src
    assert '"BT08": 0.8' in src and '"BT06": 0.6' in src
    assert "REF omits the key" in src
    # G2 harness pinned: kd 1.7, bear filter, G 2.0, win_start 5
    assert "mult * 1.7 * base_size" in src
    assert 'kw["sleeve_gross_cap"] = 2.0' in src
    assert 'kw["sleeve_risk_budget"]' in src and "0.26" in src
    assert "rolling(1200" in src and "min_periods=600" in src
    assert "win_start=5" in src
    assert "bybit_minutes" in src and "2021-11-15" in src
    assert "attrib=att" in src and "pair_rungs" in src
    assert "year_reset" in (OC / "analyze_booktrim.py").read_text()
    assert "v388.mix" in (OC / "analyze_booktrim.py").read_text()


def test_pair_rungs_hand_checked():
    m = _load_compute()
    T = pd.Timestamp("2022-01-01", tz="UTC")
    ev = [
        dict(t=T, symbol="BTCUSDT", kind="rung_fill", weight=1.0),
        dict(t=T + pd.Timedelta(hours=2), symbol="BTCUSDT", kind="rung_tp",
             weight=1.0, ret=0.01),
        dict(t=T + pd.Timedelta(hours=1), symbol="ETHUSDT", kind="rung_fill", weight=0.5),
        dict(t=T + pd.Timedelta(hours=5), symbol="ETHUSDT", kind="rung_sl",
             weight=0.5, ret=-0.02),
    ]
    fns, xns, ws = m.pair_rungs(ev)
    assert len(ws) == 2
    assert sorted(ws.tolist()) == [0.5, 1.0]
    # unpaired fill raises (causality: every fill must carry its exit)
    import pytest
    with pytest.raises(AssertionError):
        m.pair_rungs([dict(t=T, symbol="BTCUSDT", kind="rung_fill", weight=1.0)])


def test_cap_sweep_hand_checked_and_order_invariant():
    m = _load_compute()
    T0 = pd.Timestamp("2022-01-01", tz="UTC").value
    H = 3600 * 10 ** 9
    # two overlapping rungs w=1.0, third arriving at full concurrency
    fns = np.array([T0, T0 + H, T0 + 2 * H])
    xns = np.array([T0 + 8 * H, T0 + 9 * H, T0 + 3 * H])
    ws = np.array([1.0, 1.0, 0.5])
    cs = m.cap_sweep(fns, xns, ws)
    assert cs["fills_total"] == 3
    assert cs["max_concurrent"] == 2.5
    # C before fills: 0, 1.0, 2.0 -> second and third near (>= 1.5 only third);
    # over: third 2.0 + 0.5 > 2.0
    assert cs["near"] == 1
    assert cs["over"] == 1
    # truncation / order determinism: shuffled input gives identical per-fill
    # concurrency matched by fill time (causality check)
    rng = np.random.default_rng(0)
    perm = rng.permutation(3)
    cs2 = m.cap_sweep(fns[perm], xns[perm], ws[perm])
    assert cs2["near"] == cs["near"] and cs2["over"] == cs["over"]
    assert cs2["max_concurrent"] == cs["max_concurrent"]
    # disjoint rungs never near the cap
    cs3 = m.cap_sweep(np.array([T0, T0 + 2 * H]), np.array([T0 + H, T0 + 3 * H]),
                      np.array([0.1, 0.1]))
    assert cs3["max_concurrent"] == 0.1 and cs3["near"] == 0 and cs3["over"] == 0
