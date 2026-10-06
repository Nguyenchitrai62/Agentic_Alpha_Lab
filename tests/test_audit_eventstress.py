"""Blind audit test for oc_eventstress crash-week anatomy (LUNA / FTX / AUG24).

Compares research/tournament/audit_eventstress/replication.json (built blind
via heavy_slot BEFORE oc_eventstress REPORT/results were opened) against the
published research/tournament/oc_eventstress/results.json within the
assignment tolerances: 0.1 pp P&L, 0.2 pp DD, 1 day recovery.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
AUDIT = ROOT / "research/tournament/audit_eventstress"
RESULTS = ROOT / "research/tournament/oc_eventstress/results.json"

TOL_PNL = 0.10 + 1e-9
TOL_DD = 0.20 + 1e-9
TOL_REC = 1.0 + 1e-9
# non-gated dip-gross note: strict-vs-inclusive 1h mark convention
TOL_DIP = 0.05

KEYS = ("LUNA", "FTX", "AUG24")


def _load_rep():
    rep = json.loads((AUDIT / "replication.json").read_text())
    assert rep["meta"]["blind"] is True
    assert rep["meta"]["v421_v422_identical"] is True
    return {e["key"]: e for e in rep["events"]}


def _load_ref():
    ref = json.loads(RESULTS.read_text())
    return {e["key"]: e for e in ref["events"] if e["key"] in KEYS}


def test_gated_metrics_within_tolerance():
    got = _load_rep()
    ref = _load_ref()
    assert set(got) == set(KEYS) and set(ref) == set(KEYS)
    for k in KEYS:
        g, r = got[k], ref[k]
        assert g["anchor"] == r["anchor"], k
        assert g["window"] == r["window"], k
        assert abs(g["pnl_comb_pct"] - r["pnl_comb_pct"]) <= TOL_PNL, (k, g, r)
        assert abs(g["pnl_g2_pct"] - r["pnl_g2_pct"]) <= TOL_PNL, (k, g, r)
        assert abs(g["dd_close_pct"] - r["dd_close_pct"]) <= TOL_DD, (k, g, r)
        assert abs(g["dd_mark_pct"] - r["dd_mark_pct"]) <= TOL_DD, (k, g, r)
        assert g["trough_hour"] == r["trough_hour"], (k, g["trough_hour"], r["trough_hour"])
        assert g["dip_gross_hour"] == r["dip_gross_hour"], k
        gr, rr = g["rec_days"], r["rec_days"]
        assert (gr is None) == (rr is None), (k, gr, rr)
        if gr is not None:
            assert abs(gr - rr) <= TOL_REC, (k, gr, rr)


def test_dip_gross_same_hour_small_level_delta():
    got = _load_rep()
    ref = _load_ref()
    for k in KEYS:
        assert abs(got[k]["dip_gross_max"] - ref[k]["dip_gross_max"]) <= TOL_DIP, k


def test_grid_capped_and_causal_spec():
    rep = json.loads((AUDIT / "replication.json").read_text())
    assert rep["meta"]["grid"][0].startswith("2021-09-24 04:00")
    assert rep["meta"]["grid"][1].startswith("2026-09-23 12:00")
    assert rep["meta"]["event_window"].startswith("anchor-24h..anchor+7d")
    src = (AUDIT / "replicate_eventstress.py").read_text()
    # causal last-CLOSED-bar helpers, entry effective entry+4h, no REPORT import
    assert 'side="left") - 1' in src
    assert 'pd.Timedelta(hours=4)' in src
    # script documents that it does NOT open REPORT/results; assert it never reads them
    assert "oc_eventstress/results.json" not in src.replace(
        "oc_eventstress/REPORT.md or results.json until replication.json is written", ""
    ).replace("oc_eventstress REPORT/results were", "")
    assert "oc_eventstress/REPORT.md" not in src.replace(
        "oc_eventstress/REPORT.md or results.json until replication.json is written", ""
    )
    assert 'HERE / "results.json"' not in src
    assert "import compute_eventstress" not in src
    assert "from compute_eventstress" not in src
    assert "_load(\"v388_for_rep\"" in src or "v388_bot_stop_distance" in src
    for k in KEYS:
        assert json.loads((AUDIT / "replication.json").read_text()) is not None
    # every audited window has 1m coverage
    got = _load_rep()
    assert all(got[k]["m1_coverage_ok"] for k in KEYS)
