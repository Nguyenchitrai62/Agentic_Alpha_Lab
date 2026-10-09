"""Pure patient-exit helpers for oc_b7patient (no data access; unit-tested).

Trigger arithmetic VERBATIM from oc_cascadedelay delay_rule.py /
oc_cascadeboost boost_rule.py / oc_cboostpre cboostpre_rule.py
(closes-only >4sg cascade proxy, market-wide per shift); exit race VERBATIM
from oc_presampletilt build_ledger_presample.outcome_mu (mu-param) with the
oc_holdext one-bar-extension reading for V2.

IDEAS7 #6: boosted fills (B7 7d window, x1.5 sizing) keep the 4sg stop and get
room for the snapback:
  V1: TP 1.0sg -> 1.5sg for boosted fills only.
  V2: timeout clocks x2 for boosted fills only (ONE extension to T+480,
      maker-first, taker fallback).
Market-wide per shift. NOT oc_partialtp (that banked half EARLY).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST = 1.5
B7_DAYS = 7
MU_BASE = 1.0
MU_V1 = 1.5
M_SL, BACKSTOP = 4.0, 8.0
MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
NS_DAY = 86_400_000_000_000


def close_returns(closes) -> np.ndarray:
    """Close-to-close log returns; r[0] = NaN. Pure."""
    c = np.asarray(closes, dtype=float)
    r = np.full_like(c, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.log(c[1:] / c[:-1])
    r[~np.isfinite(r)] = np.nan
    return r


def trailing_sigma(r, window: int = WINDOW,
                   min_periods: int = MIN_PERIODS) -> np.ndarray:
    """SIG[i] = std(ddof=1) of r[i-window .. i-1] (tested bar EXCLUDED). Pure."""
    r = np.asarray(r, dtype=float)
    n = r.size
    out = np.full(n, np.nan)
    if n == 0:
        return out
    finite = np.isfinite(r)
    cs = np.cumsum(np.where(finite, r, 0.0))
    cs2 = np.cumsum(np.where(finite, r * r, 0.0))
    cn = np.cumsum(finite.astype(float))
    for i in range(n):
        lo = max(0, i - window)
        cnt = cn[i - 1] - (cn[lo - 1] if lo > 0 else 0.0) if i > 0 else 0.0
        if cnt < min_periods:
            continue
        s = cs[i - 1] - (cs[lo - 1] if lo > 0 else 0.0)
        s2 = cs2[i - 1] - (cs2[lo - 1] if lo > 0 else 0.0)
        var = (s2 - s * s / cnt) / (cnt - 1)
        if np.isfinite(var) and var > 0:
            out[i] = float(np.sqrt(var))
    return out


def triggers_of(closes, thresh: float = THRESH, window: int = WINDOW,
                min_periods: int = MIN_PERIODS) -> np.ndarray:
    """Bool array: bar i fires iff |r[i]| > thresh * SIG[i] (strict). Pure."""
    r = close_returns(closes)
    sig = trailing_sigma(r, window, min_periods)
    fire = np.zeros(len(r), dtype=bool)
    ok = np.isfinite(r) & np.isfinite(sig) & (sig > 0)
    fire[ok] = np.abs(r[ok]) > float(thresh) * sig[ok]
    return fire


def boosted_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                 n_days: int = B7_DAYS) -> np.ndarray:
    """For each grid time T: True iff exists tc with 0 < T - tc <= n_days. Pure."""
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(trig_ns, dtype=np.int64)
    out = np.zeros(len(grid_ns), dtype=bool)
    if trig_ns.size == 0:
        return out
    span = int(n_days) * NS_DAY
    pos = np.searchsorted(trig_ns, grid_ns, side="left") - 1
    valid = pos >= 0
    out[valid] = (grid_ns[valid] - trig_ns[pos[valid]] <= span)
    return out


# Alias kept so the verbatim-inherited arithmetic reads identically.
cooled_mask = boosted_mask


def compute_sigma(opens) -> np.ndarray:
    """Presample level sigma VERBATIM build_ledger_presample.compute_sigma. Pure."""
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def find_fill(low_win, level: float):
    """First index with low < level (strict trade-through), else None. Pure."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_ret(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
                o2: float, settle: bool):
    """VERBATIM build_ledger_presample.outcome_mu (returns ret, x, kind). Pure.

    sl = lv*(1-4sg), bl = lv*(1-8sg), tp = lv*(1+mu*sg). Race f+1..239 then
    timeout at 240. Stop-first: backstop wins ties, else TP iff strictly
    earlier than stop, else stop, else timeout.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
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
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = float(Oa[km + 1]), km + 1
        else:
            px, x = float(o2), 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    return (float(o2) / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float = 1.0) -> str:
    """Exit-kind branch (kind only), VERBATIM ordering. Pure."""
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        return "backstop"
    if kt is not None and (ks is None or kt < ks):
        return "tp"
    if ks is not None:
        return "stop"
    return "time"


def outcome_extended(Hb, Lb, Cb, Ob, lv: float, sg: float, mu: float,
                     o3: float, settle_mid: bool, settle_end: bool):
    """V2 one-bar extension over offsets 240..479 (VERBATIM holdext). Pure.

    Same sl/bl/tp(mu) levels frozen from the original lv/sg. Evaluates
    backstop -> TP (maker-first) -> close5 stop -> timeout at o3 (taker
    fallback) with stop-first priority. Funding: mid settle if held through
    T+240; end settle additionally iff timeout at o3. Returns (ret, kind2)
    where kind2 in {"backstop","tp","stop","time"} (second-clock outcome).
    Costs: TP 2*MAKER; stop/backstop/time MAKER+TAKER; entry maker included
    (same convention as outcome_ret: ret is fraction of lv net of both legs).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    H = np.asarray(Hb, dtype=float)
    L = np.asarray(Lb, dtype=float)
    C = np.asarray(Cb, dtype=float)
    O = np.asarray(Ob, dtype=float)
    assert len(H) == 240 and len(L) == 240 and len(C) == 240 and len(O) == 240
    hb = L <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = H > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    # close5 on the same wall-clock grid: absolute offsets m in 240..479
    # with (m+1)%5==0
    ks = None
    for j in range(240):
        m = 240 + j
        if (m + 1) % 5 == 0 and np.isfinite(C[j]) and C[j] <= sl:
            ks = j
            break
    mid = FUND if settle_mid else 0.0
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        ox = float(O[kb])
        if not np.isfinite(ox):
            return (np.nan, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER - mid, "backstop")
    if kt is not None and (ks is None or kt < ks):
        return (tp / lv - 1 - 2 * MAKER - mid, "tp")
    if ks is not None:
        if ks + 1 < 240:
            px = float(O[ks + 1])
            if not np.isfinite(px):
                return (np.nan, "stop")
            return (px / lv - 1 - MAKER - TAKER - mid, "stop")
        if not np.isfinite(float(o3)):
            return (np.nan, "stop")
        return (float(o3) / lv - 1 - MAKER - TAKER - mid, "stop")
    if not np.isfinite(float(o3)):
        return (np.nan, "time")
    extra = FUND if settle_end else 0.0
    return (float(o3) / lv - 1 - MAKER - TAKER - mid - extra, "time")
