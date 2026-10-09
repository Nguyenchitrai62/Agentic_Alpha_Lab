"""oc_partialtp core: D0 base replica + stop-funded partial TP (pure numpy, no I/O).

Frozen definitions in PLAN.md (IDEAS6 #2). Copies oc_dipexit/exits.py outcome_mu
verbatim (same constants, same stop-first priority); the partial leg is new.

Costs: maker 0.0002 (fill + TP/partial legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 iff the exit at offset 240 is at a settling bar open
((T+4h).hour in (0,8,16)); intrabar exits pay no funding. A split fill whose
remainder exits at 240 pays FUND on the remainder half only (0.5*FUND total),
since the exited half is not held at the settlement (disclosed in PLAN.md).
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
# Frozen partial multiples (PLAN.md): V1 half at 0.5sg, V2 half at 0.75sg.
MU_V1 = 0.5
MU_V2 = 0.75
MU_RUN = 1.0


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
    ht = np.asarray(Ha[f + 1:240]) > tp
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


def outcome_partial(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu_p: float,
                    o2: float, settle: bool):
    """Stop-funded partial TP: HALF at mu_p maker + runner re-race at 1.0sg.

    Frozen race in PLAN.md (stop-first, no re-peg). Returns (ret, x, how) where
    how in {"tp","stop","backstop","time"} (whole, == BASE) or
    {"part_tp","part_stop","part_backstop","part_time"} (split, half early).
    x = remainder/whole exit offset (240 = next-bar open).
    NaN ret when the exit price is missing (stop open NaN / o2 NaN).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    pp = lv * (1 + mu_p * sg)
    tp = lv * (1 + MU_RUN * sg)
    Ha = np.asarray(Ha, dtype=float)
    La = np.asarray(La, dtype=float)
    Ca = np.asarray(Ca, dtype=float)
    Oa = np.asarray(Oa, dtype=float)
    post = np.arange(f + 1, 240)
    trig = (Ca[f + 1:240] <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La[f + 1:240] <= bl
    kb = _first_idx(hb)
    hp = Ha[f + 1:240] > pp
    kp = _first_idx(hp)
    ht = Ha[f + 1:240] > tp
    kt = _first_idx(ht)
    # (1) backstop first (or tied): whole backstop, no partial.
    if kb is not None and (ks is None or kb <= ks) and (kp is None or kb <= kp):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    # (2) partial strictly before any close5 stop: bank half, remainder re-races.
    if kp is not None and (ks is None or kp < ks):
        xp = f + 1 + kp
        r_part = pp / lv - 1 - 2 * MAKER
        # Same-minute runner: the 1m bar traded straight through tp (high(xp) >
        # tp implies high(xp) > pp), so the runner fills maker the same minute.
        # Safe: branch (2) already excludes any stop/backstop at xp.
        if np.isfinite(Ha[xp]) and Ha[xp] > tp:
            r_rem = tp / lv - 1 - 2 * MAKER
            return (0.5 * r_part + 0.5 * r_rem, xp, "part_tp")
        # Remainder race on xp+1..239.
        if xp + 1 >= 240:
            # Partial at the last minute: remainder can only time out at o2.
            if not np.isfinite(o2):
                return (np.nan, 240, "part_time")
            r_rem = o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0)
            return (0.5 * r_part + 0.5 * r_rem, 240, "part_time")
        post2 = np.arange(xp + 1, 240)
        trig2 = (Ca[xp + 1:240] <= sl) & ((post2 + 1) % 5 == 0)
        ks2 = _first_idx(trig2)
        hb2 = La[xp + 1:240] <= bl
        kb2 = _first_idx(hb2)
        ht2 = Ha[xp + 1:240] > tp
        kt2 = _first_idx(ht2)
        if kb2 is not None and (ks2 is None or kb2 <= ks2) and \
                (kt2 is None or kb2 <= kt2):
            x = xp + 1 + kb2
            ox = Oa[x]
            if not np.isfinite(ox):
                return (np.nan, x, "part_backstop")
            fill_px = bl if ox > bl else ox
            r_rem = fill_px / lv - 1 - MAKER - TAKER
            return (0.5 * r_part + 0.5 * r_rem, x, "part_backstop")
        if kt2 is not None and (ks2 is None or kt2 < ks2):
            x = xp + 1 + kt2
            r_rem = tp / lv - 1 - 2 * MAKER
            return (0.5 * r_part + 0.5 * r_rem, x, "part_tp")
        if ks2 is not None:
            km = xp + 1 + ks2
            if km + 1 < 240:
                px, x = Oa[km + 1], km + 1
            else:
                px, x = o2, 240
            if not np.isfinite(px):
                return (np.nan, x, "part_stop")
            r_rem = px / lv - 1 - MAKER - TAKER
            if x == 240 and settle:
                r_rem -= FUND
            return (0.5 * r_part + 0.5 * r_rem, x, "part_stop")
        if not np.isfinite(o2):
            return (np.nan, 240, "part_time")
        r_rem = o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0)
        return (0.5 * r_part + 0.5 * r_rem, 240, "part_time")
    # (3) close5 stop first (or tied with partial): whole stop, as BASE.
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
    # (4) no stop, no partial (hence no runner TP either): whole timeout.
    if not np.isfinite(o2):
        return (np.nan, 240, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), 240, "time")


def outcome_pair_partial(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                         o2: float, settle: bool):
    """Paired BASE/V1/V2 outcome for one fill.

    Ha/La/Ca/Oa: length>=240 arrays for offsets 0..239 (no second-bar data needed;
    the runner re-races inside the same bar). Fills whose partial never triggers
    return V == BASE exactly.
    Returns (b_ret,b_x,b_how, v1_ret,v1_x,v1_how, v2_ret,v2_x,v2_how, split_any).
    Any non-finite leg -> NaN there (caller drops triples with any NaN).
    """
    b_ret, b_x, b_how = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, MU_RUN, o2, settle)
    r1, x1, h1 = outcome_partial(Ha, La, Ca, Oa, f, lv, sg, MU_V1, o2, settle)
    r2, x2, h2 = outcome_partial(Ha, La, Ca, Oa, f, lv, sg, MU_V2, o2, settle)
    split = h1.startswith("part_") or h2.startswith("part_")
    return (b_ret, b_x, b_how, r1, x1, h1, r2, x2, h2, split)
