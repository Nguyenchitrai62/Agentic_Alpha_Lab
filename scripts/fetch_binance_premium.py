"""Download Binance USD-M public archive data for the majors: 1m premium-index klines and settled funding rates.

Source: https://data.binance.vision (public, no key). Monthly zips 2020-01..latest, plus daily zips for the current month.
The premium index P(t) = (max(0, impact bid - index) - max(0, index - impact ask)) / index is what drives the funding rate:
funding = clamp(avg_8h(P) + clamp(interest - avg_8h(P), -0.05%, 0.05%)), so the 1m series gives the predicted funding known at
every minute (no look-ahead to the settled value) and shows the last-minute moves around each settlement.
Output: data/raw/binance_premium_20260928/{SYM}_premium_1m.parquet, {SYM}_funding.parquet, manifest.json (sha256, rows, ranges).

  python scripts/fetch_binance_premium.py
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BASE = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
OUT = Path("data/raw/binance_premium_20260928")
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume",
         "taker_buy_quote_volume", "ignore"]


def keys(prefix: str) -> list[str]:
    out, marker = [], ""
    while True:
        x = urllib.request.urlopen(f"{S3}?prefix={prefix}&marker={marker}", timeout=60).read().decode()
        k = re.findall(r"<Key>([^<]+)</Key>", x)
        out += [a for a in k if a.endswith(".zip")]
        if "<IsTruncated>true" not in x:
            return out
        marker = k[-1]


def read_zip(key: str) -> pd.DataFrame:
    raw = urllib.request.urlopen(BASE + key, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            txt = f.read().decode()
    first = txt.split("\n", 1)[0]
    has_header = not first[:1].isdigit()
    return pd.read_csv(io.StringIO(txt), header=0 if has_header else None)


def premium(sym: str) -> pd.DataFrame:
    monthly = keys(f"data/futures/um/monthly/premiumIndexKlines/{sym}/1m/")
    last_month = max(re.search(r"(\d{4}-\d{2})\.zip", k).group(1) for k in monthly)
    daily = [k for k in keys(f"data/futures/um/daily/premiumIndexKlines/{sym}/1m/")
             if re.search(r"(\d{4}-\d{2})-\d{2}\.zip", k).group(1) > last_month]
    parts = []
    for k in monthly + daily:
        d = read_zip(k)
        d = d.iloc[:, :len(KCOLS)]
        d.columns = KCOLS[:d.shape[1]]
        parts.append(d[["open_time", "open", "high", "low", "close"]])
        print(sym, k.rsplit("/", 1)[-1], len(d), flush=True)
    p = pd.concat(parts, ignore_index=True)
    p["open_time"] = pd.to_numeric(p["open_time"])
    unit = "us" if p["open_time"].max() > 1e14 else "ms"  # the archive switched to microseconds in 2025
    p["open_time"] = pd.to_datetime(p["open_time"], unit=unit, utc=True)
    p = p.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    for c in ("open", "high", "low", "close"):
        p[c] = p[c].astype(float)
    return p


def funding(sym: str) -> pd.DataFrame:
    parts = [read_zip(k) for k in keys(f"data/futures/um/monthly/fundingRate/{sym}/")]
    f = pd.concat(parts, ignore_index=True)
    f.columns = [c.strip() for c in f.columns]
    f["calc_time"] = pd.to_datetime(pd.to_numeric(f["calc_time"]), unit="ms", utc=True)
    return f.drop_duplicates("calc_time").sort_values("calc_time").reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"source": BASE, "types": ["premiumIndexKlines 1m (monthly + daily)", "fundingRate (monthly)"], "files": {}}
    for sym in SYMS:
        for name, fn in ((f"{sym}_premium_1m.parquet", premium), (f"{sym}_funding.parquet", funding)):
            d = fn(sym)
            path = OUT / name
            d.to_parquet(path)
            tcol = d.columns[0] if name.endswith("1m.parquet") else "calc_time"
            man["files"][name] = {"rows": len(d), "first": str(d[tcol].iloc[0]), "last": str(d[tcol].iloc[-1]),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            print("saved", name, man["files"][name], flush=True)
            (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
