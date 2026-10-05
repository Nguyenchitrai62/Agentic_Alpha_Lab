"""Build 4h OHLCV bars (00/04/08/12/16/20 UTC) for the 5 majors from raw 1m klines, minutes < 2025-09-24 only (hard stop)."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "bars_4h.parquet"
DEV_END = pd.Timestamp("2025-09-24", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume"]


def files(sym):
    if sym == "BTCUSDT":
        fs = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        fs = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    # never open files that only hold the hidden year
    return [f for f in fs if int(f.stem[-4:]) <= 2025 and int(f.stem[-4:]) >= 2020]


out = []
for sym in MAJORS:
    parts = []
    for f in files(sym):
        m = pd.read_parquet(f, columns=COLS, filters=[("open_time", "<", DEV_END)])
        parts.append(m)
    m = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
    assert m.open_time.max() < DEV_END
    m["T"] = m.open_time.dt.floor("4h")
    g = m.groupby("T")
    b = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                      "volume": g.volume.sum(), "amount": g.quote_volume.sum(), "nmin": g.size()}).reset_index()
    b["sym"] = sym
    # last bar opened 2025-09-23 20:00 closes at 2025-09-24 00:00 -> complete
    print(sym, len(b), b["T"].min(), b["T"].max(), "incomplete bars:", int((b.nmin < 240).sum()))
    out.append(b)
bars = pd.concat(out, ignore_index=True)
bars.to_parquet(OUT)
print("saved", OUT, len(bars))
