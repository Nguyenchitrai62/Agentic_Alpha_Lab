"""As-of multi-frame windows and execution-aware candidate labels (no oracle prices)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.timeframes import resample_closed_ohlcv

FIELDS = ["open", "high", "low", "close", "volume", "quote_volume"]


def candidates(config: dict) -> np.ndarray:
    # Fixed ex ante: side, offset bps, SL ATR, TP1 ATR, TP2 ATR.
    return np.asarray([[side, offset, *bracket] for side in (1, -1)
                       for offset in config["entry_offsets_bps"]
                       for bracket in config["brackets_atr"]], dtype=np.float32)


def bracket_prices(close: float, atr: float, candidate: np.ndarray, config: dict) -> dict:
    side, offset, stop, tp1, tp2 = map(float, candidate)
    if not np.isfinite([close, atr, side, offset, stop, tp1, tp2]).all():
        raise ValueError("Non-finite bracket")
    if close <= 0 or atr <= 0 or side not in (-1, 1) or offset < 0 or stop <= 0 or not 0 < tp1 < tp2:
        raise ValueError("Invalid bracket")
    entry = close * (1 - side * offset / 10_000)
    unit = max(atr, close * config["minimum_risk_bps"] / 10_000)
    result = {"direction": int(side), "entry_limit": entry, "stop_loss": entry - side * stop * unit,
              "take_profit_1": entry + side * tp1 * unit, "take_profit_2": entry + side * tp2 * unit,
              "leverage": 1.0}
    if min(result[k] for k in ("entry_limit", "stop_loss", "take_profit_1", "take_profit_2")) <= 0:
        raise ValueError("Non-positive bracket price")
    return result


class WindowStore:
    def __init__(self, candles: pd.DataFrame, config: dict):
        self.config = config
        self.frames = [resample_closed_ohlcv(candles, tf) for tf in config["timeframes"]]
        self.values = [f[FIELDS].to_numpy(np.float32) for f in self.frames]
        self.ends = [pd.DatetimeIndex(f.close_time).asi8 for f in self.frames]
        self.stamps = []
        for frame in self.frames:
            t = frame.open_time.dt
            self.stamps.append(np.stack([t.minute, t.hour, t.dayofweek, t.day, t.month], -1).astype(np.float32))

    def at(self, as_of: pd.Timestamp) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        windows, stamps, ages = [], [], []
        length = self.config["context"]
        for tf, values, times, ends in zip(self.config["timeframes"], self.values, self.stamps, self.ends):
            end = int(np.searchsorted(ends, pd.Timestamp(as_of).value, side="right"))
            if end < length:
                raise ValueError("Insufficient closed multi-frame history")
            windows.append(values[end-length:end])
            stamps.append(times[end-length:end])
            ages.append((pd.Timestamp(as_of).value - ends[end-1]) / pd.Timedelta(tf).value)
        return np.stack(windows), np.stack(stamps), np.asarray(ages, np.float32)


def atr_series(candles: pd.DataFrame) -> pd.Series:
    previous = candles.close.shift(1)
    return pd.concat([candles.high - candles.low, (candles.high - previous).abs(),
                      (candles.low - previous).abs()], axis=1).max(axis=1).rolling(14).mean()


def candidate_labels(candles: pd.DataFrame, index: int, atr: float, config: dict) -> np.ndarray:
    """Net percent / OHLC fill / positive-net outcome; WAIT has zero payoff.

    Reuse the exact portfolio engine, on one candidate at a time at equity 100.
    Future bars enter labels only, never the candidate construction or features.
    """
    horizon = config["holding_bars"]
    window = candles.iloc[index:index + horizon + 2].reset_index(drop=True)
    if len(window) != horizon + 2:
        raise ValueError("Truncated label horizon")
    labels = []
    for candidate in candidates(config):
        signal = bracket_prices(float(window.close.iloc[0]), atr, candidate, config)
        signal["bar_index"] = 0
        result, trades = run_backtest(window, pd.DataFrame([signal]), initial_equity=100,
                                     costs=CostModel(**config["costs"]),
                                     execution=ExecutionConfig(max_holding_bars=horizon))
        labels.append([result.net_profit, float(bool(trades)), float(result.net_profit > 0)])
    return np.asarray(labels, dtype=np.float32)


def decode_suggestion(prediction: np.ndarray, close: float, atr: float, config: dict) -> dict:
    """Columns: mean net %, ordered q10/q50/q90 %, fill logit, win logit."""
    expected = (len(candidates(config)), 6)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"Expected finite prediction {expected}")
    win = 1 / (1 + np.exp(-np.clip(prediction[:, 5], -50, 50)))
    eligible = (prediction[:, 0] > config["minimum_net_bps"] / 100) & (win >= config["minimum_win_score"])
    if not eligible.any():
        return {"action": "WAIT", "reason": "No candidate passes fixed net/uncalibrated-score gates",
                "leverage": 1.0, "calibrated": False}
    chosen = int(np.argmax(np.where(eligible, prediction[:, 0], -np.inf)))
    row = prediction[chosen]
    return {"action": "LONG" if candidates(config)[chosen, 0] == 1 else "SHORT",
            "candidate_id": chosen, **bracket_prices(close, atr, candidates(config)[chosen], config),
            "expected_net_bps": float(row[0] * 100), "net_quantiles_bps": (row[1:4] * 100).tolist(),
            "ohlc_fill_score": float(1 / (1 + np.exp(-np.clip(row[4], -50, 50)))),
            "win_score": float(win[chosen]), "calibrated": False,
            "holding_bars": config["holding_bars"], "entry_expiry_bars": 1, "tp1_fraction": 0.5}
