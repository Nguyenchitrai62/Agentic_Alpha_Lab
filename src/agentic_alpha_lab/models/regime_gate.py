"""Causal regime filters, explicitly heuristic rather than calibrated probabilities."""
import numpy as np
from agentic_alpha_lab.data.swing import grid


def regime_mask(features, config, gate):
    x = np.asarray(features)
    side = grid(config)[:, 0]
    if gate == "none":
        return np.ones((len(x), len(side)), dtype=bool)
    # Each frame contributes8 fields; frame order5m,15m,1h,4h,1d.
    trend_long = (x[:, 38] > 0) & (x[:, 30] > 0)
    trend_short = (x[:, 38] < 0) & (x[:, 30] < 0)
    if gate == "trend":
        long, short = trend_long, trend_short
    elif gate == "confirmed_reversal_or_pullback":
        # Reversal requires recovery already visible, not merely a large drawdown.
        reversal_long = (x[:, 35] < -.15) & (x[:, 33] > 0) & (x[:, 25] > 0)
        reversal_short = (x[:, 36] > .20) & (x[:, 33] < 0) & (x[:, 25] < 0)
        pullback_long = trend_long & ((x[:, 17] < 0) | (x[:, 9] < 0))
        pullback_short = trend_short & ((x[:, 17] > 0) | (x[:, 9] > 0))
        long, short = reversal_long | pullback_long, reversal_short | pullback_short
    else:
        raise ValueError("Unknown regime gate")
    return np.where(side[None] > 0, long[:, None], short[:, None])


def apply_gate(predictions, features, config, gate):
    result = predictions.copy()
    eligible = regime_mask(features, config, gate)
    result[..., 0] = np.where(eligible, result[..., 0], -1e6)
    return result
