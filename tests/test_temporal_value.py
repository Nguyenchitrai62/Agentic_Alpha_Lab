import numpy as np
import torch
from agentic_alpha_lab.models.temporal_value import TemporalValue
from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.data.sequence_context import encode_windows


def test_sequence_price_encoding_invariant_to_currency_scale():
    rng=np.random.default_rng(15)
    w=np.exp(rng.normal(size=(5,128,6))*.01)*100
    shifted=w.copy()
    shifted[...,:4]*=5
    np.testing.assert_allclose(encode_windows(w),encode_windows(shifted),atol=1e-6)
    flat=np.ones((5,128,6))
    flat[...,4:]=0
    assert np.isfinite(encode_windows(flat)).all()


def test_temporal_encoder_is_order_sensitive_and_trainable():
    torch.set_num_threads(2)
    torch.manual_seed(16)
    candidates=grid({"entry_atr_5m":[.5,1.5],"brackets_atr_4h":[[2,2,4],[3,3,6]],"holding_days":[3,7]})
    model=TemporalValue(candidates,width=16,dropout=0)
    x=torch.randn(2,5,128,6)
    f=torch.zeros(2,40)
    first,_=model(x,f)
    reverse,_=model(x.flip(2),f)
    assert first.shape==(2,16,2)
    assert not torch.allclose(first,reverse)
    first.square().mean().backward()
    grad=model.history.weight_hh_l0.grad
    assert torch.isfinite(grad).all() and grad.abs().sum()>0
