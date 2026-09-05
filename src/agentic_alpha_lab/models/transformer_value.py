"""Joint attention over80past patches with learned frame and age embeddings."""
import torch
from torch import nn
from agentic_alpha_lab.models.temporal_value import predict


class TemporalValue(nn.Module):
    def __init__(self,candidates,width=192,dropout=.15,layers=6,heads=6):
        super().__init__()
        self.register_buffer("feature_mean",torch.zeros(40))
        self.register_buffer("feature_scale",torch.ones(40))
        self.register_buffer("candidates",torch.as_tensor(candidates,dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale",torch.tensor([1.,1.5,3.,3.,6.,7.]))
        self.patch=nn.Sequential(nn.Linear(48,width),nn.GELU(),nn.LayerNorm(width))
        self.frame_embedding=nn.Parameter(torch.randn(1,5,1,width)*.02)
        self.age_embedding=nn.Parameter(torch.randn(1,1,16,width)*.02)
        self.layers=nn.ModuleList([nn.TransformerEncoderLayer(width,heads,4*width,dropout,
                                     activation="gelu",batch_first=True,norm_first=True) for _ in range(layers)])
        self.norm=nn.LayerNorm(width)
        self.frame_features=nn.Sequential(nn.Linear(8,width),nn.GELU())
        self.macro=nn.Sequential(nn.Linear(2*width,width),nn.GELU(),nn.Dropout(dropout))
        self.micro=nn.Sequential(nn.Linear(3*width,width),nn.GELU(),nn.Dropout(dropout))
        self.gate=nn.Linear(width,width)
        self.action=nn.Sequential(nn.Linear(6,width),nn.GELU())
        self.score=nn.Sequential(nn.Linear(4*width,width),nn.GELU(),nn.Dropout(dropout),nn.Linear(width,2))
        self.regime=nn.Linear(width,1)

    def forward(self,sequence,features):
        n=len(sequence)
        token=self.patch(sequence.reshape(n,5,16,48))+self.frame_embedding+self.age_embedding
        token=token.reshape(n,80,-1)
        # Every token comes from candles already closed at the current decision.
        # Bidirectional attention within that past context introduces no future data.
        for layer in self.layers: token=layer(token)
        normalized=((features-self.feature_mean)/self.feature_scale).clamp(-10,10)
        frames=self.norm(token).reshape(n,5,16,-1)[:,:,-1]+self.frame_features(normalized.reshape(n,5,8))
        macro=self.macro(frames[:,3:].flatten(1))
        micro=self.micro(frames[:,:3].flatten(1))*self.gate(macro).sigmoid()
        action=self.action(self.candidates/self.candidate_scale); k=len(action)
        ma,mi,ac=macro[:,None].expand(-1,k,-1),micro[:,None].expand(-1,k,-1),action[None].expand(n,-1,-1)
        return self.score(torch.cat((ma,mi,ac,(ma+mi)*ac),-1)),self.regime(macro).squeeze(-1)
