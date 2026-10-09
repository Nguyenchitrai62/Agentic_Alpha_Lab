"""oc_presampletilt: Chronos-Bolt-small inference on pre-sample 4h bars (GPU).

EXACTLY oc_chronos/run_chronos_4shift.py logic (see PLAN.md) on
bars_4h_presample.parquet (spot): per (sym, shift) context = last 512 closes
(log) ending at the bar closing at T, horizon 1, quantiles 0.1..0.9;
ch_q10 = (q10 - log C0)/sigma (same sigma formula as vol features), risk = -ch_q10
in the tilt step, not here. Deterministic heads, seed 20261007, batch 128.
Model amazon/chronos-bolt-small revision 772f3d25d38aec6d914c8949dab4462e2d46f5d8
(requested; resolved revision logged; fallback to hub default if pinned fetch fails).

Output: chronos_features_presample.parquet (sym, shift, T, ch_q10, ch_q50, ch_q90, sigma).
Resume-safe per (sym, shift) checkpoint. Heartbeat every 600 s. GPU via heavy_slot.
torch is imported BEFORE pandas (Windows DLL load order).
"""
import sys
import time
from pathlib import Path

import torch  # before pandas (Windows DLL load order)

HERE = Path(__file__).resolve().parent
PYLIB = HERE.parent / "oc_chronos" / "pylib"
sys.path.insert(0, str(PYLIB))

import numpy as np
import pandas as pd

from chronos import ChronosBoltPipeline

MODEL = "amazon/chronos-bolt-small"
REVISION = "772f3d25d38aec6d914c8949dab4462e2d46f5d8"
BARS = HERE / "bars_4h_presample.parquet"
OUT = HERE / "chronos_features_presample.parquet"
B = 128
P, H = 512, 1
HB_S = 600
dev = "cuda:0"


def main():
    torch.manual_seed(20261007)
    try:
        pipe = ChronosBoltPipeline.from_pretrained(MODEL, revision=REVISION)
        resolved = REVISION
    except Exception as e:
        print(f"pinned revision fetch failed ({e}); fallback to hub default",
              flush=True)
        pipe = ChronosBoltPipeline.from_pretrained(MODEL)
        resolved = None
    pipe.model.to(dev).eval()
    try:
        rev = pipe.model.config.revision if hasattr(pipe.model.config, "revision") else None
    except Exception:
        rev = None
    print(f"model={MODEL} requested_revision={REVISION} resolved={resolved} "
          f"config_revision={rev} quantiles={pipe.quantiles}", flush=True)
    try:
        import transformers
        print(f"transformers={transformers.__version__}", flush=True)
    except Exception as e:
        print(f"transformers version unknown: {e}", flush=True)
    import importlib.metadata as md
    try:
        print(f"chronos-forecasting={md.version('chronos-forecasting')}", flush=True)
    except Exception as e:
        print(f"chronos-forecasting version unknown: {e}", flush=True)

    bars = pd.read_parquet(BARS)
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
    for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
        if (sym, shift) in done:
            continue
        b = b.sort_values("T").reset_index(drop=True)
        closes = b["close"].to_numpy(dtype=np.float64)
        lo = np.log(np.clip(b["open"].to_numpy(dtype=np.float64), 1e-12, None))
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
        E = np.arange(len(b))
        E = E[(E >= P) & np.isfinite(sig) & np.isfinite(closes)]
        # require all 512 context closes + C0 finite
        logc = np.log(np.clip(closes, 1e-12, None))
        keep = np.isfinite(logc[E - 1])
        for k in range(1, 2):
            pass
        # vectorised context-finiteness check in batches below (skip non-finite rows)
        E = E[keep]
        C0 = closes[E - 1]
        sg = sig[E]
        # drop rows whose 512-bar context has any non-finite close
        good = []
        for e in E:
            seg = logc[e - P:e]
            good.append(bool(np.isfinite(seg).all()))
        good = np.array(good, dtype=bool)
        E, C0, sg = E[good], C0[good], sg[good]
        qs10, qs50, qs90 = [], [], []
        with torch.no_grad():
            for i in range(0, len(E), B):
                e = E[i:i + B]
                ctx = torch.from_numpy(
                    np.ascontiguousarray(logc[e[:, None] + np.arange(-P, 0)],
                                         dtype=np.float32))
                pred = pipe.predict(ctx.to(dev), prediction_length=H)
                q = pred[:, :, 0].float().cpu().numpy()
                qs10.append(q[:, 0])
                qs50.append(q[:, 4])
                qs90.append(q[:, 8])
                now = time.time()
                if (i // B) % 10 == 0 or now - last_hb >= HB_S:
                    print(f"{sym} s{shift} {i + len(e)}/{len(E)} elapsed {now - t0:.0f}s",
                          flush=True)
                if now - last_hb >= HB_S:
                    last_hb = now
                    print(f"[hb] run_chronos_presample alive elapsed {now - t0:.0f}s",
                          flush=True)
        q10 = np.concatenate(qs10) if qs10 else np.empty(0)
        q50 = np.concatenate(qs50) if qs50 else np.empty(0)
        q90 = np.concatenate(qs90) if qs90 else np.empty(0)
        lc0 = np.log(np.clip(C0, 1e-12, None))
        df = pd.DataFrame({
            "sym": sym,
            "shift": shift,
            "T": b["T"].to_numpy()[E],
            "ch_q10": (q10 - lc0) / sg,
            "ch_q50": (q50 - lc0) / sg,
            "ch_q90": (q90 - lc0) / sg,
            "sigma": sg,
        })
        res.append(df)
        pd.concat(res, ignore_index=True).to_parquet(OUT)
        print(f"group done {(sym, shift)} n={len(df)} elapsed {time.time() - t0:.0f}s",
              flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} groups "
          f"{out[['sym', 'shift']].drop_duplicates().shape[0]}/{n_groups} "
          f"range={out['T'].min()}..{out['T'].max()} runtime {time.time() - t0:.0f}s",
          flush=True)


if __name__ == "__main__":
    main()
