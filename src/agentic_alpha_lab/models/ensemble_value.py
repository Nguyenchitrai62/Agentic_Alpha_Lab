"""Candidate-level ensemble mean and disagreement gate; disagreement is not probability."""
import numpy as np


def combine(predictions, disagreement_penalty=0.):
    p=np.asarray(predictions,dtype=np.float64)
    if p.ndim!=4 or p.shape[-1]!=6 or p.shape[0]<2 or not np.isfinite(p).all() or disagreement_penalty<0:
        raise ValueError("Need finite seed/decision/candidate/six-column predictions")
    fill=1/(1+np.exp(-np.clip(p[...,4],-40,40)))
    expected=p[...,0]*fill
    mean=expected.mean(0)
    disagreement=expected.std(0)
    average_fill=np.clip(fill.mean(0),1e-6,1-1e-6)
    score=mean-disagreement_penalty*disagreement
    result=np.zeros((*mean.shape,6),np.float32)
    result[...,0]=score/average_fill
    result[...,4]=np.log(average_fill/(1-average_fill))
    return result,{"mean_expected_net_percent":mean,"seed_std_net_percent":disagreement,
                   "selection_score_percent":score,"mean_fill_score":average_fill}


def directional_consensus(predictions,candidate_directions,minimum_net=.3,minimum_fill=.25):
    """Allow actions only on the unanimous eligible top-action side; otherwise WAIT.

    This is learned-model agreement, not calibrated confidence. It uses no labels.
    """
    p=np.asarray(predictions,dtype=np.float64)
    directions=np.asarray(candidate_directions)
    if p.ndim!=4 or p.shape[-1]!=6 or p.shape[0]<2 or not np.isfinite(p).all():
        raise ValueError("Invalid ensemble predictions")
    if directions.shape!=(p.shape[2],) or not np.isin(directions,[-1,1]).all():
        raise ValueError("Invalid candidate directions")
    fill=1/(1+np.exp(-np.clip(p[...,4],-40,40)))
    value=p[...,0]*fill
    eligible=(fill>=minimum_fill)&(value>=minimum_net)
    top=np.where(eligible,value,-np.inf).argmax(-1)
    votes=np.where(eligible.any(-1),directions[top],0)
    unanimous=(votes==votes[:1]).all(0)&(votes[0]!=0)
    return unanimous[:,None]&(directions[None]==votes[0,:,None]),votes
