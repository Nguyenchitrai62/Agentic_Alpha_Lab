"""mj W14: majors intraday data download (assignment OPENCODE_MJ_W14_DATA.md).

Majors: ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (BTC already in data/raw/btc_intraday_20260924).

Outputs (only paths this task may write):
  research/mj/fetch_majors.py            (this file)
  data/raw/majors_intraday_20260924/{SYM}_15m.parquet
  data/raw/majors_intraday_20260924/{SYM}_1h.parquet
  data/raw/majors_intraday_20260924/{SYM}_1m_{YYYY}.parquet  (one per symbol-year with rows)
  data/raw/majors_intraday_20260924/manifest.json

1. 1m klines from each symbol's first month (ETH 2019-11, BNB 2020-02,
   XRP 2020-01, SOL 2020-09) to 2026-09-23 (latest complete archive day on run
   date 2026-09-24) from the Binance public archive
   (data.binance.vision, futures/um monthly zips; daily zips for the current
   partial month and as fallback). Zips are read fully in memory
   (requests -> BytesIO -> zipfile); no temp files are written anywhere.
   Some CSVs carry a header row and some do not: handled by inspecting the
   first field (``open_time`` header vs integer millisecond timestamp).
2. 15m, 1h klines via agentic_alpha_lab.data.binance_usdm.fetch_klines
   (Binance USD-M REST). 4h/1d/funding already exist in data/raw/xasset_20260924.
3. Validation: duplicate open_time, missing minutes per year (internal gaps
   within each stored file), OHLC sanity; manifest.json with row counts,
   first/last times, gaps, SHA-256 per file.
4. Cross-check per symbol: resample 1m -> 4h, compare close against
   data/raw/xasset_20260924/{SYM}_4h.parquet; max abs diff in manifest.

Known source limitation (documented, not filled): months/days before a
symbol's futures listing have no archive file (404); those are recorded as
missing-source in the manifest. The REST 15m/1h series cover the full
requested window from each symbol's first month.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from agentic_alpha_lab.data.binance_usdm import (
    KLINE_COLUMNS,
    fetch_klines,
    validate_klines,
)

SYMBOL_STARTS: dict[str, datetime] = {
    "ETHUSDT": datetime(2019, 11, 1, tzinfo=timezone.utc),
    "XRPUSDT": datetime(2020, 1, 1, tzinfo=timezone.utc),
    "BNBUSDT": datetime(2020, 2, 1, tzinfo=timezone.utc),
    "SOLUSDT": datetime(2020, 9, 1, tzinfo=timezone.utc),
}
END_1M = datetime(2026, 9, 23, 23, 59, 59, tzinfo=timezone.utc)
OUT_DIR = Path("data/raw/majors_intraday_20260924")
XASSET_DIR = Path("data/raw/xasset_20260924")
VISION = "https://data.binance.vision/data/futures/um"

NUMERIC_COLS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "num_trades",
    "taker_buy_volume",
    "taker_buy_quote_volume",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_vision_csv(payload: bytes) -> pd.DataFrame:
    """Parse one Binance-vision kline CSV (header row present or not)."""
    text = payload.decode("utf-8", errors="strict")
    first_line = text.split("\n", 1)[0]
    has_header = first_line.split(",", 1)[0].strip() == "open_time"
    frame = pd.read_csv(
        io.StringIO(text),
        header=None,
        skiprows=1 if has_header else 0,
    )
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise ValueError(f"Unexpected column count: {frame.shape[1]}")
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for col in NUMERIC_COLS:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    return frame.drop(columns=["ignore"])


def download_zip_csv(session: requests.Session, url: str) -> pd.DataFrame | None:
    """GET a vision zip fully in memory; return parsed klines or None on 404."""
    resp = session.get(url, timeout=120)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{url}: expected 1csv, got {names}")
        with zf.open(names[0]) as f:
            return parse_vision_csv(f.read())


def month_list(start: datetime, end: datetime) -> list[tuple[int, int]]:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return months


def fetch_1m_archive(
    session: requests.Session, symbol: str, start: datetime
) -> tuple[pd.DataFrame, dict]:
    """Download 1m klines for [start, END_1M]; monthly zips + daily fallback."""
    frames: list[pd.DataFrame] = []
    missing_files: list[str] = []
    used_monthly: list[str] = []
    used_daily: list[str] = []
    months = month_list(start, END_1M)
    last_ym = (END_1M.year, END_1M.month)
    for y, m in months:
        tag = f"{y:04d}-{m:02d}"
        if (y, m) == last_ym:
            use_monthly = False  # current partial month -> daily zips
        else:
            url = f"{VISION}/monthly/klines/{symbol}/1m/{symbol}-1m-{tag}.zip"
            frame = download_zip_csv(session, url)
            if frame is not None:
                frames.append(frame)
                used_monthly.append(tag)
                print(f"{symbol} monthly {tag}: {len(frame)} rows", flush=True)
                continue
            use_monthly = False  # no monthly zip (e.g. pre-listing) -> daily fallback
            missing_files.append(f"{symbol} monthly/{tag} (404 -> daily fallback)")
        # daily zips for each in-range day of this month
        day = datetime(y, m, 1, tzinfo=timezone.utc)
        while (day.year, day.month) == (y, m):
            if start.date() <= day.date() <= END_1M.date():
                dtag = day.strftime("%Y-%m-%d")
                url = f"{VISION}/daily/klines/{symbol}/1m/{symbol}-1m-{dtag}.zip"
                frame = download_zip_csv(session, url)
                if frame is None:
                    missing_files.append(f"{symbol} daily/{dtag} (404)")
                else:
                    frames.append(frame)
                    used_daily.append(dtag)
            day += timedelta(days=1)
        time.sleep(0.05)
    if not frames:
        raise RuntimeError(f"{symbol}: no 1m archive files could be downloaded")
    full = pd.concat(frames, ignore_index=True)
    full = full.drop_duplicates(subset=["open_time"], keep="last")
    full = full.sort_values("open_time").reset_index(drop=True)
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(END_1M) + pd.Timedelta(minutes=1)  # inclusive day end
    full = full.loc[(full["open_time"] >= lo) & (full["open_time"] < hi)].copy()
    full = full.sort_values("open_time").reset_index(drop=True)
    full, extra_daily, extra_missing = fill_gaps_with_daily(session, symbol, full)
    used_daily.extend(extra_daily)
    missing_files.extend(extra_missing)
    info = {
        "used_monthly": used_monthly,
        "used_daily": used_daily,
        "missing_files": missing_files,
    }
    return full, info


def fill_gaps_with_daily(
    session: requests.Session, symbol: str, frame: pd.DataFrame
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Patch internal 1m gaps using daily zips (monthly files can be short).

    Some monthly archive files omit whole days (e.g. XRP/SOL 2022-02,
    2022-04); the daily zips for those dates usually exist. Returns the
    patched frame plus (used_daily, missing_files) additions.
    """
    used_daily: list[str] = []
    missing_files: list[str] = []
    diffs = frame["open_time"].sort_values().diff().dropna()
    over = diffs[diffs > pd.Timedelta(minutes=1)]
    if not len(over):
        return frame, used_daily, missing_files
    missing_days: set[str] = set()
    ts = frame["open_time"].sort_values().reset_index(drop=True)
    for i in over.index:
        start_gap = ts.iloc[i - 1] + pd.Timedelta(minutes=1)
        end_gap = ts.iloc[i] - pd.Timedelta(minutes=1)
        for day in pd.date_range(start_gap.floor("D"), end_gap.floor("D"), freq="D"):
            missing_days.add(day.strftime("%Y-%m-%d"))
    extra: list[pd.DataFrame] = []
    for dtag in sorted(missing_days):
        url = f"{VISION}/daily/klines/{symbol}/1m/{symbol}-1m-{dtag}.zip"
        part = download_zip_csv(session, url)
        if part is None:
            missing_files.append(f"{symbol} daily-gapfill/{dtag} (404)")
        else:
            extra.append(part)
            used_daily.append(dtag)
            print(f"{symbol} gapfill daily {dtag}: {len(part)} rows", flush=True)
    if extra:
        frame = pd.concat([frame, *extra], ignore_index=True)
        frame = frame.drop_duplicates(subset=["open_time"], keep="last")
        frame = frame.sort_values("open_time").reset_index(drop=True)
    return frame, used_daily, missing_files


