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


# Rate limits (429), IP bans (418) and gateway errors are transient: one of them used to fail a whole web pipeline cycle,
# whose immediate retry then hit the rate limit again (2026-10-09: 25 failed cycles in a row).
TRANSIENT_STATUS = {418, 429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 5
RETRY_MAX_WAIT_S = 120.0


def _get(client, url: str, timeout: float, **kw) -> requests.Response:
    """GET with exponential backoff on connection errors and transient statuses (Retry-After honoured, capped)."""
    delay = 2.0
    for attempt in range(RETRY_ATTEMPTS):
        last = attempt == RETRY_ATTEMPTS - 1
        try:
            response = client.get(url, timeout=timeout, **kw)
        except (requests.ConnectionError, requests.Timeout):
            if last:
                raise
            time.sleep(delay)
            delay = min(2 * delay, 60.0)
            continue
        if response.status_code in TRANSIENT_STATUS and not last:
            try:
                wait = float(response.headers.get("Retry-After", delay))
            except (TypeError, ValueError):
                wait = delay
            time.sleep(min(max(wait, delay), RETRY_MAX_WAIT_S))
            delay = min(2 * delay, 60.0)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("unreachable")


def get_server_time(session: requests.Session | None = None) -> int:
    client = session or requests.Session()
    return int(_get(client, f"{BASE_URL}/fapi/v1/time", timeout=30).json()["serverTime"])


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
        response = _get(
            client,
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


def _ms_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def fetch_klines_cached(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime | None = None,
    session: requests.Session | None = None,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """fetch_klines backed by an on-disk store of closed klines (<cache_dir>/<SYMBOL>_<interval>.parquet).

    fetch_klines only ever returns closed candles, which Binance never changes, so only the ranges before and after the
    stored span are requested and the result equals fetch_klines(symbol, interval, start, end). The web plans used to
    re-download every 1m candle since each paper start on every 15-minute refresh (hundreds of requests per cycle).
    """
    if cache_dir is None:
        return fetch_klines(symbol, interval, start, end, session=session)
    client = session or requests.Session()
    step = INTERVAL_MS[interval]
    path = Path(cache_dir) / f"{symbol.upper()}_{interval}.parquet"
    try:
        stored = pd.read_parquet(path) if path.exists() else None
    except Exception:  # noqa: BLE001 - a damaged cache file is rebuilt from the exchange
        stored = None
    if stored is None or stored.empty:
        merged = fetch_klines(symbol, interval, start, end, session=client)
        changed = True
    else:
        def part(a_ms: int, b: datetime | None) -> pd.DataFrame | None:
            try:
                return fetch_klines(symbol, interval, _ms_dt(a_ms), b, session=client)
            except RuntimeError as exc:
                if "returned no klines" in str(exc):
                    return None
                raise

        first = int(stored["open_time"].min().value // 1_000_000)
        last = int(stored["open_time"].max().value // 1_000_000)
        start_ms = _to_utc_ms(start)
        end_ms = _to_utc_ms(end) if end else None
        head = part(start_ms, _ms_dt(first - 1)) if start_ms < first else None
        tail = part(last + step, end) if end_ms is None or end_ms >= last + step else None
        pieces = [p for p in (head, stored, tail) if p is not None and not p.empty]
        changed = len(pieces) > 1
        merged = pd.concat(pieces, ignore_index=True) if changed else stored
        merged = merged.drop_duplicates(subset=["open_time"], keep="last").sort_values("open_time").reset_index(drop=True)
    if changed:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{time.time_ns()}.tmp")
            merged.to_parquet(tmp, index=False)
            tmp.replace(path)
        except OSError:  # cache is best effort (e.g. the file is open in another process on Windows)
            tmp.unlink(missing_ok=True)
    lo = pd.Timestamp(_to_utc_ms(start), unit="ms", tz="UTC")
    keep = merged["open_time"] >= lo
    if end is not None:
        keep &= merged["open_time"] <= pd.Timestamp(_to_utc_ms(end), unit="ms", tz="UTC")
    out = merged.loc[keep].reset_index(drop=True)
    if out.empty:
        raise RuntimeError("Binance returned no klines for the requested range")
    return out


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
