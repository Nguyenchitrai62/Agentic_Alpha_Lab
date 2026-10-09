"""oc_dip1h core: pure-numpy 1h dip-sleeve mechanics (FROZEN per PLAN.md 2026-10-08).

G2 parameters copied from config before any outcome:
  RUNGS=(2.5,3,3.5,4,5) (history_tm v321 R2 ladder), TP 1.0 sigma
  (engine_user m_sleeve_tp default), stop 4.0 sigma TOUCH market taker,
  stop-first on same-bar ties. Costs: maker 0.0002, taker 0.00055,
  funding 0.0001 on timeout exits at settling opens (00/08/16 UTC).
No I/O, no fits. Imported by run_dip1h.py and tests/test_oc_dip1h.py.
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
LIVE_A, LIVE_B = 5, 59  # inclusive minute offsets with a live bid
SETTLE_HOURS = (0, 8, 16)
SIG_WIN = 720
SIG_MIN = 120

# G2 per-rung size as a fraction of equity (engine_user SIZE/S_REF x D17 kd):
# (0.25/4/1.657)*1.7. H05 = x0.5, H025 = x0.25.
SIZE_G2 = (0.25 / 4.0 / 1.657) * 1.7
SIZE = {"H05": SIZE_G2 * 0.5, "H025": SIZE_G2 * 0.25}


def sigma1h_causal(opens_1h: np.ndarray) -> np.ndarray:
    """Causal hourly sigma: std of last 720 hourly LOG returns of 1h opens.

    sg[j] = std(lr[j-720:j], ddof=1), lr[i] = ln(o[i]/o[i-1]); min 120,
    else NaN. Uses only bars strictly before bar j (known at j's open).
    """
    o = np.asarray(opens_1h, dtype=float)
    n = len(o)
    lr = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = o[1:] / o[:-1]
        ok = np.isfinite(r) & (r > 0)
        lr[1:][ok] = np.log(r[ok])
    sg = pd.Series(lr).rolling(SIG_WIN, min_periods=SIG_MIN).std(ddof=1)
    return sg.shift(1).to_numpy(dtype=float)


def bar_outcomes(o0: float, O: np.ndarray, H: np.ndarray, L: np.ndarray,
                 sg: float, o_next: float, settle_timeout: bool) -> list:
    """One 1h bar: ladder fills + TP/stop/timeout exits. Returns list of dicts.

    O/H/L: 60 minute values (offsets 0..59). Strict trade-through fills
    (low < bid) in minutes 5..59 at the bid (maker). After a fill at f,
    minutes f+1..59: stop (low <= stop, market at min(stop, open), taker)
    checked BEFORE TP (high > TP, limit at TP, maker) each minute. Open at
    minute 60 exits at o_next (taker). ret_unit is per-notional net of fees
    and (timeout only) funding.
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
        lo = L[f + 1:60]
        hi = H[f + 1:60]
        op = O[f + 1:60]
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
            ret = px / fill - 1.0 - MAKER - TAKER
            out.append(dict(k=k, f=f, x=ks, fill=fill, exit=px,
                            how="stop", ret=float(ret)))
        elif kt is not None:
            ret = tp / fill - 1.0 - 2.0 * MAKER
            out.append(dict(k=k, f=f, x=kt, fill=fill, exit=tp,
                            how="tp", ret=float(ret)))
        else:
            ret = (o_next / fill - 1.0 - MAKER - TAKER
                   - (FUND if settle_timeout else 0.0))
            out.append(dict(k=k, f=f, x=60, fill=fill, exit=float(o_next),
                            how="time", ret=float(ret)))
    return out


def pct_per_month(e_end: float) -> float:
    """Geometric %/month from a 1.0-based year-end equity (12-month norm)."""
    return float(100.0 * (float(e_end) ** (1.0 / 12.0) - 1.0))


def max_dd(equity: np.ndarray) -> float:
    """Max drawdown in % of a 1.0-based equity path (NaN-safe)."""
    e = np.asarray(equity, dtype=float)
    e = e[np.isfinite(e)]
    if len(e) == 0:
        return float("nan")
    pk = np.maximum.accumulate(e)
    return float(100.0 * np.max(1.0 - e / pk))
