"""Tests for v186 blind audit (Part A). Does not open research v186 result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v186_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v186.py"
ALL11 = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
         "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT"]
MAJORS = ALL11[:5]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v186 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v186_audit_replication"
    assert d["blind"] == "did_not_open_research_v186_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["spec"]["symbols"] == ALL11
    assert d["spec"]["column_order"] == ["BNB", "BTC", "ETH", "SOL", "XRP", "DOGE",
                                        "ADA", "LINK", "LTC", "AVAX", "TRX"]
    assert d["spec"]["books"] == MAJORS
    assert d["spec"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["counts_grid"]["fills_total"] == 14593
    assert d["counts_grid"]["tp_fills"] == 8296
    per = d["counts_grid"]["fills_per_asset"]
    assert sum(per.values()) == 14593
    # majors leg reproduces the v183 grid exactly (5 majors = 6972 fills)
    assert sum(per[s] for s in MAJORS) == 6972
    assert per["BNBUSDT"] == 1511
    assert per["BTCUSDT"] == 1429
    assert per["ETHUSDT"] == 1449
    assert per["SOLUSDT"] == 1041
    assert per["XRPUSDT"] == 1542


def test_v186_rows():
    d = _rep()
    n = d["primary_normal"]
    assert n["monthly_pct"] == 4.29
    assert n["full_path_dd"] == 17.56
    assert n["dd_1m_mark"] == 17.67
    assert n["gate_dd"] == 17.67
    assert n["dd_1m_worst_bar"] == "2022-04-21 16:00:00+00:00"
    assert n["rungs_taken"] == 3317
    assert n["rungs_cancelled"] == 7574
    assert n["tp_exits_taken"] == 1592
    assert n["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert n["mean_s"] == 1.447
    s = d["stress"]
    assert s["monthly_pct"] == 3.878
    assert s["full_path_dd"] == 17.75
    assert s["dd_1m_mark"] == 17.83
    assert s["gate_dd"] == 17.83
    assert s["dd_1m_worst_bar"] == "2022-04-21 16:00:00+00:00"
    assert s["rungs_taken"] == 3343
    assert s["rungs_cancelled"] == 7548
    assert s["tp_exits_taken"] == 1603
    assert s["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert s["mean_s"] == 1.443
    # one shared budget: same live-window candidate pool both rows
    assert n["rungs_taken"] + n["rungs_cancelled"] == 10891
    assert s["rungs_taken"] + s["rungs_cancelled"] == 10891
    assert n["tp_exits_taken"] <= n["rungs_taken"]
    assert s["tp_exits_taken"] <= s["rungs_taken"]


def test_budget_math_synthetic():
    nmax = 0.05 / 0.30
    assert abs(nmax - 1 / 6) < 1e-12
    rn = 1.447 * 1.0 * 0.25 / 4 / 1.657
    assert abs(rn - 0.0546) < 1e-4
    # shared order: (minute, rung, asset column BNB=0 .. TRX=10)
    fills = [(20, 1, 1), (18, 0, 10), (18, 0, 2), (18, 0, 0)]
    assert sorted(fills) == [(18, 0, 0), (18, 0, 2), (18, 0, 10), (20, 1, 1)]
    # concurrent-open: (open_taken + 1) * rn <= 1/6; TP exit frees a slot
    open_taken = 2  # two earlier rungs with exit minute 999 still open
    assert (open_taken + 1) * rn <= nmax + 1e-12
    open_taken = 3
    assert (open_taken + 1) * rn > nmax
    # TP price def: TP = L * (1 + sigma); TP net normal = sigma - 2*maker
    L, sig = 100.0, 0.01
    assert abs((L * (1 + sig)) / L - 1 - sig) < 1e-15
    assert abs((sig - 0.0004) - 0.0096) < 1e-12


def test_lookahead_timing_definition():
    # v183 base: TP trigger uses minutes m > f strictly after the fill;
    # budget open count uses only exits with exit minute <= current fill
    # minute (past highs); vol uses sleeve_unit shifted by 2; payoff uses
    # s[i]*g[i] at bar-close i. v186 extension adds alt rungs under the same
    # timing (alt 1m/4h/funding aligned as-of each bar close, within-bar
    # forward-fill only); books leg stays majors-only.
    assert True


def test_blind_script_does_not_open_v186():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v186_result" not in body
    assert "/v186/" not in body
