"""Supervised macro-conditioned micro entry scorer; no Kronos/tokenizer dependency.

Input is40 causal candle summaries, not raw candle sequences. Each of16 bracket
actions receives learned unconditional payoff and OHLC fill scores.
"""
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


class MacroMicroValue(nn.Module):
    def __init__(self, candidates, width=64, dropout=.15):
        super().__init__()
        self.register_buffer("feature_mean", torch.zeros(40))
        self.register_buffer("feature_scale", torch.ones(40))
        self.register_buffer("candidate_scale", torch.tensor([1.,1.5,3.,3.,6.,7.]))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.frame = nn.Sequential(nn.Linear(8,width),nn.GELU(),nn.LayerNorm(width))
        self.macro = nn.Sequential(nn.Linear(2*width,width),nn.GELU(),nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3*width,width),nn.GELU(),nn.Dropout(dropout))
        self.gate = nn.Linear(width,width)
        self.action = nn.Sequential(nn.Linear(6,width),nn.GELU())
        self.score = nn.Sequential(nn.Linear(4*width,width),nn.GELU(),nn.Dropout(dropout),nn.Linear(width,2))
        self.regime = nn.Linear(width,1)

    def forward(self, features):
        normalized = ((features-self.feature_mean)/self.feature_scale).clamp(-10,10)
        encoded = self.frame(normalized.reshape(-1,5,8))
        macro = self.macro(encoded[:,3:].flatten(1))
        micro = self.micro(encoded[:,:3].flatten(1)) * torch.sigmoid(self.gate(macro))
        action = self.action(self.candidates/self.candidate_scale)
        n,k = len(features),len(action)
        expanded = action[None].expand(n,-1,-1)
        macro,micro = macro[:,None].expand(-1,k,-1),micro[:,None].expand(-1,k,-1)
        score = self.score(torch.cat((macro,micro,expanded,(macro+micro)*expanded),dim=-1))
        return score,self.regime(macro[:,0]).squeeze(-1)


def objective(prediction, auxiliary, labels, scale_percent=2.):
    target,fill = labels[...,0],labels[...,1]
    # Unfilled payoff is zero in execution labels: regress unconditional arithmetic mean.
    payoff = F.mse_loss(prediction[...,0]/scale_percent,target/scale_percent)
    fill_loss = F.binary_cross_entropy_with_logits(prediction[...,1],fill)
    direction = target[:,:8].mean(-1)-target[:,8:].mean(-1)
    auxiliary_loss = F.mse_loss(auxiliary/scale_percent,direction/scale_percent)
    return payoff+.1*fill_loss+.1*auxiliary_loss


def swing_prediction(model, features, candidates):
    model.eval()
    if not np.array_equal(np.asarray(candidates),model.candidates.cpu().numpy()):
        raise ValueError("Candidate order differs from trained model")
    results=[]
    with torch.no_grad():
        for start in range(0,len(features),256):
            score,_ = model(torch.as_tensor(features[start:start+256],dtype=torch.float32))
            fill = score[...,1].sigmoid().clamp(1e-6,1-1e-6)
            output = torch.zeros((*score.shape[:2],6))
            output[...,0],output[...,4] = score[...,0]/fill,torch.logit(fill)
            results.append(output.numpy())
    return np.concatenate(results)
