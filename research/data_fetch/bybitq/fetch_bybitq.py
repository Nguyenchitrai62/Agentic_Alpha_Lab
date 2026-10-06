"""Bybit quarterly/dated futures + spot hourly fetch (PUBLIC endpoints only).

Assignment: docs/opencode/OPENCODE_W_data_bybitq.md
Writes ONLY: research/data_fetch/bybitq/ (this script, inventory, REPORT)
and data under data/raw/bybit_quarterly_20261006/ (gitignored).

  .venv/Scripts/python.exe research/data_fetch/bybitq/fetch_bybitq.py
  .venv/Scripts/python.exe research/data_fetch/bybitq/fetch_bybitq.py --inventory-only

Rules: Bybit V5 public market endpoints only (no keys), <= 5 req/s
(4 req/s via RATE_SLEEP), resume-safe (skip + backfill per-symbol parquet).

Endpoints used (all GET, public, no auth):
  /v5/market/instruments-info?category=linear|inverse|spot&status=Trading|Closed
    (paginated via nextPageCursor; dated = contractType LinearFutures /
    InverseFutures with a nonzero deliveryTime)
  /v5/market/kline?category=...&symbol=...&interval=60&start=..&end=..&limit=1000
    (delisted contracts still serve klines when start/end fall in their
    lifetime; verified 2026-10-06 for inverse BTCUSDZ23 and linear BTC-01SEP23)

Layout under OUT_DIR:
  inventory.json            all BTC/ETH dated contracts (linear+inverse, Trading+Closed)
  spot_<SYM>_1h.parquet     Bybit spot hourly (open_time, open, high, low, close, volume, turnover)
  inv_<SYM>_1h.parquet      inverse coin-margined dated futures hourly
  lin_<SYM>_1h.parquet      linear USDT/USDC-settled dated futures hourly
  (symbol sanitised: '-' -> '_'; USDC weeklies BTC-01SEP23 -> lin_BTC_01SEP23_1h.parquet)
Columns: open_time (UTC ms int64, hour open), open/high/low/close (float),
volume (float, base coin for spot/linear, USD for inverse), turnover (float).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT_DIR = ROOT / "data" / "raw" / "bybit_quarterly_20261006"

API = "https://api.bybit.com"
RATE_SLEEP = 0.25  # 4 req/s, under the 5 req/s limit
PAGE_LIMIT = 1000  # max kline rows per request
RETRIES = 5

COINS = ["BTC", "ETH"]
SPOT_SYMS = ["BTCUSDT", "ETHUSDT"]


def api_get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = API + path + "?" + qs
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("retCode") != 0:
                raise RuntimeError(f"retCode={d.get('retCode')} retMsg={d.get('retMsg')}")
            time.sleep(RATE_SLEEP)
            return d
        except Exception as e:  # backoff, then re-raise on last attempt
            last = e
            time.sleep(RATE_SLEEP * (2 ** (attempt + 1)))
    raise RuntimeError(f"GET {path} failed after {RETRIES}: {last}")


def list_instruments(category: str, status: str) -> list[dict]:
    out: list[dict] = []
    cursor = ""
    while True:
        p: dict = {"category": category, "status": status, "limit": "1000"}
        if cursor:
            p["cursor"] = cursor
        d = api_get("/v5/market/instruments-info", p)
        out.extend(d["result"]["list"])
        cursor = d["result"].get("nextPageCursor", "")
        if not cursor:
            break
    return out


def is_dated(it: dict) -> bool:
    ct = str(it.get("contractType", ""))
    if "Futures" not in ct or "Perpetual" in ct:
        return False
    try:
        return int(it.get("deliveryTime") or 0) > 0
    except (TypeError, ValueError):
        return False


def build_inventory() -> dict:
    recs: list[dict] = []
    for cat in ("linear", "inverse"):
        for status in ("Trading", "Closed"):
            for it in list_instruments(cat, status):
                if it.get("baseCoin") not in COINS:
                    continue
                if not is_dated(it):
                    continue
                recs.append(
                    {
                        "symbol": it["symbol"],
                        "category": cat,
                        "status": status,
                        "contractType": it.get("contractType"),
                        "baseCoin": it.get("baseCoin"),
                        "quoteCoin": it.get("quoteCoin"),
                        "settleCoin": it.get("settleCoin"),
                        "launchTime": int(it.get("launchTime") or 0),
                        "deliveryTime": int(it.get("deliveryTime") or 0),
                        "deliveryFeeRate": it.get("deliveryFeeRate"),
                    }
                )
    # dedupe (a symbol could in principle appear under both statuses)
    seen: dict[str, dict] = {}
    for r in recs:
        k = r["category"] + "|" + r["symbol"]
        if k not in seen or r["status"] == "Trading":
            seen[k] = r
    recs = sorted(seen.values(), key=lambda r: (r["category"], r["baseCoin"], r["deliveryTime"]))
    return {"endpoint": "GET /v5/market/instruments-info", "records": recs}


def fname(rec: dict) -> str:
    safe = rec["symbol"].replace("-", "_")
    prefix = "inv" if rec["category"] == "inverse" else "lin"
    return f"{prefix}_{safe}_1h.parquet"


def fetch_kline_range(category: str, symbol: str, start_ms: int, end_ms: int) -> list[list]:
    """Hourly klines in [start_ms, end_ms).

    The API returns newest-first capped at PAGE_LIMIT rows, so a long range
    must be paged BACKWARDS from end_ms (forward paging from start_ms would
    silently return only the most recent PAGE_LIMIT bars).
    """
    import pandas as pd  # noqa: F401 (ensures dep present)

    ded: dict[int, list] = {}
    cur_end = end_ms
    while cur_end > start_ms:
        d = api_get(
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": "60",
                "start": str(start_ms),
                "end": str(cur_end),
                "limit": str(PAGE_LIMIT),
            },
        )
        page = d["result"].get("list") or []
        if not page:
            break
        page = sorted(page, key=lambda r: int(r[0]))
        for r in page:
            t = int(r[0])
            if start_ms <= t < end_ms:
                ded[t] = r
        oldest = int(page[0][0])
        if oldest <= start_ms or len(page) < PAGE_LIMIT:
            # reached the head of the available history (or a gap at the head:
            # the API returns [] beyond it, verified by the break above on
            # the next iteration; stop when no progress is possible)
            if oldest <= start_ms:
                break
            # page < LIMIT but oldest > start: there may be older history with
            # a gap in between; keep paging back to be sure.
            cur_end = oldest - 1
            if cur_end <= start_ms:
                break
            continue
        cur_end = oldest - 1
    return [ded[k] for k in sorted(ded)]


def to_frame(rows: list[list]):
    import pandas as pd

    if not rows:
        return pd.DataFrame(
            columns=["open_time", "open", "high", "low", "close", "volume", "turnover"]
        )
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])
    df["open_time"] = df["open_time"].astype("int64")
    for c in ("open", "high", "low", "close", "volume", "turnover"):
        df[c] = df[c].astype(float)
    return df.sort_values("open_time").reset_index(drop=True)


def sync_symbol(rec: dict, now_ms: int, kline_category: str) -> dict:
    """Resume-safe sync of one contract parquet. Returns coverage info."""
    import pandas as pd

    path = OUT_DIR / fname(rec)
    launch = int(rec["launchTime"])
    end = min(int(rec["deliveryTime"]) + 3_600_000, now_ms)
    info: dict = {"symbol": rec["symbol"], "file": path.name}
    if path.exists():
        try:
            old = pd.read_parquet(path)
            have_min = int(old["open_time"].min()) if len(old) else None
            have_max = int(old["open_time"].max()) if len(old) else None
        except Exception:
            old, have_min, have_max = None, None, None
    else:
        old, have_min, have_max = None, None, None
    ranges: list[tuple[int, int]] = []
    if old is None or have_min is None:
        ranges = [(launch, end)]
    else:
        if have_min > launch:
            ranges.append((launch, have_min))
        if have_max is not None and have_max + 3_600_000 < end:
            ranges.append((have_max + 3_600_000, end))
    frames = [old] if old is not None and len(old) else []
    served_any = bool(frames and len(frames[0]))
    for s, e in ranges:
        if s >= e:
            continue
        rows = fetch_kline_range(kline_category, rec["symbol"], s, e)
        if rows:
            served_any = True
        frames.append(to_frame(rows))
    if frames:
        import pandas as pd

        df = pd.concat(frames, ignore_index=True).drop_duplicates("open_time")
        df = df.sort_values("open_time").reset_index(drop=True)
    else:
        df = to_frame([])
    df.to_parquet(path, index=False)
    info.update(
        {
            "rows": int(len(df)),
            "first_open_time": int(df["open_time"].min()) if len(df) else None,
            "last_open_time": int(df["open_time"].max()) if len(df) else None,
            "launchTime": launch,
            "deliveryTime": int(rec["deliveryTime"]),
            "serves_kline": bool(served_any),
        }
    )
    return info


def sync_spot(symbol: str, now_ms: int) -> dict:
    import pandas as pd

    path = OUT_DIR / f"spot_{symbol}_1h.parquet"
    if path.exists():
        try:
            old = pd.read_parquet(path)
            have_min = int(old["open_time"].min()) if len(old) else None
            have_max = int(old["open_time"].max()) if len(old) else None
        except Exception:
            old, have_min, have_max = None, None, None
    else:
        old, have_min, have_max = None, None, None
    # full range ever requested: earliest probe (2021-01-01; the API returns
    # what exists — Bybit spot history starts 2021-08-26) through now.
    frames = [old] if old is not None and len(old) else []
    ranges: list[tuple[int, int]] = []
    if have_min is None:
        ranges = [(1609459200000, now_ms)]
    else:
        if have_min > 1609459200000:
            ranges.append((1609459200000, have_min))
        if have_max is not None and have_max + 3_600_000 < now_ms:
            ranges.append((have_max + 3_600_000, now_ms))
    for s, e in ranges:
        if s >= e:
            continue
        rows = fetch_kline_range("spot", symbol, s, e)
        frames.append(to_frame(rows))
    import pandas as pd

    df = (
        pd.concat(frames, ignore_index=True).drop_duplicates("open_time")
        if frames
        else to_frame([])
    )
    df = df.sort_values("open_time").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return {
        "symbol": symbol,
        "file": path.name,
        "rows": int(len(df)),
        "first_open_time": int(df["open_time"].min()) if len(df) else None,
        "last_open_time": int(df["open_time"].max()) if len(df) else None,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory-only", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inv_path = HERE / "inventory.json"

    if inv_path.exists():
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        print(f"inventory: loaded {len(inv['records'])} records from {inv_path.name}")
    else:
        inv = build_inventory()
        inv_path.write_text(json.dumps(inv, indent=1), encoding="utf-8")
        print(f"inventory: fetched {len(inv['records'])} BTC/ETH dated contracts")

    if args.inventory_only:
        return

    import datetime

    now_ms = int(time.time() * 1000)
    print("now:", datetime.datetime.fromtimestamp(now_ms / 1000, datetime.timezone.utc))

    coverage: list[dict] = []
    for i, rec in enumerate(inv["records"]):
        info = sync_symbol(rec, now_ms, kline_category=rec["category"])
        coverage.append(info)
        if (i + 1) % 25 == 0 or (i + 1) == len(inv["records"]):
            n_rows = sum(c["rows"] for c in coverage)
            print(f"  contracts {i + 1}/{len(inv['records'])} rows={n_rows}")
    empty = [c["symbol"] for c in coverage if not c["serves_kline"]]
    print(f"contracts with zero kline rows: {len(empty)} {empty[:10]}")

    spots = []
    for sym in SPOT_SYMS:
        s = sync_spot(sym, now_ms)
        spots.append(s)
        print(f"spot {sym}: rows={s['rows']} first={s['first_open_time']} last={s['last_open_time']}")

    (HERE / "coverage.json").write_text(
        json.dumps({"contracts": coverage, "spot": spots}, indent=1), encoding="utf-8"
    )
    # lightweight manifest of data files (full MANIFEST.json is written by analyze step)
    manifest = [
        {
            "path": f"data/raw/bybit_quarterly_20261006/{p.name}",
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(OUT_DIR.glob("*.parquet"))
    ]
    (OUT_DIR / "manifest_data.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"data files: {len(manifest)} parquet")


if __name__ == "__main__":
    main()
