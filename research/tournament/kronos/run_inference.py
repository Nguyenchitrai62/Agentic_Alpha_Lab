"""Zero-shot Kronos-small forecasts for every 4h bar open T (majors), settings fixed in PLAN.md.

Forecast for bar T uses the 400 bars that closed at or before T (indices e-400 .. e-1 where bar e opens at T). Output:
kronos_4h_features.parquet (sym, T, sigma, C0, er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3).
Usage: python run_inference.py [model_name] [stride] [out_name]
"""
import sys
import time
from pathlib import Path

import torch  # before pandas (Windows DLL load order)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import kronos_fast as kf
from model import Kronos, KronosTokenizer

MODEL = sys.argv[1] if len(sys.argv) > 1 else "NeoQuasar/Kronos-small"
STRIDE = int(sys.argv[2]) if len(sys.argv) > 2 else 1
OUT = HERE / (sys.argv[3] if len(sys.argv) > 3 else "kronos_4h_features.parquet")
P, H, S = 400, 6, 64
B = int(sys.argv[4]) if len(sys.argv) > 4 else 32
TEMP, TOP_P, TOP_K = 1.0, 0.9, 0
START, DEV_END = pd.Timestamp("2020-08-01", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
dev = "cuda:0"


def stamps(ts):
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], -1).astype(np.float32)


def main():
    torch.manual_seed(1234)
    tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(dev).eval()
    mdl = Kronos.from_pretrained(MODEL).to(dev).eval()
    bars = pd.read_parquet(HERE / "bars_4h.parquet")
    assert bars["T"].max() < DEV_END
    res = []
    t0 = time.time()
    for sym, b in bars.groupby("sym", sort=False):
        b = b.sort_values("T").reset_index(drop=True)
        X = b[["open", "high", "low", "close", "volume", "amount"]].to_numpy(np.float32)
        st = stamps(b["T"])
        lo = np.log(b.open.to_numpy())
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()  # 360 returns ending at open(T)
        E = np.arange(len(b))
        E = E[(E >= P) & (b["T"].to_numpy() >= START) & np.isfinite(sig)][::STRIDE]
        off = np.arange(-P, 0)
        hoff = pd.to_timedelta(4 * np.arange(H), unit="h")
        for i in range(0, len(E), B):
            e = E[i:i + B]
            x = X[e[:, None] + off]  # [b,P,6]
            m, s = x.mean(1, keepdims=True), x.std(1, keepdims=True)
            xn = (x - m) / (s + 1e-5)
            xs = st[e[:, None] + off]
            ys = np.stack([stamps(b["T"].iloc[k] + hoff) for k in e])  # calendar stamps of bars T..T+20h
            f = lambda a: torch.from_numpy(np.ascontiguousarray(a, dtype=np.float32)).to(dev)
            out = kf.sample_paths(tok, mdl, f(xn), f(xs), f(ys), H, S, T=TEMP, top_k=TOP_K, top_p=TOP_P)  # [b,S,H,6]
            out = out.double() * (f(s)[:, None, :, :].double() + 1e-5) + f(m)[:, None, :, :].double()  # de-normalise
            O, Hh, L, C = out[..., 0], out[..., 1], out[..., 2], out[..., 3]
            Leff = torch.minimum(torch.minimum(L, O), C).clamp_min(1e-12)
            Heff = torch.maximum(torch.maximum(Hh, O), C)
            C0 = torch.from_numpy(X[e - 1, 3].astype(np.float64)).to(dev)[:, None]
            sg = torch.from_numpy(sig[e]).to(dev)[:, None]
            r1 = torch.log(C[..., 0].clamp_min(1e-12) / C0) / sg
            r6 = torch.log(C[..., 5].clamp_min(1e-12) / C0) / (sg * np.sqrt(6))
            l1 = torch.log(Leff[..., 0] / C0) / sg
            feats = dict(er1=r1.mean(1), er6=r6.mean(1), vol1=r1.std(1), vol6=r6.std(1),
                         rng1=(torch.log(Heff[..., 0] / Leff[..., 0]) / sg).mean(1), low1=l1.mean(1),
                         pdrop2=(l1 < -2).double().mean(1), pdrop3=(l1 < -3).double().mean(1))
            df = pd.DataFrame({k: v.cpu().numpy() for k, v in feats.items()})
            df.insert(0, "C0", X[e - 1, 3])
            df.insert(0, "sigma", sig[e])
            df.insert(0, "T", b["T"].to_numpy()[e])
            df.insert(0, "sym", sym)
            res.append(df)
            if (i // B) % 50 == 0:
                print(f"{sym} {i + len(e)}/{len(E)} elapsed {time.time() - t0:.0f}s", flush=True)
        pd.concat(res, ignore_index=True).to_parquet(OUT)  # checkpoint after every coin
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print("saved", OUT, len(out), f"runtime {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
