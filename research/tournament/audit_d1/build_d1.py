"""audit_d1 feature rebuild: trailing-6d downside-RV share (D1), blind independent implementation.

Frozen spec (oc_downshare PLAN.md):
  r[i] = log(C[i]) - log(C[i-1)], r[0] = NaN (float64).
  share(rs) = sum(min(r,0)^2) / sum(r^2); NaN if any non-finite, len==0,
    or total <= 0 / non-finite. share in [0,1].
  D1 at bar index E (bar open T[E]): window = r[E-36 .. E-1]; requires E >= 37
    and all 36 finite, else NaN (only closes of bars closing <= T[E]).

Source: research/tournament/oc_kronoshidden/bars_4h_4shift.parquet (read-only).
Output: research/tournament/audit_d1/downshare_D1_4shift.parquet (sym, shift, T, risk_D1).
CPU-only, fast.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
OUT = HERE / "downshare_D1_4shift.parquet"
WIN = 36


def share_of(rs: np.ndarray) -> float:
    """Pure helper: downside-RV share of a finite window (unit-tested)."""
    a = np.asarray(rs, dtype=np.float64)
    if a.size == 0:
        return float("nan")
    if not np.all(np.isfinite(a)):
        return float("nan")
    tot = float(np.sum(a * a))
    if not np.isfinite(tot) or tot <= 0:
        return float("nan")
    down = float(np.sum(np.minimum(a, 0.0) ** 2))
    return down / tot


def d1_for_group(closes: np.ndarray) -> np.ndarray:
    """Vectorized D1 for one (sym, shift) close series (sorted by T)."""
    c = np.asarray(closes, dtype=np.float64)
    n = len(c)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < WIN + 1:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        logc = np.log(c)
    r = np.empty(n, dtype=np.float64)
    r[0] = np.nan
    r[1:] = logc[1:] - logc[:-1]
    finite = np.isfinite(r)
    d2 = np.where(finite, np.minimum(np.where(finite, r, 0.0), 0.0) ** 2, 0.0)
    t2 = np.where(finite, np.where(finite, r, 0.0) ** 2, 0.0)
    f1 = finite.astype(np.int64)
    cd = np.concatenate([[0.0], np.cumsum(d2)])
    ct = np.concatenate([[0.0], np.cumsum(t2)])
    cf = np.concatenate([[0], np.cumsum(f1)])
    # window [E-WIN, E-1]: sum = c[E] - c[E-WIN]
    for E in range(WIN + 1, n):
        if cf[E] - cf[E - WIN] != WIN:
            continue
        tot = ct[E] - ct[E - WIN]
        if not np.isfinite(tot) or tot <= 0:
            continue
        down = cd[E] - cd[E - WIN]
        out[E] = down / tot
    return out


def build() -> pd.DataFrame:
    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    parts = []
    for (sym, shift), g in bars.groupby(["sym", "shift"], sort=True):
        g = g.sort_values("T").reset_index(drop=True)
        risk = d1_for_group(g["close"].to_numpy(dtype=np.float64))
        parts.append(pd.DataFrame({
            "sym": str(sym),
            "shift": int(shift),
            "T": g["T"],
            "risk_D1": risk,
        }))
        print(f"{sym} shift {shift}: rows {len(g)} nonNaN {int(np.isfinite(risk).sum())}", flush=True)
    df = pd.concat(parts, ignore_index=True).sort_values(["sym", "shift", "T"]).reset_index(drop=True)
    return df


def main():
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT} rows={len(df)} nonNaN={int(df['risk_D1'].notna().sum())}", flush=True)


if __name__ == "__main__":
    main()
