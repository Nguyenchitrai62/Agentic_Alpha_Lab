"""oc_decayexit: signal-decay exit / asymmetric hold (IDEAS8 #6) pure helpers.

Frozen definitions in PLAN.md. No I/O, no fits, no test-year statistics.
|w| = |tg| current policy target; |w0| = |tg| at the flat->open decision that
issued the current position's entry order (frozen for the life of the position).
Fractions 0.3 (V1) / 0.5 (V2) frozen ex-ante. G2 grid remainder bit-identical
(B_abs 0.03, B_rel 0.40, COOL 6, THETA 0.05).

Usage: imported by run_engine.py (policy wrapper) and compute_controls.py
(standard-grid proxy). Unit-tested in tests/test_oc_decayexit.py.
"""
from __future__ import annotations

import numpy as np

THETA = 0.05
B_ABS = 0.03
B_REL = 0.40
COOL = 6
FRAC_V1 = 0.3
FRAC_V2 = 0.5


def sgn_of(tg: float, theta: float = THETA) -> int:
    """Sign of the book target with the G2 opening threshold."""
    try:
        v = float(tg)
    except (TypeError, ValueError):
        return 0
    if not np.isfinite(v):
        return 0
    if abs(v) < theta:
        return 0
    return 1 if v > 0 else -1


def decay_close(atv: float, w0: float, frac: float) -> bool:
    """True iff the decay exit fires: |tg| < frac * w0 (both finite, w0 > 0)."""
    try:
        a = float(atv)
        b = float(w0)
        f = float(frac)
    except (TypeError, ValueError):
        return False
    if not (np.isfinite(a) and np.isfinite(b) and np.isfinite(f)):
        return False
    if b <= 0:
        return False
    return a < f * b


def decay_policy(b_abs: float = B_ABS, b_rel: float = B_REL, frac: float = FRAC_V1,
                 cool: int = COOL, theta: float = THETA):
    """G2 grid policy with an overriding signal-decay full close.

    State: per-coin w0 (entry |tg|), set on flat->open, cleared on flat.
    In-position: reversal (tighten+close, kept) -> decay-close -> G2 remainder.
    The returned callable has attributes _w0 (dict), _frac, _params for tests.
    """
    if frac not in (FRAC_V1, FRAC_V2):
        raise ValueError(f"frozen fractions only 0.3/0.5, got {frac}")
    w0: dict[int, float] = {}

    def pol(i, a, st):
        # Flat (no position): G2 opens unconditionally; record w0.
        if st.get("pos", 0) == 0:
            w0.pop(a, None)
            try:
                tg = float(st.get("tg", 0.0))
            except (TypeError, ValueError):
                tg = 0.0
            if np.isfinite(tg) and abs(tg) >= theta:
                w0[a] = abs(tg)
            return "open"
        side = st["pos"]
        tg = st.get("tg", 0.0)
        sgn = st.get("sgn", 0)
        w = st.get("w", 0.0)
        valid = st.get("valid", ())
        # 1. reversal kept (tighten + limit close, identical to G2).
        if sgn == -side:
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        # 2. decay full close (sgn==0 is a subcase when 0 < frac*w0).
        cur0 = w0.get(a)
        if cur0 is None or not np.isfinite(cur0) or cur0 <= 0:
            # Warm-up fallback: position predates live tracking (opened before
            # the live window). Initialise from current causal state once.
            try:
                atv0 = abs(float(tg)) if np.isfinite(float(tg)) else 0.0
            except (TypeError, ValueError):
                atv0 = 0.0
            try:
                wv = float(w) if np.isfinite(float(w)) else 0.0
            except (TypeError, ValueError):
                wv = 0.0
            init = max(atv0, wv)
            if np.isfinite(init) and init >= theta:
                w0[a] = init
                cur0 = init
            else:
                cur0 = None
        if cur0 is not None and np.isfinite(cur0) and cur0 > 0:
            try:
                atv = abs(float(tg))
            except (TypeError, ValueError):
                atv = float("nan")
            if np.isfinite(atv) and atv < float(frac) * cur0:
                return "close" if "close" in valid else "hold"
        # 3. G2 remainder bit-identical.
        if sgn == 0:
            return "close" if "close" in valid else "hold"
        since_adj = st.get("since_adj", 10 ** 6)
        try:
            sa = int(since_adj)
        except (TypeError, ValueError):
            sa = 10 ** 6
        if sa < cool:
            return "hold"
        try:
            band = max(float(b_abs), float(b_rel) * abs(float(tg)))
        except (TypeError, ValueError):
            band = float(b_abs)
        try:
            diff = abs(float(tg)) - float(w)
        except (TypeError, ValueError):
            return "hold"
        if diff > band and "add" in valid:
            return {"add": diff}
        try:
            wv2 = float(w)
        except (TypeError, ValueError):
            wv2 = 0.0
        if -diff > band and "reduce" in valid and wv2 > 0:
            return {"reduce": min(1.0, -diff / wv2)}
        return "hold"

    pol._w0 = w0  # type: ignore[attr-defined]
    pol._frac = frac  # type: ignore[attr-defined]
    pol._params = (b_abs, b_rel, cool, theta)  # type: ignore[attr-defined]
    return pol


