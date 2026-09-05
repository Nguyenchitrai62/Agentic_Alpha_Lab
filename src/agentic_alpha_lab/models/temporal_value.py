"""Learn temporal order in16 patches per timeframe, then macro-conditioned bracket values."""
import torch
from torch import nn


class TemporalValue(nn.Module):
    def __init__(self,candidates,width=48,dropout=.15):
        super().__init__()
        self.register_buffer("feature_mean",torch.zeros(40))
        self.register_buffer("feature_scale",torch.ones(40))
        self.register_buffer("candidates",torch.as_tensor(candidates,dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale",torch.tensor([1.,1.5,3.,3.,6.,7.]))
        self.patch=nn.Sequential(nn.Linear(8*6,width),nn.GELU(),nn.LayerNorm(width))
        self.history=nn.GRU(width,width,batch_first=True)
        self.frame_features=nn.Sequential(nn.Linear(8,width),nn.GELU())
        self.macro=nn.Sequential(nn.Linear(2*width,width),nn.GELU(),nn.Dropout(dropout))
        self.micro=nn.Sequential(nn.Linear(3*width,width),nn.GELU(),nn.Dropout(dropout))
        self.gate=nn.Linear(width,width)
        self.action=nn.Sequential(nn.Linear(6,width),nn.GELU())
        self.score=nn.Sequential(nn.Linear(4*width,width),nn.GELU(),nn.Dropout(dropout),nn.Linear(width,2))
        self.regime=nn.Linear(width,1)

    def forward(self,sequence,features):
        n=len(sequence)
        patches=self.patch(sequence.reshape(n*5,16,48))
        _,hidden=self.history(patches)
        normalized=((features-self.feature_mean)/self.feature_scale).clamp(-10,10)
        frames=hidden[-1].reshape(n,5,-1)+self.frame_features(normalized.reshape(n,5,8))
        macro=self.macro(frames[:,3:].flatten(1))
        micro=self.micro(frames[:,:3].flatten(1))*self.gate(macro).sigmoid()
        action=self.action(self.candidates/self.candidate_scale)
        k=len(action)
        ma,mi,ac=macro[:,None].expand(-1,k,-1),micro[:,None].expand(-1,k,-1),action[None].expand(n,-1,-1)
        return self.score(torch.cat((ma,mi,ac,(ma+mi)*ac),dim=-1)),self.regime(macro).squeeze(-1)


def predict(model,sequence,features,batch_size=128):
    model.eval()
    device=next(model.parameters()).device
    result=[]
    with torch.no_grad():
        for start in range(0,len(features),batch_size):
            score,_=model(torch.as_tensor(sequence[start:start+batch_size],dtype=torch.float32,device=device),
                          torch.as_tensor(features[start:start+batch_size],dtype=torch.float32,device=device))
            fill=score[...,1].sigmoid().clamp(1e-6,1-1e-6)
            output=torch.zeros((*score.shape[:2],6),device=device)
            output[...,0],output[...,4]=score[...,0]/fill,torch.logit(fill)
            result.append(output.cpu())
    return torch.cat(result).numpy()
