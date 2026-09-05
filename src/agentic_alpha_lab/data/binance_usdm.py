from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


BASE_URL = "https://fapi.binance.com"
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "num_trades",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]
INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "8h": 28_800_000,
    "1d": 86_400_000,
}


@dataclass(frozen=True)
class DataQuality:
    rows: int
    first_open_time: str
    last_close_time: str
    duplicate_open_times: int
    missing_intervals: int
    invalid_ohlc_rows: int
    non_positive_price_rows: int


def _to_utc_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def get_server_time(session: requests.Session | None = None) -> int:
    client = session or requests.Session()
    response = client.get(f"{BASE_URL}/fapi/v1/time", timeout=30)
    response.raise_for_status()
    return int(response.json()["serverTime"])


def fetch_klines(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch closed Binance USD-M klines with deterministic pagination."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    client = session or requests.Session()
    server_time = get_server_time(client)
    start_ms = _to_utc_ms(start)
    requested_end_ms = _to_utc_ms(end) if end else server_time
    end_ms = min(requested_end_ms, server_time)
    step_ms = INTERVAL_MS[interval]
    rows: list[list[object]] = []

    cursor = start_ms
    while cursor < end_ms:
        response = client.get(
            f"{BASE_URL}/fapi/v1/klines",
            params={
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
            timeout=60,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + step_ms
        if next_cursor <= cursor:
            raise RuntimeError("Binance pagination did not advance")
        cursor = next_cursor
        if len(batch) < 1500:
            break
        time.sleep(0.05)

    if not rows:
        raise RuntimeError("Binance returned no klines for the requested range")

    frame = pd.DataFrame(rows, columns=KLINE_COLUMNS)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "num_trades",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")

    server_ts = pd.to_datetime(server_time, unit="ms", utc=True)
    frame = frame.loc[frame["close_time"] < server_ts].copy()
    frame = frame.drop(columns=["ignore"])
    frame = frame.drop_duplicates(subset=["open_time"], keep="last")
    frame = frame.sort_values("open_time").reset_index(drop=True)
    return frame


def validate_klines(frame: pd.DataFrame, interval: str) -> DataQuality:
    if frame.empty:
        raise ValueError("Kline frame is empty")
    required = {"open_time", "close_time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    gaps = frame["open_time"].sort_values().diff().dropna()
    invalid_ohlc = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    prices = frame[["open", "high", "low", "close"]]
    return DataQuality(
        rows=len(frame),
        first_open_time=frame["open_time"].min().isoformat(),
        last_close_time=frame["close_time"].max().isoformat(),
        duplicate_open_times=int(frame["open_time"].duplicated().sum()),
        missing_intervals=int((gaps > expected).sum()),
        invalid_ohlc_rows=int(invalid_ohlc.sum()),
        non_positive_price_rows=int((prices <= 0).any(axis=1).sum()),
    )


def update_dataset(
    output_path: Path,
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    days: int = 30,
) -> tuple[pd.DataFrame, DataQuality]:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing: pd.DataFrame | None = None
    if output_path.exists():
        existing = pd.read_parquet(output_path)
        existing["open_time"] = pd.to_datetime(existing["open_time"], utc=True)
        existing["close_time"] = pd.to_datetime(existing["close_time"], utc=True)

    now = datetime.now(timezone.utc)
    default_start = now - timedelta(days=days)
    if existing is not None and not existing.empty:
        tail_start = existing["open_time"].max().to_pydatetime() - timedelta(minutes=10)
        existing_start = existing["open_time"].min().to_pydatetime()
        start = tail_start if existing_start <= default_start else default_start
    else:
        start = default_start

    fresh = fetch_klines(symbol=symbol, interval=interval, start=start, end=now)
    if existing is not None:
        frame = pd.concat([existing, fresh], ignore_index=True)
        cutoff = pd.Timestamp(default_start)
        frame = frame.loc[frame["open_time"] >= cutoff].copy()
    else:
        frame = fresh

    frame = frame.drop_duplicates(subset=["open_time"], keep="last")
    frame = frame.sort_values("open_time").reset_index(drop=True)
    quality = validate_klines(frame, interval)
    if quality.duplicate_open_times or quality.invalid_ohlc_rows or quality.non_positive_price_rows:
        raise ValueError(f"Dataset failed quality checks: {quality}")

    frame.to_parquet(output_path, index=False)
    manifest = {
        "source": "binance_usdm_rest",
        "symbol": symbol.upper(),
        "interval": interval,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "quality": asdict(quality),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return frame, quality
