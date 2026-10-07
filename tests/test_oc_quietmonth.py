"""Tests for oc_quietmonth (light, no simulation): file presence, 60-month
causal bucketing, per-bucket distribution consistency vs oc_edgedecay
monthly parts, frozen thresholds, and the Vietnamese conclusion."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
QM = ROOT / "research/diagnostics/oc_quietmonth"
ED = ROOT / "research/diagnostics/oc_edgedecay"


def _res():
    return json.loads((QM / "results.json").read_text())


def _ed_monthly():
    return json.loads((ED / "results.json").read_text())["components"]["monthly"]


def test_files_present():
    for f in ("run_quietmonth.py", "results.json", "REPORT.md"):
        assert (QM / f).exists(), f


def test_60_months_partition_and_frozen_thresholds():
    r = _res()
    assert r["variant"] == "R2B1D17BFG2"
    assert r["bucket_thresholds"]["p25"] == 7 and r["bucket_thresholds"]["p75"] == 20
    assert r["bucket_thresholds"]["frozen_history_p10_p25_p50_p75_p90"] == [4, 7, 15, 20, 29]
    months = r["months"]
    assert len(months) == 60
    assert months[0]["month"] == "2021-10" and months[-1]["month"] == "2026-09"
    counts = [len(r["buckets"][b]["months"]) for b in ("low", "normal", "high")]
    assert sum(counts) == 60 and counts == r["checks"]["n_low_normal_high"]
    assert counts == [12, 34, 14]
    for m in months:
        # bucket label matches the frozen thresholds
        t, b = m["prior30_total"], m["bucket"]
        assert b == ("low" if t < 7 else ("high" if t > 20 else "normal")), m
        assert m["prior30_total"] == sum(m["per_coin"].values())
        assert set(m["per_coin"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        # causal window: [month_start - 30d, month_start)
        start = pd.Timestamp(m["month_start"])
        assert pd.Timestamp(m["window_start"]) == start - pd.Timedelta(days=30)
    assert [m["month"] for m in months] == [c["month"] for c in _ed_monthly()]


def _dist(v):
    a = np.asarray(v, float)
    return (len(a), round(float(a.mean()), 3), round(float(np.median(a)), 3),
            round(float(np.percentile(a, 10)), 2), round(float(np.percentile(a, 90)), 2),
            round(float(np.mean(a >= 5)), 4), round(float(np.mean(a < 0)), 4))


def test_bucket_distributions_match_edgedecay_parts():
    r = _res()
    comp = {c["month"]: c for c in _ed_monthly()}
    for b, bd in r["buckets"].items():
        ms = bd["months"]
        assert len(ms) == bd["total"]["n"] == bd["book_pp"]["n"] == bd["dip_pp"]["n"]
        for series, key in (("total", "total"), ("book_pp", "book_pp"), ("dip_pp", "dip_pp")):
            vals = [comp[m][series] for m in ms]
            n, mean, med, p10, p90, ge5, lose = _dist(vals)
            got = bd[key]
            assert (got["n"], got["mean"], got["median"], got["p10"], got["p90"],
                    got["share_ge5"], got["share_losing"]) == (n, mean, med, p10, p90, ge5, lose), (b, key)
    # overall reconciles with edgedecay full-sample stats
    assert r["overall_next_month"]["total"]["mean"] == 6.103
    assert r["overall_next_month"]["total"]["median"] == 3.65


def test_report_conclusion_and_current_reading():
    rep = (QM / "REPORT.md").read_text(encoding="utf-8")
    assert "Ket luan" in rep and "VERDICT" in rep
    assert "6 flush" in rep  # current reading conditioned on
    for token in ("4.87", "7.55", "3.64", "n=12"):
        assert token in rep, token
