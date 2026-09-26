"""v91 helpers: pure weight math + 1m limit-fill rule (importable by tests).

Fill rule (assignment): limit at the 4h open price, filled only if a LATER 1m
bar trades THROUGH it within 15 minutes (maker fee), else market at minute-15
open with taker fee + slippage. Spot legs use perp 1m bars as proxy.
"""

from __future__ import annotations

import numpy as np

ALLOC = 1 / 3
TREND_LEV = 1.5
CARRY_LEV = 3.0
CAP = 1.2
N_ASSETS = 5


def book_weights(regime_sig: float, tsmom_sig: float, carry_on: float,
                 K: float, scale: float, is_btc: bool):
    """Perp/spot weight contribution of one asset at one bar (fractions of equity)."""
    perp = 0.0
    spot = 0.0
    if is_btc:
        perp += ALLOC * TREND_LEV * float(regime_sig) * float(scale)
    perp += ALLOC * TREND_LEV * float(K) * float(tsmom_sig) / N_ASSETS
    notion = ALLOC * CARRY_LEV * float(carry_on) / N_ASSETS / CAP
    perp -= notion
    spot += notion
    return perp, spot


def limit_filled(side: int, limit_px: float, highs: np.ndarray, lows: np.ndarray) -> bool:
    """True if a later 1m bar trades THROUGH the limit price.

    side>0 (buy): needs a bar with low STRICTLY below limit (pass-through).
    side<0 (sell): needs a bar with high STRICTLY above limit.
    Empty window -> False (goes to market). Touch-without-crossing does not fill.
    """
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    if highs.size == 0 or lows.size == 0:
        return False
    if not np.isfinite(limit_px):
        return False
    if side > 0:
        return bool(np.any(lows < limit_px))
    if side < 0:
        return bool(np.any(highs > limit_px))
    return False
