"""Fetch N2 CME front-month continuous daily bars (BTC=F, ETH=F) via Yahoo Finance chart API.

Saves raw JSON per symbol into data/raw/newinfo_20261005/ + manifest.json entries (URL + sha256).
ETH futures exist from 2021-02-08 (covers all five test years starting 2021-09-24).
Re-runnable: skips files already on disk.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "AgenticAlphaLab/1.0 (research contact local)"}
SYMBOLS = ["BTC=F", "ETH=F"]
# 2016-01-01 00:00 UTC .. 2026-09-24 00:00 UTC
P1 = 1451606400
P2 = 1789948800
RAW = Path(__file__).resolve().parents[3] / "data" / "raw" / "newinfo_20261005"


def url(sym: str) -> str:
    s = sym.replace("=", "%3D")
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={P1}&period2={P2}&interval=1d&events=div%7Csplit"


def get(u: str, tries: int = 5) -> bytes:
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 - network retry
            last = exc
            time.sleep(min(60, 5 * (k + 1)))
    raise RuntimeError(f"GET failed {u}: {last}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    man_path = RAW / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
    for sym in SYMBOLS:
        fname = f"cme_{sym.replace('=', '')}_daily.json"
        fpath = RAW / fname
        u = url(sym)
        if fpath.exists():
            print(f"skip {fname}", flush=True)
        else:
            body = get(u)
            payload = json.loads(body)
            assert payload.get("chart", {}).get("result"), f"empty result for {sym}: {body[:200]}"
            fpath.write_bytes(body)
            print(f"saved {fname} ({len(body)} B)", flush=True)
            time.sleep(3)
        sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        manifest[fname] = {"url": u, "sha256": sha, "bytes": fpath.stat().st_size}
        man_path.write_text(json.dumps(manifest, indent=2))
    print(f"done, manifest at {man_path}")


if __name__ == "__main__":
    main()
