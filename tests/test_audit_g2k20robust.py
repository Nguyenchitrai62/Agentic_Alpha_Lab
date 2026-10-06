"""audit_g2k20robust: fast regression on the stored blind replication.

Reads research/diagnostics/audit_g2k20robust/replication.json (no recompute,
no ROBUST.md read here) and checks the claim cells within the assignment
tolerances (0.01 %/mo, 0.05 pp DD), plus the claim inequalities.
"""

import json
from pathlib import Path

REP = Path("research/diagnostics/audit_g2k20robust/replication.json")
SCENS = ("base", "S1", "S2", "S3", "S4", "S5")

# ROBUST.md G2K20 cells (base: yearly R/DD, mean5y, maxDD, mix fullDD;
# carry: yearly R/DD, mean5y, maxDD, chained fullDD).
RB = {
    "base": ([2.832, 3.272, 7.149, 11.644, 4.716], [12.01, 17.79, 15.79, 9.34, 13.65], 5.874, 17.79, 17.69),
    "S1": ([2.194, 2.556, 5.580, 10.568, 3.833], [12.38, 18.01, 15.98, 9.35, 15.17], 4.903, 18.01, 17.92),
    "S2": ([2.773, 3.123, 6.783, 11.448, 4.559], [11.95, 17.80, 15.84, 9.35, 13.76], 5.690, 17.80, 17.72),
    "S3": ([2.205, 2.616, 4.953, 10.664, 4.394], [12.86, 17.90, 15.91, 9.45, 13.53], 4.924, 17.90, 17.82),
    "S4": ([2.665, 3.049, 5.118, 11.447, 4.555], [12.76, 17.95, 17.08, 9.34, 14.40], 5.320, 17.95, 17.86),
    "S5": ([2.338, 2.678, 6.002, 11.450, 4.494], [12.83, 18.76, 16.70, 10.47, 13.27], 5.342, 18.76, 19.61),
}
RC = {
    "base": ([2.976, 3.325, 7.403, 11.737, 4.747], [11.78, 17.66, 15.75, 9.24, 13.40], 5.989, 17.66, 17.66),
    "S1": ([2.334, 2.605, 5.864, 10.662, 3.862], [12.13, 17.88, 15.95, 9.25, 14.70], 5.022, 17.88, 17.88),
    "S2": ([2.917, 3.176, 7.046, 11.543, 4.590], [11.72, 17.67, 15.80, 9.25, 13.52], 5.807, 17.67, 17.67),
    "S3": ([2.359, 2.673, 5.271, 10.766, 4.426], [12.60, 17.77, 15.86, 9.35, 13.29], 5.056, 17.77, 17.77),
    "S4": ([2.812, 3.103, 5.430, 11.542, 4.587], [12.49, 17.82, 17.05, 9.24, 14.15], 5.448, 17.82, 17.82),
    "S5": ([2.489, 2.734, 6.288, 11.544, 4.526], [12.63, 18.63, 16.57, 10.37, 13.03], 5.465, 18.63, 19.72),
}


def _rep():
    return json.loads(REP.read_text())


def test_replication_file_present():
    assert REP.exists(), "run replicate_g2k20robust.py first"


def test_base_rows_match_within_tolerance():
    r = _rep()
    for sc in SCENS:
        b = r["base"][sc]
        er, ed, em, emd, efd = RB[sc]
        for got, exp in zip([y["R"] for y in b["years"]], er):
            assert abs(got - exp) <= 0.01, (sc, got, exp)
        for got, exp in zip([y["DD"] for y in b["years"]], ed):
            assert abs(got - exp) <= 0.05, (sc, got, exp)
        assert abs(b["R_5y"] - em) <= 0.01, sc
        assert abs(b["DD_maxyearly"] - emd) <= 0.05, sc
        assert abs(b["full_path_dd_mix"] - efd) <= 0.05, sc
        assert b["losing"] == 0, sc


def test_carry_yearstart_matches_and_claim_holds():
    r = _rep()
    for sc in SCENS:
        c = r["carry_yearstart_f025"][sc]
        cr, cd, cm, cmd, cfd = RC[sc]
        for got, exp in zip([y["R"] for y in c["years"]], cr):
            assert abs(got - exp) <= 0.01, (sc, got, exp)
        for got, exp in zip([y["DD"] for y in c["years"]], cd):
            assert abs(got - exp) <= 0.05, (sc, got, exp)
        assert abs(c["R_5y"] - cm) <= 0.01, sc
        assert abs(c["DD_maxyearly"] - cmd) <= 0.05, sc
        assert abs(c["full_path_dd_chained"] - cfd) <= 0.05, sc
        assert c["R_5y"] >= 5.0, sc
        assert max(c["DD_maxyearly"], c["full_path_dd_chained"]) < 20.0, sc
        assert c["losing"] == 0, sc
    worst = min(r["carry_yearstart_f025"][sc]["R_5y"] for sc in SCENS)
    assert abs(worst - 5.022) <= 0.01, worst
    assert r["carry_yearstart_f025"]["S1"]["R_5y"] == worst


def test_compounded_overlay_supports_claim():
    r = _rep()
    for sc in SCENS:
        c = r["carry_compounded_f025"][sc]
        assert c["R_5y"] >= 5.0, sc
        assert c["DD_maxyearly"] < 20.0, sc
        assert c["losing"] == 0, sc
    assert r["checks"]["s1_min_stressed_ret_alloc"] > 0
