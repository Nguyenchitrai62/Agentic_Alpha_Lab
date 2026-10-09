"""Zero-shot Datadog Toto forecasts on FOUR 4h clock shifts (settings = oc_toto/PLAN.md Part A).

For each majors coin, each clock shift s = 0..3 (4h bars from
oc_kronoshidden/bars_4h_4shift.parquet), each bar open T: context = the last
512 closes of that shift's bars ending at the bar closing at T (log prices),
forecast horizon 1 bar. Quantile forecasts q10/q50/q90 of the next close from
the Toto next-patch predictive distribution:
  f_q10 = (q10 - log C0) / sigma, f_q50/f_q90 likewise,
  sigma = std of the last 360 4h log returns (SAME formula as Kronos' sigma:
  std of diff(log(open)) rolling 360), C0 = close of the bar closing at T,
  risk = -f_q10 (in tilt_rule / make_fits, not here).

Predictive-distribution sampling (PLAN-registered alternative to the
TotoForecaster sampling loop, which repeats the context per sample-batch and
is ~25x slower): one backbone forward per batch yields the next-patch
predictive distribution (Student-T mixture via AffineTransformed); 256 i.i.d.
samples are drawn from that distribution object with replace_extreme_values
(same as the forecaster), and q10/q50/q90 are sample quantiles. With horizon 1
only a single patch is generated, so this is the same distribution the
forecaster's first (and only) patch iteration samples; statistical equivalence
on dummy + real BTC contexts was checked before the full run (differences
within 256-sample noise; extreme-value replacement replicated).

Forecast for bar open T uses ONLY closes of bars closing <= T on that shift's
grid (bars e-512..e-1 for the bar at index e; open of bar e known at T feeds
sigma only, same indexing as kronos/run_inference_4shift.py and
oc_chronos/run_chronos_4shift.py). Output:
toto_features_4shift.parquet (sym, shift, T, f_q10, f_q50, f_q90, sigma).

Context scaling: log closes are passed directly; Toto's internal scaler
(CausalStdMeanScaler selected by the checkpoint config) handles magnitude, same
convention as oc_chronos (log prices, no manual z-norm). Timestamps: zeros with
constant time_interval_seconds = 14400 (official quick-start convention;
causal, deterministic; absolute offset carries no information for a regular
4h grid under relative rotary embeddings).

Resume-safe: checkpoint per (sym, shift) group to the parquet; finished groups
are skipped. Heartbeat print every 600 s.

Usage: python run_toto_4shift.py [out_name] [batch] [device]
Run through heavy_slot (one GPU job at a time).
"""
import sys
import time
from pathlib import Path

import torch  # before pandas (Windows DLL load order)

HERE = Path(__file__).resolve().parent
PYLIB = HERE / "pylib"
sys.path.insert(0, str(PYLIB))

import numpy as np
import pandas as pd

from toto.data.util.dataset import pad_array, pad_id_mask, replace_extreme_values
from toto.inference.forecaster import TotoForecaster
from toto.model.toto import Toto

MODEL = "Datadog/Toto-Open-Base-1.0"
OUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "toto_features_4shift.parquet")
B = int(sys.argv[2]) if len(sys.argv) > 2 else 32
DEV_ARG = sys.argv[3] if len(sys.argv) > 3 else "auto"
P, H, NSAMP = 512, 1, 256
INTERVAL_S = 14400
START = pd.Timestamp("2020-08-01", tz="UTC")
HB_S = 600
SEED = 20261008


