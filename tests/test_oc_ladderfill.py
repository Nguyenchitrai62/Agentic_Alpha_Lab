"""Tests for research/tournament/oc_ladderfill (diagnostic, no rule)."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_ladderfill"
KPI = ROOT / "research/tournament/oc_kpi"
RES = json.loads((HERE / "results.json").read_text())


def load_pairs(shift):
    ev = pd.read_parquet(KPI / f"events_s{shift}.parquet")
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    ev = ev.sort_values("t").reset_index(drop=True)
    pend, out, unpaired = {}, [], 0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q = pend.get(r.symbol)
            if q:
                f0 = q.popleft()
                out.append((r.symbol, pd.Timestamp(f0.t), pd.Timestamp(r.t),
                            r.kind, float(r.ret), float(f0.rung)))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


def test_pairing_matches_results():
    n, un, left = 0, 0, 0
    for s in range(4):
        o, u, l = load_pairs(s)
        n += len(o)
        un += u
        left += l
    assert n == RES["checks"]["n_paired"] == 21389
    assert un == RES["checks"]["unpaired_exits"] == 0
    assert left == RES["checks"]["left_open"] == 0


def test_fill_minute_range_per_shift():
    for s in range(4):
        pairs, _, _ = load_pairs(s)
        for _, fill_t, _, _, _, _ in pairs:
            mins = (fill_t - fill_t.floor("D")).total_seconds() / 60.0
            f = int((mins - s * 60) % 240)
            assert 16 <= f <= 238, (s, fill_t, f)
    assert RES["checks"]["f_outside_16_238"] == 0


def test_exit_mix_matches_oc_kpi():
    assert RES["exit_mix"] == {"rung_tp": 10761, "rung_timeout": 9704, "rung_sl": 924}


def test_bucket_hist_covers_all():
    h = RES["fill_minute"]["bucket_hist"]
    assert sum(h.values()) == RES["checks"]["n_paired"]
    assert h["outside"] == 0


def test_fast_tp_nested_and_shares():
    f = RES["fast_tp"]
    assert f["5"]["n"] < f["15"]["n"] < f["60"]["n"] <= f["tp_total"]["n_tp"]
    assert f["5"]["win"] == f["15"]["win"] == f["60"]["win"] == 1.0
    assert abs(f["15"]["edge_share_w"] - 0.9331) < 1e-4
    assert abs(f["5"]["edge_share_w"] - 0.533) < 1e-4


def test_paper_zero_fills():
    p = RES["paper"]
    assert p["n_fill_ops"] == 0 and p["n_exchange_execs"] == 0
    assert p["dip_fills"] == 0 and p["book_fills"] == 0


def test_win_rate_cross_check():
    assert abs(RES["overall_pnl"]["win"] - 0.6869) < 1e-4
    assert abs(RES["overall_pnl"]["mean_bps"] - 17.76) < 0.01
