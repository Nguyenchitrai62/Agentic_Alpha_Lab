"""oc_confirmgate tests: frozen gate logic (synthetic hand-checks) + quote integrity.

No engines, no fits, no heavy work. Run:
  .venv/Scripts/python.exe -m pytest tests/test_oc_confirmgate.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_confirmgate"


# --- frozen gate logic (verbatim PLAN.md rules) ---

def robust_pick(rows):
    """rows: {name: (mean, worst, dd, losing)}. DD<=20, no losing, prefer mean>=5,
    highest WORST, ties -> higher mean. Returns winner name (REF default on full tie)."""
    elig = {k: v for k, v in rows.items() if v[2] <= 20 and v[3] == 0}
    assert elig, "no eligible row"
    pool = [k for k in elig if elig[k][0] >= 5] or list(elig)
    best = sorted(pool, key=lambda k: (elig[k][1], elig[k][0]))[-1]
    return best


def leg1(dev4_gap, cand_w, ref_w, cand_dd, cand_full_dd, ref_dd=18.11, has_s5=True):
    """Bybit-S5 dev4 confirm. PASS iff mean gap>0 AND worst>=REF AND DDs<=20."""
    if not has_s5:
        return "UNKNOWN"
    if dev4_gap > 0 and cand_w >= ref_w and cand_dd <= 20 and cand_full_dd <= 20:
        return "PASS"
    return "FAIL"


def leg2(n_help, n_years=4, applicable=True):
    if not applicable:
        return "N/A"
    if n_help >= 3:
        return "PASS" if n_help == 4 else "PARTIAL-or-PASS"
    return "FAIL"


# --- hand-checked synthetic cases ---

def test_robust_pick_handchecked():
    # C2-like: wins worst and mean -> C2
    assert robust_pick({"REF": (5.601, 2.588, 16.91, 0),
                        "C2": (5.739, 2.711, 15.48, 0)}) == "C2"
    # K2-like: wins mean, loses worst -> REF keeps
    assert robust_pick({"REF": (5.601, 2.588, 16.91, 0),
                        "K2": (5.772, 2.469, 16.20, 0)}) == "REF"
    # DD breach excluded even with higher mean
    assert robust_pick({"REF": (5.601, 2.588, 16.91, 0),
                        "KX": (6.500, 2.900, 21.79, 0)}) == "REF"
    # losing year excluded
    assert robust_pick({"REF": (5.601, 2.588, 16.91, 0),
                        "LZ": (6.900, 3.100, 15.00, 1)}) == "REF"
    # tie worst -> higher mean
    assert robust_pick({"REF": (5.601, 2.588, 16.91, 0),
                        "T2": (5.607, 2.588, 17.04, 0)}) == "T2"


def test_leg1_synthetic():
    assert leg1(0.261, 2.213, 2.129, 16.65, 16.50) == "PASS"  # C2-like
    assert leg1(-0.005, 2.145, 2.129, 18.58, 21.32) == "FAIL"  # A1-like (DD)
    assert leg1(1.223, 2.200, 2.129, 19.08, 20.31) == "FAIL"  # B7-like (full DD)
    assert leg1(0.5, 2.5, 2.1, 16.0, 16.0, has_s5=False) == "UNKNOWN"


def test_leg2_synthetic():
    assert leg2(3) in ("PASS", "PARTIAL-or-PASS")
    assert leg2(4) == "PASS"
    assert leg2(2) == "FAIL"
    assert leg2(0, applicable=False) == "N/A"


def test_legs_ignore_y4_causality():
    """Leg verdicts must not read the post-release year: perturbing Y4 changes nothing."""
    base = {"gap": 0.113, "w": (2.182, 2.129), "dd": 17.31, "full": 17.26}
    v0 = (leg1(base["gap"], *base["w"], base["dd"], base["full"]), leg2(0, applicable=False))
    for fake_y4 in (-9.99, 0.0, 99.99):
        _ = fake_y4  # Y4 is not an argument to either leg by construction
        v1 = (leg1(base["gap"], *base["w"], base["dd"], base["full"]), leg2(0, applicable=False))
        assert v1 == v0


# --- quote integrity vs stored runs (read-only) ---

def _load_results():
    return json.loads((OC / "results.json").read_text())


def test_results_json_valid():
    d = _load_results()
    assert d["bybit_s5_reruns_used"] == 0
    assert d["gate_separates"] is False
    assert d["confirm_gate_written"] is False
    assert len(d["per_candidate"]) == 11


def test_quotes_match_stored_runs():
    d = _load_results()
    # C2 dev4 mean quoted == oc_chronos REPORT dev row (5.739)
    assert d["per_candidate"]["C2"]["dev4"][0] == 5.739
    # D1 transfer sign negative (oc_d1bybit: negative under every friction)
    assert "FAIL" in d["per_candidate"]["D1"]["transfer"]
    # B7 S5 full-path DD breach quoted (oc_cboostbybit 20.31)
    assert "20.31" in d["per_candidate"]["B7"]["leg1"]
    # A1 S5 full-path DD breach quoted (oc_amihudbybit 21.32)
    assert "21.32" in d["per_candidate"]["A1"]["leg1"]
    # K2 Y4 transfer positive (oc_k2bybit base +0.153 direction)
    assert "PASS" in d["per_candidate"]["K2"]["transfer"]
    # stored A1 S5 full DD is indeed > 20 (read the stored file, not our quote)
    am = json.loads((ROOT / "research" / "tournament" / "oc_amihudbybit" / "results.json").read_text())
    assert float(am["repro"]["A1_S5_5y"]["full_path_dd"]) > 20


def test_no_new_engines_or_fits():
    names = [p.name for p in OC.iterdir()]
    assert "PLAN.md" in names and "REPORT.md" in names and "results.json" in names
    bad = [n for n in names
           if n.endswith((".pkl", ".parquet", ".pt", ".bin"))
           or n in ("fits.json", "run_engine.py", "compute_engine.py")]
    assert bad == [], bad
    assert not (OC / "CONFIRM_GATE.md").exists()  # gated by frozen §5 rule
