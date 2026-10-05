"""oc_rips backtest core: rip-fade (short) ladder + mirrored dip reference.

Pure numpy logic on 1m arrays; no I/O here (see run.py). All choices match
research/tournament/oc_rips/PLAN.md. Costs: maker 0.0002, taker 0.00055.
"""
from __future__ import annotations

import numpy as np

MK = 0.0002
TK = 0.00055
KS = (2.5, 3.0, 4.0)
LIVE_A, LIVE_B = 16, 238  # offsets of live window inside the 240-min bar
TP_K, SC_K, BS_K = 1.0, 4.0, 8.0


def sigma_from_bar_opens(opens: np.ndarray, lookback: int = 360, min_periods: int = 120) -> np.ndarray:
    """Rolling std (ddof=1) of simple open-to-open returns; sigma[j] uses O[j]."""
    opens = np.asarray(opens, dtype=float)
    sig = np.full(len(opens), np.nan)
    if len(opens) < 2:
        return sig
    with np.errstate(divide="ignore", invalid="ignore"):
        r = opens[1:] / opens[:-1] - 1.0
    for j in range(len(opens)):
        lo = max(1, j - lookback + 1)
        win = r[lo:j + 1]  # r index i corresponds to O[i+1]; r[j] uses O[j]
        win = win[np.isfinite(win)]
        if len(win) >= min_periods and j >= 1:
            sig[j] = float(np.std(win, ddof=1)) if len(win) > 1 else np.nan
    return sig


def resolve_exit(O, H, Lw, C, f: int, level: float, s: float, b0: int, side: int):
    """Exit for one filled rung. side=-1 short (rip), +1 long (dip).

    Returns (exit_idx, exit_px, how) with how in {tp, stop, time}, or None if
    the timeout price is missing. Only complete 5-min blocks [f+1..f+5], ...
    are evaluated for the close-stop; a trailing partial block is ignored.
    Same-minute priority: backstop touch first, then block-close stop, then TP.
    """
    n = len(O)
    end = min(b0 + 239, n - 1)
    if side == -1:
        tp = level * (1 - TP_K * s)
        sc = level * (1 + SC_K * s)
        bs = level * (1 + BS_K * s)
    else:
        tp = level * (1 + TP_K * s)
        sc = level * (1 - SC_K * s)
        bs = level * (1 - BS_K * s)
    t_end = b0 + 240
    for t in range(f + 1, end + 1):
        if t < 0 or t >= n:
            continue
        if side == -1:
            if np.isfinite(H[t]) and H[t] >= bs:
                px = bs if not np.isfinite(O[t]) else max(bs, O[t])
                return t, float(px), "stop"
        else:
            if np.isfinite(Lw[t]) and Lw[t] <= bs:
                px = bs if not np.isfinite(O[t]) else min(bs, O[t])
                return t, float(px), "stop"
        if (t - f) % 5 == 0:  # complete-block close
            c = C[t]
            if np.isfinite(c) and ((side == -1 and c > sc) or (side == 1 and c < sc)):
                x = t + 1
                if x > b0 + 240 or x >= n or not np.isfinite(O[x]):
                    return None
                return x, float(O[x]), "stop"
        if side == -1:
            if np.isfinite(Lw[t]) and Lw[t] < tp:
                return t, float(tp), "tp"
        else:
            if np.isfinite(H[t]) and H[t] > tp:
                return t, float(tp), "tp"
    if t_end >= n or not np.isfinite(O[t_end]):
        return None
    return t_end, float(O[t_end]), "time"


def net_short(level: float, exit_px: float, how: str) -> float:
    fee = MK if how == "tp" else TK
    return (level - exit_px) / level - MK - fee


def net_long(level: float, exit_px: float, how: str) -> float:
    fee = MK if how == "tp" else TK
    return (exit_px - level) / level - MK - fee


def simulate_symbol(idx, O, H, Lw, C, bar_pos: np.ndarray, bar_time, sig: np.ndarray,
                     side: int, ks=KS):
    """Loop 4h bars; at most one fill per (bar, k). Returns list of dicts."""
    evs = []
    n = len(O)
    for j, b0 in enumerate(bar_pos):
        b0 = int(b0)
        if b0 + 240 > n:
            continue
        o = O[b0]
        s = sig[j] if j < len(sig) else np.nan
        if not np.isfinite(o) or o <= 0 or not np.isfinite(s) or s <= 0:
            continue
        a, b = b0 + LIVE_A, min(b0 + LIVE_B, n - 1)
        if b <= a:
            continue
        for k in ks:
            if side == -1:
                level = o * (1 + float(k) * s)
                win = H[a:b + 1] > level
            else:
                level = o * (1 - float(k) * s)
                win = Lw[a:b + 1] < level
            win = np.where(np.isfinite(win), win, False)
            if not np.any(win):
                continue
            f = a + int(np.argmax(win))
            r = resolve_exit(O, H, Lw, C, f, level, s, b0, side)
            if r is None:
                continue
            x, px, how = r
            net = net_short(level, px, how) if side == -1 else net_long(level, px, how)
            evs.append({
                "bar_open": bar_time[j], "fill_idx": f, "fill_time": idx[f],
                "exit_idx": x, "exit_time": idx[x] if 0 <= x < len(idx) else None,
                "k": float(k), "level": float(level), "sigma": float(s),
                "exit_px": float(px), "how": how, "net": float(net),
            })
    return evs
