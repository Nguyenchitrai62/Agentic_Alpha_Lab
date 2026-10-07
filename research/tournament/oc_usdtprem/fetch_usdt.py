"""oc_usdtprem: fetch USDT-USD 1h history (Coinbase; Kraken fallback).

Per PLAN.md: Coinbase Exchange public candles for USDT-USD, granularity 3600,
300 candles per request, <= 3 req/s, no key, listing date (2021) -> 2026-09-24,
into data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet with manifest
(source, sha256, row count, gaps, first/last). If Coinbase history is
unavailable, Kraken public OHLC USDTZUSD is the fallback; REPORT states which
source was used.

Schema mirrors data/raw/coinbase_20260925/*_1h.parquet:
open_time (UTC bar START), open, high, low, close, volume.

  python research/tournament/oc_usdtprem/fetch_usdt.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUTDIR = ROOT / "data/raw/coinbase_usdt_20261006"
OUT = OUTDIR / "USDT-USD_1h.parquet"
MANIFEST = OUTDIR / "manifest.json"

CB_URL = "https://api.exchange.coinbase.com/products/USDT-USD/candles"
KR_URL = "https://api.kraken.com/0/public/OHLC"

START = dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 9, 24, 0, 0, tzinfo=dt.timezone.utc)  # exclusive bound
CHUNK_H = 300
RATE_SLEEP = 0.45  # <= ~2.2 req/s, under the 3 req/s limit


def _get_json(url: str, params: dict, timeout: int = 30):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}", headers={"User-Agent": "oc_usdtprem/1.0"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"GET failed {url} {params}: {last}")


def fetch_coinbase() -> pd.DataFrame:
    rows: list[list] = []
    cur = START
    while cur < END:
        nxt = min(cur + dt.timedelta(hours=CHUNK_H), END)
        data = _get_json(CB_URL, {
            "granularity": 3600,
            "start": cur.isoformat(),
            "end": nxt.isoformat(),
        })
        if not isinstance(data, list):
            raise RuntimeError(f"unexpected coinbase payload: {str(data)[:200]}")
        rows.extend(data)
        time.sleep(RATE_SLEEP)
        cur = nxt
    if not rows:
        raise RuntimeError("coinbase returned no candles for USDT-USD")
    # payload: [time, low, high, open, close, volume]
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("open_time")
    df = df[(df["open_time"] >= START) & (df["open_time"] < END)]
    return df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def fetch_kraken() -> pd.DataFrame:
    # Kraken USDTZUSD, interval=60; paginated via `since`.
    out: list[list] = []
    since = int(START.timestamp())
    end_ts = int(END.timestamp())
    last_ts = None
    while True:
        data = _get_json(KR_URL, {"pair": "USDTZUSD", "interval": 60, "since": since})
        if data.get("error"):
            raise RuntimeError(f"kraken error: {data['error']}")
        res = data["result"]
        key = next(k for k in res if k != "last")
        candles = res[key]
        if not candles:
            break
        out.extend(candles)
        last_ts = int(res["last"])
        newest = max(int(c[0]) for c in candles)
        if newest >= end_ts - 3600 or last_ts <= since:
            break
        since = last_ts
        time.sleep(RATE_SLEEP)
    if not out:
        raise RuntimeError("kraken returned no candles for USDTZUSD")
    # [time, open, high, low, close, vwap, volume, count]
    df = pd.DataFrame(out, columns=["t", "open", "high", "low", "close",
                                    "vwap", "volume", "count"])
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["t"]), unit="s", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    df = df.dropna(subset=["close"]).sort_values("open_time")
    df = df[(df["open_time"] >= START) & (df["open_time"] < END)]
    return df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def gaps(df: pd.DataFrame) -> list[dict]:
    t = pd.to_datetime(df["open_time"], utc=True).sort_values().reset_index(drop=True)
    d = t.diff().dropna()
    out = []
    for i in d[d > pd.Timedelta(hours=1)].index:
        out.append({"after": str(t[i - 1]), "before": str(t[i]),
                    "missing_hours": int((t[i] - t[i - 1]).total_seconds() // 3600) - 1})
        if len(out) >= 50:
            out.append({"truncated": True, "total_gaps": int((d > pd.Timedelta(hours=1)).sum())})
            break
    return out


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    source = "coinbase:USDT-USD"
    try:
        df = fetch_coinbase()
    except Exception as e:  # noqa: BLE001
        print(f"coinbase fetch failed ({e}); trying kraken USDTZUSD", flush=True)
        df = fetch_kraken()
        source = "kraken:USDTZUSD"
    df.to_parquet(OUT)
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    manifest = {
        "source": source,
        "coinbase_url": CB_URL + "?granularity=3600&start=..&end=..",
        "requested_range": [str(START), str(END)],
        "file": "USDT-USD_1h.parquet",
        "rows": int(len(df)),
        "first": str(df["open_time"].iloc[0]),
        "last": str(df["open_time"].iloc[-1]),
        "sha256": sha,
        "n_gaps": int((pd.to_datetime(df['open_time'], utc=True).sort_values().reset_index(drop=True).diff() > pd.Timedelta(hours=1)).sum()),
        "gaps": gaps(df),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: v for k, v in manifest.items() if k != "gaps"}, indent=1))
    print(f"rows={len(df)} first={manifest['first']} last={manifest['last']}")


if __name__ == "__main__":
    main()
