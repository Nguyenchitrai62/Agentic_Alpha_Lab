"""oc_dvol fetch: Deribit get_volatility_index_data, BTC+ETH, 1h (3600), 2021-04..2026-09.

Raw JSON responses -> data/raw/deribit_dvol_20261005/<CUR>_YYYY-MM.json
+ manifest.json (request URL + sha256 per file). Single process, sequential,
polite sleep; follows `continuation` paging if ever non-null.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/raw/deribit_dvol_20261005"
BASE = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
CURS = ("BTC", "ETH")
RES = "3600"
SPAN_START = (2021, 4)
SPAN_END = (2026, 9)  # inclusive month; clamp end to 2026-09-24 00:00 UTC
HARD_END_MS = int(calendar.timegm((2026, 9, 24, 0, 0, 0, 0, 0, 0))) * 1000


def month_bounds(y: int, m: int) -> tuple[int, int]:
    s = int(calendar.timegm((y, m, 1, 0, 0, 0, 0, 0, 0))) * 1000
    em = m + 1 if m < 12 else 1
    ey = y if m < 12 else y + 1
    e = int(calendar.timegm((ey, em, 1, 0, 0, 0, 0, 0, 0))) * 1000
    return s, min(e, HARD_END_MS)


def build_url(cur: str, start_ms: int, end_ms: int) -> str:
    q = urllib.parse.urlencode(
        {"currency": cur, "resolution": RES,
         "start_timestamp": start_ms, "end_timestamp": end_ms}
    )
    return BASE + "?" + q


def get(url: str, tries: int = 5) -> dict:
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as ex:  # noqa: BLE001 - retry transient network errors
            last = ex
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}: {last}")


def fetch_month(cur: str, y: int, m: int) -> tuple[list, list[str]]:
    """Return (all candles, urls used). Pages via continuation if needed."""
    s, e = month_bounds(y, m)
    candles: list = []
    urls: list[str] = []
    end = e
    while True:
        url = build_url(cur, s, end)
        urls.append(url)
        payload = get(url)
        res = payload.get("result", {})
        data = res.get("data", [])
        candles.extend(data)
        cont = res.get("continuation")
        if cont is None:
            break
        end = int(cont)
        if end <= s:
            break
        time.sleep(0.2)
    # dedupe by timestamp, sort ascending
    seen: dict[int, list] = {}
    for c in candles:
        seen[int(c[0])] = c
    return [seen[k] for k in sorted(seen)], urls


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"base": BASE, "resolution": RES, "files": {}}
    months: list[tuple[int, int]] = []
    y, m = SPAN_START
    while (y, m) <= SPAN_END:
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    total = 0
    for cur in CURS:
        for y, m in months:
            name = f"{cur}_{y:04d}-{m:02d}.json"
            fp = OUT / name
            if fp.exists():
                payload = json.loads(fp.read_text())
                n = len(payload["candles"])
                print(f"skip {name} ({n} candles, cached)", flush=True)
                manifest["files"][name] = {
                    "url": payload["urls"][0],
                    "sha256": hashlib.sha256(fp.read_bytes()).hexdigest(),
                    "candles": n,
                }
                total += n
                continue
            candles, urls = fetch_month(cur, y, m)
            payload = {"currency": cur, "resolution": RES,
                       "urls": urls, "candles": candles}
            raw = json.dumps(payload).encode()
            fp.write_bytes(raw)
            manifest["files"][name] = {
                "url": urls[0],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "candles": len(candles),
            }
            total += len(candles)
            print(f"saved {name} ({len(candles)} candles, {len(urls)} req)", flush=True)
            time.sleep(0.2)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"DONE files={len(manifest['files'])} total_candles={total}")


if __name__ == "__main__":
    main()
