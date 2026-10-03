"""Fetch Bybit USDT-perpetual 1m klines (public v5 kline endpoint), research only.

Endpoint: GET https://api.bybit.com/v5/market/kline
  ?category=linear&symbol=<SYM>&interval=1&start=<ms>&end=<ms>&limit=1000
result.list rows = [startTime ms, open, high, low, close, volume, turnover],
NEWEST FIRST. Public endpoint, no credentials, never places orders.

Symbols BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT; range 2021-06-01 00:00
UTC (or the symbol's first available minute) .. the last CLOSED minute at run
time. Polite (<= 5 requests/second), retries with backoff on HTTP errors /
retCode != 0, resumable (re-running fetches only what is missing).

Output: data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet with columns
open_time (UTC, ms int64), open, high, low, close, volume, turnover (float64),
sorted, no duplicates; plus manifest.json (per symbol first/last open_time,
rows, sha256, missing minute ranges inside the range).

  python scripts/fetch_bybit_klines.py [--symbols BTCUSDT ETHUSDT ...] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data/raw/bybit_linear_1m_20261004"

BASE_URL = "https://api.bybit.com/v5/market/kline"
CATEGORY = "linear"
INTERVAL = "1"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
START_MS = int(datetime(2021, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
MINUTE_MS = 60_000
CHUNK_MINUTES = 1000  # == API limit per request

MIN_INTERVAL_S = 0.21  # <= 5 requests/second
MAX_RETRIES = 6
BACKOFF_BASE_S = 2.0

COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "turnover"]
PRICE_COLS = ["open", "high", "low", "close", "volume", "turnover"]

EMPTY_FRAME = pd.DataFrame(
    {c: pd.Series(dtype="int64" if c == "open_time" else "float64") for c in COLUMNS}
)


def last_closed_minute_ms(now_ms: int | None = None) -> int:
    """Open time (ms) of the last fully CLOSED 1m kline at run time."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    return (now_ms // MINUTE_MS - 1) * MINUTE_MS


def parse_kline_list(rows: list) -> pd.DataFrame:
    """Parse raw result.list rows (NEWEST FIRST) into a sorted, de-duplicated frame."""
    if not rows:
        return EMPTY_FRAME.copy()
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])
    df["open_time"] = df["open_time"].astype("int64")
    for c in PRICE_COLS:
        df[c] = df[c].astype("float64")
    df = df.sort_values("open_time", kind="stable").drop_duplicates("open_time", keep="first")
    return df[COLUMNS].reset_index(drop=True)


