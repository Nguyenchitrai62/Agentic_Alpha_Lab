import numpy as np
import pytest
import torch
from safetensors.torch import save_file,load_file
from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.models.macro_micro_value import MacroMicroValue,objective,swing_prediction


def candidates():
    return grid({"entry_atr_5m":[.5,1.5],"brackets_atr_4h":[[2,2,4],[3,3,6]],"holding_days":[3,7]})


def test_checkpoint_replays_and_candidate_order_rejected(tmp_path):
    torch.set_num_threads(2)
    torch.manual_seed(14)
    packed=np.concatenate((np.zeros((16,40),np.float32),candidates()),axis=1)
    assert not packed[:,-6:].flags.c_contiguous
    model=MacroMicroValue(packed[:,-6:],width=16)
    features=np.random.default_rng(2).normal(size=(4,40)).astype(np.float32)
    output=swing_prediction(model,features,candidates())
    path=tmp_path/"model.safetensors"
    save_file(model.state_dict(),str(path))
    restored=MacroMicroValue(candidates(),width=16)
    restored.load_state_dict(load_file(str(path)))
    np.testing.assert_array_equal(output,swing_prediction(restored,features,candidates()))
    with pytest.raises(ValueError,match="Candidate order"):
        swing_prediction(restored,features,candidates()[::-1])


def test_macro_and_micro_heads_receive_payoff_gradients():
    torch.set_num_threads(2)
    torch.manual_seed(17)
    model=MacroMicroValue(candidates(),width=16,dropout=0)
    labels=torch.randn(8,16,3)
    labels[...,1]=1
    score,aux=model(torch.randn(8,40))
    objective(score,aux,labels).backward()
    for name in ("frame.0.weight","macro.0.weight","micro.0.weight","gate.weight","action.0.weight","score.0.weight"):
        grad=dict(model.named_parameters())[name].grad
        assert torch.isfinite(grad).all() and grad.abs().sum()>0
