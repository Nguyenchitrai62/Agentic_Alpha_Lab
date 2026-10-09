"""oc_makerexit core: D0 base replica + maker-timeout window (pure numpy, no I/O).

Frozen definitions in PLAN.md (IDEAS6 #1). Copies oc_dipexit/exits.py outcome_mu
verbatim (same constants, same stop-first priority); the maker window is new.

Costs: maker 0.0002 (fill + TP/maker legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 iff the timeout settlement (T+240).hour in (0,8,16);
the 60-min maker window never crosses a second settlement (T+240 is 4h-aligned),
so maker legs pay the same mid fund as the BASE timeout they replace.
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
# Frozen tick proxies (PLAN.md tick note): +1tick -> +1bps, +3ticks -> +3bps.
DELTA1 = 0.0001
DELTA3 = 0.0003
# Maker window (offsets from T): banned 240..244, live 245..299, remainder at 300.
WIN_LIVE_A, WIN_LIVE_B, WIN_END = 245, 299, 300


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """v399-exact correlation count per live minute (0..4). NaN -> no detect."""
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
    """First live-window index with low < level (STRICT). None if never."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """oc_dipexit-exact long rung outcome for TP multiple mu.

    Returns (ret, x, how); x = exit offset (240 = next-bar open).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = Oa[km + 1], km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")


def outcome_maker_window(Hw, Lw, Cw, Ow, px: float, sg: float, P: float,
                         o3m: float, settle_mid: bool):
    """One maker half over offsets 240..299 (60-min window, 5-min ban).

    Hw/Lw/Cw/Ow: length-60 arrays for absolute offsets 240..299 (index i -> m=240+i).
    o3m: 1m open at offset 300 (remainder taker price). settle_mid: mid settlement flag.
    Frozen sl/bl from px, sg; same wall-clock (m+1)%5==0; stop-first per minute:
    backstop > close5 stop > maker (same-minute stop+maker -> stop).
    Returns (ret, x, how); how in {"maker","stop","backstop","remainder"}; x in 245..300.
    NaN ret when the exit price is missing (stop open NaN / o3m NaN).
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    Hw = np.asarray(Hw, dtype=float)
    Lw = np.asarray(Lw, dtype=float)
    Cw = np.asarray(Cw, dtype=float)
    Ow = np.asarray(Ow, dtype=float)
    assert Hw.shape == (60,) and Lw.shape == (60,) and Cw.shape == (60,) and Ow.shape == (60,)
    mid_fund = FUND if settle_mid else 0.0
    for i in range(60):
        m = 240 + i
        if m < WIN_LIVE_A:
            continue  # banned minutes 240..244: no fills, no stops either
        lo = Lw[i]
        if np.isfinite(lo) and lo <= bl:
            ox = Ow[i]
            if not np.isfinite(ox):
                return (np.nan, m, "backstop")
            fill_px = bl if ox > bl else ox
            return (fill_px / px - 1 - MAKER - TAKER - mid_fund, m, "backstop")
        if (m + 1) % 5 == 0:
            cl = Cw[i]
            if np.isfinite(cl) and cl <= sl:
                if i + 1 < 60:
                    ex = Ow[i + 1]
                    x = m + 1
                else:
                    ex, x = o3m, WIN_END
                if not np.isfinite(ex):
                    return (np.nan, x, "stop")
                return (float(ex) / px - 1 - MAKER - TAKER - mid_fund, x, "stop")
        hi = Hw[i]
        if np.isfinite(hi) and hi > float(P):
            return (float(P) / px - 1 - 2 * MAKER - mid_fund, m, "maker")
    if not np.isfinite(float(o3m)):
        return (np.nan, WIN_END, "remainder")
    return (float(o3m) / px - 1 - MAKER - TAKER - mid_fund, WIN_END, "remainder")


def outcome_pair_maker(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                       o2: float, settle_mid: bool,
                       Hw, Lw, Cw, Ow, o3m: float):
    """Paired BASE/V1/V2 outcome for one fill.

    Ha/La/Ca/Oa: length>=240 arrays for offsets 0..239. Hw/Lw/Cw/Ow: length-60
    window arrays for offsets 240..299. o3m: open at 300.
    Non-timeout fills: V1 == V2 == BASE (no window data needed).
    Timeout fills: V1 = maker half at P1; V2 = 0.5*P1 + 0.5*P3.
    Returns (b_ret,b_x,b_how, v1_ret,v1_x,v1_how, v2_ret,v2_x,v2_how, extended).
    Any non-finite leg -> NaN there (caller drops triples with any NaN).
    """
    b_ret, b_x, b_how = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 1.0, o2, settle_mid)
    if b_how != "time":
        return (b_ret, b_x, b_how, b_ret, b_x, b_how, b_ret, b_x, b_how, False)
    if not np.isfinite(float(o2)):
        nan = np.nan
        return (b_ret, b_x, b_how, nan, 240, "remainder", nan, 240, "remainder", True)
    P1 = float(o2) * (1 + DELTA1)
    P3 = float(o2) * (1 + DELTA3)
    r1, x1, h1 = outcome_maker_window(Hw, Lw, Cw, Ow, lv, sg, P1, o3m, settle_mid)
    ra, xa, ha = outcome_maker_window(Hw, Lw, Cw, Ow, lv, sg, P1, o3m, settle_mid)
    rb, xb, hb = outcome_maker_window(Hw, Lw, Cw, Ow, lv, sg, P3, o3m, settle_mid)
    if not (np.isfinite(r1) and np.isfinite(ra) and np.isfinite(rb)):
        nan = np.nan
        return (b_ret, b_x, b_how, r1, x1, h1,
                (nan if not (np.isfinite(ra) and np.isfinite(rb)) else 0.5 * ra + 0.5 * rb),
                max(xa, xb) if (np.isfinite(ra) and np.isfinite(rb)) else WIN_END,
                "split", True)
    v2 = 0.5 * float(ra) + 0.5 * float(rb)
    return (b_ret, b_x, b_how, float(r1), int(x1), h1,
            float(v2), int(max(xa, xb)), "split", True)
