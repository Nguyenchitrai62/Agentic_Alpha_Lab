"""oc_downshare feature build: trailing downside-RV share per (sym, shift, T).

Frozen definitions (see PLAN.md):
  r[i]      = log(C[i]) - log(C[i-1)] (close-to-close 4h log returns; r[0] = NaN)
  D1[E]     = share(r[E-36 .. E-1])  (trailing 6d downside-RV share)
  D2[E]     = 0.6*share(r[E-6 .. E-1]) + 0.4*share(r[E-30 .. E-1])  (HAR-RS blend)
  share(rs) = sum(min(r,0)^2) / sum(r^2); NaN unless all finite and total > 0.

Causal by construction: only closes of bars closing <= T[E].
Input (read-only): research/tournament/oc_kronoshidden/bars_4h_4shift.parquet
Output: downshare_features_4shift.parquet (sym, shift, T, risk_D1, risk_D2).
CPU-only, fast (< 2 min for 20 groups).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
OUT = HERE / "downshare_features_4shift.parquet"

sys.path.insert(0, str(HERE))
from tilt_rule import WIN_D1, WIN_DAILY, WIN_WEEKLY, blend_d2, share_of  # noqa: E402


def shares_for_returns(r: np.ndarray) -> tuple:
    """Vectorised causal D1/D2 for one sorted series (r[0] = NaN)."""
    n = len(r)
    d1 = np.full(n, np.nan)
    d2 = np.full(n, np.nan)
    r2 = r * r
    neg2 = np.minimum(r, 0.0) ** 2
    # prefix sums ignoring non-finite (windows requiring all-finite checked separately)
    for e in range(n):
        if e >= WIN_D1 + 1:
            w = r[e - WIN_D1:e]
            if np.all(np.isfinite(w)):
                tot = float(np.sum(w * w))
                if tot > 0 and np.isfinite(tot):
                    d1[e] = float(np.sum(np.minimum(w, 0.0) ** 2) / tot)
        if e >= WIN_WEEKLY + 1:
            wd = r[e - WIN_DAILY:e]
            ww = r[e - WIN_WEEKLY:e]
            if np.all(np.isfinite(wd)) and np.all(np.isfinite(ww)):
                totd = float(np.sum(wd * wd))
                totw = float(np.sum(ww * ww))
                if totd > 0 and totw > 0 and np.isfinite(totd) and np.isfinite(totw):
                    sd = float(np.sum(np.minimum(wd, 0.0) ** 2) / totd)
                    sw = float(np.sum(np.minimum(ww, 0.0) ** 2) / totw)
                    d2[e] = blend_d2(sd, sw)
    return d1, d2


def main() -> None:
    t0 = time.time()
    print(f"[build_downshare {datetime.now(timezone.utc):%H:%M:%S}Z] start", flush=True)
    bars = pd.read_parquet(BARS)
    print(f"bars rows={len(bars)} range={bars['T'].min()}..{bars['T'].max()}", flush=True)
    res = []
    for (sym, shift), b in bars.groupby(["sym", "shift"], sort=True):
        b = b.sort_values("T").reset_index(drop=True)
        C = b["close"].to_numpy(dtype=float)
        lc = np.log(np.clip(C, 1e-12, None))
        r = np.empty_like(lc)
        r[0] = np.nan
        r[1:] = lc[1:] - lc[:-1]
        d1, d2 = shares_for_returns(r)
        Ttz = pd.to_datetime(b["T"], utc=True)
        df = pd.DataFrame({"sym": str(sym), "shift": int(shift),
                           "T": Ttz.values,
                           "risk_D1": d1, "risk_D2": d2})
        df["T"] = pd.to_datetime(df["T"], utc=True)
        res.append(df)
        print(f"group done {(sym, shift)} n={len(df)} "
              f"d1_cov={float(np.isfinite(d1).mean()):.4f} "
              f"d2_cov={float(np.isfinite(d2).mean()):.4f}", flush=True)
    out = pd.concat(res, ignore_index=True).sort_values(["sym", "shift", "T"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    print(f"saved {OUT} rows={len(out)} range={out['T'].min()}..{out['T'].max()} "
          f"d1_cov={float(np.isfinite(out['risk_D1']).mean()):.4f} "
          f"d2_cov={float(np.isfinite(out['risk_D2']).mean()):.4f} "
          f"elapsed={time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
