"""Pooled BOOK-trade experience for any coin (v300): what happens to a book-style trade in direction d opened at a 4h decision.

For holding bar j of a coin (4h bars from v293.Asset, sigma_4h = Asset.sig as in engine_user) and each direction d in {+1, -1}:
  entry  resting limit at open_j x (1 - d x max(0.001, 0.25 sigma_4h)) (the G2 order, k_off 0.25), filled only on a 1m trade-through
         from minute 5 of bar j (maker 0.0002); no fill -> no sample.
  exits  on 1h bars after the fill hour, stop-first inside an hour: stop-loss at entry x (1 - d 4 sigma_d) (taker 0.00055; a gap through
         the stop fills at the hour open), break-even move after +2 sigma_d (stop -> entry x (1 + d 0.001)), take-profit at
         entry x (1 + d 8 sigma_d) (maker), else a time exit at the open 48 hours after the fill hour (taker) - sigma_d = sigma_4h sqrt 6,
         the engine's book stop structure (m_sl 4, TP 2 m_sl, be_k 2).
  funding longs pay 0.0001 per 00 / 08 / 16 UTC settlement held.
  label  y = d (exit / entry - 1) - fees - funding.
Features known at the decision (the open of bar j; 1m data up to the minute before it), signed by d so one model covers both sides:
  x0 d trend42 (Asset.trend), x1 d trend180, x2 volreg, x3 efficiency ratio of the last 42 4h opens (|net move| / path length),
  x4 distance from the favourable 24h extreme / sigma_4h (long: log(close / 24h high), short: -log(close / 24h low)), x5 d BTC trend42,
  x6 BTC volreg, x7 hour of the decision.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
HOLD_H = 48


def hourly(A):
    n = len(A.O) // 60
    O = A.O[: n * 60].reshape(n, 60)[:, 0]
    H = np.nanmax(A.H[: n * 60].reshape(n, 60), axis=1)
    L = np.nanmin(A.L[: n * 60].reshape(n, 60), axis=1)
    return O, H, L


def asset_extras(A):
    o = pd.Series(A.o)
    trend180 = ((np.log(o) - np.log(o.shift(180))) / (pd.Series(A.sig) * np.sqrt(180))).to_numpy()
    lr = np.log(o).diff()
    er = (np.log(o) - np.log(o.shift(42))).abs() / lr.abs().rolling(42).sum()
    lmin24 = pd.Series(A.L).rolling(1440, min_periods=720).min().to_numpy()
    return trend180, er.to_numpy(), lmin24


def decision_features(A, ex, btc, j, d):
    trend180, er, lmin24 = ex
    k = j * 240 - 1                       # close of the last minute before the decision
    sg = A.sig[j]
    c = A.C[k]
    fav = np.log(c / A.hmax24[k]) / sg if d > 0 else -np.log(c / lmin24[k]) / sg
    return [d * A.trend[j], d * trend180[j], A.volreg[j], er[j], fav, d * btc.trend[j], btc.volreg[j], A.t0[j].hour]


def experience(A, btc, t_min=None):
    """All book-trade samples of one coin -> DataFrame (t = decision time, t_exit, d, x0..x7, y)."""
    ex = asset_extras(A)
    Oh, Hh, Lh = hourly(A)
    nh = len(Oh)
    rows = []
    for j in range(200, A.nb - 13):
        sg, o0 = A.sig[j], A.o[j]
        if not (np.isfinite(sg) and sg > 0 and np.isfinite(o0)) or not np.isfinite(A.trend[j]):
            continue
        if t_min is not None and A.t0[j] < t_min:
            continue
        sd = sg * np.sqrt(6)
        for d in (1, -1):
            px = o0 * (1 - d * max(0.001, 0.25 * sg))
            seg = A.L[j * 240 + 5: j * 240 + 240] if d > 0 else A.H[j * 240 + 5: j * 240 + 240]
            hit = (seg < px) if d > 0 else (seg > px)
            if not np.any(hit):
                continue
            fmin = j * 240 + 5 + int(np.argmax(hit))
            h0 = fmin // 60 + 1
            if h0 + HOLD_H >= nh:
                continue
            sl, be_trig, tp = px * (1 - d * 4 * sd), px * (1 + d * 2 * sd), px * (1 + d * 8 * sd)
            be = False
            ex_px, ex_h, kind = Oh[h0 + HOLD_H], h0 + HOLD_H, "time"
            for h in range(h0, h0 + HOLD_H):
                o_, hi, lo = Oh[h], Hh[h], Lh[h]
                if not (np.isfinite(o_) and np.isfinite(hi) and np.isfinite(lo)):
                    continue
                adverse = lo if d > 0 else hi
                favor = hi if d > 0 else lo
                if (d > 0 and o_ <= sl) or (d < 0 and o_ >= sl):
                    ex_px, ex_h, kind = o_, h, "stop"
                    break
                if (d > 0 and adverse <= sl) or (d < 0 and adverse >= sl):
                    ex_px, ex_h, kind = sl, h, "stop"
                    break
                if (d > 0 and favor > tp) or (d < 0 and favor < tp):
                    ex_px, ex_h, kind = tp, h, "tp"
                    break
                if not be and ((d > 0 and favor >= be_trig) or (d < 0 and favor <= be_trig)):
                    be, sl = True, px * (1 + d * 0.001)
            if not np.isfinite(ex_px):
                continue
            t_fill = A.t0[0] + pd.Timedelta(minutes=int(fmin))
            t_exit = A.t0[0] + pd.Timedelta(hours=int(ex_h))
            n_fund = sum(1 for hh in pd.date_range(t_fill.ceil("h"), t_exit, freq="h") if hh.hour in (0, 8, 16)) if d > 0 else 0
            fee = MAKER + (MAKER if kind == "tp" else TAKER)
            y = d * (ex_px / px - 1) - fee - FUND * n_fund
            x = decision_features(A, ex, btc, j, d)
            rows.append([A.t0[j], t_exit, d, *x, y])
    return pd.DataFrame(rows, columns=["t", "t_exit", "d"] + [f"x{q}" for q in range(8)] + ["y"])
