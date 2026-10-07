"""oc_eventblk tests: universe counts, calendar UTC/provenance, EVENTBAR causality."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_eventblk"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5
import analyze_eventblk as A

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
COUNTS = [990, 1045, 1330, 989, 1144]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def test_universe_counts():
    d = H5.load()
    m = d["sym"].isin(MAJORS) & d["x1"].isin(R2)
    assert int(m.sum()) == 6876
    d = d[m].reset_index(drop=True)
    T = pd.to_datetime(d["T"], utc=True)
    assert (T < CUTOFF).all()
    mins = (T.to_numpy(dtype="datetime64[ns]").astype(np.int64) // 60_000_000_000) % (24 * 60)
    assert set(np.unique(mins)) <= {0, 240, 480, 720, 960, 1200}
    for k, a in enumerate(H5.ANCHORS):
        te = (d["sym"].isin(MAJORS) & d["k"].isin(R2)
              & (d["T"] >= a) & (d["T"] < a + pd.Timedelta(days=365)) & d["size_dep"].notna())
        assert int(te.sum()) == COUNTS[k], f"year {a.date()}: {int(te.sum())}"
    # outcome column is y_dep from the deployed-TP join
    assert "y_dep" in d.columns and d["y_dep"].notna().all()


def test_calendar_utc():
    cal = pd.read_csv(OC / "event_calendar.csv")
    assert len(cal) == 136
    assert int((cal["series"] == "FOMC").sum()) == 54
    assert int((cal["series"] == "CPI").sum()) == 82
    assert (pd.to_datetime(cal["release_utc"], utc=True) < CUTOFF).all()
    spot = {(r["series"], r["date"]): r["release_utc"] for _, r in cal.iterrows()}
    assert spot[("FOMC", "2022-01-26")] == "2022-01-26 19:00:00+00:00"  # EST
    assert spot[("FOMC", "2022-06-15")] == "2022-06-15 18:00:00+00:00"  # EDT
    assert spot[("CPI", "2024-01-11")] == "2024-01-11 13:30:00+00:00"  # EST
    assert spot[("CPI", "2024-06-12")] == "2024-06-12 12:30:00+00:00"  # EDT
    assert spot[("FOMC", "2020-09-16")] == "2020-09-16 18:00:00+00:00"  # EDT tail
    assert spot[("CPI", "2020-08-12")] == "2020-08-12 12:30:00+00:00"  # EDT tail
    assert spot[("CPI", "2025-10-24")] == "2025-10-24 12:30:00+00:00"  # delayed Sep ref
    assert spot[("CPI", "2025-12-18")] == "2025-12-18 13:30:00+00:00"  # Nov ref
    # manifest provenance: every raw file re-hashes
    man = json.loads((OC / "manifest.json").read_text())
    assert len(man) == 18
    for m in man:
        blob = (OC / m["file"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == m["sha256"], m["file"]
        assert blob and len(blob) == m["bytes"]


def test_eventbar_causal():
    """Instant-in-bar from T + calendar: hand-checked boundaries + invariance."""
    cal = pd.read_csv(OC / "event_calendar.csv")

    def flag(t):
        T = pd.Series(pd.to_datetime([t], utc=True))
        both, _ = A.eventbar_flags(T, cal)
        return bool(both[0])

    # CPI 2024-01-11 13:30 UTC (no FOMC nearby): bar [12:00,16:00) contains it
    assert flag("2024-01-11 12:00") is True
    assert flag("2024-01-11 08:00") is False  # R 1.5h after bar end
    assert flag("2024-01-11 16:00") is False
    assert flag("2024-01-10 20:00") is False
    assert flag("2024-01-11 13:30") is True  # R exactly at T counts (T <= R)
    # FOMC 2024-01-31 19:00 UTC: [16:00,20:00) contains it
    assert flag("2024-01-31 16:00") is True
    assert flag("2024-01-31 12:00") is False
    # NOT window overlap: a bar starting after R is excluded even within 5h
    # (CPI R=13:30; T=16:00 bar starts 2.5h after R -> excluded)
    assert flag("2024-01-11 16:00") is False
    # flags need no market/outcome columns
    d = H5.load()
    m = d["sym"].isin(MAJORS) & d["x1"].isin(R2)
    d = d[m].reset_index(drop=True)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    full, _ = A.eventbar_flags(d["T"], cal)
    slim, _ = A.eventbar_flags(d[["T"]]["T"], cal)
    assert (full == slim).all()
    y = d["y_dep"].to_numpy()
    assert int(full.sum()) == 155  # pooled event-bar rung count


def test_decision_counts_match():
    res = json.loads((OC / "results.json").read_text())
    yrs, loyo = res["years"], res["loyo"]
    sgn = [1 if (w["spread_bps"] or 0) > 0 else -1 for w in yrs]
    dom = max(sgn.count(1), sgn.count(-1))
    assert res["decision"]["dominant_sign_count"] == f"{dom}/5"
    assert res["decision"]["loyo_agree_count"] == f"{sum(1 for L in loyo if L['sign_agrees'])}/5"
    assert res["decision"]["tail_not_worse_count"] == f"{sum(1 for w in yrs if w['tail_pass'])}/5"
    assert res["decision"]["gain_pos_count"] == f"{sum(1 for w in yrs if w['gain_pass'])}/5"
    assert res["decision"]["promising"] is False
    assert [w["n"] for w in yrs] == COUNTS
    assert [w["n_in"] for w in yrs] == [67, 38, 17, 15, 8]
