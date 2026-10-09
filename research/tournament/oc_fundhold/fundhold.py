"""oc_fundhold core: B1 static fill, D0 base exit, conditional +8h extension leg.

Pure numpy, no I/O. Base definitions vendored holdext-exact (PLAN.md frozen).
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 per 8h settlement held.
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


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (holdext-exact, v399 B1, both arms)."""
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
    """B1 size multiplier, both arms: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First offset index into the live window with low < level (STRICT)."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_base(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle: bool):
    """D0 replica from fill px (holdext outcome_base exact copy).

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. Stop-first.
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
        fill_px = bl if ox > bl else ox
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


def outcome_ext8_phase(H2, L2, C2, O2, px: float, sg: float,
                       o4: float, mid1: bool, mid2: bool, final: bool):
    """Two-bar extension leg for a BASE timeout: same sl/bl/tp, offsets 240..719.

    H2/L2/C2/O2: length-480 arrays for minutes T+240..T+719. Returns
    (ret, x, how); x in 240..719 intrabar, 720 = timeout at o4 (open T+720).
    Funding: every extended exit held through T+240 pays FUND if mid1; exits at
    offset >= 480 additionally pay FUND if mid2; timeouts at 720 additionally
    pay FUND if final. Clock (t+1)%5==0 on absolute offsets continues the wall
    grid. Stop-first, same as base.
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    H2 = np.asarray(H2, dtype=float)
    L2 = np.asarray(L2, dtype=float)
    C2 = np.asarray(C2, dtype=float)
    O2 = np.asarray(O2, dtype=float)
    clk = (np.arange(240, 720) + 1) % 5 == 0
    trig = (C2 <= sl) & clk
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = L2 <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = H2 > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    f1 = FUND if mid1 else 0.0
    f2 = FUND if mid2 else 0.0
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        i = kb
        ox = float(O2[i])
        if not np.isfinite(ox):
            return (np.nan, 240 + i, "backstop")
        fill_px = bl if ox > bl else ox
        fund = f1 + (f2 if 240 + i >= 480 else 0.0)
        return (fill_px / px - 1 - MAKER - TAKER - fund, 240 + i, "backstop")
    if kt is not None and (ks is None or kt < ks):
        i = kt
        fund = f1 + (f2 if 240 + i >= 480 else 0.0)
        return (tp / px - 1 - 2 * MAKER - fund, 240 + i, "tp")
    if ks is not None:
        i = ks
        if i + 1 < 480:
            ex = float(O2[i + 1])
            x = 240 + i + 1
        else:
            ex, x = float(o4), 720
        if not np.isfinite(ex):
            return (np.nan, x, "stop")
        fund = f1 + (f2 if x >= 480 else 0.0)
        ret = ex / px - 1 - MAKER - TAKER - fund
        if x == 720 and final:
            ret -= FUND
        return (ret, x, "stop")
    if not np.isfinite(float(o4)):
        return (np.nan, 720, "time")
    ret = (float(o4) / px - 1 - MAKER - TAKER - f1 - f2
           - (FUND if final else 0.0))
    return (ret, 720, "time")


def outcome_conditional(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                        o2: float, settle_mid: bool, extend: bool,
                        H2, L2, C2, O2, o4: float,
                        mid1: bool, mid2: bool, final: bool):
    """Paired base/conditional outcome for one fill.

    Returns (base_ret, base_x, base_how, var_ret, var_x, var_how, extended).
    extended=True iff the base timed out AND extend=True and the 8h leg ran.
    Either ret may be NaN (missing exit price); the caller drops triples with
    any non-finite leg (paired-keep rule in PLAN.md).
    """
    b_ret, b_x, b_how = outcome_base(Ha, La, Ca, Oa, f, px, sg, o2, settle_mid)
    if b_how != "time" or not extend:
        return (b_ret, b_x, b_how, b_ret, b_x, b_how, False)
    e_ret, e_x, e_how = outcome_ext8_phase(H2, L2, C2, O2, px, sg, o4,
                                           mid1, mid2, final)
    return (b_ret, b_x, b_how, e_ret, e_x, e_how, True)


def fee_for(how: str) -> float:
    """Per-fill fee drag in return units (fill + exit legs)."""
    if how == "tp":
        return 2 * MAKER
    return MAKER + TAKER
