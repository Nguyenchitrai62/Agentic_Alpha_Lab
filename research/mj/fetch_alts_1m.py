"""Out-of-universe 1m klines for the dip-rebound robustness test (research only; not traded).

Downloads Binance USD-M 1m klines (public archive data.binance.vision, via research/mj/fetch_majors.fetch_1m_archive)
for DOGE, ADA, LINK, LTC, AVAX, TRX from 2020-02-01 (or listing) to 2026-09-23 and stores one parquet per symbol-year
in data/raw/alts_intraday_20260926/, same columns as data/raw/majors_intraday_20260924, plus manifest.json (rows,
first/last, sha256). No credentials.

  python research/mj/fetch_alts_1m.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
OUT = Path("data/raw/alts_intraday_20260926")
SYMS = ("DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT")

spec = importlib.util.spec_from_file_location("fetch_majors", HERE / "fetch_majors.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    manifest = {"source": "data.binance.vision futures/um 1m (monthly zips, daily fallback)", "end": str(fm.END_1M), "symbols": {}}
    for s in SYMS:
        frame, info = fm.fetch_1m_archive(sess, s, datetime(2020, 2, 1, tzinfo=timezone.utc))
        files = {}
        for year, part in frame.groupby(frame["open_time"].dt.year):
            p = OUT / f"{s}_1m_{year}.parquet"
            part.reset_index(drop=True).to_parquet(p)
            files[p.name] = {"rows": int(len(part)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        manifest["symbols"][s] = {"first": str(frame["open_time"].min()), "last": str(frame["open_time"].max()),
                                  "rows": int(len(frame)), "files": files, "missing": len(info["missing_files"])}
        print(s, manifest["symbols"][s]["first"], manifest["symbols"][s]["rows"], flush=True)
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
