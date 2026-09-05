"""Versioned, as-of features and purged chronological supervised datasets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.data.timeframes import resample_closed_ohlcv


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_source(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles.copy()
    for column in ("open_time", "close_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame = frame.sort_values("open_time").reset_index(drop=True)
    if frame.empty or frame.open_time.duplicated().any():
        raise ValueError("Empty or duplicate source candles")
    if not frame.open_time.diff().dropna().eq(pd.Timedelta(minutes=5)).all():
        raise ValueError("Source must contain contiguous 5m candles; do not forward-fill gaps")
    values = frame[["open", "high", "low", "close", "volume", "quote_volume"]]
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError("Source contains non-finite values")
    if (values.iloc[:, :4] <= 0).any().any() or (values.iloc[:, 4:] < 0).any().any():
        raise ValueError("Invalid prices or volumes")
    if (frame.high < frame[["open", "close", "low"]].max(axis=1)).any() or (
        frame.low > frame[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("Invalid OHLC bounds")
    resample_closed_ohlcv(frame, "5min")  # validates UTC grid and close timestamps
    if frame.close_time.iloc[-1] >= pd.Timestamp.now(tz="UTC"):
        raise ValueError("Source includes an unclosed candle")
    return frame


def make_features(candles: pd.DataFrame, timeframes: list[str]) -> pd.DataFrame:
    """Every right-hand candle is complete at the left-hand decision timestamp."""
    result = candles[["close_time", "close"]].rename(columns={"close_time": "signal_time"}).copy()
    result["bar_index"] = np.arange(len(candles))
    for rule in timeframes:
        frame = resample_closed_ohlcv(candles, rule)
        close = frame.close
        previous = close.shift(1)
        true_range = pd.concat([frame.high - frame.low, (frame.high - previous).abs(),
                                (frame.low - previous).abs()], axis=1).max(axis=1)
        prefix = f"x_{rule}_"
        features = pd.DataFrame({"available_at": frame.close_time})
        for lag in (1, 3, 12):
            features[prefix + f"return_{lag}"] = close.pct_change(lag, fill_method=None)
        features[prefix + "range"] = (frame.high - frame.low) / close
        features[prefix + "body"] = (close - frame.open) / frame.open
        features[prefix + "atr"] = true_range.rolling(14).mean() / close
        features[prefix + "volatility"] = np.log(close).diff().rolling(14).std()
        features[prefix + "trend"] = close / close.rolling(14).mean() - 1
        features[prefix + "volume_ratio"] = frame.volume / frame.volume.rolling(14).mean().replace(0, np.nan) - 1
        result = pd.merge_asof(result, features, left_on="signal_time", right_on="available_at",
                               direction="backward", allow_exact_matches=True).drop(columns="available_at")
    return result


def make_examples(candles: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = make_features(candles, config["timeframes"])
    band = config["wait_band_bps"] / 10_000
    if band <= 2 * config["costs"]["fee_rate_per_fill"]:
        raise ValueError("WAIT band must exceed round-trip fees")
    for horizon in config["horizons"]:
        returns = candles.close.shift(-horizon) / candles.close - 1
        result[f"y_return_{horizon}"] = returns
        # Class order is fixed even if a class is absent from a small split.
        result[f"y_direction_{horizon}"] = np.select([returns < -band, returns > band], [0, 2], default=1)
        future_high = candles.high.shift(-1).iloc[::-1].rolling(horizon).max().iloc[::-1]
        future_low = candles.low.shift(-1).iloc[::-1].rolling(horizon).min().iloc[::-1]
        # Unconditional excursions from current close, NOT post-limit-fill targets.
        result[f"y_up_excursion_{horizon}"] = (future_high / candles.close - 1).clip(lower=0)
        result[f"y_down_excursion_{horizon}"] = (1 - future_low / candles.close).clip(lower=0)
    offset = config["entry_offset_bps"] / 10_000
    result["y_long_touch"] = (candles.low.shift(-1) <= candles.close * (1 - offset)).astype(int)
    result["y_short_touch"] = (candles.high.shift(-1) >= candles.close * (1 + offset)).astype(int)
    # Includes next-bar entry + the timeout-open needed by the execution engine.
    result["label_end"] = candles.open_time.shift(-(max(config["horizons"]) + 1))
    return result.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def chronological_splits(examples: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
    fractions = np.asarray(config["split_fractions"], dtype=float)
    if len(fractions) != 4 or (fractions <= 0).any() or not np.isclose(fractions.sum(), 1):
        raise ValueError("Expected four positive fractions summing to one")
    embargo = int(config["embargo_bars"])
    if embargo < max(config["horizons"]) + 1:
        raise ValueError("Embargo must cover longest label/execution horizon")
    boundaries = [0, *[int(len(examples) * f) for f in np.cumsum(fractions)[:-1]], len(examples)]
    splits = {}
    for i, name in enumerate(("train", "validation", "calibration", "test")):
        part = examples.iloc[boundaries[i]:boundaries[i + 1]].copy()
        if i:
            start = examples.signal_time.iloc[boundaries[i]] + pd.Timedelta(minutes=5 * embargo)
            part = part.loc[part.signal_time >= start]
        if i < 3:
            next_start = examples.signal_time.iloc[boundaries[i + 1]]
            part = part.loc[part.label_end < next_start]
        if len(part) < 32:
            raise ValueError(f"Too few {name} rows after purge/embargo ({len(part)}); acquire more history")
        splits[name] = part.reset_index(drop=True)
    return splits


def verified_split(root: Path, name: str, manifest: dict | None = None) -> pd.DataFrame:
    if name not in {"train", "validation", "calibration", "test"}:
        raise ValueError("Unknown split")
    manifest = manifest or json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    path = root / f"{name}.parquet"
    if sha256(path) != manifest["files"][path.name]:
        raise ValueError(f"Hash mismatch: {path.name}")
    return pd.read_parquet(path)
