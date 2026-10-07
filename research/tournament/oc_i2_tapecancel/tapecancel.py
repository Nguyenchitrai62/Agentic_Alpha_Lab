"""oc_i2_tapecancel core: vendored B1/D0 replica + tape-contingent cancel + G-cap walk.

Pure numpy, no I/O. Replica definitions bit-identical to oc_bidttl/bidttl.py
(oc_dipexit D0 + oc_b1deeper B1 sizes + oc_rearm G-cap walk):
costs maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs);
funding: longs pay 0.0001 when the timeout exit is at a settling bar open
((bar_open+4h).hour in (0,8,16)); intrabar exits pay no funding.

Tape-cancel (IDEAS2_20261007 §3, pre-registered in REPORT.md):
- Live window opens at minute 16 (PLACEMENT_MIN). C1 cancels unfilled rungs
  at CANCEL1_MIN = 46 (+30m); C2 at CANCEL2_MIN = 76 (+60m). Never re-pegged.
- Tape window C1: 1m bars with offset in (16, 46] (30 bars); C2: (16, 76].
- s = taker-sell notional / total taker notional over the window (own coin,
  Binance aggTrades 1m size store). Window INVALID (NaN) if any minute is
  missing/non-finite or the total is <= 0.
- Thresholds: q80 (C1) / q90 (C2) = linear-interpolated quantile of the same
  window-stat over trailing-30d same-coin bars with bar open in [T-30d, T-4h]
  (all phases pooled); >= MIN_SAMPLES samples required else NaN (= never
  cancel). STRICT > : equality never cancels.
- A rung with fill f is cancelled iff toxic AND f > cancel minute. Rungs with
  f <= cancel minute already filled before the decision and are always kept.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
PLACEMENT_MIN = 16
CANCEL1_MIN = 46   # C1: +30m after live-open
CANCEL2_MIN = 76   # C2: +60m after live-open
WIN1 = (PLACEMENT_MIN + 1, CANCEL1_MIN)  # offsets 17..46 inclusive (30 bars)
WIN2 = (PLACEMENT_MIN + 1, CANCEL2_MIN)  # offsets 17..76 inclusive (60 bars)
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
GROSS_CAP = 2.0
CAP_EPS = 1e-12
MIN_SAMPLES = 30
TRAIL_DAYS = 30


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


def size_mult(n_fill: int) -> float:
    """B1 size multiplier: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if never.

    NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the fill price px (= lv here).

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


def tape_sell_share(buy: np.ndarray, sell: np.ndarray) -> float:
    """Taker-sell notional share over a window. NaN if invalid.

    buy/sell: parallel per-minute taker notional arrays over the window.
    Invalid when any minute is non-finite or the total is <= 0 or empty.
    """
    b = np.asarray(buy, dtype=float)
    s = np.asarray(sell, dtype=float)
    if b.size == 0 or b.shape != s.shape:
        return float("nan")
    if not (np.isfinite(b).all() and np.isfinite(s).all()):
        return float("nan")
    tot = float(b.sum() + s.sum())
    if not np.isfinite(tot) or tot <= 0:
        return float("nan")
    return float(s.sum() / tot)


def trailing_quantile(sample_opens_ns: np.ndarray, sample_s: np.ndarray,
                      bar_ns: int, q: float) -> float:
    """Causal trailing-30d quantile of a window-stat at bar open bar_ns.

    Uses samples with open in [bar_ns - 30d, bar_ns - 4h]. NaN when fewer
    than MIN_SAMPLES finite samples. STRICT comparison is applied by the
    caller (cancel iff s > thr).
    """
    lo = bar_ns - TRAIL_DAYS * 86_400_000_000_000
    hi = bar_ns - 4 * 3_600_000_000_000
    m = (sample_opens_ns >= lo) & (sample_opens_ns <= hi) & np.isfinite(sample_s)
    vals = sample_s[m]
    if vals.size < MIN_SAMPLES:
        return float("nan")
    return float(np.quantile(vals, q))


def cancelled(fill_f: int, s: float, thr: float, cancel_min: int) -> bool:
    """State-contingent cancel for one rung.

    True iff the rung is still unfilled at the cancel minute (f >
    cancel_min), the tape stat and threshold are finite, and s > thr
    (STRICT). NaN stat/threshold never cancels. Rungs filled at or before
    the cancel minute are always kept.
    """
    if int(fill_f) <= int(cancel_min):
        return False
    if not (np.isfinite(s) and np.isfinite(thr)):
        return False
    return bool(float(s) > float(thr))


def choose_variant(dev_stats: dict):
    """Pre-registered dev4-only robust choice (dev years 2021-2024 only).

    dev_stats: {variant: {"years_sum_ge": int, "years_dd_ok": int,
      "worst_delta_dev4": float, "dSum_dev4": float}}.
    Eligible iff DD leg holds 4/4 dev years and sum leg holds >= 3/4;
    among eligible pick the highest dev4 WORST-year delta, ties -> the
    higher dev4 mean delta. None when nobody is eligible.
    """
    elig = [v for v, s in dev_stats.items()
            if s["years_dd_ok"] == 4 and s["years_sum_ge"] >= 3]
    if not elig:
        return None
    return sorted(elig,
                  key=lambda v: (dev_stats[v]["worst_delta_dev4"],
                                 dev_stats[v]["dSum_dev4"]))[-1]


def gross_cap_weights(f, x, w, order, G=GROSS_CAP):
    """Engine `sleeve_gross_cap` walk: cut each new rung to the room left.

    f/x/w: parallel sequences (fill offset, exit offset, size) of one
    (phase, bar) candidate pool. order: positions in processing order
    ((f ASC, k ASC, coin ASC)). Returns dict pos -> w_kept (0.0 = skipped).
    Open at f = kept fills with exit x > f (an exit at minute <= f is
    observably closed by f). Skipped fills never open. oc_rearm-exact.
    """
    kept = {}
    open_fills = []  # (x_exit, w_kept) of kept fills so far
    for p in order:
        fi, xi, wi = int(f[p]), int(x[p]), float(w[p])
        open_w = sum(wk for (xk, wk) in open_fills if xk > fi)
        room = float(G) - open_w
        if room <= CAP_EPS:
            kept[p] = 0.0
        else:
            wk = wi if wi <= room else room
            kept[p] = wk
            open_fills.append((xi, wk))
    return kept


def exit_day_iso(t_bar, x: int) -> str:
    """Calendar UTC exit date ISO for a fill of bar t_bar with exit offset x."""
    import pandas as pd

    if int(x) < 240:
        return (t_bar + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (t_bar + pd.Timedelta(hours=4)).date().isoformat()


def cell_stats_dict(dates, wy):
    """(S, worst_day, maxDD, ndays) of daily sums. DD >= 0 in w*y units."""
    import numpy as np

    dates = np.asarray(dates)
    wy = np.asarray(wy, dtype=float)
    if wy.size == 0:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in zip(dates.tolist(), wy.tolist()):
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)
