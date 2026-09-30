"""1m klines of the causal alt universe U2020 (top-30 non-major USD-M perps by December-2020 volume, full month listed), research only.

The universe comes from data/raw/um_universe_20260930/volume_2020_12.csv (scripts/fetch_um_universe_2020.py) - information available on
2021-01-01, later-delisted symbols included (no survivorship selection). Symbols already stored in data/raw/alts_intraday_20260926 are
not downloaded again. Public archive (data.binance.vision, monthly zips with daily fallback via research/mj/fetch_majors), from
2020-08-01 (or listing) to the archive end; one parquet per symbol-year in data/raw/alts2020_intraday_20260930/ + manifest.json.
Resumable: a symbol with a manifest entry is skipped. Never traded.
  python scripts/fetch_alts2020_1m.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/alts2020_intraday_20260930"
HAVE = ROOT / "data/raw/alts_intraday_20260926"
MAJORS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
N_UNIVERSE = int(__import__("os").environ.get("N_UNIVERSE", "30"))

spec = importlib.util.spec_from_file_location("fetch_majors", ROOT / "research/mj/fetch_majors.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)


def universe() -> list[str]:
    v = pd.read_csv(ROOT / "data/raw/um_universe_20260930/volume_2020_12.csv")
    v = v[(v.days >= 28) & ~v.symbol.isin(MAJORS)].sort_values("quote_volume_usd", ascending=False)
    return list(v.symbol.head(N_UNIVERSE))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mf = OUT / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {
        "source": "data.binance.vision futures/um 1m (monthly zips, daily fallback)", "universe": universe(), "symbols": {}}
    sess = requests.Session()
    for s in manifest["universe"]:
        if s in manifest["symbols"] or any(HAVE.glob(f"{s}_1m_*.parquet")):
            continue
        try:
            frame, info = fm.fetch_1m_archive(sess, s, datetime(2020, 8, 1, tzinfo=timezone.utc))
        except Exception as exc:  # recorded, never silently skipped
            manifest["symbols"][s] = {"error": repr(exc)[:200]}
            mf.write_text(json.dumps(manifest, indent=1))
            print(s, "ERROR", repr(exc)[:200], flush=True)
            continue
        files = {}
        for year, part in frame.groupby(frame["open_time"].dt.year):
            p = OUT / f"{s}_1m_{year}.parquet"
            part.reset_index(drop=True).to_parquet(p)
            files[p.name] = {"rows": int(len(part)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        manifest["symbols"][s] = {"first": str(frame["open_time"].min()), "last": str(frame["open_time"].max()),
                                  "rows": int(len(frame)), "files": files, "missing": len(info["missing_files"])}
        mf.write_text(json.dumps(manifest, indent=1))
        print(s, manifest["symbols"][s]["first"], manifest["symbols"][s]["last"], manifest["symbols"][s]["rows"], flush=True)


if __name__ == "__main__":
    main()
