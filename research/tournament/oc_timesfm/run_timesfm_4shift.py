"""Zero-shot TimesFM-2.5 forecasts on FOUR 4h clock shifts (settings = oc_timesfm/PLAN.md Part A).

For each majors coin, each clock shift s = 0..3 (4h bars from
oc_kronoshidden/bars_4h_4shift.parquet), each bar open T: context = the last
512 closes of that shift's bars ending at the bar closing at T (log prices,
raw log values; model-side scaling via ForecastConfig normalize_inputs=True),
forecast horizon 1 bar. Quantile forecasts q10/q50/q90 of the next close from
TimesFM 2.5 continuous quantile head (deterministic given weights):
  f_q10 = (q10 - log C0) / sigma, f_q50 likewise (f_q90 stored too),
  sigma = std of the last 360 4h log returns (SAME formula as Kronos' sigma:
  std of diff(log(open)) rolling 360), C0 = close of the bar closing at T,
  risk = -f_q10 (in tilt_rule / make_fits, not here).

Forecast for bar open T uses ONLY closes of bars closing <= T on that shift's
grid (bars e-512..e-1 for the bar at index e). Output:
timesfm_features_4shift.parquet (sym, shift, T, f_q10, f_q50, f_q90, sigma).

Resume-safe: checkpoint per (sym, shift) group to the parquet; finished groups
are skipped. Heartbeat print every 600 s.

Usage: python run_timesfm_4shift.py [out_name] [batch]
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

import timesfm

MODEL = "google/timesfm-2.5-200m-pytorch"
OUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "timesfm_features_4shift.parquet")
B = int(sys.argv[2]) if len(sys.argv) > 2 else 64
P, H = 512, 1
START = pd.Timestamp("2020-08-01", tz="UTC")
HB_S = 600


def main():
    torch.manual_seed(20261008)
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(MODEL, torch_compile=False)
    fc = timesfm.ForecastConfig(
        max_context=P,
        max_horizon=H,
        normalize_inputs=True,
        per_core_batch_size=32,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    )
    model.compile(fc)
    print(f"model={MODEL} ctx={P} horizon={H} batch={B} "
          f"device={model.model.device} quant_head={fc.use_continuous_quantile_head}",
          flush=True)
    try:
        import importlib.metadata as md
        print(f"timesfm={md.version('timesfm')}", flush=True)
    except Exception as e:
        print(f"timesfm version unknown: {e}", flush=True)

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
            logc = np.log(np.clip(closes, 1e-12, None)).astype(np.float64)
            C0 = closes[E - 1]
            sg = sig[E]
            qs10, qs50, qs90 = [], [], []
            for i in range(0, len(E), B):
                e = E[i:i + B]
                ctx = [np.ascontiguousarray(logc[k - P:k], dtype=np.float32)
                       for k in e]
                _, quant = model.forecast(horizon=H, inputs=ctx)
                # quant shape (b, H, 10) = [mean, q10..q90]
                q = np.asarray(quant, dtype=np.float64)
                qs10.append(q[:, 0, 1])
                qs50.append(q[:, 0, 5])
                qs90.append(q[:, 0, 9])
                now = time.time()
                if (i // B) % 10 == 0 or now - last_hb >= HB_S:
                    print(f"{sym} s{shift} {i + len(e)}/{len(E)} elapsed {now - t0:.0f}s",
                          flush=True)
                if now - last_hb >= HB_S:
                    last_hb = now
                    print(f"[hb] run_timesfm_4shift alive elapsed {now - t0:.0f}s",
                          flush=True)
            q10 = np.concatenate(qs10) if qs10 else np.empty(0)
            q50 = np.concatenate(qs50) if qs50 else np.empty(0)
            q90 = np.concatenate(qs90) if qs90 else np.empty(0)
            lc0 = np.log(np.clip(C0, 1e-12, None))
            df = pd.DataFrame({
                "sym": sym,
                "shift": shift,
                "T": b["T"].to_numpy()[E],
                "f_q10": (q10 - lc0) / sg,
                "f_q50": (q50 - lc0) / sg,
                "f_q90": (q90 - lc0) / sg,
                "sigma": sg,
            })
            res.append(df)
            pd.concat(res, ignore_index=True).to_parquet(OUT)  # checkpoint per (sym, shift)
            print(f"group done {(sym, shift)} n={len(df)} elapsed {time.time() - t0:.0f}s",
                  flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} groups done "
          f"{out[['sym','shift']].drop_duplicates().shape[0]}/{n_groups} "
          f"range={out['T'].min()}..{out['T'].max()} runtime {time.time() - t0:.0f}s",
          flush=True)


if __name__ == "__main__":
    main()