def grid_policy_ref(b_abs: float = B_ABS, b_rel: float = B_REL,
                    cool: int = COOL):
    """Bit-identical G2 grid policy (for tests: decay with frac=+inf == G2)."""
    def pol(i, a, st):
        if st.get("pos", 0) == 0:
            return "open"
        side = st["pos"]
        tg = st.get("tg", 0.0)
        w = st.get("w", 0.0)
        valid = st.get("valid", ())
        if st.get("sgn", 0) == -side:
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        if st.get("sgn", 0) == 0:
            return "close" if "close" in valid else "hold"
        try:
            sa = int(st.get("since_adj", 10 ** 6))
        except (TypeError, ValueError):
            sa = 10 ** 6
        if sa < cool:
            return "hold"
        band = max(float(b_abs), float(b_rel) * abs(float(tg)))
        diff = abs(float(tg)) - float(w)
        if diff > band and "add" in valid:
            return {"add": diff}
        if -diff > band and "reduce" in valid and float(w) > 0:
            return {"reduce": min(1.0, -diff / float(w))}
        return "hold"
    return pol


def simulate_proxy(postbear: np.ndarray, frac: float,
                   theta: float = THETA) -> np.ndarray:
    """Standard-grid decay proxy (causal, per-coin, no fills/SL/TP).

    postbear: (n_bars, n_coins) post-bear book weights (NaN->0 inside).
    Returns proxy weights of the same shape: 0 on decay/flat bars, tg otherwise.
    State (side, w0) carries continuously in grid order (never reset per year).
    """
    w = np.nan_to_num(np.asarray(postbear, dtype=float), nan=0.0)
    n, na = w.shape
    out = np.zeros_like(w)
    side = np.zeros(na, dtype=int)
    w0 = np.full(na, np.nan)
    for i in range(n):
        for a in range(na):
            tg = float(w[i, a])
            atv = abs(tg)
            s = 0
            if np.isfinite(tg) and atv >= theta:
                s = 1 if tg > 0 else -1
            if side[a] == 0:
                if s != 0:
                    side[a] = s
                    w0[a] = atv
                    out[i, a] = tg
                else:
                    out[i, a] = 0.0
            else:
                if s == -side[a]:
                    side[a] = s
                    w0[a] = atv
                    out[i, a] = tg
                elif s == 0:
                    side[a] = 0
                    w0[a] = np.nan
                    out[i, a] = 0.0
                elif np.isfinite(w0[a]) and w0[a] > 0 and atv < float(frac) * w0[a]:
                    side[a] = 0
                    w0[a] = np.nan
                    out[i, a] = 0.0
                else:
                    out[i, a] = tg
    return out


def control_mult_per_year(ref_abs_sum: np.ndarray, var_abs_sum: np.ndarray) -> float:
    """Exposure-matched constant for one year: sum|var| / sum|ref| (1.0 if ref 0)."""
    r = float(np.sum(ref_abs_sum))
    v = float(np.sum(var_abs_sum))
    if not np.isfinite(r) or not np.isfinite(v) or r <= 0:
        return 1.0
    c = v / r
    if not np.isfinite(c) or c < 0:
        return 1.0
    return float(c)
