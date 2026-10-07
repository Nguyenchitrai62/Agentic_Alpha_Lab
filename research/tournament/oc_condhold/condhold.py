"""oc_condhold core: B1 static fill, D0 base exit, conditional extended-bar leg.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #35).
BASE = oc_b1deeper B1 / oc_holdext BASE replica (static bid, D0 exits).
CONDITIONAL = BASE, except a BASE timeout (how == "time") that is IN PROFIT
at the mid open o2 (base_ret > 0 strictly, i.e. mark above fill + round-trip
fees + any mid-settlement funding) runs the oc_holdext extended leg over
minutes 240..479 with the same frozen sl/bl/tp. Gate-FALSE timeouts exit at
o2 as today.

Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 per 8h settlement held (mid open T+240 for every
extended exit; final open T+480 additionally for extended timeouts).
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
    """Correlation count per live minute (vector length W).

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) sg_b(T).
    Returns int array (W,) with values 0..4. NaN open/sigma/close -> no
    detection (conservative). Flush at exactly 2.5 sigma counts (<=).
    Copied from oc_holdext/oc_b1deeper (v399-exact).
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
    """B1 size multiplier, both arms: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_base(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle: bool):
    """D0 replica measured from fill price px (oc_b1deeper B1 arm exact copy).

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first.
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


def in_profit(o2: float, px: float, settle_mid: bool) -> bool:
    """Profit gate at the mid open: mark above fill + fees (+mid funding).

    Returns True iff o2/px - 1 - MAKER - TAKER - (FUND if settle_mid) > 0
    strictly with finite o2/px. Causal: uses only the mid open o2 (known at
    T+240), the fill price px and the settlement flag (known from the bar
    clock). Exactly flat (== 0) is NOT profit (gate FALSE). A 1e-12 dust
    tolerance treats binary-float rounding at the exact boundary as flat.
    """
    if not (np.isfinite(float(o2)) and np.isfinite(float(px))) or float(px) <= 0:
        return False
    net = float(o2) / float(px) - 1 - MAKER - TAKER - (FUND if settle_mid else 0.0)
    return bool(net > 1e-12)


def outcome_ext_phase(H1, L1, C1, O1, px: float, sg: float,
                      o3: float, mid_settle: bool, final_settle: bool):
    """Second-bar leg for a gated BASE timeout: same sl/bl/tp, offsets 240..479.

    H1/L1/C1/O1: length-240 arrays for minutes T+240..T+479. Returns
    (ret, x, how); x in 240..479 intrabar, 480 = timeout at o3 (open T+480).
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Funding: mid fund (held through T+240) on EVERY extended exit;
    final fund additionally on timeouts at a settling o3.
    Clock (t+1)%5==0 on absolute offsets t=240+i continues the wall-clock
    grid ((240+i+1)%5==0 <=> (i+1)%5==0 since 240%5==0).
    Identical to the oc_holdext extended leg; only the caller gates it.
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    H1 = np.asarray(H1, dtype=float)
    L1 = np.asarray(L1, dtype=float)
    C1 = np.asarray(C1, dtype=float)
    O1 = np.asarray(O1, dtype=float)
    clk = (np.arange(240, 480) + 1) % 5 == 0
    trig = (C1 <= sl) & clk
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = L1 <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = H1 > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    mid_fund = FUND if mid_settle else 0.0
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        i = kb
        ox = float(O1[i])
        if not np.isfinite(ox):
            return (np.nan, 240 + i, "backstop")
        fill_px = bl if ox > bl else ox
        return (fill_px / px - 1 - MAKER - TAKER - mid_fund, 240 + i, "backstop")
    if kt is not None and (ks is None or kt < ks):
        i = kt
        return (tp / px - 1 - 2 * MAKER - mid_fund, 240 + i, "tp")
    if ks is not None:
        i = ks
        if i + 1 < 240:
            ex = float(O1[i + 1])
            x = 240 + i + 1
        else:
            ex, x = float(o3), 480
        if not np.isfinite(ex):
            return (np.nan, x, "stop")
        ret = ex / px - 1 - MAKER - TAKER - mid_fund
        if x == 480 and final_settle:
            ret -= FUND
        return (ret, x, "stop")
    if not np.isfinite(float(o3)):
        return (np.nan, 480, "time")
    ret = (float(o3) / px - 1 - MAKER - TAKER - mid_fund
           - (FUND if final_settle else 0.0))
    return (ret, 480, "time")


def outcome_pair(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle_mid: bool,
                 H1, L1, C1, O1, o3: float, settle_final: bool):
    """Paired base/conditional outcome for one fill.

    Returns (base_ret, base_x, base_how, cond_ret, cond_x, cond_how,
             cond_extended, gate_true).
    cond_extended == gate_true == True iff the base timed out AND the mid-open
    profit gate passed AND the second-bar leg ran. Otherwise cond == base.
    Either ret may be NaN (missing exit price); the caller drops pairs with
    any non-finite leg (paired-keep rule in PLAN.md).
    """
    b_ret, b_x, b_how = outcome_base(Ha, La, Ca, Oa, f, px, sg, o2, settle_mid)
    if b_how != "time":
        return (b_ret, b_x, b_how, b_ret, b_x, b_how, False, False)
    if not in_profit(o2, px, settle_mid):
        # At a loss or exactly flat at the mid open: exit at o2 as today.
        # No second-bar data is touched (causal + needs no o3).
        return (b_ret, b_x, b_how, b_ret, b_x, b_how, False, False)
    e_ret, e_x, e_how = outcome_ext_phase(H1, L1, C1, O1, px, sg, o3,
                                          settle_mid, settle_final)
    return (b_ret, b_x, b_how, e_ret, e_x, e_how, True, True)
