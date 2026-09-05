import numpy as np
import pytest
from agentic_alpha_lab.models.ensemble_value import combine,directional_consensus


def test_combine_uses_unconditional_values_and_fill_probabilities():
    p=np.zeros((2,1,1,6))
    p[...,0]=np.array([4.,2.]).reshape(2,1,1)
    p[...,4]=np.log(np.array([.25/.75,.75/.25])).reshape(2,1,1)
    result,details=combine(p,1.)
    assert details["mean_expected_net_percent"].item()==pytest.approx(1.25)
    assert details["seed_std_net_percent"].item()==pytest.approx(.25)
    assert result[0,0,0]==pytest.approx(2.)
    assert result[0,0,4]==pytest.approx(0.)


def test_permuting_seed_order_does_not_select_a_winner():
    p=np.random.default_rng(1).normal(size=(3,4,16,6))
    np.testing.assert_allclose(combine(p,.5)[0],combine(p[::-1],.5)[0])
    with pytest.raises(ValueError):
        combine(p,-1)


def test_direction_agreement_abstains_on_disagreement_and_wait_vote():
    p=np.zeros((3,3,2,6))
    p[...,0]=[2.,1.]
    p[1,1,:,0]=[1.,2.]
    p[2,2,:,0]=0
    allowed,votes=directional_consensus(p,[1,-1])
    np.testing.assert_array_equal(allowed,[[True,False],[False,False],[False,False]])
    assert votes[2,2]==0


def test_direction_agreement_respects_candidate_order_and_fill_gate():
    p=np.zeros((3,1,2,6))
    p[...,0]=[1.,2.]
    allowed,_=directional_consensus(p,[-1,1])
    np.testing.assert_array_equal(allowed,[[False,True]])
    p[0,0,1,4]=-20
    assert not directional_consensus(p,[-1,1])[0].any()
