"""oc_dipdaily core: pure-numpy daily-grid dip-sleeve mechanics (FROZEN per PLAN.md 2026-10-08).

G2 parameters copied from config before any outcome:
  RUNGS=(2.5,3,3.5,4,5) (history_tm v321 R2 ladder), TP 1.0 sigma
  (engine_user m_sleeve_tp default), stop 4.0 sigma TOUCH market taker,
  stop-first on same-bar ties. Costs: maker 0.0002, taker 0.00055.
  Funding: 0.0001 per 8h settlement (00/08/16 UTC) spanned by the hold,
  charged on every exit type.
No I/O, no fits. Imported by run_dipdaily.py and tests/test_oc_dipdaily.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
M_SL = 4.0
M_TP = 1.0
LIVE_A, LIVE_B = 5, 1439  # inclusive minute offsets with a live bid
DAY_MIN = 1440
SETTLE_HOURS = (0, 8, 16)
SIG_WIN = 120
SIG_MIN = 60

# G2 per-rung size as a fraction of equity (engine_user SIZE/S_REF x D17 kd):
# (0.25/4/1.657)*1.7. D05 = x0.5, D025 = x0.25.
SIZE_G2 = (0.25 / 4.0 / 1.657) * 1.7
SIZE = {"D05": SIZE_G2 * 0.5, "D025": SIZE_G2 * 0.25}


def sigma1d_causal(opens_1d: np.ndarray) -> np.ndarray:
    """Causal daily sigma: std of last 120 daily LOG returns of daily opens.

    sg[j] = std(lr[j-120:j], ddof=1), lr[i] = ln(o[i]/o[i-1]); min 60,
    else NaN. Uses only bars strictly before day j (known at j's open).
    """
    o = np.asarray(opens_1d, dtype=float)
    n = len(o)
    lr = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = o[1:] / o[:-1]
        ok = np.isfinite(r) & (r > 0)
        lr[1:][ok] = np.log(r[ok])
    sg = pd.Series(lr).rolling(SIG_WIN, min_periods=SIG_MIN).std(ddof=1)
    return sg.shift(1).to_numpy(dtype=float)


def count_settlements(f: int, x: int) -> int:
    """Number of 00/08/16 UTC settlement timestamps with f < ts <= x.

    f, x are minute offsets from the day open (x=1440 means the next-day open).
    """
    n = 0
    for h in SETTLE_HOURS:
        ts = h * 60 if h > 0 else DAY_MIN  # 00 UTC = next-day open = offset 1440
        if f < ts <= x:
            n += 1
    return n


def day_outcomes(o0: float, O: np.ndarray, H: np.ndarray, L: np.ndarray,
                 sg: float, o_next: float) -> list:
    """One daily bar: ladder fills + TP/stop/timeout exits. Returns list of dicts.

    O/H/L: 1440 minute values (offsets 0..1439). Strict trade-through fills
    (low < bid) in minutes 5..1439 at the bid (maker). After a fill at f,
    minutes f+1..1439: stop (low <= stop, market at min(stop, open), taker)
    checked BEFORE TP (high > TP, limit at TP, maker) each minute. Open at
    minute 1440 exits at o_next (taker). ret_unit is per-notional net of fees
    and per-settlement funding (all exit types).
    """
    out: list = []
    if not (np.isfinite(o0) and o0 > 0 and np.isfinite(sg) and sg > 0
            and np.isfinite(o_next) and o_next > 0):
        return out
    O = np.asarray(O, dtype=float)
    H = np.asarray(H, dtype=float)
    L = np.asarray(L, dtype=float)
    for k in RUNGS:
        bid = o0 * (1.0 - k * sg)
        if not (np.isfinite(bid) and bid > 0):
            continue
        live = L[LIVE_A:LIVE_B + 1]
        hit = np.isfinite(live) & (live < bid)
        if not bool(hit.any()):
            continue
        f = LIVE_A + int(np.argmax(hit))
        fill = float(bid)
        stop = fill * (1.0 - M_SL * sg)
        tp = fill * (1.0 + M_TP * sg)
        lo = L[f + 1:DAY_MIN]
        hi = H[f + 1:DAY_MIN]
        op = O[f + 1:DAY_MIN]
        sh = np.isfinite(lo) & (lo <= stop)
        th = np.isfinite(hi) & (hi > tp)
        ks = (f + 1 + int(np.argmax(sh))) if bool(sh.any()) else None
        kt = (f + 1 + int(np.argmax(th))) if bool(th.any()) else None
        if ks is not None and (kt is None or ks <= kt):
            ex = float(op[ks - (f + 1)])
            if not np.isfinite(ex):
                out.append(dict(k=k, f=f, x=ks, fill=fill, exit=np.nan,
                                how="stop", ret=np.nan))
                continue
            px = stop if stop < ex else ex
            nst = count_settlements(f, ks)
            ret = px / fill - 1.0 - MAKER - TAKER - nst * FUND
            out.append(dict(k=k, f=f, x=ks, fill=fill, exit=px,
                            how="stop", ret=float(ret), nst=nst))
        elif kt is not None:
            nst = count_settlements(f, kt)
            ret = tp / fill - 1.0 - 2.0 * MAKER - nst * FUND
            out.append(dict(k=k, f=f, x=kt, fill=fill, exit=tp,
                            how="tp", ret=float(ret), nst=nst))
        else:
            nst = count_settlements(f, DAY_MIN)
            ret = (o_next / fill - 1.0 - MAKER - TAKER - nst * FUND)
            out.append(dict(k=k, f=f, x=DAY_MIN, fill=fill, exit=float(o_next),
                            how="time", ret=float(ret), nst=nst))
    return out


def pct_per_month(e_end: float, n_days: float | None = None) -> float:
    """Geometric %/month from a 1.0-based year-end equity.

    Default: 12-month norm (full 365d years). n_days given -> partial-leg norm
    100*(E^(30.4375/n_days)-1) (oc_presample2 convention).
    """
    if n_days is None:
        return float(100.0 * (float(e_end) ** (1.0 / 12.0) - 1.0))
    return float(100.0 * (float(e_end) ** (30.4375 / float(n_days)) - 1.0))


def max_dd(equity: np.ndarray) -> float:
    """Max drawdown in % of a 1.0-based equity path (NaN-safe)."""
    e = np.asarray(equity, dtype=float)
    e = e[np.isfinite(e)]
    if len(e) == 0:
        return float("nan")
    pk = np.maximum.accumulate(e)
    return float(100.0 * np.max(1.0 - e / pk))
