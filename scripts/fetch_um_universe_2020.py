"""Causal alt universe for pooled RL training: USD-M perps ranked by December-2020 quote volume (Binance public archive, no keys).

Lists every symbol under data/futures/um/monthly/klines/ (including later-delisted ones), downloads its 2020-12 1d monthly zip when it
exists, and writes data/raw/um_universe_20260930/volume_2020_12.csv (symbol, quote_volume_usd) - information available on 2021-01-01.
  python scripts/fetch_um_universe_2020.py
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/um_universe_20260930"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"


def symbols(s: requests.Session) -> list[str]:
    out, marker = [], ""
    while True:
        r = s.get(S3, params={"delimiter": "/", "prefix": "data/futures/um/monthly/klines/", "marker": marker}, timeout=60)
        r.raise_for_status()
        pre = re.findall(r"<Prefix>data/futures/um/monthly/klines/([^<]+)/</Prefix>", r.text)
        out += pre
        if "<IsTruncated>true" not in r.text:
            return sorted(set(out))
        marker = re.findall(r"<NextMarker>([^<]+)</NextMarker>", r.text)[0]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    syms = [x for x in symbols(s) if x.endswith("USDT")]
    print("USDT perps in the archive:", len(syms), flush=True)
    rows = []
    for x in syms:
        url = f"https://data.binance.vision/data/futures/um/monthly/klines/{x}/1d/{x}-1d-2020-12.zip"
        r = s.get(url, timeout=60)
        if r.status_code != 200:
            continue
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            d = pd.read_csv(z.open(z.namelist()[0]), header=None)
        if not str(d.iloc[0, 0]).isdigit():
            d = d.iloc[1:]
        rows.append((x, float(d.iloc[:, 7].astype(float).sum()), len(d)))
    v = pd.DataFrame(rows, columns=["symbol", "quote_volume_usd", "days"]).sort_values("quote_volume_usd", ascending=False)
    v.to_csv(OUT / "volume_2020_12.csv", index=False)
    print(v.head(40).to_string(index=False))


if __name__ == "__main__":
    main()
