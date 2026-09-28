"""Stream Binance USD-M aggTrades (public archive) month by month and keep only 4h taker-flow aggregates by trade size.

Source: https://data.binance.vision/data/futures/um/monthly/aggTrades/{SYM}/ (+ daily files after the last monthly one).
Each aggTrade = one taker order's fill at one price. Per UTC 4h bar and size tier (notional USDT: <10k, 10k-100k, 100k-1M, >=1M) the
script keeps the taker-buy notional, taker-sell notional and the count, so large-order ("whale") flow can be separated from retail
flow. The raw zip is processed in chunks and discarded (no raw data kept). Resumable: finished months are listed in the output.
Output: data/raw/aggflow_20260928/{SYM}_flow_4h.parquet (index bar open UTC; columns {buy,sell,n}_{tier}), manifest.json.

  python scripts/fetch_aggtrades_flow.py [SYM ...] [--months 2024-03] [--market spot]
(--market spot: Binance SPOT aggTrades from data/spot/..., output data/raw/aggflow_spot_20260928)
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
OUT = Path("data/raw/aggflow_20260928")
TIERS = (0.0, 1e4, 1e5, 1e6, np.inf)
TNAME = ("lt10k", "10k_100k", "100k_1m", "ge1m")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def keys(prefix: str) -> list[str]:
    out, marker = [], ""
    while True:
        x = urllib.request.urlopen(f"{S3}?prefix={prefix}&marker={marker}", timeout=60).read().decode()
        k = re.findall(r"<Key>([^<]+)</Key>", x)
        out += [a for a in k if a.endswith(".zip")]
        if "<IsTruncated>true" not in x:
            return out
        marker = k[-1]


def aggregate(raw: bytes) -> pd.DataFrame:
    parts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            head = f.readline().decode()
            has_header = not head[:1].isdigit()
        with z.open(z.namelist()[0]) as f:
            it = pd.read_csv(f, header=0 if has_header else None, chunksize=2_000_000,
                             usecols=[1, 2, 5, 6] if not has_header else None)
            for ch in it:
                if has_header:
                    ch = ch[["price", "quantity", "transact_time", "is_buyer_maker"]]
                ch.columns = ["price", "qty", "ts", "ibm"]
                ts = pd.to_numeric(ch["ts"])
                unit = "us" if ts.max() > 1e14 else "ms"
                t = pd.to_datetime(ts, unit=unit, utc=True).dt.floor("4h")
                n = ch["price"].astype(float) * ch["qty"].astype(float)
                sell = ch["ibm"].astype(str).str.lower().isin(("true", "1"))
                tier = pd.cut(n, TIERS, right=False, labels=TNAME)
                d = pd.DataFrame({"t": t, "tier": tier, "buy": n.where(~sell, 0.0), "sell": n.where(sell, 0.0), "n": 1})
                parts.append(d.groupby(["t", "tier"], observed=True)[["buy", "sell", "n"]].sum())
    g = pd.concat(parts).groupby(level=[0, 1], observed=True).sum().unstack("tier")
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    return g


MARKET = "futures/um"


def run(sym: str, only=None, since=None):
    OUT.mkdir(parents=True, exist_ok=True)
    path, man_p = OUT / f"{sym}_flow_4h.parquet", OUT / f"manifest_{sym}.json"  # one manifest per symbol (parallel runs)
    man = json.loads(man_p.read_text()) if man_p.exists() else {"source": BASE, "tiers_usdt": list(TNAME), "done": {}}
    done = set(man["done"].get(sym, []))
    monthly = [k for k in keys(f"data/{MARKET}/monthly/aggTrades/{sym}/") if re.search(r"-\d{4}-\d{2}\.zip$", k)]
    last = max(re.search(r"(\d{4}-\d{2})\.zip", k).group(1) for k in monthly)
    daily = [k for k in keys(f"data/{MARKET}/daily/aggTrades/{sym}/")
             if re.search(r"-(\d{4}-\d{2})-\d{2}\.zip$", k) and re.search(r"-(\d{4}-\d{2})-\d{2}\.zip$", k).group(1) > last]
    todo = [k for k in monthly + daily if k.rsplit("/", 1)[-1] not in done]
    if only:
        todo = [k for k in todo if any(m in k for m in only)]
    if since:
        todo = [k for k in todo if re.search(r"-(\d{4}-\d{2})(-\d{2})?\.zip$", k).group(1) >= since]
    acc = pd.read_parquet(path) if path.exists() else None
    for k in todo:
        t0 = time.time()
        raw = urllib.request.urlopen(BASE + k, timeout=600).read()
        g = aggregate(raw)
        acc = g if acc is None else pd.concat([acc, g]).groupby(level=0).sum()
        acc.sort_index().to_parquet(path)
        man["done"].setdefault(sym, []).append(k.rsplit("/", 1)[-1])
        man_p.write_text(json.dumps(man, indent=1))
        print(sym, k.rsplit("/", 1)[-1], f"{len(raw) / 1e6:.0f}MB", f"{time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*", default=list(SYMS))
    ap.add_argument("--months", nargs="*", default=None)
    ap.add_argument("--market", choices=["um", "spot"], default="um")
    ap.add_argument("--since", default=None, help="first month YYYY-MM to fetch")
    a = ap.parse_args()
    global MARKET, OUT
    if a.market == "spot":
        MARKET, OUT = "spot", Path("data/raw/aggflow_spot_20260928")
    for s in a.syms:
        run(s, a.months, a.since)


if __name__ == "__main__":
    main()
