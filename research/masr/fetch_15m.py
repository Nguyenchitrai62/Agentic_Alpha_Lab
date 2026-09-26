"""W12 helper: fetch BTCUSDT 15m klines 2019-09-08 .. latest closed bar.

Writes data/raw/btc_intraday_20260924/klines_15m.parquet (git-ignored).
Safe to re-run: skips if file already exists with recent data.
"""

import torch  # noqa: F401  (import first: Windows DLL load order)
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.data.binance_usdm import fetch_klines, validate_klines

OUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "btc_intraday_20260924" / "klines_15m.parquet"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        cur = pd.read_parquet(OUT)
        print(f"exists: rows={len(cur)} last_close={cur['close_time'].max()}")
        return
    start = datetime(2019, 9, 8, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    print(f"fetching 15m {start.isoformat()} .. {end.isoformat()} ...")
    df = fetch_klines("BTCUSDT", "15m", start, end)
    q = validate_klines(df, "15m")
    print(f"rows={q.rows} first={q.first_open_time} last={q.last_close_time} "
          f"dups={q.duplicate_open_times} gaps={q.missing_intervals} bad_ohlc={q.invalid_ohlc_rows}")
    df.to_parquet(OUT, index=False)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
