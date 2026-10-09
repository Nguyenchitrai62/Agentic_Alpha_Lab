"""oc_ripcont backtest core: buy-the-first-pullback-after-a-rip (long sleeve).

Pure numpy logic on 1m arrays; no I/O here (see run.py). All choices match
research/tournament/oc_ripcont/PLAN.md (pre-registered).
Costs: maker 0.0002 (entry + TP), taker 0.00055 (SL/timeout).
Funding: longs pay 0.0001 per 8h settlement (00/08/16 UTC) crossed.
"""
from __future__ import annotations

import numpy as np

MK = 0.0002
TK = 0.00055
FUND = 0.0001
TP_K = 0.75
SL_K = 1.0
PULLBACK_K = 1.0  # L = O * exp((k - 1) * s)
TRIG_MIN, TRIG_MAX = 5, 239
ENTRY_LAST = 199
EXIT_LAST = 239  # offsets inside the bar; timeout at offset 240


def sigma_from_bar_opens_log(opens: np.ndarray, lookback: int = 360,
                             min_periods: int = 120) -> np.ndarray:
    """Rolling std (ddof=1) of log open-to-open returns; sigma[j] uses O[j].

    r[j] = ln(O[j] / O[j-1]) for j >= 1. sigma[j] = std of r over
    {r[max(1,j-lookback+1)] .. r[j]}, NaN when fewer than min_periods
    finite returns or j < 1. Uses only opens up to O[j] -> known at bar open.
    """
    opens = np.asarray(opens, dtype=float)
    sig = np.full(len(opens), np.nan)
    if len(opens) < 2:
        return sig
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(opens[1:] / opens[:-1])
    for j in range(1, len(opens)):
        lo = max(1, j - lookback + 1)
        win = r[lo - 1:j]  # r index i corresponds to O[i+1]; r[j-1] uses O[j]
        win = win[np.isfinite(win)]
        if len(win) >= min_periods:
            sig[j] = float(np.std(win, ddof=1)) if len(win) > 1 else np.nan
    return sig


def count_funding(fill_ns: int, exit_ns: int) -> int:
    """Number of 00/08/16 UTC settlements with fill_ns < s <= exit_ns."""
    if exit_ns <= fill_ns:
        return 0
    step = 8 * 3600 * 10 ** 9
    # first settlement strictly after fill_ns
    first = (fill_ns // step + 1) * step
    if first > exit_ns:
        return 0
    return int((exit_ns - first) // step + 1)


def net_long(level: float, exit_px: float, how: str, n_fund: int = 0) -> float:
    fee = MK if how == "tp" else TK
    return (exit_px - level) / level - MK - fee - FUND * n_fund


def resolve_exit_long(H, Lw, O, f: int, L: float, s: float, b0: int):
    """Exit for one filled long. Returns (exit_idx, exit_px, how) or None.

    Search t in [f+1, b0+239]; SL (touch low <= SL_px) checked BEFORE TP
    (high > TP_px) each minute (stop-first). Timeout at b0+240 (caller checks
    its open for NaN). Only indices < len(O) are considered.
    """
    n = len(O)
    tp = L * float(np.exp(TP_K * s))
    sl = L * float(np.exp(-SL_K * s))
    end = min(b0 + EXIT_LAST, n - 1)
    for t in range(f + 1, end + 1):
        if t < 0 or t >= n:
            continue
        lw = Lw[t]
        if np.isfinite(lw) and lw <= sl:
            return t, float(sl), "stop"
        h = H[t]
        if np.isfinite(h) and h > tp:
            return t, float(tp), "tp"
    x = b0 + 240
    if x >= n or not np.isfinite(O[x]):
        return None
    return x, float(O[x]), "time"


def simulate_clock(idx_ns: np.ndarray, O, H, Lw, C, bar_pos: np.ndarray,
                   bar_time, sig: np.ndarray, k: float):
    """Loop 4h bars of one clock; at most one fill per bar. Returns events."""
    evs = []
    n = len(O)
    k = float(k)
    for j, b0 in enumerate(bar_pos):
        b0 = int(b0)
        if b0 + 240 >= n and b0 + 240 > n - 1:
            if b0 + 240 >= n:
                continue
        o = O[b0]
        s = sig[j] if j < len(sig) else np.nan
        if not np.isfinite(o) or o <= 0 or not np.isfinite(s) or s <= 0:
            continue
        a = b0 + TRIG_MIN
        b = min(b0 + TRIG_MAX, n - 1)
        if b <= a:
            continue
        trig = o * float(np.exp(k * s))
        segH = H[a:b + 1]
        hit = np.isfinite(segH) & (segH >= trig)
        if not np.any(hit):
            continue
        m = a + int(np.argmax(hit))  # first trigger minute
        L = o * float(np.exp((k - PULLBACK_K) * s))
        fa = m + 1
        fb = min(b0 + ENTRY_LAST, n - 1)
        if fb < fa:
            continue
        segL = Lw[fa:fb + 1]
        fill_hit = np.isfinite(segL) & (segL < L)  # strict trade-through
        if not np.any(fill_hit):
            continue
        f = fa + int(np.argmax(fill_hit))
        r = resolve_exit_long(H, Lw, O, f, L, s, b0)
        if r is None:
            continue
        x, px, how = r
        nf = count_funding(int(idx_ns[f]), int(idx_ns[x]))
        net = net_long(L, px, how, nf)
        evs.append({
            "bar_open": bar_time[j], "fill_idx": int(f), "exit_idx": int(x),
            "k": k, "level": float(L), "sigma": float(s),
            "exit_px": float(px), "how": how,
            "n_fund": int(nf), "net": float(net),
        })
    return evs


def placebo_exit(H, Lw, O, idx_ns: np.ndarray, b0: int, m_off: int,
                 L: float, s: float):
    """Placebo entry filled immediately at minute b0+m_off at price L.

    Same TP/SL multiples, timeout and funding as the real sleeve. Returns
    (exit_idx, exit_px, how, n_fund, net) or None if timeout open is NaN.
    """
    n = len(O)
    f = b0 + int(m_off)
    if f < 0 or f >= n:
        return None
    r = resolve_exit_long(H, Lw, O, f, L, s, b0)
    if r is None:
        return None
    x, px, how = r
    nf = count_funding(int(idx_ns[f]), int(idx_ns[x]))
    return x, px, how, nf, net_long(L, px, how, nf)
