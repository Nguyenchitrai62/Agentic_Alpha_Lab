import torch
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from safetensors.torch import load_file, save_file
from agentic_alpha_lab.models.tcn_fusion_value import CausalBlock, TemporalValue
from agentic_alpha_lab.models.temporal_value import predict
from agentic_alpha_lab.data.swing import grid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from train_tcn_kaggle import fold_indices, stable_evaluation_backend
from package_tcn_kaggle import collect


def candidates():
    return grid({"entry_atr_5m": [.5, 1.5], "brackets_atr_4h": [[2, 2, 4], [3, 3, 6]], "holding_days": [3, 7]})


def test_causal_tcn_cannot_see_later_candles():
    torch.set_num_threads(2)
    block = CausalBlock(8, 4, 0).eval()
    x = torch.randn(2, 8, 128)
    changed = x.clone(); changed[:, :, 64:] += 100
    torch.testing.assert_close(block(x)[:, :, :64], block(changed)[:, :, :64], rtol=0, atol=0)


def test_all_frames_attention_and_heads_receive_gradients_and_reload(tmp_path):
    stable_evaluation_backend()
    torch.set_num_threads(2); torch.manual_seed(19)
    spec = dict(width=24, tcn_width=8, layers=2, heads=3, dropout=0, dilations=[1, 2])
    model = TemporalValue(candidates(), **spec)
    x = torch.randn(2, 5, 128, 6, requires_grad=True); f = torch.randn(2, 40)
    score, aux = model(x, f)
    (score.square().mean() + aux.square().mean()).backward()
    assert score.shape == (2, 16, 2)
    assert (x.grad.abs().sum((0, 2, 3)) > 0).all()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    assert all(layer.self_attn.in_proj_weight.grad.abs().sum() > 0 for layer in model.layers)
    save_file(model.state_dict(), str(tmp_path / "weights.safetensors"))
    clone = TemporalValue(candidates(), **spec)
    clone.load_state_dict(load_file(str(tmp_path / "weights.safetensors")))
    np.testing.assert_allclose(predict(model, x.detach().numpy(), f.numpy()),
                               predict(clone, x.detach().numpy(), f.numpy()), rtol=1e-6, atol=1e-6)


def test_v19_capacity_is_in_declared_range():
    spec = json.loads(Path("configs/swing_v19_tcn_fusion.json").read_text())
    # Parameter sizing only; no local full model training.
    with torch.device("meta"):
        model = TemporalValue(candidates(), **spec["network"])
    assert 20_000_000 <= sum(p.numel() for p in model.parameters()) <= 30_000_000


def test_fold_uses_label_maturity_and_global_not_quarter_end_cutoff():
    decisions = pd.DataFrame({"signal_time": pd.date_range("2023-01-01", "2023-07-31", freq="D", tz="UTC")})
    decisions["label_end"] = decisions.signal_time + pd.Timedelta(days=7)
    parent = {"folds": [["2023-06-01T00:00Z", "2023-07-01T00:00Z"]], "complete_evaluation_until": "2023-08-10T00:00Z"}
    train, test = fold_indices(decisions, parent, {"window_days": 730, "embargo_days": 8, "minimum_train_decisions": 20}, 0)
    assert decisions.iloc[train].label_end.max() < pd.Timestamp("2023-05-24T00:00Z")
    assert decisions.iloc[test].signal_time.max() == pd.Timestamp("2023-06-30T00:00Z")
    assert not np.intersect1d(train, test).size


def test_bundle_allowlist_excludes_credentials_candles_and_checkpoints():
    # This is an integration check when the local ignored training snapshot exists.
    if not Path("data/processed/swing_regime_research_v4/manifest.json").exists():
        import pytest
        pytest.skip("Private dataset intentionally absent from Git")
    paths = collect(Path("configs/swing_v19_tcn_fusion.json").resolve())
    assert all(p.name not in {"access_token", "kaggle.json", ".env", "candles.parquet"} for p in paths)
    assert all(p.suffix != ".safetensors" for p in paths)
