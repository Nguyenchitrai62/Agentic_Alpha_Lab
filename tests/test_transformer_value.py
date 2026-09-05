import numpy as np
import torch
from agentic_alpha_lab.models.transformer_value import TemporalValue
from agentic_alpha_lab.models.temporal_value import predict
from agentic_alpha_lab.data.swing import grid


def test_transformer_gradients_and_replay_include_all_frames_and_layers():
    torch.set_num_threads(2);torch.manual_seed(18)
    c=grid({"entry_atr_5m":[.5,1.5],"brackets_atr_4h":[[2,2,4],[3,3,6]],"holding_days":[3,7]})
    m=TemporalValue(c,width=24,layers=2,heads=3,dropout=0)
    x=torch.randn(2,5,128,6,requires_grad=True);f=torch.randn(2,40)
    score,aux=m(x,f);(score.square().mean()+aux.square().mean()).backward()
    assert score.shape==(2,16,2)
    assert (x.grad.abs().sum((0,2,3))>0).all()
    for layer in m.layers: assert layer.self_attn.in_proj_weight.grad.abs().sum()>0
    clone=TemporalValue(c,width=24,layers=2,heads=3,dropout=0);clone.load_state_dict(m.state_dict())
    a=predict(m,x.detach().numpy(),f.numpy());b=predict(clone,x.detach().numpy(),f.numpy())
    np.testing.assert_allclose(a,b,rtol=1e-6,atol=1e-6)
