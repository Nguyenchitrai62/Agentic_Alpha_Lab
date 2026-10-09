"""oc_presampletilt: causal RV6 + frozen-GARCH risk features on pre-sample 4h bars.

Frozen definitions (see PLAN.md, EXACT oc_voltilt replica except the GARCH params
are the FROZEN anchor-2021 fits for every year):
  r[i]     = log(C[i]) - log(C[i-1)]
  sig[E]   = rolling(360).std(ddof=1) of diff(log(open)) at E
  RV6[E]   = std(ddof=1) of r[E-6..E-1] (= r.rolling(6).std().shift(1))
  risk_RV6 = RV6 / sig
  GARCH(1,1) zero-mean filter with the frozen anchor-2021 (omega, alpha, beta, v0)
  per sym from oc_voltilt/garch_params.json (copied verbatim into FROZEN_GARCH);
  var[0] = unconditional, E>=1 uses only r[E-1] and earlier (non-finite -> 0.0,
  exactly as oc_voltilt.garch_filter); risk_GARCH = sqrt(var)/sig, E<360 -> NaN.

Output: vol_features_presample.parquet (sym, shift, T, sigma, risk_RV6, risk_GARCH).
CPU-only. Heartbeat every 600 s.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BARS = HERE / "bars_4h_presample.parquet"
OUT = HERE / "vol_features_presample.parquet"

# Frozen anchor-2021 GARCH params (verbatim from oc_voltilt/garch_params.json).
FROZEN_GARCH = {
    "BTCUSDT": {"omega": 2.962749661683187e-06, "alpha": 0.06526335208168146,
                "beta": 0.927825881135516, "v0": 0.00030457605407065315},
    "ETHUSDT": {"omega": 9.972397326731373e-06, "alpha": 0.06760328712823072,
                "beta": 0.9113538693053522, "v0": 0.0005169218725223849},
    "BNBUSDT": {"omega": 9.640560196328421e-06, "alpha": 0.10024750483483949,
                "beta": 0.8886495920681354, "v0": 0.0007154168357336774},
    "XRPUSDT": {"omega": 1.107902967921202e-05, "alpha": 0.1460578011936826,
                "beta": 0.8529388899901152, "v0": 0.001066255372848162},
}

HB_S = 600


def garch_filter(r: np.ndarray, om: float, al: float, be: float,
                 v0: float) -> np.ndarray:
    n = len(r)
    uncond = om / (1 - al - be) if (al + be) < 1 else v0
    var = np.empty(n)
    v = uncond if np.isfinite(uncond) and uncond > 0 else v0
    var[0] = v
    for e in range(1, n):
        x = r[e - 1]
        x = 0.0 if not np.isfinite(x) else x
        v = om + al * x * x + be * v
        var[e] = v
    return var


def main() -> None:
    t0 = time.time()
    last_hb = t0
    bars = pd.read_parquet(BARS)
    print(f"bars rows={len(bars)} range={bars['T'].min()}..{bars['T'].max()}",
          flush=True)
    res = []
    done: set = set()
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print("resume: groups already done", sorted(done), flush=True)
    for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
        if (sym, shift) in done:
            continue
        b = b.sort_values("T").reset_index(drop=True)
        T = b["T"].to_numpy()
        O = b["open"].to_numpy(dtype=float)
        C = b["close"].to_numpy(dtype=float)
        lo = np.log(np.clip(O, 1e-12, None))
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
        lc = np.log(np.clip(C, 1e-12, None))
        r = np.empty_like(lc)
        r[0] = np.nan
        r[1:] = lc[1:] - lc[:-1]
        rv6 = pd.Series(r).rolling(6).std().shift(1).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            risk_rv6 = rv6 / sig
        risk_rv6[~(np.isfinite(rv6) & np.isfinite(sig) & (sig > 0))] = np.nan
        f = FROZEN_GARCH[str(sym)]
        var = garch_filter(r, f["omega"], f["alpha"], f["beta"], f["v0"])
        sg = np.sqrt(var)
        sg[np.arange(len(b)) < 360] = np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            risk_g = sg / sig
        risk_g[~(np.isfinite(sg) & np.isfinite(sig) & (sig > 0))] = np.nan
        df = pd.DataFrame({"sym": sym, "shift": shift, "T": T, "sigma": sig,
                           "risk_RV6": risk_rv6, "risk_GARCH": risk_g})
        df = df[np.isfinite(df["sigma"].to_numpy())].reset_index(drop=True)
        res.append(df)
        pd.concat(res, ignore_index=True).to_parquet(OUT)
        print(f"group done {(sym, shift)} n={len(df)} "
              f"rv6_cov={float(np.isfinite(df['risk_RV6']).mean()):.4f} "
              f"g_cov={float(np.isfinite(df['risk_GARCH']).mean()):.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_vol_presample alive elapsed {last_hb - t0:.0f}s",
                  flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} range={out['T'].min()}..{out['T'].max()} "
          f"runtime {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
