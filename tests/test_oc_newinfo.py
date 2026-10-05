"""Tests for oc_newinfo (Wikipedia attention + CME gap study).

Causality: truncation tests assert features at day D use nothing after D 00:00 UTC.
Integrity: manifest sha256; decision-rule consistency vs results.json.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_newinfo"))

from features_cme import sunday_reopen_hour, weekend_gaps  # noqa: E402
from features_wiki import COINS, compute_features, load_views  # noqa: E402

RAW = ROOT / "data" / "raw" / "newinfo_20261005"
HERE = ROOT / "research" / "tournament" / "oc_newinfo"


def test_manifest_integrity():
    man = json.loads((RAW / "manifest.json").read_text())
    assert len(man) >= 79, f"expected >=79 raw files, got {len(man)}"
    for fname, meta in man.items():
        assert meta["url"].startswith(("https://wikimedia.org/", "https://query1.finance.yahoo.com/")), fname
        p = RAW / fname
        assert p.exists(), fname
        body = p.read_bytes()
        assert hashlib.sha256(body).hexdigest() == meta["sha256"], fname
        assert len(body) == meta["bytes"], fname


def test_wiki_truncation_causality_20_days():
    views = load_views(RAW)
    full = compute_features(views)
    rng = np.random.default_rng(7)
    idx = views.index
    cuts = sorted(rng.choice(np.arange(200, len(idx) - 1), size=20, replace=False))
    for c in cuts:
        cut_day = idx[c]
        part = compute_features(views.loc[:cut_day])
        pd.testing.assert_frame_equal(
            full.loc[:cut_day], part, check_dtype=False, obj=f"wiki causality cut={cut_day.date()}")
    # feature row D must be NaN until enough trailing history exists (no silent backfill)
    assert full["BTC"]["wiki_z90"].iloc[:90].isna().all()


def test_cme_sunday_reopen_dst_hours():
    cases = {  # Sunday -> expected UTC reopen hour (CME Globex 17:00 CT)
        pd.Timestamp("2024-01-07"): 23,   # CST
        pd.Timestamp("2024-03-10"): 22,   # DST starts this Sunday (2nd Sun Mar)
        pd.Timestamp("2024-07-07"): 22,   # CDT
        pd.Timestamp("2024-11-03"): 23,   # DST ends this Sunday (1st Sun Nov)
        pd.Timestamp("2025-06-22"): 22,
        pd.Timestamp("2025-12-28"): 23,
    }
    for sunday, hour in cases.items():
        assert sunday_reopen_hour(sunday).hour == hour, sunday


def _synth_hourly(start="2024-01-01", days=140):
    idx = pd.date_range(start, periods=days * 24, freq="h", tz="UTC")
    t = np.arange(len(idx))
    price = 60000 + 500 * np.sin(t / 50) + 0.05 * t
    rows = []
    for sym in ("BTCUSDT", "ETHUSDT"):
        px = price * (0.05 if sym.startswith("ETH") else 1.0)
        rows.append(pd.DataFrame({"t": idx, "open": px, "high": px * 1.001,
                                  "low": px * 0.999, "close": px, "sym": sym}))
    return pd.concat(rows, ignore_index=True)


def _synth_cme():
    dates = pd.date_range("2024-01-01", "2024-05-19", freq="D", tz="UTC")
    out = {}
    for coin in ("BTC", "ETH"):
        df = pd.DataFrame({"date": [d.normalize() for d in dates],
                           "open": 60000.0, "high": 60100.0, "low": 59900.0, "close": 60050.0})
        out[coin] = df
    return out


def test_cme_truncation_causality():
    hourly = _synth_hourly()
    cme = _synth_cme()
    full = weekend_gaps(cme, hourly).reset_index(drop=True)
    assert full["gap_sigma"].notna().sum() > 10, "synthetic gaps must be finite"
    cut = pd.Timestamp("2024-03-20", tz="UTC")
    part = weekend_gaps(cme, hourly[pd.to_datetime(hourly["t"], utc=True) < cut]).reset_index(drop=True)
    horizon = cut - pd.Timedelta(days=8)  # weekends fully observable before cut
    keep = full[pd.to_datetime(full["friday"], utc=True) < horizon].reset_index(drop=True)
    got = part[pd.to_datetime(part["friday"], utc=True) < horizon].reset_index(drop=True)
    pd.testing.assert_frame_equal(keep, got, check_dtype=False)


def test_decision_rule_consistency():
    res = json.loads((HERE / "results.json").read_text())

    def rule(ic):
        ic = np.array(ic, float)
        n_same = int((np.sign(ic) == np.sign(np.nanmean(ic))).sum())
        mean_ic = float(np.nanmean(ic))
        others_sign = []
        for i in range(len(ic)):
            rest = float(np.nanmean([v for j, v in enumerate(ic) if j != i]))
            others_sign.append(np.sign(ic[i]) == np.sign(rest) and rest != 0)
        n_loyo = int(sum(others_sign))
        return ("PROMISING" if (n_same >= 4 and abs(mean_ic) >= 0.03 and n_loyo >= 4)
                else "NOT_PROMISING", n_same, mean_ic, n_loyo)

    checked = 0
    for section in ("N1_daily", "N2_gaps"):
        for feat, v in res[section].items():
            exp, ns, m, nl = rule(v["ic_by_year"])
            assert v["decision"]["verdict"] == exp, feat
            assert v["decision"]["n_same_sign"] == ns, feat
            assert abs(v["decision"]["mean_ic"] - m) < 1e-12, feat
            assert v["decision"]["loyo_hold"] == nl, feat
            checked += 1
    v = res["N1_monthly_vs_edge"]
    ic5 = [v[f"anchor_{2021 + i}"]["ic"] for i in range(5)]
    exp, _, _, _ = rule(ic5)
    assert v["decision"]["verdict"] == exp
    assert checked == 10


def test_no_data_beyond_2026_09_24():
    views = load_views(RAW)
    assert views.index.max() <= pd.Timestamp("2026-09-23")
    res = json.loads((HERE / "results.json").read_text())
    assert res["meta"]["coverage"]["views_days"][1] <= "2026-09-23"
    assert res["meta"]["coverage"]["daily_days"][1] <= "2026-09-23"