def describe_gaps(frame: pd.DataFrame, step: pd.Timedelta) -> dict:
    diffs = frame["open_time"].sort_values().diff().dropna()
    over = diffs[diffs > step]
    missing_intervals = int((over / step).apply(lambda x: int(x) - 1).sum()) if len(over) else 0
    return {
        "missing_intervals": missing_intervals,
        "num_gaps": int((diffs > step).sum()),
        "largest_gap": str(over.max()) if len(over) else "0 days",
        "largest_gap_start": str(frame["open_time"].iloc[over.index[0] - 1]) if len(over) else None,
    }


def file_entry(path: Path, frame: pd.DataFrame, step: pd.Timedelta) -> dict:
    quality = validate_klines(frame, "1m" if step == pd.Timedelta(minutes=1) else ("15m" if step == pd.Timedelta(minutes=15) else "1h"))
    return {
        "rows": len(frame),
        "first_open_time": str(frame["open_time"].iloc[0]),
        "last_open_time": str(frame["open_time"].iloc[-1]),
        "last_close_time": str(frame["close_time"].iloc[-1]),
        "duplicate_open_times": int(frame["open_time"].duplicated().sum()),
        "invalid_ohlc_rows": int(quality.invalid_ohlc_rows),
        "non_positive_price_rows": int(quality.non_positive_price_rows),
        "gaps": describe_gaps(frame, step),
        "sha256": sha256_of(path),
    }


