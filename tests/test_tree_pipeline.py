import numpy as np
import pytest
from sklearn.ensemble import ExtraTreesRegressor
from agentic_alpha_lab.models.tree_pipeline import PortableForest, export_forests


def test_regime_gate_requires_confirmation_not_just_drawdown():
    import json
    from pathlib import Path
    from agentic_alpha_lab.models.regime_gate import regime_mask, apply_gate
    from agentic_alpha_lab.data.swing import grid
    cfg = json.loads((Path(__file__).resolve().parents[1] / "configs/kronos_swing.json").read_text())
    x = np.zeros((2, 40))
    x[:, 35] = -.35  # Deep daily drawdown alone must NOT buy.
    x[:, 38], x[:, 30] = -.1, -.1
    mask = regime_mask(x, cfg, "confirmed_reversal_or_pullback")
    long = grid(cfg)[:, 0] > 0
    assert not mask[:, long].any()
    x[1, 33], x[1, 25] = .03, .01
    mask = regime_mask(x, cfg, "confirmed_reversal_or_pullback")
    assert mask[1, long].all() and not mask[0, long].any()
    p = np.ones((2, len(long), 6), np.float32)
    gated = apply_gate(p, x, cfg, "confirmed_reversal_or_pullback")
    assert (gated[0, long, 0] < 0).all()
    np.testing.assert_array_equal(p, np.ones_like(p))
    with pytest.raises(ValueError, match="Unknown"):
        regime_mask(x, cfg, "invented")


def test_safe_forest_export_matches_sklearn_on_unseen_features(tmp_path):
    rng = np.random.default_rng(7)
    x, y = rng.normal(size=(120, 6)), rng.normal(size=(120, 3))
    forest = ExtraTreesRegressor(n_estimators=8, max_depth=5, random_state=7).fit(x, y)
    output = tmp_path / "forest"
    export_forests({"expected": forest}, output)
    portable = PortableForest(output)
    test = rng.normal(size=(30, 6))
    np.testing.assert_allclose(portable.predict("expected", test), forest.predict(test), atol=1e-12)
    with pytest.raises(ValueError, match="Invalid features"):
        portable.predict("expected", np.full((2, 6), np.nan))
    with (output / "forests.npz").open("ab") as f:
        f.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        PortableForest(output)
