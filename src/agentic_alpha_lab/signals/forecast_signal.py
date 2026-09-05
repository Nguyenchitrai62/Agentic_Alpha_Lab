from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastSignal:
    bar_index: int
    signal_time: str
    direction: int
    label: str
    current_close: float
    predicted_close: float
    predicted_return: float
    threshold: float
    atr: float
    entry_limit: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float


def calculate_atr(candles: pd.DataFrame, end_index: int, window: int = 14) -> float:
    start = max(0, end_index - window)
    sample = candles.iloc[start : end_index + 1]
    previous_close = candles["close"].shift(1).iloc[start : end_index + 1]
    true_range = pd.concat(
        [
            sample["high"] - sample["low"],
            (sample["high"] - previous_close).abs(),
            (sample["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = float(true_range.dropna().tail(window).mean())
    if not np.isfinite(value) or value <= 0:
        raise ValueError("ATR is not positive")
    return value


def forecast_to_signal(
    candles: pd.DataFrame,
    bar_index: int,
    prediction: pd.DataFrame,
    threshold_bps: float = 12.0,
    atr_window: int = 14,
    entry_limit_offset_bps: float = 0.0,
    stop_atr: float = 1.25,
    tp1_atr: float = 1.0,
    tp2_atr: float = 2.0,
) -> ForecastSignal:
    """Convert a forecast path into an auditable bracket-order candidate."""
    current = float(candles["close"].iloc[bar_index])
    predicted_close = float(prediction["close"].iloc[-1])
    predicted_return = predicted_close / current - 1.0
    threshold = threshold_bps / 10_000.0
    direction = 1 if predicted_return > threshold else -1 if predicted_return < -threshold else 0
    label = "LONG" if direction == 1 else "SHORT" if direction == -1 else "WAIT"
    atr = calculate_atr(candles, bar_index, atr_window)
    atr_pct = atr / current
    offset = entry_limit_offset_bps / 10_000.0

    if direction == 1:
        entry = current * (1.0 - offset)
        forecast_favorable = max(0.0, float(prediction["high"].max()) / current - 1.0)
        forecast_adverse = max(0.0, 1.0 - float(prediction["low"].min()) / current)
        stop_distance = np.clip(max(stop_atr * atr_pct, forecast_adverse), 0.5 * atr_pct, 2.5 * atr_pct)
        tp1_distance = np.clip(max(0.5 * forecast_favorable, tp1_atr * atr_pct), 0.5 * atr_pct, 3.0 * atr_pct)
        tp2_distance = np.clip(max(forecast_favorable, tp2_atr * atr_pct), tp1_distance, 5.0 * atr_pct)
        stop_loss = entry * (1.0 - stop_distance)
        take_profit_1 = entry * (1.0 + tp1_distance)
        take_profit_2 = entry * (1.0 + tp2_distance)
    elif direction == -1:
        entry = current * (1.0 + offset)
        forecast_favorable = max(0.0, 1.0 - float(prediction["low"].min()) / current)
        forecast_adverse = max(0.0, float(prediction["high"].max()) / current - 1.0)
        stop_distance = np.clip(max(stop_atr * atr_pct, forecast_adverse), 0.5 * atr_pct, 2.5 * atr_pct)
        tp1_distance = np.clip(max(0.5 * forecast_favorable, tp1_atr * atr_pct), 0.5 * atr_pct, 3.0 * atr_pct)
        tp2_distance = np.clip(max(forecast_favorable, tp2_atr * atr_pct), tp1_distance, 5.0 * atr_pct)
        stop_loss = entry * (1.0 + stop_distance)
        take_profit_1 = entry * (1.0 - tp1_distance)
        take_profit_2 = entry * (1.0 - tp2_distance)
    else:
        entry = current
        stop_loss = current
        take_profit_1 = current
        take_profit_2 = current

    return ForecastSignal(
        bar_index=bar_index,
        signal_time=pd.Timestamp(candles["close_time"].iloc[bar_index]).isoformat(),
        direction=direction,
        label=label,
        current_close=current,
        predicted_close=predicted_close,
        predicted_return=predicted_return,
        threshold=threshold,
        atr=atr,
        entry_limit=float(entry),
        stop_loss=float(stop_loss),
        take_profit_1=float(take_profit_1),
        take_profit_2=float(take_profit_2),
    )


def signal_dict(signal: ForecastSignal) -> dict[str, object]:
    return asdict(signal)