def cross_check_4h(symbol: str, bars1m: pd.DataFrame) -> dict:
    """Resample 1m -> 4h and compare close vs xasset 4h REST series."""
    ref_path = XASSET_DIR / f"{symbol}_4h.parquet"
    ref = pd.read_parquet(ref_path)
    ref["open_time"] = pd.to_datetime(ref["open_time"], utc=True)
    work = bars1m.copy()
    work["bar4h"] = work["open_time"].dt.floor("4h")
    agg = work.groupby("bar4h").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        n_1m=("close", "size"),
    )
    ref_idx = pd.to_datetime(ref["open_time"], utc=True).dt.floor("4h")
    ref = ref.set_index(ref_idx)
    common = agg.index.intersection(ref.index)
    # complete 4h bars only (240 1m bars each)
    complete = common[agg.loc[common, "n_1m"] == 240]
    diff = (agg.loc[complete, "close"] - ref.loc[complete, "close"]).abs()
    rel = diff / ref.loc[complete, "close"]
    return {
        "reference": ref_path.as_posix(),
        "archive_1m_4h_bars": int(len(agg)),
        "reference_4h_rows": int(len(ref)),
        "common_4h_bars": int(len(common)),
        "complete_4h_bars": int(len(complete)),
        "max_abs_diff_close": float(diff.max()) if len(diff) else None,
        "mean_abs_diff_close": float(diff.mean()) if len(diff) else None,
        "max_abs_diff_bps": float((rel.max() * 1e4)) if len(diff) else None,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest: dict = {
        "requested_1m_range_end": END_1M.isoformat(),
        "requested_starts": {s: t.isoformat() for s, t in SYMBOL_STARTS.items()},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "klines_15m_1h": "Binance USD-M REST fapi/v1/klines via agentic_alpha_lab.data.binance_usdm.fetch_klines",
            "klines_1m": "Binance public archive data.binance.vision (futures/um monthly + daily zips, in-memory)",
        },
        "symbols": {},
        "files": {},
    }

    for symbol, start in SYMBOL_STARTS.items():
        print(f"=== {symbol} from {start.date()} ===", flush=True)
        sym_entry: dict = {"requested_start": start.isoformat()}

        # 1. 15m + 1h via REST, full window -> latest closed bar.
        for interval in ("15m", "1h"):
            print(f"fetching {symbol} {interval} via REST ...", flush=True)
            bars = fetch_klines(symbol, interval, start, session=session)
            path = OUT_DIR / f"{symbol}_{interval}.parquet"
            bars.to_parquet(path, index=False)
            step = pd.Timedelta(minutes=15) if interval == "15m" else pd.Timedelta(hours=1)
            manifest["files"][path.as_posix()] = file_entry(path, bars, step)
            print(f"{symbol} {interval}: {len(bars)} rows {bars['open_time'].iloc[0]} .. {bars['open_time'].iloc[-1]}", flush=True)

        # 2. 1m via public archive.
        print(f"fetching {symbol} 1m via vision archive ...", flush=True)
        bars1m, archive_info = fetch_1m_archive(session, symbol, start)
        sym_entry["archive"] = archive_info
        by_year = bars1m.groupby(bars1m["open_time"].dt.year)
        for year, group in sorted(by_year, key=lambda kv: kv[0]):
            group = group.sort_values("open_time").reset_index(drop=True)
            path = OUT_DIR / f"{symbol}_1m_{int(year)}.parquet"
            group.to_parquet(path, index=False)
            manifest["files"][path.as_posix()] = file_entry(path, group, pd.Timedelta(minutes=1))
            print(f"{symbol} 1m {year}: {len(group)} rows", flush=True)

        # 3. Cross-check: 1m -> 4h vs xasset 4h REST series.
        cc = cross_check_4h(symbol, bars1m)
        sym_entry["cross_check_1m_to_4h"] = cc
        print(f"{symbol} cross-check 4h: common={cc['common_4h_bars']} complete={cc['complete_4h_bars']} max_abs_diff={cc['max_abs_diff_close']}", flush=True)

        manifest["symbols"][symbol] = sym_entry

    manifest["archive_coverage_note"] = (
        "Vision archive holds futures/um 1m from each symbol's listing month "
        "onwards; days before listing have no archive file (404) and are recorded "
        "under missing_files per symbol. Run date 2026-09-24: latest complete "
        "archive day is 2026-09-23."
    )
    man_path = OUT_DIR / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {man_path}", flush=True)


if __name__ == "__main__":
    main()
