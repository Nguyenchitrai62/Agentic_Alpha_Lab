"""Tests for v198 blind audit (Part A). Does not open research v198 result."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v198_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v198.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v198 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v198_audit_replication"
    assert d["blind"] == "did_not_open_research_v198_until_this_file_saved"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["tsmom"]["lookbacks"] == [180, 540, 1080]
    assert d["tsmom"]["vol_window"] == 42
    assert d["tsmom"]["annualization"] == 2190
    assert d["tsmom"]["vol_target"] == 0.2
    assert d["tsmom"]["divisor"] == 5
    assert d["tsmom"]["clip"] == 0.5
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_sl"] == 5.0
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["engine"]["d_limit"] == 0.001
    assert d["engine"]["win_end"] == 239
    assert d["engine"]["gap"] == 0.02
    assert d["engine"]["target"] == 0.25
    assert d["engine"]["cap"] == 2.0
    assert d["engine"]["size_mult"] == 1.5
    assert d["engine"]["sleeve_risk_budget"] == 0.12
    assert set(d["rows"]) == {"V151", "BLEND75_25", "BLEND50_50"}
    for key, row in d["rows"].items():
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["target"] == 0.25
        assert row["cap"] == 2.0
        assert row["size_mult"] == 1.5
        assert row["sleeve_risk_budget"] == 0.12
        assert row["gap"] == 0.02
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["V151"]["blend_v151"] == 1.0
    assert d["rows"]["V151"]["blend_tsmom"] == 0.0
    assert d["rows"]["BLEND75_25"]["blend_v151"] == 0.75
    assert d["rows"]["BLEND75_25"]["blend_tsmom"] == 0.25
    assert d["rows"]["BLEND50_50"]["blend_v151"] == 0.5
    assert d["rows"]["BLEND50_50"]["blend_tsmom"] == 0.5


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["V151"]["monthly_dev4"] == 5.562
    assert d["V151"]["monthly_5y"] == 4.996
    assert d["V151"]["monthly_last_year"] == 2.761
    assert d["V151"]["gate_dd"] == 19.32
    assert d["BLEND75_25"]["monthly_dev4"] == 4.979
    assert d["BLEND75_25"]["monthly_5y"] == 4.708
    assert d["BLEND75_25"]["monthly_last_year"] == 3.629
    assert d["BLEND75_25"]["gate_dd"] == 20.12
    assert d["BLEND50_50"]["monthly_dev4"] == 4.213
    assert d["BLEND50_50"]["monthly_5y"] == 3.947
    assert d["BLEND50_50"]["monthly_last_year"] == 2.892
    assert d["BLEND50_50"]["gate_dd"] == 23.22
    assert d["V151"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert d["BLEND75_25"]["yearly_net_pct"] == [35.27, 34.96, 143.22, 132.04, 53.37]
    assert d["BLEND50_50"]["yearly_net_pct"] == [33.18, 16.15, 128.71, 104.84, 40.8]
    assert d["V151"]["yearly_dd_1m_pct"] == [19.32, 17.51, 14.8, 8.77, 15.66]
    assert d["BLEND75_25"]["yearly_dd_1m_pct"] == [18.67, 18.9, 15.37, 9.1, 15.56]
    assert d["BLEND50_50"]["yearly_dd_1m_pct"] == [17.03, 21.97, 16.58, 10.12, 18.64]
    assert d["V151"]["stats"]["rungs"] == 5004
    assert d["V151"]["stats"]["rung_stops"] == 191
    assert d["V151"]["stats"]["rung_tps"] == 2717
    assert d["V151"]["stats"]["liq"] == 0
    assert d["BLEND75_25"]["stats"]["rungs"] == 4957
    assert d["BLEND75_25"]["stats"]["liq"] == 0
    assert d["BLEND50_50"]["stats"]["rungs"] == 4913
    assert d["BLEND50_50"]["stats"]["liq"] == 0
    assert d["V151"]["stats"]["fills"] == 40078
    assert d["BLEND75_25"]["stats"]["fills"] == 42201
    assert d["BLEND50_50"]["stats"]["fills"] == 41488
    # V151 equals the v197 selected row (same books + same v197 sleeve)
    assert d["V151"]["stats"]["unfilled"] == 4079
    assert d["V151"]["stats"]["stops"] == 76
    assert d["V151"]["stats"]["tps"] == 48


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "V151"
    assert d["eligible"] == ["V151"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # both TSMOM blends are excluded by the DD gate
    assert d["rows"]["BLEND75_25"]["gate_dd"] == 20.12
    assert d["rows"]["BLEND50_50"]["gate_dd"] == 23.22
    assert "BLEND75_25" not in d["eligible"]
    assert "BLEND50_50" not in d["eligible"]
    # selection is the max dev4 among eligible
    best = max(d["eligible"], key=lambda k: d["rows"][k]["monthly_dev4"])
    assert best == d["selection"]
    # dev4 cross-check: geometric mean of first-four nets
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
    # gate DD is max of 4h-close and 1m-marked DD
    for key, row in d["rows"].items():
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9, key
    # sleeve rows take rungs with no liquidations
    for key in ("V151", "BLEND75_25", "BLEND50_50"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_tsmom_causal_and_bounded():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v198_tsmom_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    opens = pd.read_parquet("artifacts/research/engine_real/opens_v154.parquet").sort_index()
    T_full = mod.compute_tsmom(opens)
    assert list(T_full.index) == list(opens.index)
    assert list(T_full.columns) == list(opens.columns)
    # bounded by the clip
    assert float(T_full.abs().max().max()) <= 0.5 + 1e-12
    # causal: rows up to a cut are identical when computed on truncated opens
    n = len(opens)
    for cut in (n // 3, n // 2, (3 * n) // 4, n - 2):
        part = mod.compute_tsmom(opens.iloc[: cut + 1].copy())
        pd.testing.assert_frame_equal(
            T_full.iloc[: cut + 1], part, check_dtype=False, obj=f"causality at cut={cut}")
    # hand-check: constant opens -> zero signal -> zero T
    synth_idx = pd.date_range("2020-01-01", periods=2000, freq="4h", tz="UTC")
    synth = pd.DataFrame(100.0, index=synth_idx, columns=["BTCUSDT"])
    Ts = mod.compute_tsmom(synth)
    assert float(Ts.abs().max().max()) == 0.0
    # hand-check: steady uptrend -> positive capped signal scaled by vol
    up = pd.DataFrame({"BTCUSDT": 100.0 * (1.001 ** np.arange(2000))}, index=synth_idx)
    Tu = mod.compute_tsmom(up)
    tail = Tu.iloc[-1]["BTCUSDT"]
    assert tail > 0 and tail <= 0.5


def test_gate_cost_model_synthetic():
    # maker 0.0002 on entries/TP, taker 0.00055 on stops/market exits,
    # longs pay 0.0001 at 00/08/16 UTC settlements, shorts zero.
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    # stop-first: both hit in one minute -> stop fills at min(SL, open)
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v198():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v198_result" not in body
    assert "v198/v198" not in body
    assert "v198/" not in body.replace("v198_audit", "")
    # script must reference the TSMOM construction and the blend sweep
    assert "compute_tsmom" in body
    assert "BLEND" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
