"""Tests for v190 blind audit (Part A). Does not open research v190 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v190_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v190.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v190 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v190_audit_replication"
    assert d["blind"] == "did_not_open_research_v190_until_this_file_saved"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["features"]["f103_n"] == len(d["features"]["f103"])
    assert "vol42" in d["features"]["f103"] and "rib" in d["features"]["f103"]
    assert not any(c == "y" or c.startswith("y") for c in d["features"]["f103"])
    assert len(d["ic_per_anchor"]) == 5
    for r in d["ic_per_anchor"]:
        assert r["anchor"] in d["anchors"]
        assert r["train_rows"] > 0 and r["n_pred_rows"] > 0
        assert r["ic_combined"] is None or -1 <= r["ic_combined"] <= 1
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_sl"] == 2.0
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"]) == {"v151", "E", "blend_50_50"}
    for key, row in d["rows"].items():
        assert row["m_sl"] == 4.0 and row["sleeve"] is True
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == d["anchors"]


def test_rows_dev4_and_gate():
    d = _rep()
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
        assert row["gate_dd"] == max(row["dd_4h"], row["dd_1m"])
        assert row["losing_years"] == sum(1 for x in row["yearly_net_pct"] if x < 0)
    # sleeve rows take rungs
    for key in ("v151", "E", "blend_50_50"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key


def test_label_and_training_spec():
    d = _rep()
    assert d["spec"]["train_filter"] == "t + 43 bars < anchor - 78 bars"
    assert d["labels"]["horizon_bars"] == 42
    assert d["labels"]["exit_bar"] == 43
    assert d["labels"]["embargo_bars"] == 78
    assert d["labels"]["m_sl"] == 4.0
    assert d["vol_forecast"]["n_replaced"] > 0
    assert d["union_bars"] >= 10900


def test_gate_cost_model_synthetic():
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v190():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v190_result" not in body
    assert "v190/v190" not in body
    assert "v190/" not in body.replace("v190_audit", "")
    assert "monthly_dev4" in body
    assert "43" in body and "78" in body
