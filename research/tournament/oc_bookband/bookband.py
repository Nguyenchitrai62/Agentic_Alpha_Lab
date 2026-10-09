"""oc_bookband: no-trade band on book target changes (PLAN frozen 2026-10-08).

Pure helpers, no I/O, no fits, no test-year statistics. All thresholds frozen
ex-ante: p in {0.10, 0.25}, trailing window 540 4h bars (90d), min_periods 120.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
WINDOW = 540          # 90d of 4h bars
MIN_PERIODS = 120
EPS_TYP = 1e-12


def trailing_typical(T: pd.DataFrame) -> pd.DataFrame:
    """Trailing-90d mean |T| per coin, strictly-before-t (causal).

    typ[t,s] = mean(|T[k,s]| for k in [t-540, t-1]); min 120 bars else mean of
    all available strictly-before-t bars; NaN where no history / non-finite.
    """
    absT = T.abs()
    # shift(1) makes the window strictly before t; rolling min_periods=MIN_PERIODS
    # gives NaN when <120 bars available -> fall back to expanding mean below.
    rolled = absT.shift(1).rolling(WINDOW, min_periods=MIN_PERIODS).mean()
    need = rolled.isna()
    if bool(need.any().any()):
        expand = absT.shift(1).expanding(min_periods=1).mean()
        rolled = rolled.where(~need, expand)
    return rolled


def apply_band(T: pd.DataFrame, typ: pd.DataFrame, p: float) -> pd.DataFrame:
    """No-trade-band filter F of target T (sequential, causal, per coin).

    F[0,s]=T[0,s]. For t>0 with prev=F[t-1,s], cur=T[t,s]:
      flip bypass if prev!=0 and cur!=0 and sign differs -> cur;
      else if typ active (finite and >1e-12) and |cur-prev| <= p*typ -> prev;
      else cur. Exact-0.0 tolerance (no epsilon band on zero).
    """
    tvals = T.to_numpy(dtype=float)
    yvals = typ.to_numpy(dtype=float)
    n, m = tvals.shape
    F = np.empty_like(tvals)
    F[0] = tvals[0]
    for i in range(1, n):
        for j in range(m):
            prev = F[i - 1, j]
            cur = tvals[i, j]
            if prev != 0.0 and cur != 0.0 and np.sign(cur) != np.sign(prev):
                F[i, j] = cur
                continue
            ty = yvals[i, j]
            if np.isfinite(ty) and ty > EPS_TYP and abs(cur - prev) <= p * ty:
                F[i, j] = prev
            else:
                F[i, j] = cur
    return pd.DataFrame(F, index=T.index, columns=T.columns)


def turnover_frame(T: pd.DataFrame, typ: pd.DataFrame, fwd1: pd.DataFrame,
                   p_list: tuple = (0.10, 0.25),
                   fee_rate: float = 0.0002) -> dict:
    """Descriptive turnover/P&L split per p (4h open-to-open proxy, disclosed).

    d[t]=T[t]-T[t-1] (first vs 0); small_p iff band active and |d|<=p*typ.
    gross_total=sum T*fwd1; gross_small=sum_{small} d*fwd1 (marginal increment);
    fee=turnover*fee_rate. All sums skip NaN fwd1 rows.
    """
    res: dict = {}
    d = T.diff().fillna(T)  # first bar vs 0
    valid = fwd1.notna().all(axis=1)
    Tv, dv, fv = T[valid], d[valid], fwd1[valid]
    typv = typ[valid]
    gross_total = float((Tv * fv).sum().sum())
    to_total = float(dv.abs().sum().sum())
    out_ps: dict = {}
    for p in p_list:
        active = typv.notna() & (typv > EPS_TYP)
        small = active & (dv.abs() <= p * typv)
        small = small.fillna(False)
        to_s = float(dv[small].abs().sum().sum())
        n_nonzero = int(((dv != 0.0) & active).sum().sum())
        n_small = int(small.sum().sum())
        gross_s = float((dv[small] * fv[small]).sum().sum())
        out_ps[str(p)] = dict(
            n_nonzero=int(n_nonzero), n_small=int(n_small),
            count_share=(round(n_small / n_nonzero, 6) if n_nonzero else None),
            turnover_small=round(to_s, 6),
            turnover_share=(round(to_s / to_total, 6) if to_total else None),
            fee_small=round(to_s * fee_rate, 6),
            gross_small=round(gross_s, 6),
            net_small=round(gross_s - to_s * fee_rate, 6),
        )
    res = dict(gross_total=round(gross_total, 6), turnover_total=round(to_total, 6),
               fee_total=round(to_total * fee_rate, 6),
               net_total=round(gross_total - to_total * fee_rate, 6),
               per_p=out_ps)
    return res
