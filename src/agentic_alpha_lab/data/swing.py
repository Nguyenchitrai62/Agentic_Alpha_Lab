"""Medium-term, execution-aware labels and causal coarse-to-fine features."""
from __future__ import annotations
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.kronos_trading import WindowStore, atr_series


def grid(config):
    return np.asarray([[s, e, *b, d] for s in (1, -1) for e in config["entry_atr_5m"]
                       for b in config["brackets_atr_4h"] for d in config["holding_days"]], np.float32)


def prices(close, atr5, atr4, candidate, config):
    side, offset, stop, tp1, tp2, days = map(float, candidate)
    if not np.isfinite([close, atr5, atr4]).all() or min(close, atr5, atr4) <= 0:
        raise ValueError("Invalid price/ATR")
    unit = max(atr4, close * config["minimum_risk_fraction"])
    entry = close - side * offset * atr5
    levels = [entry - side * stop * unit, entry, entry + side * tp1 * unit, entry + side * tp2 * unit]
    if min(levels) <= 0 or not np.all(np.diff(levels) * side > 0):
        raise ValueError("Invalid ordered bracket")
    return {"direction": int(side), "entry_limit": entry, "stop_loss": levels[0],
            "take_profit_1": levels[2], "take_profit_2": levels[3], "holding_bars": int(days * 288), "leverage": 1.0}


def context_features(windows):
    """40 dimensionless past-only features; preserves drawdown/trend lost by z-scoring."""
    rows = []
    for w in windows:
        close = w[:, 3].astype(float)
        volume = w[:, 4].astype(float)
        rows.extend([close[-1] / close[-1-lag] - 1 for lag in (1, 3, 12)])
        rows.extend([close[-1] / w[:, 1].max() - 1, close[-1] / w[:, 2].min() - 1,
                     (w[-14:, 1] - w[-14:, 2]).mean() / close[-1],
                     close[-1] / close[-30:].mean() - 1,
                     volume[-1] / max(volume[-30:].mean(), 1e-8) - 1])
    return np.clip(np.asarray(rows, np.float32), -10, 10)


def fast_outcome(ohlc, funding_times, index, signal, config):
    """Fixed-1x scalar equivalent of ohlc-v2 labels (not a portfolio simulator).

    Tested against the reference engine. No liquidation at 1x. OHLC values are
    open/high/low/close, funding_times flags UTC boundaries. Returns net percent,
    fill indicator and positive-net outcome conditional on fill (mask if unfilled).
    """
    side, limit = signal["direction"], signal["entry_limit"]
    horizon, expiry = signal["holding_bars"], config["entry_expiry_bars"]
    if index + expiry + horizon >= len(ohlc):
        raise ValueError("Incomplete swing label horizon")
    entry_index, entry = None, None
    for i in range(index + 1, index + expiry + 1):
        op, hi, lo, _ = ohlc[i]
        if (side == 1 and lo <= limit) or (side == -1 and hi >= limit):
            entry_index = i
            entry = min(op, limit) if side == 1 else max(op, limit)
            break
    if entry_index is None:
        return np.asarray([0, 0, 0], np.float32)
    fee = config["costs"]["fee_rate_per_fill"]
    rate = config["costs"]["funding_long_rate"] if side == 1 else config["costs"]["funding_short_rate"]
    net, remaining, tp1_done = -fee, 1.0, False
    end = entry_index + horizon
    for i in range(entry_index, end):
        op, hi, lo, _ = ohlc[i]
        if i > entry_index and funding_times[i]:
            net -= op / entry * remaining * rate
        stop = signal["stop_loss"]
        if (side == 1 and lo <= stop) or (side == -1 and hi >= stop):
            fill = min(op, stop) if side == 1 else max(op, stop)
            net += (side * (fill / entry - 1) - fee * fill / entry) * remaining
            remaining = 0
            break
        allow = i != entry_index or (op <= limit if side == 1 else op >= limit)
        if allow:
            for target, fraction in ((signal["take_profit_1"], 0.5), (signal["take_profit_2"], remaining)):
                first = target == signal["take_profit_1"]
                if first and tp1_done:
                    continue
                if (side == 1 and hi >= target) or (side == -1 and lo <= target):
                    fill = max(op, target) if side == 1 else min(op, target)
                    fraction = 0.5 if first else remaining
                    net += (side * (fill / entry - 1) - fee * fill / entry) * fraction
                    remaining -= fraction
                    if first:
                        tp1_done = True
            if remaining <= 0:
                break
    if remaining > 0:
        op = ohlc[end, 0]
        if funding_times[end]:
            net -= op / entry * remaining * rate
        net += (side * (op / entry - 1) - fee * op / entry) * remaining
    return np.asarray([net * 100, 1, float(net > 0)], np.float32)


def funding_flags(candles, interval=8):
    t = candles.open_time.dt
    return ((t.hour % interval == 0) & (t.minute == 0) & (t.second == 0)).to_numpy()


def swing_labels(candles, index, atr5, atr4, config, ohlc=None, funding=None):
    ohlc = candles[["open", "high", "low", "close"]].to_numpy(float) if ohlc is None else ohlc
    funding = funding_flags(candles, config["costs"]["funding_interval_hours"]) if funding is None else funding
    return np.stack([fast_outcome(ohlc, funding, index,
                      prices(float(candles.close.iloc[index]), atr5, atr4, c, config), config) for c in grid(config)])


class SwingStore(WindowStore):
    def __init__(self, candles, config):
        super().__init__(candles, config)
        self.atr4 = atr_series(self.frames[3]).to_numpy()
        self.atr5 = atr_series(self.frames[0]).to_numpy()

    def sample(self, as_of):
        windows, stamps, ages = self.at(as_of)
        ends = [np.searchsorted(self.ends[i], pd.Timestamp(as_of).value, side="right") - 1 for i in (0, 3)]
        atr5, atr4 = float(self.atr5[ends[0]]), float(self.atr4[ends[1]])
        return windows, stamps, ages, context_features(windows), atr5, atr4


def choose(prediction, close, atr5, atr4, config):
    if prediction.shape != (len(grid(config)), 6) or not np.isfinite(prediction).all():
        raise ValueError("Bad swing prediction")
    fill = 1 / (1 + np.exp(-np.clip(prediction[:, 4], -40, 40)))
    expected = fill * prediction[:, 0]  # mean is conditional on OHLC fill
    policy = config["policy"]
    eligible = (expected >= policy["minimum_expected_net_percent"]) & (fill >= policy["minimum_fill_score"])
    if not eligible.any():
        return {"action": "WAIT", "calibrated": False}
    k = int(np.argmax(np.where(eligible, expected, -np.inf)))
    return {"action": "LONG" if grid(config)[k, 0] == 1 else "SHORT", "candidate_id": k,
            **prices(close, atr5, atr4, grid(config)[k], config), "expected_net_percent": float(expected[k]),
            "conditional_net_quantiles_percent": prediction[k, 1:4].tolist(), "ohlc_fill_score": float(fill[k]),
            "conditional_win_score": float(1 / (1 + np.exp(-np.clip(prediction[k, 5], -40, 40)))),
            "calibrated": False, "entry_expiry_bars": config["entry_expiry_bars"], "tp1_fraction": 0.5}
