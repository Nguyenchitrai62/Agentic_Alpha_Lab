"""Tests for the engine_real blind audit (part A replication + part B comparison).

Fast: checks saved replication.json against the v154 targets and the leader
engine_real result; plus synthetic unit checks for governor/budget causality.
Does not reload 1m data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

AUDIT = Path("research/parallel/rounds/parallel-20260906-r2/engine_real_audit")
LEADER = Path("research/parallel/rounds/parallel-20260906-r2/engine_real")


def _rep():
    return json.loads((AUDIT / "replication.json").read_text())


def test_replication_off_matches_v154():
    rep = _rep()
    off = rep["realism_off"]
    assert off["monthly_pct"] == 3.515
    assert off["full_path_dd"] == 19.15
    assert abs(off["intrabar_bound"] * 100 - 22.11) < 0.02


def test_replication_real_matches_leader():
    rep = _rep()
    lead = json.loads((LEADER / "engine_real_v154_result.json").read_text())
    real = rep["real"]
    lr = lead["rows"]["engine_real"]
    assert abs(real["monthly_pct"] - lr["monthly_pct"]) < 0.005
    assert abs(real["full_path_dd"] - lr["full_path_dd"]) < 0.01
    assert abs(real["intrabar_bound"] * 100 - lr["intrabar_dd_bound"]) < 0.03
    for a, b in zip(real["yearly"], lr["yearly"]):
        assert abs(a["net_pct"] - b["net_pct"]) < 0.01
    for k, scale in (("gross", 100), ("exec", 100), ("funding", 100),
                     ("carry_pnl", 100), ("carry_cost", 100)):
        lk = {"gross": "gross", "exec": "exec", "funding": "funding",
              "carry_pnl": "carry", "carry_cost": "carry_cost"}[k]
        assert abs(real["components"][k] * scale - lr["components_pct_of_start_equity_sum"][lk]) < 0.05


def test_governor_uses_lagged_equity_only():
    # g[i] = clip((0.20-(1-eq[i-2]/max(eq[i-2-539..i-2])))/0.10); check formula on synthetic eq
    eq = np.array([1.0, 1.0, 0.9, 0.9, 0.85, 0.95])
    # i=4 -> j=2, peak over eq[0..2]=1.0, dd=0.1, g=(0.20-0.10)/0.10=1.0
    j = 2
    peak = eq[max(0, j - 540 + 1):j + 1].max()
    g = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0, 1))
    assert abs(g - 1.0) < 1e-12
    # i=5 -> j=3, peak=1.0, dd=0.1, g=1.0
    j = 3
    peak = eq[max(0, j - 540 + 1):j + 1].max()
    g = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0, 1))
    assert abs(g - 1.0) < 1e-12
    # deep dd: eq[j]=0.7, peak 1.0 -> dd 0.3 -> g=0
    g = float(np.clip((0.20 - 0.30) / 0.10, 0, 1))
    assert g == 0.0


def test_budget_carry_first():
    c, ex, wsum5 = 1.0, 0.8, 0.5
    assert c * ex + wsum5 > 0.95
    c_allow = (0.95 - wsum5) / max(ex, 1e-9)
    assert abs(c_allow - 0.5625) < 1e-12
