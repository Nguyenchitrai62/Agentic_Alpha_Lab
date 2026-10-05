"""Fetch N1 Wikipedia daily pageviews (2016-01-01..2026-09-23) with manifest.

Source: Wikimedia REST per-article API, en.wikipedia, access=all-access, agent=user.
Saves raw JSON per (article, year-chunk) into data/raw/newinfo_20261005/ + manifest.json (URL + sha256).
Throttled (>=5 s between requests) with retry/backoff. Re-runnable: skips chunks already on disk.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "AgenticAlphaLab/1.0 (research contact local)"}
# Post-hoc source-completeness fix (before any outcome statistic; logged in REPORT.md):
# the XRP article lived at Ripple_(payment_protocol) until its Nov-2024 move to XRP_Ledger, so XRP
# unions all three title variants (summed per day; redirect titles carry ~zero direct views).
ARTICLES = {
    "BTC": ["Bitcoin"],
    "ETH": ["Ethereum"],
    "SOL": ["Solana_(blockchain_platform)"],  # created 2021-09-10; no predecessor title exists
    "BNB": ["Binance"],  # article created 2018; no predecessor
    "XRP": ["XRP_Ledger", "Ripple_(payment_protocol)", "XRP"],
}
START = (2016, 1, 1)
END = (2026, 9, 23)  # inclusive
RAW = Path(__file__).resolve().parents[3] / "data" / "raw" / "newinfo_20261005"
SLEEP_S = 6


def chunk_url(article: str, s: str, e: str) -> str:
    return (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/user/{article}/daily/{s}/{e}"
    )


def get(url: str, tries: int = 5) -> bytes | None:
    """GET with retry. Returns None when the API reports 404 (article had no views / did not exist yet)."""
    import urllib.error

    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # no data for this range (e.g. article created later)
            last = exc
            time.sleep(min(60, 5 * (k + 1)))
        except Exception as exc:  # noqa: BLE001 - network retry
            last = exc
            time.sleep(min(60, 5 * (k + 1)))
    raise RuntimeError(f"GET failed {url}: {last}")


def year_chunks():
    for y in range(START[0], END[0] + 1):
        s = f"{y}0101" if y > START[0] else f"{START[0]}{START[1]:02d}{START[2]:02d}"
        e = f"{y}1231" if y < END[0] else f"{END[0]}{END[1]:02d}{END[2]:02d}"
        yield y, s, e


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    man_path = RAW / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
    for coin, arts in ARTICLES.items():
        for art in arts:
            for y, s, e in year_chunks():
                fname = f"wiki_{coin}_{art}_{s}_{e}.json"
                fpath = RAW / fname
                url = chunk_url(art, s, e)
                if fpath.exists():
                    print(f"skip {fname}", flush=True)
                else:
                    body = get(url)
                    if body is None:
                        body = json.dumps({"items": [], "note": "API 404: no data for range"}).encode()
                        print(f"empty {fname} (API 404)", flush=True)
                    else:
                        print(f"saved {fname} ({len(body)} B)", flush=True)
                    fpath.write_bytes(body)
                    time.sleep(SLEEP_S)
                sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
                manifest[fname] = {"url": url, "sha256": sha, "bytes": fpath.stat().st_size}
                man_path.write_text(json.dumps(manifest, indent=2))
    print(f"done: {len(manifest)} raw files, manifest at {man_path}")


if __name__ == "__main__":
    main()