def resolve_device():
    if DEV_ARG != "auto":
        return DEV_ARG
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def main():
    torch.manual_seed(SEED)
    dev = resolve_device()
    print(f"device={dev} batch={B} nsamp={NSAMP} ctx={P} horizon={H} seed={SEED}", flush=True)
    toto = Toto.from_pretrained(MODEL)
    try:
        cfg = toto.model_kwargs
    except Exception:
        cfg = {}
    print(f"model={MODEL} model_kwargs={cfg}", flush=True)
    try:
        import importlib.metadata as md
        print(f"toto-ts={md.version('toto-ts')}", flush=True)
    except Exception as e:
        print(f"toto-ts version unknown: {e}", flush=True)
    print(f"torch={torch.__version__} patch={toto.model.patch_embed.patch_size} "
          f"stride={toto.model.patch_embed.stride}", flush=True)
    toto.to(dev).eval()
    bb = toto.model
    stride = int(bb.patch_embed.stride)
    plen = int(bb.patch_embed.patch_size)

    bars = pd.read_parquet(HERE.parent / "oc_kronoshidden" / "bars_4h_4shift.parquet")
    res = []
    done = set()
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print("resume: groups already done", sorted(done), flush=True)
    t0 = time.time()
    last_hb = t0
    n_groups = bars[["sym", "shift"]].drop_duplicates().shape[0]
    with torch.no_grad():
        for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
            if (sym, shift) in done:
                continue
            b = b.sort_values("T").reset_index(drop=True)
            closes = b["close"].to_numpy(dtype=np.float64)
            lo = np.log(b["open"].to_numpy(dtype=np.float64))
            sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
            E = np.arange(len(b))
            E = E[(E >= P) & (b["T"].to_numpy() >= START) & np.isfinite(sig)]
            logc = np.log(np.clip(closes, 1e-12, None))
            C0 = closes[E - 1]
            sg = sig[E]
            lc0 = np.log(np.clip(C0, 1e-12, None))
            n = len(E)
            q10a = np.empty(n, dtype=np.float64)
            q50a = np.empty(n, dtype=np.float64)
            q90a = np.empty(n, dtype=np.float64)
            for i in range(0, n, B):
                e = E[i:i + B]
                ctx = np.ascontiguousarray(logc[e[:, None] + np.arange(-P, 0)], dtype=np.float32)
                s = torch.from_numpy(ctx).unsqueeze(1).to(dev)
                s = pad_array(s, stride)
                pm = pad_array(torch.ones(s.shape[0], 1, P, dtype=torch.bool, device=dev), stride)
                idm = pad_id_mask(torch.zeros(s.shape[0], 1, P, dtype=torch.int, device=dev), stride)
                tss = pad_array(torch.zeros(s.shape[0], 1, P, dtype=torch.int, device=dev), stride)
                tiv = torch.full((s.shape[0], 1), INTERVAL_S, device=dev)
                base, loc, scale = bb(inputs=s.float(), input_padding_mask=pm, id_mask=idm,
                                      kv_cache=None, scaling_prefix_length=s.shape[-1],
                                      num_exogenous_variables=0)
                distr = TotoForecaster.create_affine_transformed(base, loc, scale)
                S = replace_extreme_values(distr.sample((NSAMP,)))
                fut = S[..., -plen:]
                step0 = fut[..., 0]
                q10 = step0.quantile(0.1, dim=0).squeeze().cpu().numpy()
                q50 = step0.quantile(0.5, dim=0).squeeze().cpu().numpy()
                q90 = step0.quantile(0.9, dim=0).squeeze().cpu().numpy()
                q10a[i:i + len(e)] = np.atleast_1d(q10).astype(np.float64)
                q50a[i:i + len(e)] = np.atleast_1d(q50).astype(np.float64)
                q90a[i:i + len(e)] = np.atleast_1d(q90).astype(np.float64)
                now = time.time()
                if (i // B) % 10 == 0 or now - last_hb >= HB_S:
                    print(f"{sym} s{shift} {i + len(e)}/{n} elapsed {now - t0:.0f}s", flush=True)
                if now - last_hb >= HB_S:
                    last_hb = now
                    print(f"[hb] run_toto_4shift alive elapsed {now - t0:.0f}s", flush=True)
            df = pd.DataFrame({
                "sym": sym,
                "shift": shift,
                "T": b["T"].to_numpy()[E],
                "f_q10": (q10a - lc0) / sg,
                "f_q50": (q50a - lc0) / sg,
                "f_q90": (q90a - lc0) / sg,
                "sigma": sg,
            })
            res.append(df)
            pd.concat(res, ignore_index=True).to_parquet(OUT)  # checkpoint per (sym, shift)
            print(f"group done {(sym, shift)} n={len(df)} elapsed {time.time() - t0:.0f}s", flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} groups done "
          f"{out[['sym','shift']].drop_duplicates().shape[0]}/{n_groups} "
          f"range={out['T'].min()}..{out['T'].max()} runtime {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
