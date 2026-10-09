"""oc_presample step 1: download Binance SPOT 1m monthly klines + verify + pack.

Frozen by PLAN.md. Symbols/months:
  BTCUSDT, ETHUSDT: 2017-08 .. 2020-09
  BNBUSDT:          2017-11 .. 2020-09
  XRPUSDT:          2018-05 .. 2020-09
Output (ONLY data/raw/spot_1m_presample_20261007/):
  <SYM>.parquet (open_time UTC, o,h,l,c,volume), manifest.json
Scratch: research/tournament/oc_presample/tmp/ (cached zips in tmp/zips/)
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT = ROOT / "data/raw/spot_1m_presample_20261007"
TMP = HERE / "tmp" / "zips"

BASE = "https://data.binance.vision/data/spot/monthly/klines"


def months_between(a: str, b: str):
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    out = []
    y, m = ya, ma
    while (y, m) <= (yb, mb):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


PLAN = {
    "BTCUSDT": months_between("2017-08", "2020-09"),
    "ETHUSDT": months_between("2017-08", "2020-09"),
    "BNBUSDT": months_between("2017-11", "2020-09"),
    "XRPUSDT": months_between("2018-05", "2020-09"),
}

COLS = ["open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "num_trades",
        "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
USE = ["open_time", "open", "high", "low", "close", "volume"]


def fetch(url: str, tries: int = 5) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "oc_presample/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - retry any transient error
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def read_zip_frames(sym, months, raw_by_month):
    """Parse cached/fetched zip bytes -> raw frames (open_time as int ms)."""
    import pandas as pd  # noqa: PLC0415
    frames = []
    for ym in months:
        zname = f"{sym}-1m-{ym}.zip"
        with zipfile.ZipFile(io.BytesIO(raw_by_month[ym])) as z:
            csv_name = f"{sym}-1m-{ym}.csv"
            if csv_name not in z.namelist():
                raise RuntimeError(f"{zname} missing {csv_name}")
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None, names=COLS, usecols=USE)
        frames.append(df)
    return frames


def pack_symbol(frames, sym):
    """Merge monthly frames -> deduplicated UTC-minute frame.

    Data fix (post-PLAN discovery, pre-outcome, disclosed in PLAN.md):
    the 2017-12/2018-01/2018-02 archive rows for BTC/ETH/BNB carry
    sub-minute open_time offsets (+~15-22 s). Rows with real content are
    floored to the minute grid; backfill placeholders (volume == 0 AND
    o == h == l == c, the archive's flat zero-volume filler rows, which
    carry the same offsets) are dropped. On a floored/aligned timestamp
    collision the aligned (exact-minute) row wins.
    """
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    m = pd.concat(frames, ignore_index=True)
    n_raw = len(m)
    raw_ms = m["open_time"].to_numpy(dtype="int64")
    non = (raw_ms % 60000) != 0
    n_non = int(non.sum())
    n_ph = 0
    if n_non:
        sub = m[non]
        is_ph = ((sub["volume"] == 0) & (sub["open"] == sub["high"])
                 & (sub["high"] == sub["low"])
                 & (sub["low"] == sub["close"])).to_numpy()
        n_ph = int(is_ph.sum())
        floored = (raw_ms // 60000) * 60000
        # aligned prio 0 sorts before floored prio 1: aligned wins dedup
        m = m.drop(columns=["open_time"]).assign(
            _ts=pd.to_datetime(np.where(non, floored, raw_ms),
                               unit="ms", utc=True),
            _prio=np.where(non, 1, 0).astype(np.int64))
        drop = np.zeros(len(m), dtype=bool)
        drop[np.flatnonzero(non)[is_ph]] = True
        m = m[~drop]  # drop backfill placeholders
        m = (m.sort_values(["_ts", "_prio"])
              .drop_duplicates("_ts", keep="first")
              .sort_values("_ts")
              .rename(columns={"_ts": "open_time"})
              .drop(columns=["_prio"]))
        m = m.reset_index(drop=True)
    else:
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        m = (m.drop_duplicates("open_time").sort_values("open_time")
              .reset_index(drop=True))
    n_aligned = int((~non).sum())
    n_coll = int(n_non - n_ph - (len(m) - n_aligned))
    return m, {"n_raw_rows": int(n_raw),
               "n_subminute_rows": n_non, "n_placeholders_dropped": n_ph,
               "n_floor_collisions": max(n_coll, 0)}


def pack_and_write(sym, months, m, zips_ok, manifest):
    """Grid-pack one symbol's merged frame -> parquet + manifest entry."""
    import pandas as pd  # noqa: PLC0415
    m = m.rename(columns={"open": "o", "high": "h", "low": "l",
                          "close": "c"})
    first, last = m["open_time"].iloc[0], m["open_time"].iloc[-1]
    # full 1m grid first -> 2020-10-01 (exclusive end keeps Sept timeout opens)
    grid = pd.date_range(first.floor("min"),
                         datetime(2020, 10, 1, tzinfo=timezone.utc),
                         freq="1min")
    grid = grid[grid < datetime(2020, 10, 1, tzinfo=timezone.utc)]
    mm = m.set_index("open_time").reindex(grid)
    miss = mm["o"].isna()
    n_missing = int(miss.sum())
    # gap runs (consecutive missing minutes)
    runs = []
    if n_missing:
        idx = mm.index[miss]
        start = prev = idx[0]
        for t in idx[1:]:
            if t == prev + pd.Timedelta(minutes=1):
                prev = t
            else:
                runs.append((start, prev))
                start = prev = t
        runs.append((start, prev))
    long_runs = [{"start": str(a), "end": str(b),
                 "minutes": int((b - a).total_seconds() // 60) + 1}
                for a, b in runs if (b - a).total_seconds() >= 3600]
    out = pd.DataFrame({"open_time": mm.index, "o": mm["o"].to_numpy(float),
                        "h": mm["h"].to_numpy(float),
                        "l": mm["l"].to_numpy(float),
                        "c": mm["c"].to_numpy(float),
                        "volume": mm["volume"].to_numpy(float)})
    out.to_parquet(OUT / f"{sym}.parquet", index=False)
    manifest["symbols"][sym] = {
        "months": months, "n_months": len(months),
        "n_rows_present": int(len(m)), "n_grid": int(len(mm)),
        "n_missing_minutes": n_missing,
        "first_bar": str(first), "last_bar": str(last),
        "zips": zips_ok,
        "gap_runs_over_60min": long_runs,
        "n_gap_runs": len(runs),
    }
    return n_missing, len(runs), len(long_runs)


def main(pack_only: bool = False) -> None:
    import pandas as pd  # noqa: PLC0415 - local import keeps startup light
    _ = pd  # silence unused (pack helpers import their own)
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    manifest = {"source": BASE, "symbols": {},
                "note": "spot 1m presample 2017-2020-09"}
    old = None
    if pack_only and (OUT / "manifest.json").exists():
        old = json.loads((OUT / "manifest.json").read_text())
    for sym, months in PLAN.items():
        raw_by_month, zips_ok = {}, []
        for ym in months:
            zname = f"{sym}-1m-{ym}.zip"
            url = f"{BASE}/{sym}/1m/{zname}"
            zpath = TMP / zname
            if pack_only and zpath.exists():
                raw = zpath.read_bytes()
                if old is not None:
                    expect = {z["month"]: z["sha256"]
                              for z in old["symbols"][sym]["zips"]}[ym]
                    got = hashlib.sha256(raw).hexdigest()
                    if got != expect:
                        raise RuntimeError(f"cached {zname} sha changed")
                got = hashlib.sha256(raw).hexdigest()
                rows = len(read_zip_frames(sym, [ym], {ym: raw})[0])
            else:
                raw = fetch(url)
                chk_txt = fetch(url + ".CHECKSUM").decode().strip()
                expect = chk_txt.split()[0]  # "<sha256>  <filename>"
                got = hashlib.sha256(raw).hexdigest()
                if got != expect:
                    raise RuntimeError(f"sha256 mismatch {zname}")
                zpath.write_bytes(raw)
                rows = len(read_zip_frames(sym, [ym], {ym: raw})[0])
            raw_by_month[ym] = raw
            zips_ok.append({"month": ym, "sha256": got, "rows": rows,
                            "bytes": len(raw)})
            print(f"{sym} {ym}: {rows} rows sha {got[:12]}", flush=True)
        frames = read_zip_frames(sym, months, raw_by_month)
        m, stats = pack_symbol(frames, sym)
        n_missing, n_runs, n_long = pack_and_write(sym, months, m, zips_ok,
                                                  manifest)
        manifest["symbols"][sym].update(stats)
        print(f"{sym}: present={len(m)} missing={n_missing} runs={n_runs} "
              f"long={n_long} submin={stats['n_subminute_rows']} "
              f"phdrop={stats['n_placeholders_dropped']} "
              f"coll={stats['n_floor_collisions']}", flush=True)
    manifest["data_fix"] = ("2017-12..2018-02 archive rows carry sub-minute "
                            "open_time offsets; real rows floored to the "
                            "minute, flat zero-volume backfill placeholders "
                            "dropped (see pack_symbol + PLAN.md disclosure).")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("manifest written", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main(pack_only="--pack-only" in sys.argv)
