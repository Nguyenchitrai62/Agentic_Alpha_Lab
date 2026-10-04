"""Bitfinex margin-positioning fetcher (new-data round A, tag bitfinex, 2026-10-04).

Public endpoints only. Polite: >=3 s between requests, exponential backoff on
429/5xx. Resumable: per-key checkpoint of next_start_ms + appended raw JSONL;
re-running continues where it left off and rebuilds the parquet + manifest.

Source: https://api-pub.bitfinex.com/v2/stats1/{key}/hist
Keys: pos.size:1h:t{SYM}:{long,short} for BTCUSD, ETHUSD, XRPUSD, SOLUSD.
BNB has no Bitfinex margin market (probed 2026-10-04: empty history for
tBNBUSD/tBNBUSDT long/short) -> no native BNB series; BNB rows use BTC-wide
features in the study. Funding-book keys (credits.size:1h:...) are probed and
the outcome recorded in the manifest; only non-empty keys are fetched.

Publication-lag assumption (documented in manifest + feature module): a value
stamped h is usable from h + 1h. The study joins strictly before the fill
minute on availability time = stamp + 1h.

Usage:
    .venv/Scripts/python.exe data/raw/bitfinex_20261004/fetch_bitfinex.py
    .venv/Scripts/python.exe data/raw/bitfinex_20261004/fetch_bitfinex.py --probe-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api-pub.bitfinex.com/v2/stats1"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
LIMIT = 10000
SLEEP_S = 3.0
MAX_RETRIES = 12

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
CKPT_DIR = HERE / "checkpoints"
PARQUET = HERE / "bitfinex_margin_1h.parquet"
MANIFEST = HERE / "manifest.json"

PAIRS = {"BTC": "tBTCUSD", "ETH": "tETHUSD", "XRP": "tXRPUSD", "SOL": "tSOLUSD"}
SIDES = ("long", "short")
KEYS = [f"pos.size:1h:{PAIRS[s]}:{side}" for s in PAIRS for side in SIDES]

FUNDING_CANDIDATES = [
    "credits.size:1h:fUSD:long",
    "credits.size:1h:fUSD:short",
    "credits.size:1h:fUSD",
    "credits.size:1h:fUSD:tBTCUSD",
]


def _get(session: requests.Session, url: str, params: dict) -> list:
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, params=params, timeout=60)
        except requests.RequestException:
            time.sleep(min(600, (2 ** attempt) * 10))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(600, (2 ** attempt) * 15))
            continue
        r.raise_for_status()
    raise RuntimeError(f"GET failed after retries: {url} {params}")


def probe_key(session: requests.Session, key: str, n: int = 2) -> list:
    time.sleep(SLEEP_S)
    return _get(session, f"{API}/{key}/hist", {"limit": n, "sort": 1})


def fetch_key(session: requests.Session, key: str) -> list[list]:
    safe = key.replace(":", "_").replace(".", "_")
    ckpt = CKPT_DIR / f"{safe}.json"
    out_path = RAW_DIR / f"{safe}.jsonl"
    next_start = None
    if ckpt.exists():
        next_start = json.loads(ckpt.read_text()).get("next_start_ms")
    mode = "ab" if (next_start is not None and out_path.exists()) else "wb"
    n_new = 0
    with open(out_path, mode) as f:
        while True:
            params = {"limit": LIMIT, "sort": 1}
            if next_start is not None:
                params["start"] = next_start
            time.sleep(SLEEP_S)
            rows = _get(session, f"{API}/{key}/hist", params)
            if not rows:
                break
            for mts, val in rows:
                f.write((json.dumps([int(mts), float(val)]) + "\n").encode())
            n_new += len(rows)
            last = int(rows[-1][0])
            nxt = last + 1
            if nxt == next_start or len(rows) < LIMIT:
                next_start = nxt
                ckpt.write_text(json.dumps({"next_start_ms": next_start, "done": len(rows) < LIMIT}))
                break
            next_start = nxt
            ckpt.write_text(json.dumps({"next_start_ms": next_start, "done": False}))
    rows: list[list] = []
    with open(out_path, "rb") as f:
        for line in f:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r[0])
    # de-duplicate by mts (keep last on re-fetch overlap)
    dedup: dict[int, float] = {}
    for mts, val in rows:
        dedup[int(mts)] = float(val)
    return [[k, v] for k, v in sorted(dedup.items())]


def build_parquet(all_rows: dict[str, list[list]]) -> None:
    import pandas as pd

    frames = {}
    for key, rows in all_rows.items():
        ts = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
        vals = pd.Series([r[1] for r in rows], index=ts).sort_index()
        vals = vals[~vals.index.duplicated(keep="last")]
        if key.startswith("credits"):
            frames["FUSD"] = vals
            continue
        # key = pos.size:1h:tBTCUSD:long
        parts = key.split(":")
        pair, side = parts[2], parts[3]
        sym = next(s for s, p in PAIRS.items() if p == pair)
        frames[f"{sym}_{side}"] = vals
    panel = pd.DataFrame(frames).sort_index()
    panel.index.name = "ts"
    panel.to_parquet(PARQUET)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. funding-book availability probe (small requests)
    funding_probe: dict[str, object] = {}
    for key in FUNDING_CANDIDATES:
        try:
            rows = probe_key(session, key, 1)
            funding_probe[key] = {"n_probe_rows": len(rows), "sample": rows[:1]}
        except Exception as exc:  # noqa: BLE001 - record and continue
            funding_probe[key] = {"error": repr(exc)[:200]}
    fetchable_funding = [
        k for k, v in funding_probe.items()
        if isinstance(v, dict) and int(v.get("n_probe_rows", 0)) > 0
    ]
    if args.probe_only:
        print(json.dumps({"keys_sample": "skipped", "funding_probe": funding_probe}, indent=1)[:2000])
        return

    # 2. full fetch of margin keys (+ any non-empty funding keys)
    t0 = datetime.now(timezone.utc).isoformat()
    all_rows: dict[str, list[list]] = {}
    per_key: dict[str, dict[str, object]] = {}
    for key in KEYS + fetchable_funding:
        rows = fetch_key(session, key)
        all_rows[key] = rows
        per_key[key] = {
            "n": len(rows),
            "first": datetime.fromtimestamp(rows[0][0] / 1000, timezone.utc).isoformat() if rows else None,
            "last": datetime.fromtimestamp(rows[-1][0] / 1000, timezone.utc).isoformat() if rows else None,
        }
        print(f"{key}: {len(rows)} rows", flush=True)

    build_parquet(all_rows)

    sha = hashlib.sha256(PARQUET.read_bytes()).hexdigest()
    import pandas as pd

    panel = pd.read_parquet(PARQUET)
    manifest = {
        "source": API + "/{key}/hist?limit=10000&sort=1&start=..&end=..",
        "keys": KEYS,
        "funding_probe": funding_probe,
        "funding_fetched": fetchable_funding,
        "rows": int(len(panel)),
        "columns": list(panel.columns),
        "first": panel.index.min().isoformat(),
        "last": panel.index.max().isoformat(),
        "sha256": sha,
        "per_key": per_key,
        "availability": "hourly snapshot stamped h covers [h, h+1h); use only from h + 1h (safety lag).",
        "rate_limit": f"<=1 request / 2 s required; used {SLEEP_S} s + exp backoff.",
        "notes": "BNB has no Bitfinex margin market (empty history); no native BNB series.",
        "fetched_at": t0,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(f"wrote {PARQUET} ({len(panel)} rows) + manifest")


if __name__ == "__main__":
    main()
