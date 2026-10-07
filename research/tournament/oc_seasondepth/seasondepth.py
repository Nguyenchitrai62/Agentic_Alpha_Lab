"""oc_seasondepth core: seasonal-factor table, B1 sizing, D0-from-fill exits.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #70).
BASE = oc_dipexit D0 replica (v293 Asset/outcomes) + oc_b1deeper B1 sizes.
RULE = same with sigma_eff = sigma_4h * sqrt(s), TP/stops in sigma_eff units.
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
N_SLOTS = 42


def weekly_slots(idx) -> np.ndarray:
    """Weekly 4h slot q(m) in 0..41 for each minute timestamp.

    q = (((dow*24 + hour)*60 + minute) // 240) % 42, Monday = dow 0 (UTC).
    """
    dow = idx.dayofweek.to_numpy()
    hh = idx.hour.to_numpy()
    mm = idx.minute.to_numpy()
    return ((((dow * 24 + hh) * 60 + mm) // 240) % N_SLOTS).astype(np.int64)


def factor_table(C: np.ndarray, idx, anchors, win_days: int = 365) -> dict:
    """Walk-forward hour-of-week volatility factors per anchor.

    C: full-length 1m closes (float, NaN = missing). r_m = ln(C_m/C_{m-1})
    over consecutive minutes; a_m = |r_m|. For anchor A, window
    W_A = [A - win_days, A): slot mean M(A,q) = mean(a_m for m in W_A with
    q(m) = q); overall M(A) = mean over all m in W_A. s(A,q) = M(A,q)/M(A),
    fallback 1.0 when either mean is non-finite/non-positive or the slot is
    empty. Returns {anchor_iso_date: (42,) float array}.
    """
    import pandas as pd

    C = np.asarray(C, dtype=float)
    n = len(C)
    logC = np.full(n, np.nan)
    ok = np.isfinite(C) & (C > 0)
    logC[ok] = np.log(C[ok])
    a = np.full(n, np.nan)
    a[1:] = np.abs(logC[1:] - logC[:-1])  # NaN where either close missing
    q = weekly_slots(idx)
    out = {}
    for A in anchors:
        lo = A - pd.Timedelta(days=int(win_days))
        m = (idx >= lo) & (idx < A) & np.isfinite(a)
        tot = float(np.mean(a[m])) if m.any() else np.nan
        qq = q[m]
        cnt = np.bincount(qq, minlength=N_SLOTS).astype(float)
        sm = np.bincount(qq, weights=a[m].astype(float), minlength=N_SLOTS)
        with np.errstate(invalid="ignore", divide="ignore"):
            means = sm / np.where(cnt > 0, cnt, np.nan)
            s = means / tot
        s = np.where(np.isfinite(s) & (s > 0), s, 1.0)
        out[A.date().isoformat()] = s.astype(float)
    return out


def sigma_eff(sg: float, s: float) -> float:
    """Effective sigma with fixed 1/2 shrinkage; s fallback -> sg."""
    if not (np.isfinite(s) and s > 0):
        return float(sg)
    return float(sg) * float(np.sqrt(s))


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W), v399-exact.

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) BASE sg_b(T).
    Returns int array (W,) 0..4. NaN -> no detection. Flush at exactly
    2.5 sigma counts (<=).
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


def size_mult(n_fill: int) -> float:
    """B1 size multiplier: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill.
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg_arm: float,
                      o2: float, settle: bool):
    """D0 replica measured from the ACTUAL fill price px with arm sigma.

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first (oc_dipexit D0 / v293).
    """
    sl = px * (1 - M_SL * sg_arm)
    bl = px * (1 - BACKSTOP * sg_arm)
    tp = px * (1 + 1.0 * sg_arm)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = _first_idx(ht)
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


def daily_path(recs):
    """recs: iterable of (exit_date_iso, w_y). Returns (S, worst_day, maxDD, ndays)."""
    daily = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    if not daily:
        return 0.0, 0.0, 0.0, 0
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)
