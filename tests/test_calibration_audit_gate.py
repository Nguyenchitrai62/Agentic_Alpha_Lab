import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_causal_calibration import run


def test_tcn_calibration_cannot_bypass_full_local_replay(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    (source / "summary.json").write_text(json.dumps({"plan": {"model_family": "tcn_fusion"}}))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"source": str(source), "dataset": str(tmp_path / "dataset")}))
    with pytest.raises(ValueError, match="full-forecast audit"):
        run(SimpleNamespace(plan=plan, output=tmp_path / "output"))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("field,value,match", [("embargo_days", 0, "embargo"), ("exposures", [2.0], "leverage")])
def test_calibration_rejects_undeclared_embargo_or_leverage(tmp_path, field, value, match):
    source = tmp_path / "source"; source.mkdir()
    (source / "summary.json").write_text(json.dumps({"plan": {"model_family": "gru"}}))
    plan = tmp_path / "plan.json"
    settings = {"source": str(source), "dataset": str(tmp_path / "dataset"), "embargo_days": 8, "exposures": [1.]}
    settings[field] = value
    plan.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match=match):
        run(SimpleNamespace(plan=plan, output=tmp_path / "output"))
