"""Zero-shot Kronos-small forecasts on FOUR 4h clock shifts (settings = kronos/PLAN.md).

Copied logic from research/tournament/kronos/run_inference.py (identical
sampling/feature math; grid extended to shifts 0..3 and to the last local
bar). Forecast for bar open T uses ONLY the 400 bars closing <= T on that
shift's grid. Output: kronos_features_4shift.parquet (sym, shift, T, sigma,
C0, er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3).

Usage: python run_inference_4shift.py [out_name] [batch]
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

MODEL = "NeoQuasar/Kronos-small"
OUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "kronos_features_4shift.parquet")
P, H, S = 400, 6, 64
B = int(sys.argv[2]) if len(sys.argv) > 2 else 32
TEMP, TOP_P, TOP_K = 1.0, 0.9, 0
START = pd.Timestamp("2020-08-01", tz="UTC")
dev = "cuda:0"


def stamps(ts):
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], -1).astype(np.float32)


def main():
    torch.manual_seed(1234)
    tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(dev).eval()
    mdl = Kronos.from_pretrained(MODEL).to(dev).eval()
    bars = pd.read_parquet(HERE / "bars_4h_4shift.parquet")
    res = []
    done = set()
    if OUT.exists():  # leader resume patch 2026-10-07: the run was killed after 18/20 groups (watchdog killed the parent worker);
        prev = pd.read_parquet(OUT)  # keep finished groups, compute only the missing ones (RNG stream differs for those - sampling noise only)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print("resume: groups already done", sorted(done), flush=True)
    t0 = time.time()
    for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
        if (sym, shift) in done:
            continue
        b = b.sort_values("T").reset_index(drop=True)
        X = b[["open", "high", "low", "close", "volume", "amount"]].to_numpy(np.float32)
        st = stamps(b["T"])
        lo = np.log(b.open.to_numpy())
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
        E = np.arange(len(b))
        E = E[(E >= P) & (b["T"].to_numpy() >= START) & np.isfinite(sig)]
        off = np.arange(-P, 0)
        hoff = pd.to_timedelta(4 * np.arange(H), unit="h")
        for i in range(0, len(E), B):
            e = E[i:i + B]
            x = X[e[:, None] + off]  # [b,P,6]
            m, s = x.mean(1, keepdims=True), x.std(1, keepdims=True)
            xn = (x - m) / (s + 1e-5)
            xs = st[e[:, None] + off]
            ys = np.stack([stamps(b["T"].iloc[k] + hoff) for k in e])
            f = lambda a: torch.from_numpy(np.ascontiguousarray(a, dtype=np.float32)).to(dev)
            out = kf.sample_paths(tok, mdl, f(xn), f(xs), f(ys), H, S, T=TEMP, top_k=TOP_K, top_p=TOP_P)
            out = out.double() * (f(s)[:, None, :, :].double() + 1e-5) + f(m)[:, None, :, :].double()
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
            df.insert(0, "shift", shift)
            df.insert(0, "sym", sym)
            res.append(df)
            if (i // B) % 50 == 0:
                print(f"{sym} s{shift} {i + len(e)}/{len(E)} elapsed {time.time() - t0:.0f}s", flush=True)
        pd.concat(res, ignore_index=True).to_parquet(OUT)  # checkpoint per (sym, shift)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print("saved", OUT, len(out), f"runtime {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
