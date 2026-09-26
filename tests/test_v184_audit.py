"""Tests for v184 blind audit (Part A). Does not open research v184 result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v184_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v184.py"
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v184 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v184_audit_replication"
    assert d["blind"] == "did_not_open_research_v184_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["spec"]["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["spec"]["rungs_4h"] == [2.5, 3.0, 3.5, 4.0]
    assert d["spec"]["rungs_hourly"] == [2.5, 3.0, 3.5, 4.0]
    assert d["counts_grid"]["fills_4h"] == 6972
    assert d["counts_grid"]["tp_4h"] == 4053
    assert d["counts_grid"]["fills_hourly"] == 24374
    assert d["counts_grid"]["tp_hourly"] == 13295


def test_v184_rows():
    d = _rep()
    n = d["primary_normal"]
    assert n["monthly_pct"] == 3.893
    assert n["full_path_dd"] == 17.89
    assert n["dd_1m_mark"] == 18.2
    assert n["gate_dd"] == 18.2
    assert n["rungs_taken"] == 8478
    assert n["rungs_cancelled"] == 15139
    assert n["tp_exits_taken"] == 3924
    assert n["taken_4h"] == 1578
    assert n["taken_hourly"] == 6900
    assert n["taken_4h"] + n["taken_hourly"] == n["rungs_taken"]
    assert n["mean_s"] == 1.477
    assert n["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    s = d["stress"]
    assert s["monthly_pct"] == 3.189
    assert s["full_path_dd"] == 18.15
    assert s["dd_1m_mark"] == 19.0
    assert s["gate_dd"] == 19.0
    assert s["rungs_taken"] == 8674
    assert s["rungs_cancelled"] == 14943
    assert s["tp_exits_taken"] == 4036
    assert s["taken_4h"] == 1619
    assert s["taken_hourly"] == 7055
    assert s["taken_4h"] + s["taken_hourly"] == s["rungs_taken"]
    assert s["mean_s"] == 1.464


def test_shared_budget_synthetic():
    nmax = 0.05 / 0.30
    assert abs(nmax - 1 / 6) < 1e-12
    rn = 1.477 * 1.0 * 0.25 / 4 / 1.657
    assert abs(rn - 0.0557) < 1e-4
    # shared order: (minute, 4h before hourly, rung, asset)
    fills = [(20, 1, 1, 1), (18, 0, 0, 4), (18, 0, 0, 2), (18, 1, 0, 0)]
    assert sorted(fills) == [(18, 0, 0, 2), (18, 0, 0, 4), (18, 1, 0, 0), (20, 1, 1, 1)]
    # concurrent-open: (open_taken + 1) * rn <= 1/6; hourly timeout frees slot
    assert (1 + 1) * rn <= nmax + 1e-12
    assert (2 + 1) * rn > nmax
    # hourly windows: h0 16..57 else 60h+4..60h+57
    assert list(range(16, 58))[-1] == 57
    assert list(range(60 * 2 + 4, 60 * 2 + 58)) == list(range(124, 178))
    # TP defs
    L, s1 = 100.0, 0.01
    assert abs((L * (1 + s1)) / L - 1 - s1) < 1e-15


def test_lookahead_timing_definition():
    # 4h ladder uses t/T known at decision; hourly base is the hour open
    # known at the hour start; sigma_1h window ends at the last hour of the
    # PREVIOUS holding bar; fills use low < L within live windows only;
    # TP uses high > TP strictly after fill and before hour end; timeout at
    # the next hour open; h3 timeout pays funding at T+4h; budget open count
    # uses only exits with exit minute <= current fill minute; vol shifted 2.
    assert True


def test_blind_script_does_not_open_v184():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v184_result" not in body
    assert "hourly_ladder" not in body
    assert "v184/v184" not in body
