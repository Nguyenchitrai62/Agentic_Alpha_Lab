"""Correctness check of kronos_fast vs reference calls + speed benchmark (no evaluation data touched beyond input bars)."""
import sys, time
from pathlib import Path
import torch  # before pandas (Windows DLL order)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from model import Kronos, KronosTokenizer
from model.kronos import calc_time_stamps
import kronos_fast as kf

dev = "cuda:0"
tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(dev).eval()
mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small").to(dev).eval()
bars = pd.read_parquet(Path(__file__).parent / "bars_4h.parquet")
b = bars[bars.sym == "BTCUSDT"].reset_index(drop=True)
P, H = 400, 6
def windows(idx):
    xs, xst, yst = [], [], []
    for e in idx:
        w = b.iloc[e - P:e]
        x = w[["open", "high", "low", "close", "volume", "amount"]].to_numpy(np.float32)
        m, s = x.mean(0), x.std(0)
        xs.append((x - m) / (s + 1e-5))
        xst.append(calc_time_stamps(w["T"]).to_numpy(np.float32))
        yt = pd.Series(b["T"].iloc[e - 1] + pd.to_timedelta(4 * np.arange(1, H + 1), unit="h"))
        yst.append(calc_time_stamps(yt).to_numpy(np.float32))
    f = lambda a: torch.from_numpy(np.stack(a)).to(dev)
    return f(xs), f(xst), f(yst)
x, xs, ys = windows([3000, 5000, 7000, 9000])
print("greedy check", kf.logits_check(tok, mdl, x, xs, ys, H))
print("sampled check", kf.verify(tok, mdl, x[:2], xs[:2], ys[:2], H, S=4))
for B, S in [(16, 32), (32, 32), (64, 32)]:
    x, xs, ys = windows(list(range(2000, 2000 + B)))
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); t = time.time()
    for _ in range(3):
        out = kf.sample_paths(tok, mdl, x, xs, ys, H, S)
    torch.cuda.synchronize()
    dt = (time.time() - t) / 3
    print(f"B={B} S={S}: {dt:.3f}s/batch, {dt / B * 1000:.1f} ms/series, peak {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
