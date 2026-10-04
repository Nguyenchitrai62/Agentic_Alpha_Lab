"""Fetch Binance USD-M bookDepth daily archives and aggregate to 1-minute tables.

Source (public, no key): https://data.binance.vision/data/futures/um/daily/bookDepth/{SYM}/{SYM}-bookDepth-YYYY-MM-DD.zip
Each daily CSV has columns timestamp,percentage,depth,notional: one snapshot (~every 30-60 s) x 10 rows
(percentages -5..-1 = bid side, +1..+5 = ask side; depth/notional are cumulative from the mid price).

Universe: BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT, 2023-01-01 .. 2025-09-30.
Alts in fills_U.parquet are NOT fetched: availability is patchy (e.g. YFIIUSDT-bookDepth-2023-01-01.zip
is HTTP 404 while majors return 200 with ~400-480 kB/day), so per the assignment's "if available, else
majors only" clause this dataset is majors-only.

Output (data/raw/bookdepth_20261004/): per symbol {SYM}_bookdepth_1m.parquet with the last snapshot
of each minute: minute (UTC minute floor), ts (snapshot timestamp, UTC), bid/ask notional at 1/2/5 %
(bid_n1, ask_n1, bid_n2, ask_n2, bid_n5, ask_n5), plus manifest.json (rows, first/last, sha256 per file).

Causality: raw snapshot timestamps are treated as availability times; downstream joins use only
snapshots with ts strictly before the decision time. No forward filling across the decision time.

Polite + resumable: 0.05 s sleep between requests, 3 retries with backoff, per-symbol progress file
(skips dates already written to the monthly part files), monthly part files merged at the end.

  python scripts/fetch_bookdepth.py            # full fetch (~5k zips, ~2.5 GB download)
  python scripts/fetch_bookdepth.py --check    # probe availability only, no download
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
START = date(2023, 1, 1)
END = date(2025, 9, 30)
BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"
OUT = Path("data/raw/bookdepth_20261004")
SLEEP = 0.05
RETRIES = 3


def _get(url: str) -> bytes:
    last = None
    for k in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgenticAlphaLab-research/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - retry any transient error
            last = e
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"failed {url}: {last}")


def day_to_minutes(raw: bytes) -> pd.DataFrame:
    """Parse one daily zip -> 1-minute last-snapshot table (UTC)."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, usecols=["timestamp", "percentage", "notional"])
    df["ts"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S", utc=True)
    df["pct"] = df["percentage"].astype(int)
    keep = {"bid_n1": -1, "ask_n1": 1, "bid_n2": -2, "ask_n2": 2, "bid_n5": -5, "ask_n5": 5}
    df = df[df["pct"].isin(set(keep.values()))]
    wide = df.pivot_table(index="ts", columns="pct", values="notional", aggfunc="last")
    wide.columns = [f"pct_{c}" for c in wide.columns]
    wide = wide.rename(columns={f"pct_{v}": k for k, v in keep.items()})
    wide = wide.dropna()  # require a complete snapshot (all six levels)
    wide["minute"] = wide.index.floor("min")
    last = wide.groupby("minute").tail(1)  # last snapshot per minute
    last = last.reset_index().rename(columns={"ts": "ts"})
    cols = ["minute", "ts"] + list(keep)
    return last[cols].sort_values("minute").reset_index(drop=True)


def _progress_path(sym: str) -> Path:
    return OUT / f"{sym}_progress.json"


def _load_progress(sym: str) -> set:
    p = _progress_path(sym)
    if p.exists():
        return set(json.loads(p.read_text()))
    return set()


def _save_progress(sym: str, done: set) -> None:
    _progress_path(sym).write_text(json.dumps(sorted(done)))


def fetch_symbol(sym: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    done = _load_progress(sym)
    parts: dict[str, list[pd.DataFrame]] = {}
    day = START
    n_new = 0
    while day <= END:
        ds = day.strftime("%Y-%m-%d")
        if ds not in done:
            url = f"{BASE}/{sym}/{sym}-bookDepth-{ds}.zip"
            try:
                m = day_to_minutes(_get(url))
            except RuntimeError as e:
                print(f"{sym} {ds} MISSING ({e})", flush=True)
                done.add(ds + ":missing")
                _save_progress(sym, done)
                day += timedelta(days=1)
                time.sleep(SLEEP)
                continue
            parts.setdefault(ds[:7], []).append(m)
            n_new += 1
            if n_new % 20 == 0:
                print(f"{sym} {ds} ({n_new} new days)", flush=True)
            # flush each month as soon as it completes
            nxt = day + timedelta(days=1)
            if nxt.strftime("%Y-%m") != ds[:7] or nxt > END:
                month_df = pd.concat(parts.pop(ds[:7], []), ignore_index=True)
                mp = OUT / f"{sym}_{ds[:7]}_1m.parquet"
                if mp.exists():
                    old = pd.read_parquet(mp)
                    month_df = pd.concat([old, month_df], ignore_index=True)
                    month_df = month_df.drop_duplicates("minute").sort_values("minute").reset_index(drop=True)
                month_df.to_parquet(mp, index=False)
            done.add(ds)
            _save_progress(sym, done)
            time.sleep(SLEEP)
        day += timedelta(days=1)
    # merge monthly parts into the final table
    month_files = sorted(OUT.glob(f"{sym}_????-??_1m.parquet"))
    full = pd.concat([pd.read_parquet(p) for p in month_files], ignore_index=True)
    full = full.drop_duplicates("minute").sort_values("minute").reset_index(drop=True)
    final = OUT / f"{sym}_bookdepth_1m.parquet"
    full.to_parquet(final, index=False)
    print(f"{sym}: {len(full)} minutes {full['minute'].iloc[0]} .. {full['minute'].iloc[-1]}", flush=True)
    return final


def write_manifest() -> None:
    man = {"source": BASE, "range": [START.isoformat(), END.isoformat()], "symbols": list(SYMS),
           "note": "majors only; alts unavailable for the full window (e.g. YFIIUSDT 2023-01-01 -> HTTP 404)",
           "availability": "snapshot timestamp ts is the exchange-published time; use only snapshots with ts strictly before the decision time",
           "files": {}}
    for sym in SYMS:
        final = OUT / f"{sym}_bookdepth_1m.parquet"
        if not final.exists():
            continue
        d = pd.read_parquet(final, columns=["minute"])
        man["files"][final.name] = {"rows": len(d), "first": str(d["minute"].iloc[0]),
                                    "last": str(d["minute"].iloc[-1]),
                                    "sha256": hashlib.sha256(final.read_bytes()).hexdigest()}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


def check() -> None:
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "YFIIUSDT", "WAVESUSDT"]:
        for ds in ["2023-01-01", "2025-09-30"]:
            url = f"{BASE}/{sym}/{sym}-bookDepth-{ds}.zip"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AgenticAlphaLab-research/1.0"},
                                             method="HEAD")
                r = urllib.request.urlopen(req, timeout=30)
                print(sym, ds, r.status, r.headers.get("Content-Length"))
            except Exception as e:  # noqa: BLE001
                print(sym, ds, "ERR", e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--end", default=None, help="last date to fetch (YYYY-MM-DD); default 2025-09-30")
    a = ap.parse_args()
    global END
    if a.end:
        END = date.fromisoformat(a.end)
    if a.check:
        check()
        return
    for sym in SYMS:
        fetch_symbol(sym)
    write_manifest()


if __name__ == "__main__":
    main()
