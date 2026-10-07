"""oc_idea9: fetch free Yahoo ^GSPC daily into data/raw/newinfo_idea9/ + manifest.

Free public source only (Yahoo chart API v8, no key), same convention as
data/raw/macro_20260924. Stores the raw JSON (sha256 in manifest) plus a
parsed CSV. Run from the repo root:

  python research/tournament/oc_idea9/fetch_spx.py
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT = ROOT / "data/raw/newinfo_idea9"
OUT.mkdir(parents=True, exist_ok=True)

SYM = "^GSPC"
START = dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)  # exclusive; data < 2026-09-24
P1 = int(START.timestamp())
P2 = int(END.timestamp())

URLS = [
    f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
    f"?period1={P1}&period2={P2}&interval=1d&events=div%7Csplit",
    f"https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC"
    f"?period1={P1}&period2={P2}&interval=1d&events=div%7Csplit",
]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    if not body:
        raise ValueError("empty response")
    return body


def main() -> None:
    body = None
    used = None
    last_err = None
    for u in URLS:
        try:
            body = fetch(u)
            json.loads(body)  # must be JSON
            used = u
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
    if body is None:
        raise RuntimeError(f"all Yahoo hosts failed: {last_err}")

    raw_path = OUT / "spx_daily.json"
    raw_path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()

    payload = json.loads(body)["chart"]["result"][0]
    ts = payload["timestamp"]
    q = payload["indicators"]["quote"][0]
    adj = payload["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    rows = []
    for i, t in enumerate(ts):
        d = dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).date().isoformat()
        rows.append({
            "date": d,
            "open": q["open"][i], "high": q["high"][i],
            "low": q["low"][i], "close": q["close"][i],
            "adjclose": adj[i], "volume": q["volume"][i],
        })
    rows = [r for r in rows if r["close"] is not None]
    rows.sort(key=lambda r: r["date"])

    csv_path = OUT / "spx_daily.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "adjclose", "volume"])
        w.writeheader()
        w.writerows(rows)
    csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    manifest = {
        "source": "Yahoo Finance Chart API v8 (free, no key)",
        "symbol": SYM,
        "url": used,
        "fallback_url": URLS[1] if used == URLS[0] else URLS[0],
        "start": "2016-01-01",
        "end_exclusive": "2026-09-24",
        "files": {
            "spx_daily.json": {"sha256": sha, "bytes": len(body)},
            "spx_daily.csv": {"sha256": csv_sha, "rows": len(rows)},
        },
        "first": rows[0]["date"],
        "last": rows[-1]["date"],
        "crawled_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": "Daily bars only; intraday timing resolved per PLAN.md "
                "(16:00 ET close -> 20:00 UTC EDT / 21:00 UTC EST).",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"rows={len(rows)} first={rows[0]['date']} last={rows[-1]['date']}")
    print(f"json sha256={sha}")
    print(f"csv  sha256={csv_sha}")


if __name__ == "__main__":
    main()
