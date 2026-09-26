"""v114: v113 plus Bitstamp BTC-USD 2013-2015 history (registry parallel-20260906-r2 / v114).

BTC 1h history = Bitstamp btcusd 1h (data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet) from 2013-01-01 (2011-12
excluded as illiquid: 40-89% zero-volume hours) up to the first Coinbase hour, then Coinbase (v113), then Binance.
Aggregation, books, vol targets and costs exactly as the v113 script (v92 LO, v94 LS, v96 blend); ETH as v113.
Adds the 2014 bear market to the training history. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v114/v114_bitstamp_history.py
"""

from __future__ import annotations

import importlib.util
import json
import hashlib
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v113", HERE.parent / "v113" / "v113_longer_history.py")
v113 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v113)
_cb_bars = v113.cb_bars


def cb_bars_ext(product: str, rule: str, min_hours: int) -> pd.DataFrame:
    if product != "BTC-USD":
        return _cb_bars(product, rule, min_hours)
    cb = pd.concat([pd.read_parquet("data/raw/coinbase_20260925/BTC-USD_1h_pre2017.parquet"),
                    pd.read_parquet("data/raw/coinbase_20260925/BTC-USD_1h.parquet")], ignore_index=True)
    cb["open_time"] = pd.to_datetime(cb["open_time"], utc=True)
    bs = pd.read_parquet("data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet")
    bs["open_time"] = pd.to_datetime(bs["open_time"], utc=True)
    bs = bs[(bs.open_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (bs.open_time < cb.open_time.min())]
    h = pd.concat([bs[["open_time", "open", "high", "low", "close", "volume"]], cb[["open_time", "open", "high", "low", "close", "volume"]]], ignore_index=True)
    h = h.drop_duplicates("open_time").set_index("open_time").sort_index()
    h["qv"] = h["volume"] * h["close"]
    g = h.resample(rule, label="left", closed="left")
    b = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                      "volume": g["volume"].sum(), "quote_volume": g["qv"].sum(), "n": g["close"].count()})
    b = b[b["n"] >= min_hours].drop(columns="n").reset_index()
    b["close_time"] = b["open_time"] + pd.Timedelta(rule) - pd.Timedelta(milliseconds=1)
    return b


def main():
    v113.cb_bars = cb_bars_ext
    v113.HERE = HERE  # write results into v114/
    v113.main()
    p = HERE / "v113_result.json"
    res = json.loads(p.read_text())
    res["version"] = "v114"
    raw = json.dumps(res, indent=1, default=str)
    (HERE / "v114_result.json").write_text(raw)
    p.unlink()
    print("v114 sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
