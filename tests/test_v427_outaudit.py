"""v427_out blind output audit regression test (fast: checks saved checks.json)."""
from __future__ import annotations

import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v427_audit")
CHK = AUD / "checks.json"


def _c():
    return json.loads(CHK.read_text())


def test_checks_present_and_pass():
    assert CHK.exists()
    c = _c()
    assert c["version"] == "v427_outaudit"
    assert c["anchor_recomputed"] == "2022-09-24"
    assert c["verdict"] == {"v427_out": "PASS"}
    for k in ("windows", "format_symbols", "sealed", "code_parity",
              "train_rows_2022_A", "feature_causality_20", "reproduction_2022_A"):
        assert c[k]["pass"] is True, k
    assert c["feature_list_leak"] == []


def test_windows_inside_and_quarterly():
    c = _c()["windows"]
    assert len(c["per_file"]) == 16
    for name, r in c["per_file"].items():
        assert r["inside"] is True and r["never_before_anchor"] is True, name
        assert r["n"] == 2190, name
        if r["member"] in ("Aq", "Bq"):
            qs = r["quarterly"]["quarters"]
            assert [q["n"] for q in qs] == [546, 546, 546, 552], name
            assert r["quarterly"]["covered"] == 2190, name


def test_train_rows_and_embargo():
    t = _c()["train_rows_2022_A"]
    assert t["n_train"] == 44338
    assert t["cutoff"] == "2022-09-17 00:00:00+00:00"
    assert t["last_label_end"] == "2022-09-16 20:00:00+00:00"
    assert t["embargo_days"] == 7.0 and t["embargo_bars"] == 42.0
    assert t["label_end_le_cutoff"] is True and t["embargo_ge_horizon"] is True


def test_causality_spot_check():
    f = _c()["feature_causality_20"]
    assert len(f["rows"]) == 20
    assert f["worst_max_abs_diff"] <= 1e-9
    for r in f["rows"]:
        assert r["v92"] == 0.0 and r["kline_flow"] == 0.0, r
        assert r["tv"] == 0.0 and r["order_flow"] == 0.0, r


def test_reproduction_2022_A():
    r = _c()["reproduction_2022_A"]
    assert r["index_equal"] is True and r["columns_equal"] is True
    assert r["rank_corr_flat"] > 0.99
    assert r["rank_corr_flat"] == 1.0
    assert r["max_abs_diff"] < 1e-9
    assert r["fallback_to_2021"] is False


def test_sealed_and_symbols_and_parity():
    c = _c()
    assert c["sealed"]["files_matching_2025"] == []
    assert c["sealed"]["max_before_seal"] is True
    assert c["format_symbols"]["OUT_COLS"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert c["code_parity"]["kaggle_matches_v427"] is True
    assert c["code_parity"]["prereg_lists_both"] is True
    text = (AUD / "COMPARISON.md").read_text()
    assert "v427_out: PASS" in text
    assert (AUD / "audit_v427_out.py").exists()
