"""oc_voltilt Part-A: causal realised-vol + GARCH(1,1) risk features on 4 shifts.

Frozen definitions (see PLAN.md):
  r[i]      = log(C[i]) - log(C[i-1)] (close-to-close 4h log returns)
  sig[E]    = rolling(360).std(ddof=1) of diff(log(open)) at E  (== Chronos sigma)
  RV6[E]    = std(ddof=1) of r[E-6 .. E-1]  (== r.rolling(6).std().shift(1))
  risk_RV6  = RV6 / sig
  GARCH(1,1) zero-mean: var[t] = omega + alpha*r[t-1]^2 + beta*var[t-1],
    fitted per (anchor, sym) by normal MLE (scipy L-BFGS-B) on the SHIFT-0
    series with bar close (T+4h) <= A - 7d; filter runs causally with the
    anchor-of-the-year params; risk_GARCH = sqrt(var_T) / sig (E >= 360).

Output: vol_features_4shift.parquet (sym, shift, T, sigma, risk_RV6, risk_GARCH)
  + garch_params.json. CPU-only. Resume-safe (fits cached; filter checkpoint
  per (sym, shift)). Heartbeat every 600 s.

Usage: python build_vol_features.py   (CPU-only; heavy_slot if RAM is tight)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
OUT = HERE / "vol_features_4shift.parquet"
GPATH = HERE / "garch_params.json"
TMP = HERE / "tmp"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
EMBARGO = pd.Timedelta(days=7)
HB_S = 600


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -30.0, 30.0))
    return 1.0 / (1.0 + np.exp(-x))


def unpack(u: np.ndarray) -> tuple:
    """Stationarity-by-construction: al+be <= 0.999 always (no penalty cliff)."""
    om = float(np.exp(u[0]))
    s1, s2 = float(_sigmoid(u[1])), float(_sigmoid(u[2]))
    al = 0.999 * s1
    be = 0.999 * (1.0 - s1) * s2
    return om, al, be


def garch_nll(u: np.ndarray, r: np.ndarray, v0: float) -> float:
    """Negative log-lik (zero-mean normal); params stationary by construction.

    Timing: r[t] is evaluated under the forecast variance v[t] (past only),
    then v[t+1] is updated with r[t]. (A prior version evaluated r[t] under
    the contemporaneous update — fixed pre-outcome; see PLAN post-hoc log.)
    """
    om, al, be = unpack(u)
    v = v0
    s = 0.0
    for x in r:
        if not np.isfinite(v) or v <= 0:
            return 1e12
        s += np.log(v) + x * x / v
        v = om + al * x * x + be * v
    return 0.5 * (len(r) * np.log(2 * np.pi) + s)


def fit_garch(r: np.ndarray) -> dict:
    """MLE for one (anchor, sym) shift-0 return sample. Returns params + stats."""
    r = np.asarray(r, dtype=float)
    v0 = float(np.var(r))
    # init near (alpha, beta) = (0.10, 0.85): s1 = 0.1001, s2 = 0.9454
    u0 = np.array([np.log(max(v0 * 0.05, 1e-12)), -2.197, 2.85])
    res = minimize(garch_nll, u0, args=(r, v0), method="L-BFGS-B",
                   options={"maxiter": 500})
    om, al, be = unpack(np.asarray(res.x, dtype=float))
    return dict(omega=om, alpha=al, beta=be, v0=v0,
                n_obs=int(len(r)), negloglik=float(res.fun),
                success=bool(res.success))


def garch_filter(r: np.ndarray, om: float, al: float, be: float,
                 v0: float) -> np.ndarray:
    """Causal one-step forecast variance var_T[E] for each bar index E.

    var_T[0] = unconditional variance; for E >= 1 the forecast for the bar
    opening at T[E] uses only r[1..E-1] (returns of bars closing <= T[E]).
    """
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
    TMP.mkdir(parents=True, exist_ok=True)
    bars = pd.read_parquet(BARS)
    print(f"bars rows={len(bars)} range={bars['T'].min()}..{bars['T'].max()}",
          flush=True)

    # ---- GARCH fits per (anchor, sym) on shift-0, bar close <= A - 7d ----
    if GPATH.exists():
        gparams = json.loads(GPATH.read_text())
        print(f"reuse {GPATH} ({len(gparams)} fits)", flush=True)
    else:
        gparams = {}
        b0 = bars[bars["shift"] == 0].copy()
        for a in ANCH5:
            A = pd.Timestamp(a, tz="UTC")
            cutoff = A - EMBARGO  # bar close time must be <= cutoff
            for sym, g in b0.groupby("sym"):
                g = g.sort_values("T").reset_index(drop=True)
                close_time = g["T"] + pd.Timedelta(hours=4)
                m = (close_time <= cutoff).to_numpy()
                lc = np.log(g["close"].to_numpy(dtype=float))
                rr = np.empty_like(lc)
                rr[0] = np.nan
                rr[1:] = lc[1:] - lc[:-1]
                sample = rr[m]
                sample = sample[np.isfinite(sample)]
                assert len(sample) > 500, (a, sym, len(sample))
                f = fit_garch(sample)
                f.update(dict(sym=str(sym), anchor=a,
                              fit_close_end=str(cutoff)))
                gparams[f"{a}|{sym}"] = f
                print(f"fit {a} {sym}: om={f['omega']:.3e} al={f['alpha']:.4f} "
                      f"be={f['beta']:.4f} n={f['n_obs']} "
                      f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        GPATH.write_text(json.dumps(gparams, indent=1))
        print(f"saved {GPATH}", flush=True)

    # ---- per (sym, shift) filter + RV6 + sigma ----
    done: set = set()
    res = []
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print("resume: groups already done", sorted(done), flush=True)
    anch_ts = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
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

        # GARCH filter with anchor-of-the-year params (same sym)
        E = np.arange(len(b))
        y_of = np.clip(np.searchsorted(
            np.array([a.value for a in anch_ts]),
            pd.to_datetime(b["T"], utc=True).values.astype(np.int64),
            side="right") - 1, 0, 4)
        sg = np.full(len(b), np.nan)
        for y in range(5):
            f = gparams[f"{ANCH5[y]}|{sym}"]
            var = garch_filter(r, f["omega"], f["alpha"], f["beta"], f["v0"])
            m = y_of == y
            sg[m] = np.sqrt(var[m])
        sg[E < 360] = np.nan  # burn-in (same availability as sigma)
        with np.errstate(divide="ignore", invalid="ignore"):
            risk_g = sg / sig
        risk_g[~(np.isfinite(sg) & np.isfinite(sig) & (sig > 0))] = np.nan

        df = pd.DataFrame({"sym": sym, "shift": shift, "T": T, "sigma": sig,
                           "risk_RV6": risk_rv6, "risk_GARCH": risk_g})
        # keep only rows with sigma (same availability gate as Chronos sigma)
        df = df[np.isfinite(df["sigma"].to_numpy())].reset_index(drop=True)
        res.append(df)
        pd.concat(res, ignore_index=True).to_parquet(OUT)
        print(f"group done {(sym, shift)} n={len(df)} "
              f"rv6_cov={float(np.isfinite(df['risk_RV6']).mean()):.4f} "
              f"g_cov={float(np.isfinite(df['risk_GARCH']).mean()):.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_vol_features alive elapsed "
                  f"{last_hb - t0:.0f}s", flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} "
          f"range={out['T'].min()}..{out['T'].max()} "
          f"runtime {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