def merge_klines(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Union two frames: sorted by open_time, no duplicates (keeps existing)."""
    if existing is None or len(existing) == 0:
        out = new
    elif new is None or len(new) == 0:
        out = existing
    else:
        out = pd.concat([existing, new], ignore_index=True)
        out = out.sort_values("open_time", kind="stable").drop_duplicates("open_time", keep="first")
    return out[COLUMNS].reset_index(drop=True)


def chunk_ranges(start_ms: int, end_ms: int, chunk_minutes: int = CHUNK_MINUTES) -> list[tuple[int, int]]:
    """Split [start_ms, end_ms] into consecutive minute-aligned [chunk_start, chunk_end] windows."""
    chunks = []
    cur = start_ms
    while cur <= end_ms:
        ce = min(cur + (chunk_minutes - 1) * MINUTE_MS, end_ms)
        chunks.append((cur, ce))
        cur = ce + MINUTE_MS
    return chunks


def chunks_to_fetch(
    existing_ms: set[int],
    start_ms: int,
    end_ms: int,
    known_first_ms: int | None = None,
    chunk_minutes: int = CHUNK_MINUTES,
) -> list[tuple[int, int]]:
    """Chunks that still need fetching: any expected minute absent from existing.

    Chunks fully covered by existing data are skipped (resume). Chunks ending
    before known_first_ms (pre-listing emptiness recorded in the manifest) are
    skipped as well.
    """
    todo = []
    for cs, ce in chunk_ranges(start_ms, end_ms, chunk_minutes):
        if known_first_ms is not None and ce < known_first_ms:
            continue
        m = cs
        complete = True
        while m <= ce:
            if m not in existing_ms:
                complete = False
                break
            m += MINUTE_MS
        if not complete:
            todo.append((cs, ce))
    return todo


def find_missing_ranges(existing_ms_sorted, first_ms: int, end_ms: int, max_ranges: int = 10000) -> list[list[int]]:
    """Coalesced [start_ms, end_ms] minute ranges absent strictly inside [first_ms, end_ms]."""
    have = set(int(m) for m in existing_ms_sorted)
    gaps = []
    g0 = None
    m = first_ms
    while m <= end_ms:
        if m not in have:
            if g0 is None:
                g0 = m
        else:
            if g0 is not None:
                gaps.append([g0, m - MINUTE_MS])
                if len(gaps) >= max_ranges:
                    return gaps
                g0 = None
        m += MINUTE_MS
    if g0 is not None:
        gaps.append([g0, end_ms])
    return gaps


def fetch_chunk(session: requests.Session, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Fetch one chunk with retry/backoff; raises RuntimeError after MAX_RETRIES."""
    params = {"category": CATEGORY, "symbol": symbol, "interval": INTERVAL,
              "start": start_ms, "end": end_ms, "limit": 1000}
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(BASE_URL, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            if body.get("retCode") != 0:
                last_err = f"retCode={body.get('retCode')} retMsg={body.get('retMsg')}"
                raise RuntimeError(last_err)
            return parse_kline_list(body["result"]["list"])
        except Exception as exc:  # noqa: BLE001 - retried below
            last_err = exc
            time.sleep(BACKOFF_BASE_S * (2 ** attempt))
    raise RuntimeError(f"bybit kline failed {symbol} {start_ms}..{end_ms}: {last_err}")


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_symbol(session: requests.Session, symbol: str, out_dir: Path, end_ms: int,
               checkpoint_every: int = 50) -> dict:
    """Fetch one symbol resumably; writes parquet + returns manifest entry."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_1m.parquet"
    existing = pd.read_parquet(path) if path.exists() else EMPTY_FRAME.copy()
    if len(existing):
        existing = existing.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
        existing["open_time"] = existing["open_time"].astype("int64")
    known_first = int(existing["open_time"].min()) if len(existing) else None
    have = set(int(m) for m in existing["open_time"].tolist()) if len(existing) else set()
    todo = chunks_to_fetch(have, START_MS, end_ms, known_first)
    print(f"{symbol}: have={len(have)} chunks_to_fetch={len(todo)}", flush=True)
    last_req = [0.0]
    acc = existing
    for i, (cs, ce) in enumerate(todo):
        dt = time.monotonic() - last_req[0]
        if dt < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - dt)
        frame = fetch_chunk(session, symbol, cs, ce)
        last_req[0] = time.monotonic()
        if len(frame):
            acc = merge_klines(acc, frame)
        if (i + 1) % checkpoint_every == 0 or i + 1 == len(todo):
            acc.to_parquet(path, index=False)
            print(f"{symbol}: {i + 1}/{len(todo)} chunks rows={len(acc)}", flush=True)
    if len(acc) == 0:
        raise RuntimeError(f"{symbol}: no data returned in range")
    acc = acc.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
    acc.to_parquet(path, index=False)
    first_ms, last_ms = int(acc["open_time"].min()), int(acc["open_time"].max())
    gaps = find_missing_ranges(acc["open_time"].tolist(), first_ms, end_ms)
    entry = {
        "first_open_time": ms_to_iso(first_ms),
        "first_open_time_ms": first_ms,
        "last_open_time": ms_to_iso(last_ms),
        "last_open_time_ms": last_ms,
        "rows": int(len(acc)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "missing_ranges": [[ms_to_iso(a), ms_to_iso(b)] for a, b in gaps],
        "missing_ranges_ms": gaps,
        "n_missing_minutes": int(sum((b - a) // MINUTE_MS + 1 for a, b in gaps)),
    }
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    end_ms = last_closed_minute_ms()
    print(f"range 2021-06-01 .. {ms_to_iso(end_ms)} symbols={args.symbols}", flush=True)
    mf_path = out_dir / "manifest.json"
    manifest = json.loads(mf_path.read_text()) if mf_path.exists() else {
        "source": f"{BASE_URL}?category={CATEGORY}&interval={INTERVAL} (1m linear perps)",
        "range_start": "2021-06-01T00:00:00Z",
        "range_end": ms_to_iso(end_ms),
        "range_end_ms": end_ms,
        "symbols": {},
    }
    manifest["range_end"] = ms_to_iso(end_ms)
    manifest["range_end_ms"] = end_ms
    session = requests.Session()
    try:
        for sym in args.symbols:
            try:
                manifest["symbols"][sym] = run_symbol(session, sym, out_dir, end_ms)
            except Exception as exc:  # recorded, never silently skipped
                manifest["symbols"][sym] = {"error": repr(exc)[:300]}
                print(sym, "ERROR", repr(exc)[:300], flush=True)
            mf_path.write_text(json.dumps(manifest, indent=1))
    finally:
        session.close()
    print(json.dumps({s: {k: v for k, v in e.items() if k != "missing_ranges_ms"}
                      for s, e in manifest["symbols"].items()}, indent=1)[:2000], flush=True)


if __name__ == "__main__":
    main()
