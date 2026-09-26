"""Download Binance USD-M daily 'metrics' archives (public data.binance.vision, no key) for the 5 majors.

Fields (5-minute rows): sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio,
sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio.
Output: data/raw/um_metrics_20260926/{SYM}_metrics.parquet + manifest.json (days fetched / missing). Zip CRCs are checked
by zipfile.testzip(). Research data only; metrics are published after each day, so features must lag them (see v138).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/um_metrics_20260926")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
URL = "https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"


def fetch(args):
    s, d = args
    for attempt in range(3):
        try:
            r = requests.get(URL.format(s=s, d=d), timeout=30)
            if r.status_code == 404:
                return d, None
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            if z.testzip() is not None:
                raise ValueError("bad crc")
            return d, pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
        except Exception:
            if attempt == 2:
                return d, "error"
    return d, "error"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    days = [x.strftime("%Y-%m-%d") for x in pd.date_range("2020-09-01", "2026-09-24", freq="D")]
    man = {"source": URL, "files": {}}
    for s in SYMS:
        with ThreadPoolExecutor(16) as ex:
            res = list(ex.map(fetch, [(s, d) for d in days]))
        frames = [f for _, f in res if isinstance(f, pd.DataFrame)]
        missing = [d for d, f in res if f is None]
        errors = [d for d, f in res if isinstance(f, str)]
        df = pd.concat(frames, ignore_index=True)
        df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
        df = df.drop_duplicates("create_time").sort_values("create_time").reset_index(drop=True)
        f = OUT / f"{s}_metrics.parquet"
        df.to_parquet(f, index=False)
        man["files"][s] = dict(rows=len(df), first=str(df.create_time.min()), last=str(df.create_time.max()), days_ok=len(frames),
                               days_missing=len(missing), first_ok_day=min(d for d, x in res if isinstance(x, pd.DataFrame)),
                               errors=errors, sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(s, {k: v for k, v in man["files"][s].items() if k != "errors"}, "errors", len(errors), flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
