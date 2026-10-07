"""oc_btclead core: correlation count, BTC-lead dynamic level, D0-from-fill exit.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #41).
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the timeout exit is at a settling bar open.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
BTC_K = 1.5
DEEP_K = 0.5
BETA_WIN = 180
BETA_MIN = 60
BETA_LO, BETA_HI = 0.0, 3.0


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W).

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) sg_b(T).
    Returns int array (W,) with values 0..4. NaN open/sigma/close -> no
    detection (conservative). Flush at exactly 2.5 sigma counts (<=).
    """
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def btc_drop_vector(c_btc_win: np.ndarray, o_btc: float, sg_btc: float) -> np.ndarray:
    """BTC drop in sigma units per live minute: (O - C(m-1)) / (O*sg).

    Positive when down. NaN where inputs missing/invalid. Length W.
    """
    c = np.asarray(c_btc_win, dtype=float)
    s = np.full(c.shape, np.nan, dtype=float)
    if not (np.isfinite(o_btc) and np.isfinite(sg_btc)) or o_btc <= 0 or sg_btc <= 0:
        return s
    denom = o_btc * sg_btc
    if not np.isfinite(denom) or denom <= 0:
        return s
    ok = np.isfinite(c)
    s[ok] = (o_btc - c[ok]) / denom
    return s


def beta_clip(beta: float) -> float:
    """Walk-forward beta fallback + clip: NaN/non-finite -> 1.0, else [0, 3]."""
    b = float(beta)
    if not np.isfinite(b):
        return 1.0
    if b < BETA_LO:
        return BETA_LO
    if b > BETA_HI:
        return BETA_HI
    return b


def compute_beta_series(o_alt: np.ndarray, o_btc: np.ndarray,
                        window: int = BETA_WIN, min_periods: int = BETA_MIN) -> np.ndarray:
    """Walk-forward OLS beta of alt 4h-open returns on BTC 4h-open returns.

    o_alt, o_btc: (nb,) 4h bar opens. Returns r[j] = O[j]/O[j-1]-1.
    beta[j] uses paired returns over indices [j-window, j-1] (strictly before
    bar j). min_periods finite pairs required; Var(BTC) <= 0 -> NaN.
    Raw (unclipped); clip at use time via beta_clip.
    """
    n = len(o_alt)
    beta = np.full(n, np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        denom_a = np.where(o_alt[:-1] == 0, np.nan, o_alt[:-1])
        denom_b = np.where(o_btc[:-1] == 0, np.nan, o_btc[:-1])
        ra = o_alt[1:] / denom_a - 1
        rb = o_btc[1:] / denom_b - 1
    # ra/rb length n-1, index j-1 <-> bar j. For bar j, need returns j-window..j-1
    # in bar-return indexing, i.e. ra indices (j-window-1)..(j-2) in 0-based ra array.
    for j in range(n):
        lo = j - window
        hi = j - 1
        # return for bar b lives at ra[b-1]; want b in [max(lo,1), hi]
        b_lo = max(lo, 1)
        b_hi = hi
        if b_hi < b_lo:
            continue
        xa = ra[b_lo - 1:b_hi]  # ra index b-1
        xb = rb[b_lo - 1:b_hi]
        ok = np.isfinite(xa) & np.isfinite(xb)
        if int(ok.sum()) < min_periods:
            continue
        xa, xb = xa[ok], xb[ok]
        vb = float(((xb - xb.mean()) ** 2).sum() / (len(xb) - 1)) if len(xb) > 1 else np.nan
        if not np.isfinite(vb) or vb <= 0:
            continue
        cov = float(((xa - xa.mean()) * (xb - xb.mean())).sum() / (len(xa) - 1))
        beta[j] = cov / vb
    return beta


def lead_level_vector(lv: float, sg_alt: float, beta: float,
                      s_btc: np.ndarray, alt_close_win: np.ndarray) -> np.ndarray:
    """BTC-lead bid level in force per live minute (length W).

    L(m) = lv*(1 - 0.5*beta_clip*s(m)*sg_alt) when (s>=1.5 AND alt close > lv
    AND all finite AND L in (0, lv)), else lv. Never above lv.
    """
    s = np.asarray(s_btc, dtype=float)
    ca = np.asarray(alt_close_win, dtype=float)
    W = s.shape[0]
    lvl = np.full(W, lv, dtype=float)
    if not (np.isfinite(lv) and np.isfinite(sg_alt)) or lv <= 0 or sg_alt <= 0:
        return lvl
    b = beta_clip(beta)
    if not np.isfinite(b) or b <= 0:
        # beta 0 -> no shift (L would equal lv anyway); keep lv
        return lvl
    gate = (np.isfinite(s) & (s >= BTC_K)
            & np.isfinite(ca) & (ca > lv))
    if gate.any():
        deep = lv * (1 - DEEP_K * b * s[gate] * sg_alt)
        ok = np.isfinite(deep) & (deep > 0) & (deep < lv)
        idx = np.where(gate)[0][ok]
        lvl[idx] = deep[ok]
    return lvl


def size_mult(n_fill: int) -> float:
    """B1 size multiplier kept for both arms: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level_win: np.ndarray):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < np.asarray(level_win, dtype=float)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the ACTUAL fill price px.

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first (same as oc_dipexit D0 / v293 / oc_b1deeper).
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        fill_px = bl if ox > bl else ox  # min(bl, open): gap pays the open
        return (fill_px / px - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / px - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            ex, x = float(Oa[km + 1]), km + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "stop")
        ret = ex / px - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    return (float(o2) / px - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time")
