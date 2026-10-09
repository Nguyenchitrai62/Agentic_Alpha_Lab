"""Fetch Hyperliquid hourly funding history for the 5 majors (data_hlfunding).

Public keyless endpoint, polite (<= 2 req/s, backoff on 429):
  POST https://api.hyperliquid.xyz/info
  {"type": "fundingHistory", "coin": <coin>, "startTime": <ms>, "endTime": <ms>}

Pages by time (<= ~500 rows per response; cursor = last_time + 1; de-dup on
time). Range per coin: 2023-01-01 through the last complete UTC hour at fetch
time (the fetch itself discovers the first available row).

Outputs (ONLY data/raw/hyperliquid_20261007/):
  HL_<COIN>_funding_1h.parquet  (time UTC, fundingRate, premium)
  metaAndAssetCtxs_YYYYMMDDTHHMMSSZ.json (one snapshot, for the record)
  manifest.json (rows, first/last time, sha256, fetch window, endpoint)

Run: .venv/Scripts/python.exe research/tournament/data_hlfunding/fetch_hl_funding.py
"""

import datetime as dt
import hashlib
import json
import os
import time
import urllib.request

ENDPOINT = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
UA = {"User-Agent": "AgenticAlphaLab-data_hlfunding/1.0 (public fundingHistory pull, <=2rps)"}

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "raw", "hyperliquid_20261007")
os.makedirs(OUT, exist_ok=True)

FETCH_START_MS = 1672531200000  # 2023-01-01 00:00 UTC (before venue launch; fetch finds first row)


def _now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _floor_hour(ts):
    return ts.replace(minute=0, second=0, microsecond=0)


def post(payload, timeout=90, tries=7):
    data = json.dumps(payload).encode()
    wait = 2.0
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(ENDPOINT, method="POST", headers=dict(UA, **{"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
                if r.status == 429:
                    raise IOError("HTTP 429")
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - polite retry then raise
            last = e
            if "429" in str(e) or "Too Many" in str(e):
                time.sleep(wait)
                wait = min(wait * 2.0, 60.0)
            else:
                time.sleep(min(wait, 8.0))
                wait = min(wait * 1.5, 30.0)
    raise RuntimeError(f"POST failed after {tries} tries: {last} payload={payload}")


def fetch_coin(coin, end_ms):
    cursor = FETCH_START_MS
    rows = []
    pages = 0
    while True:
        time.sleep(0.6)  # <= 2 requests/second
        batch = post({"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms})
        pages += 1
        if not batch:
            break
        rows.extend(batch)
        last_t = int(batch[-1]["time"])
        print(f"  {coin} page {pages}: +{len(batch)} rows (last={last_t})", flush=True)
        if len(batch) < 500:
            break
        cursor = last_t + 1
        if cursor > end_ms:
            break
    # de-duplicate on time, keep first; sort ascending
    seen = {}
    for r in rows:
        t = int(r["time"])
        if t not in seen:
            seen[t] = r
    dedup = [seen[t] for t in sorted(seen)]
    print(f"  {coin}: {len(rows)} raw -> {len(dedup)} dedup over {pages} pages", flush=True)
    return dedup


def main():
    import pandas as pd

    fetched_at = _now_utc()
    end_hour = _floor_hour(fetched_at)
    end_ms = int(end_hour.timestamp() * 1000)
    print(f"fetch window: start={FETCH_START_MS} end(excl)={end_ms} ({end_hour.isoformat()})", flush=True)

    manifest = {
        "endpoint": ENDPOINT,
        "request_type": "fundingHistory",
        "fetch_start_ms": FETCH_START_MS,
        "fetch_end_ms": end_ms,
        "fetch_end_excl_utc": end_hour.isoformat(),
        "fetched_at_utc": fetched_at.isoformat(),
        "rate_limit": "<=2 req/s with backoff on 429",
        "page_note": "each response returns at most ~500 rows; cursor advanced past last row time; de-duplicated on time",
        "files": {},
    }

    for coin in COINS:
        print(f"fetching {coin} ...", flush=True)
        rows = fetch_coin(coin, end_ms)
        if not rows:
            print(f"  WARNING: no rows for {coin}", flush=True)
            continue
        df = pd.DataFrame({
            "time": pd.to_datetime([int(r["time"]) for r in rows], unit="ms", utc=True),
            "fundingRate": [float(r["fundingRate"]) for r in rows],
            "premium": [float(r["premium"]) for r in rows],
        }).sort_values("time").drop_duplicates(subset="time", keep="first").reset_index(drop=True)
        path = os.path.join(OUT, f"HL_{coin}_funding_1h.parquet")
        df.to_parquet(path, index=False)
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        manifest["files"][f"HL_{coin}_funding_1h.parquet"] = {
            "coin": coin,
            "rows": int(len(df)),
            "first": str(df["time"].iloc[0]),
            "last": str(df["time"].iloc[-1]),
            "sha256": sha,
        }

    # one metaAndAssetCtxs snapshot for the record
    time.sleep(0.6)
    snap = post({"type": "metaAndAssetCtxs"})
    snap_name = f"metaAndAssetCtxs_{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(os.path.join(OUT, snap_name), "w", encoding="utf-8") as f:
        json.dump({"fetched_at_utc": fetched_at.isoformat(), "payload": snap}, f)
    with open(os.path.join(OUT, snap_name), "rb") as f:
        snap_sha = hashlib.sha256(f.read()).hexdigest()
    manifest["files"][snap_name] = {"kind": "metaAndAssetCtxs snapshot", "sha256": snap_sha}

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print("wrote manifest:", json.dumps({k: v.get("rows", v.get("kind")) for k, v in manifest["files"].items()}, indent=1), flush=True)


if __name__ == "__main__":
    main()
