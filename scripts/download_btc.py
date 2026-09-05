from __future__ import annotations

import argparse
from pathlib import Path

from agentic_alpha_lab.data.binance_usdm import update_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Download closed Binance USD-M klines")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"),
    )
    args = parser.parse_args()

    frame, quality = update_dataset(
        output_path=args.output,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
    )
    print(f"Saved {len(frame):,} closed candles to {args.output.resolve()}")
    print(quality)


if __name__ == "__main__":
    main()

