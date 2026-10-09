"""Kaggle kernel inference for oc_kronosbase: Kronos-base zero-shot forecasts.

Settings IDENTICAL to research/tournament/oc_kronoshidden/run_inference_4shift.py
except the model weights: context 400 x 4h bars, pred_len 6, S = 64 paths,
T = 1.0, top_p = 0.9, top_k = 0, torch seed 1234, fp32, per-window
z-normalisation + clip 5, same bars, same T range, same feature definitions.
Forecast for bar open T uses ONLY the 400 bars closing <= T on that shift's
grid. Bundle carries kronos_fast.py + model/ copied verbatim from
oc_kronoshidden (never modify ../Kronos); weights NeoQuasar/Kronos-base +
NeoQuasar/Kronos-Tokenizer-base come from the HF hub INSIDE the kernel.

Modes (one kernel run per clock shift if the 12 h limit is tight):
  python kernel_inference.py --model small --shifts 0 --verify50 --bars <bars.parquet> --ref <kronos_features_4shift.parquet> --out /kaggle/working/_verify.parquet
  python kernel_inference.py --model base  --shifts 0 --bars <bars.parquet> --out /kaggle/working/kronosbase_s0.parquet
  (merge per-shift outputs locally after download into kronosbase_features_4shift.parquet)

Progress: per-batch line + heartbeat line at least every 10 min (HEARTBEAT_S).
GPU scripts import torch BEFORE pandas (Windows DLL load order; same on Kaggle).
"""
import argparse
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import torch  # before pandas (DLL load order)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import kronos_fast as kf
from model import Kronos, KronosTokenizer

MODELS = {
    "small": "NeoQuasar/Kronos-small",
    "base": "NeoQuasar/Kronos-base",
}
TOK = "NeoQuasar/Kronos-Tokenizer-base"
P, H, S = 400, 6, 64
TEMP, TOP_P, TOP_K = 1.0, 0.9, 0
START = pd.Timestamp("2020-08-01", tz="UTC")
HEARTBEAT_S = 600
N_VERIFY = 50

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def stamps(ts):
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], -1).astype(np.float32)


def infer_groups(bars, tok, mdl, dev, out_path, shifts, batch, t0, tag, resume):
    res = []
    done = set()
    if resume and out_path.exists():
        prev = pd.read_parquet(out_path)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print(f"resume: groups already done {sorted(done)}", flush=True)
    for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
        if shift not in shifts or (sym, shift) in done:
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
        for i in range(0, len(E), batch):
            e = E[i:i + batch]
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
            if (i // batch) % 25 == 0:
                print(f"{sym} s{shift} {i + len(e)}/{len(E)} elapsed {time.time() - t0:.0f}s", flush=True)
        pd.concat(res, ignore_index=True).to_parquet(out_path)  # checkpoint per (sym, shift)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(out_path)
    print(f"saved {out_path} {len(out)} runtime {time.time() - t0:.0f}s [{tag}]", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["small", "base"], required=True)
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--bars", required=True)
    ap.add_argument("--ref", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--verify50", action="store_true")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    torch.manual_seed(1234)
    dev = "cuda:0"
    shifts = [int(s) for s in args.shifts.split(",")]
    t0 = time.time()
    hb = threading.Thread(target=heartbeat, args=(f"kb-{args.model}-s{args.shifts}",), daemon=True)
    hb.start()
    tok = KronosTokenizer.from_pretrained(TOK).to(dev).eval()
    mdl = Kronos.from_pretrained(MODELS[args.model]).to(dev).eval()
    bars = pd.read_parquet(args.bars)
    if args.verify50:
        assert args.model == "small" and args.ref, "--verify50 needs --model small + --ref"
        ref = pd.read_parquet(args.ref, columns=["sym", "shift", "T", "low1"])
        ref = ref[ref["shift"].isin(shifts)].sort_values(["sym", "shift", "T"])
        keys = ref[["sym", "shift", "T"]].drop_duplicates().head(N_VERIFY)
        print(f"verify50: {len(keys)} keys shifts={shifts}", flush=True)
        # restrict bars to windows ending at the 50 keys (inference still uses only bars <= T)
        keep = set(zip(keys["sym"].astype(str), keys["shift"].astype(int),
                       pd.to_datetime(keys["T"], utc=True)))
        sub = bars[bars["shift"].isin(shifts)]
        lut = set(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                      pd.to_datetime(sub["T"], utc=True)))
        missing = [k for k in keep if k not in lut]
        assert not missing, f"verify keys missing from bars: {missing[:3]}"
        out = infer_groups(bars, tok, mdl, dev, Path(args.out), shifts, args.batch, t0,
                           "verify50-small", resume=not args.no_resume)
        got = {(str(s), int(sh), pd.Timestamp(t)): float(lo)
               for s, sh, t, lo in zip(out["sym"], out["shift"], out["T"], out["low1"])}
        # pre-outcome fix 2026-10-08: pair in keys order (zip(keep-set, ...) was
        # unordered and could mismatch rows); sampling/feature math unchanged.
        exp_lut = {(str(s), int(sh), pd.Timestamp(t)): float(lo)
                   for s, sh, t, lo in zip(ref["sym"], ref["shift"], ref["T"], ref["low1"])}
        ordered = list(zip(keys["sym"].astype(str), keys["shift"].astype(int),
                           pd.to_datetime(keys["T"], utc=True)))
        diffs = [abs(got[k] - exp_lut[k]) for k in ordered]
        print(f"verify50 low1: n={len(diffs)} max_abs_diff={max(diffs):.6f} "
              f"median_abs_diff={float(np.median(diffs)):.6f}", flush=True)
    else:
        infer_groups(bars, tok, mdl, dev, Path(args.out), shifts, args.batch, t0,
                     f"{args.model}", resume=not args.no_resume)
    _stop_hb.set()


if __name__ == "__main__":
    main()
