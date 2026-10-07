"""Tests for oc_plateau2 (light: static config + pure helpers; no engine run)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PL2 = ROOT / "research/diagnostics/oc_plateau2"


def _load():
    spec = importlib.util.spec_from_file_location("oc_plateau2", PL2 / "oc_plateau2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_runs_fixed():
    m = _load()
    assert set(m.RUNS) == {"R2B1D17BFG2", "R2B1D17BFG2_TP08", "R2B1D17BFG2_TP12",
                           "R2B1D17BFG2_SL35", "R2B1D17BFG2_SL45",
                           "R2B1D17BFG2_G175", "R2B1D17BFG2_G225"}
    assert m.REF == "R2B1D17BFG2"
    base = m.RUNS["R2B1D17BFG2"]
    assert base == {"rule": "inv", "k": 1.0, "kd": 1.7, "bear": True, "G": 2.0}
    assert m.RUNS["R2B1D17BFG2_TP08"]["tp_mult"] == 0.8
    assert m.RUNS["R2B1D17BFG2_TP12"]["tp_mult"] == 1.2
    assert m.RUNS["R2B1D17BFG2_SL35"]["m_sl"] == 3.5
    assert m.RUNS["R2B1D17BFG2_SL45"]["m_sl"] == 4.5
    assert m.RUNS["R2B1D17BFG2_G175"]["G"] == 1.75
    assert m.RUNS["R2B1D17BFG2_G225"]["G"] == 2.25
    # each variant changes exactly ONE parameter vs base
    for row, cfg in m.RUNS.items():
        if row == m.REF:
            continue
        diff = {k for k in cfg if cfg[k] != base.get(k)}
        assert len(diff) == 1, (row, diff)


def test_apply_variant_base_is_noop_on_lookup():
    m = _load()
    lookup = lambda i, a, r, f: 1.5  # noqa: E731
    kw = {"sleeve_tp": lookup}
    m.apply_variant(kw, m.RUNS["R2B1D17BFG2"])
    assert kw["sleeve_tp"] is lookup  # TP_MULT=1.0 keeps learned lookup identical
    assert kw["sleeve_gross_cap"] == 2.0


def test_apply_variant_tp_scales_lookup_and_fallback():
    m = _load()
    for mult, row in ((0.8, "R2B1D17BFG2_TP08"), (1.2, "R2B1D17BFG2_TP12")):
        kw = {"sleeve_tp": lambda i, a, r, f: 1.5}
        m.apply_variant(kw, m.RUNS[row])
        assert kw["sleeve_tp"](0, 0, 0, 0) == 1.5 * mult
        assert kw["m_sleeve_tp"] == mult
        assert kw["sleeve_gross_cap"] == 2.0
        assert "m_sleeve_sl" not in kw  # stop untouched


def test_apply_variant_sl_and_g():
    m = _load()
    kw = {}
    m.apply_variant(kw, m.RUNS["R2B1D17BFG2_SL35"])
    assert kw["m_sleeve_sl"] == 3.5 and kw["sleeve_gross_cap"] == 2.0
    kw = {}
    m.apply_variant(kw, m.RUNS["R2B1D17BFG2_G175"])
    assert kw["sleeve_gross_cap"] == 1.75 and "m_sleeve_sl" not in kw


def test_leg_path_naming():
    m = _load()
    assert m.leg_path(0, "R2B1D17BFG2").name == "leg_s0_R2B1D17BFG2.pkl"
    assert m.leg_path(3, "R2B1D17BFG2_G225").parent.name == "legs"


def test_plateau_flags_rule():
    m = _load()
    base = {"mean5y": 5.41, "full_path_dd": 16.82}
    rows = {"R2B1D17BFG2_TP08": {"mean5y": 5.30, "full_path_dd": 16.0},
            "R2B1D17BFG2_TP12": {"mean5y": 5.50, "full_path_dd": 17.5},
            "R2B1D17BFG2_SL35": {"mean5y": 5.00, "full_path_dd": 16.82},  # 0.41 off -> fail
            "R2B1D17BFG2_SL45": {"mean5y": 5.41, "full_path_dd": 16.82},
            "R2B1D17BFG2_G175": {"mean5y": 5.41, "full_path_dd": 18.5},  # 1.68pp -> fail
            "R2B1D17BFG2_G225": {"mean5y": 5.41, "full_path_dd": 16.82}}
    f = m.plateau_flags(base, rows)
    assert f == {"tp": True, "sl": False, "gross_cap": False}


def test_results_schema_if_present():
    p = PL2 / "results.json"
    if not p.exists():
        return  # heavy run not finished yet
    res = json.loads(p.read_text())
    assert res["version"] == "oc_plateau2" and res["reproduced"] is True
    assert set(res["rows"]) == set(_load().RUNS)
    b = res["rows"]["R2B1D17BFG2"]
    assert (b["mean5y"], b["worst"], b["maxDD"], b["full_path_dd"]) == (5.41, 2.588, 16.91, 16.82)
    assert b["losing"] == 0 and len(b["years"]) == 5 and len(b["per_year"]) == 5
    assert set(res["plateau"]) == {"tp", "sl", "gross_cap"}
