"""oc_k2seeds per-seed Kronos-small inference (PLAN fixed settings, IDENTICAL except torch seed).

Copies research/tournament/oc_kronoshidden/run_inference_4shift.py sampling/
feature math verbatim; differences (pre-registered):
  * torch.manual_seed(SEED) once at start (SEED in {1,2,3,4});
  * scored window T in [2024-09-01, 2026-09-23] only (bars before are context);
  * output research/tournament/oc_k2seeds/kronos_features_seed{S}.parquet.
Same group order (sym,shift sorted), batch order (B=32), ctx 400x4h, pred_len 6,
S=64, T=1.0, top_p=0.9, top_k=0, fp32, per-window z-norm + clip 5.
Forecast for bar open T uses ONLY the 400 bars closing <= T on that shift's grid.

Usage: python run_inference_seed.py --seed 1 [--batch 32]
GPU via heavy_slot; import torch before pandas (Windows DLL order).
"""
import argparse
import sys
import time
from pathlib import Path

import torch  # before pandas (Windows DLL load order)

HERE = Path(__file__).resolve().parent
KH = HERE.parent / "oc_kronoshidden"
sys.path.insert(0, str(KH))
import numpy as np
import pandas as pd

import kronos_fast as kf
from model import Kronos, KronosTokenizer

MODEL = "NeoQuasar/Kronos-small"
P, H, S = 400, 6, 64
TEMP, TOP_P, TOP_K = 1.0, 0.9, 0
START = pd.Timestamp("2020-08-01", tz="UTC")
W0 = pd.Timestamp("2024-09-01", tz="UTC")
W1 = pd.Timestamp("2026-09-23 23:59", tz="UTC")
dev = "cuda:0"


def stamps(ts):
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], -1).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    SEED = int(args.seed)
    B = int(args.batch)
    OUT = HERE / f"kronos_features_seed{SEED}.parquet"

    torch.manual_seed(SEED)
    tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(dev).eval()
    mdl = Kronos.from_pretrained(MODEL).to(dev).eval()
    bars = pd.read_parquet(KH / "bars_4h_4shift.parquet")
    res = []
    done = set()
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print(f"seed {SEED} resume: groups already done {sorted(done)}", flush=True)
    t0 = time.time()
    last_hb = t0
    groups = sorted(bars.groupby(["sym", "shift"], sort=True).groups.keys())
    print(f"seed {SEED}: {len(groups)} groups, window [{W0.date()}, {W1.date()}], B={B}", flush=True)
    for (sym, shift) in groups:
        if (sym, shift) in done:
            continue
        b = bars[(bars["sym"] == sym) & (bars["shift"] == shift)].sort_values("T").reset_index(drop=True)
        X = b[["open", "high", "low", "close", "volume", "amount"]].to_numpy(np.float32)
        st = stamps(b["T"])
        lo = np.log(b.open.to_numpy())
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
        Tarr = b["T"].to_numpy()
        E = np.arange(len(b))
        E = E[(E >= P) & (b["T"].to_numpy() >= START) & np.isfinite(sig)
              & (b["T"].to_numpy() >= W0) & (b["T"].to_numpy() <= W1)]
        off = np.arange(-P, 0)
        hoff = pd.to_timedelta(4 * np.arange(H), unit="h")
        for i in range(0, len(E), B):
            e = E[i:i + B]
            x = X[e[:, None] + off]
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
                print(f"seed {SEED} {sym} s{shift} {i + len(e)}/{len(E)} elapsed {time.time() - t0:.0f}s", flush=True)
            if time.time() - last_hb >= 600:
                print(f"seed {SEED} heartbeat elapsed {time.time() - t0:.0f}s", flush=True)
                last_hb = time.time()
        pd.concat(res, ignore_index=True).to_parquet(OUT)
        print(f"seed {SEED} {sym} s{shift} checkpoint {len(E)} rows elapsed {time.time() - t0:.0f}s", flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"seed {SEED} saved {OUT} {len(out)} runtime {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
