"""Causal closed-candle flow/activity features from existing public kline fields."""
import numpy as np
import pandas as pd


def flow_features(candles, decision_times, timeframes=("5min", "15min", "1h", "4h", "1d")):
    required = ["volume", "quote_volume", "taker_buy_volume", "num_trades"]
    if not np.isfinite(candles[required].to_numpy()).all() or (candles[required] < 0).any().any():
        raise ValueError("Invalid flow/activity fields")
    if (candles.taker_buy_volume > candles.volume * (1 + 1e-6)).any():
        raise ValueError("Buy volume exceeds total volume")
    frame = candles.set_index("open_time").sort_index()
    if frame.index.has_duplicates or (frame.index.asi8 % pd.Timedelta(minutes=5).value != 0).any():
        raise ValueError("Invalid candle grid")
    if not (pd.to_datetime(frame.close_time, utc=True).array == frame.index + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)).all():
        raise ValueError("Invalid close time")
    query = pd.DataFrame({"as_of": pd.to_datetime(decision_times, utc=True), "order": np.arange(len(decision_times))})
    outputs, names = [], []
    for rule in timeframes:
        ratio = pd.Timedelta(rule) / pd.Timedelta(minutes=5)
        if ratio < 1 or int(ratio) != ratio:
            raise ValueError("Invalid timeframe")
        grouped = frame.resample(rule, closed="left", label="left", origin="epoch")
        sums = grouped[required].sum()
        sums = sums.loc[grouped.volume.count() == int(ratio)]
        if (sums.index.to_series().diff().dropna() != pd.Timedelta(rule)).any():
            raise ValueError("Gap in closed aggregated flow bars")
        vol, buy, trades = sums.volume, sums.taker_buy_volume, sums.num_trades
        eps = 1e-12
        values = pd.DataFrame({
            "buy_imbalance_1": (2 * buy / vol.clip(lower=eps) - 1).where(vol > 0, 0),
            "buy_imbalance_12": (2 * buy.rolling(12).sum() / vol.rolling(12).sum().clip(lower=eps) - 1).where(vol.rolling(12).sum() > 0, 0),
            "buy_imbalance_30": (2 * buy.rolling(30).sum() / vol.rolling(30).sum().clip(lower=eps) - 1).where(vol.rolling(30).sum() > 0, 0),
            "trade_activity_1": np.log1p(trades) - np.log1p(trades.rolling(30).mean()),
            "trade_activity_3": np.log1p(trades.rolling(3).mean()) - np.log1p(trades.rolling(30).mean()),
            "volume_per_trade_relative": np.log1p(vol / trades.clip(lower=1)) - np.log1p((vol / trades.clip(lower=1)).rolling(30).mean()),
            "quote_volume_relative": np.log1p(sums.quote_volume) - np.log1p(sums.quote_volume.rolling(30).mean()),
            "volume_growth_3": np.log1p(vol.rolling(3).mean()) - np.log1p(vol.rolling(12).mean()),
        }, index=sums.index)
        values["known_at"] = sums.index + pd.Timedelta(rule) - pd.Timedelta(milliseconds=1)
        columns = [c for c in values if c != "known_at"]
        aligned = pd.merge_asof(query.sort_values("as_of"), values.reset_index(drop=True),
                                left_on="as_of", right_on="known_at", direction="backward").sort_values("order")
        if aligned.known_at.isna().any() or (aligned.as_of - aligned.known_at >= pd.Timedelta(rule)).any():
            raise ValueError("Stale or missing completed flow context")
        x = aligned[columns].to_numpy(np.float32)
        if not np.isfinite(x).all():
            raise ValueError("Insufficient flow warmup")
        outputs.append(x)
        names.extend(f"{rule}:{c}" for c in columns)
    return np.concatenate(outputs, axis=1), names
