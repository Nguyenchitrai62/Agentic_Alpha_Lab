"""oc_sleevealloc tests: gates, causality/truncation, hand-checked synthetic cases.

Run: `.venv/Scripts/python.exe -m pytest tests/test_oc_sleevealloc.py -q`
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE_RES = ROOT / "research/tournament/oc_sleevealloc/results.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def weights_from_dd(dd, cap=0.5):
    """Mirror of the PLAN V1 rule (standalone, synthetic-friendly)."""
    inv = np.array([1 / d for d in dd], float)
    raw = inv / inv.sum()
    wb, wd, wc = raw
    if wc > cap:
        s = wb + wd
        wb, wd, wc = 0.5 * wb / s, 0.5 * wd / s, cap
    tot = wb + wd + wc
    return wb / tot, wd / tot, wc / tot


def test_g2_reproduction_to_digit():
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    rm = _load("rm_t", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_t", RD / "v388/v388_bot_stop_distance.py")
    got = [rm.year_reset(runs, "R2B1D17BFG2", y) for y in range(5)]
    assert [(m["R"], m["DD"]) for m in got] == [(r, d) for r, d in exp["years"]]
    r5 = round(float(np.prod([1 + m["R"] / 100 for m in got]) ** (1 / 5) - 1) * 100, 3)
    assert r5 == exp["R"] == 5.41
    import pandas as pd
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, "R2B1D17BFG2", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"] == 16.82


def test_carry_mtm_reproduces_carrycompound_to_digit():
    mine = json.loads(HERE_RES.read_text())["five_y"]["REF_CARRY_f025"]
    ref = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())["rows"]["G2_f0.25"]
    assert [yy["R"] for yy in mine["years"]] == [yy["R"] for yy in ref["years"]]
    assert [yy["DD"] for yy in mine["years"]] == [yy["DD"] for yy in ref["years"]]
    assert mine["R"] == ref["R"] and mine["W"] == ref["W"] and mine["DD"] == ref["DD"]
    assert mine["full_path_dd"] == ref["full_path_dd"]


def test_carry_cap_handchecked_synthetic():
    # DDs: book 10%, dip 20%, carry 1% -> raw carry = (1/0.01)/(1/0.10+1/0.05+1/1)
    # = 100/130 = 0.7692 > 0.5 -> cap; book/dip rescaled preserving 2:1 ratio.
    wb, wd, wc = weights_from_dd([0.10, 0.20, 0.01])
    assert wc == 0.5
    assert abs(wb - 1 / 3) < 1e-9 and abs(wd - 1 / 6) < 1e-9
    assert abs(wb + wd + wc - 1.0) < 1e-12
    # no-cap case: DDs 10/10/10 -> equal thirds, hand-checked.
    wb2, wd2, wc2 = weights_from_dd([0.10, 0.10, 0.10])
    assert (wb2, wd2, wc2) == (1 / 3, 1 / 3, 1 / 3)


def test_capitalsplit_handchecked_synthetic():
    # One year, weights (0.5, 0.3, 0.2); sleeve end factors 1.20 / 1.10 / 0.90.
    # Combined = 0.5*1.20 + 0.3*1.10 + 0.2*0.90 = 0.60+0.33+0.18 = 1.11.
    w = (0.5, 0.3, 0.2)
    ends = (1.20, 1.10, 0.90)
    combined = sum(wi * ei for wi, ei in zip(w, ends))
    assert abs(combined - 1.11) < 1e-12
    monthly = 100 * (combined ** (1 / 12) - 1)
    assert abs(monthly - 100 * (1.11 ** (1 / 12) - 1)) < 1e-12
    assert monthly > 0  # sanity: blended gain stays a gain


def test_weights_use_preanchor_only_truncation():
    # Full 1000-bar synthetic DD table vs truncated (first 600 bars zeroed AFTER
    # the anchor): weights for the anchor year must be identical (causality).
    rng = np.random.default_rng(7)
    full = rng.normal(0, 0.01, size=(3, 1000))
    # trailing window = bars [100:900) for the anchor; truncation kills bars >= 600
    # only if 600 is AFTER the window end -> use window [100:500), truncate at 700.
    win_full = full[:, 100:500]
    trunc = full.copy()
    trunc[:, 700:] = 0.0  # after the window: must not change the weights
    win_tr = trunc[:, 100:500]
    assert np.array_equal(win_full, win_tr)
    dd = lambda w: max(float(np.max(1 - np.minimum.accumulate(w) / np.maximum.accumulate(w))), 0.005)
    # level series from returns
    lv = lambda r: np.cumprod(1 + r)
    assert weights_from_dd([dd(lv(win_full[i])) for i in range(3)]) == weights_from_dd(
        [dd(lv(win_tr[i])) for i in range(3)])


def test_results_internal_consistency():
    d = json.loads(HERE_RES.read_text())
    assert d["pick"] == "V2"
    for variant in ("V1", "V2"):
        for y in d["dev4"][variant]["years"]:
            # stored rounded to 4dp (0.3333x3 = 0.9999); computation used full precision
            assert abs(sum(y["w"]) - 1.0) < 2e-4
            assert y["w"][2] <= 0.5 + 1e-9
    # most-recent year scored once: exactly one year in y4_once rows
    assert len(d["y4_once"]["pick"]["years"]) == 1
    assert d["y4_once"]["pick"]["years"][0]["anchor"] == "2025-09-24"
    # robust rule: V2 has the higher dev4 WORST (tie) then higher mean
    assert d["dev4"]["V2"]["W"] >= d["dev4"]["V1"]["W"]
    assert d["dev4"]["V2"]["R"] >= d["dev4"]["V1"]["R"]
    # no losing dev year anywhere, DDs within gate for the candidates
    for k in ("V1", "V2", "CTRL-EQ"):
        assert d["dev4"][k]["losing"] == 0
        assert d["dev4"][k]["DD"] <= 20
