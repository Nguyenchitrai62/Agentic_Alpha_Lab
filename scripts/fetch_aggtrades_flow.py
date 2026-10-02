"""Stream Binance USD-M aggTrades (public archive) month by month and keep only 4h taker-flow aggregates by trade size.

Source: https://data.binance.vision/data/futures/um/monthly/aggTrades/{SYM}/ (+ daily files after the last monthly one).
Each aggTrade = one taker order's fill at one price. Per UTC 4h bar and size tier (notional USDT: <10k, 10k-100k, 100k-1M, >=1M) the
script keeps the taker-buy notional, taker-sell notional and the count, so large-order ("whale") flow can be separated from retail
flow. The raw zip is processed in chunks and discarded (no raw data kept). Resumable: finished months are listed in the output.
Output: data/raw/aggflow_20260928/{SYM}_flow_4h.parquet (index bar open UTC; columns {buy,sell,n}_{tier}), manifest_{SYM}.json,
and a 1m store <OUT>_1m/{SYM}/<source file>.parquet (per minute: buy / sell notional and taker order counts in 8 log-size bins) so new
feature definitions (e.g. intrabar flow) never need the raw archive again.

  python scripts/fetch_aggtrades_flow.py [SYM ...] [--months 2024-03] [--market spot] [--orders] [--out DIR]
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
# 1m store (kept so new feature definitions need no re-download): 8 log-spaced notional bins in USDT
BINS_1M = (0.0, 1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, np.inf)
BNAME_1M = ("lt1k", "1k_10k", "10k_30k", "30k_100k", "100k_300k", "300k_1m", "1m_3m", "ge3m")
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


ORDER_LEVEL = False  # --orders: rebuild taker orders (consecutive aggTrades with the same time and side) before tiering


def _orders(ch: pd.DataFrame) -> pd.DataFrame:
    """Merge consecutive aggTrades with identical transact time and side into one taker order (a market order that swept several
    price levels is split into one aggTrade per level); notional = sum over its levels."""
    new = (ch["ts"] != ch["ts"].shift()) | (ch["ibm"] != ch["ibm"].shift())
    oid = new.cumsum()
    g = ch.assign(n=ch["price"].astype(float) * ch["qty"].astype(float)).groupby(oid, sort=False)
    return pd.DataFrame({"ts": g["ts"].first(), "ibm": g["ibm"].first(), "n": g["n"].sum()})


def aggregate(raw: bytes, store_1m: list | None = None) -> pd.DataFrame:
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
                if ORDER_LEVEL:
                    ch = _orders(ch)
                    n = ch["n"]
                else:
                    n = ch["price"].astype(float) * ch["qty"].astype(float)
                ts = pd.to_numeric(ch["ts"])
                unit = "us" if ts.max() > 1e14 else "ms"
                t = pd.to_datetime(ts, unit=unit, utc=True).dt.floor("4h")
                sell = ch["ibm"].astype(str).str.lower().isin(("true", "1"))
                tier = pd.cut(n, TIERS, right=False, labels=TNAME)
                d = pd.DataFrame({"t": t, "tier": tier, "buy": n.where(~sell, 0.0), "sell": n.where(sell, 0.0), "n": 1})
                parts.append(d.groupby(["t", "tier"], observed=True)[["buy", "sell", "n"]].sum())
                if store_1m is not None:
                    t1 = pd.to_datetime(ts, unit=unit, utc=True).dt.floor("min")
                    b1 = pd.cut(n, BINS_1M, right=False, labels=BNAME_1M)
                    d1 = pd.DataFrame({"t": t1, "bin": b1, "buy": n.where(~sell, 0.0), "sell": n.where(sell, 0.0),
                                       "nb": (~sell).astype(np.int32), "ns": sell.astype(np.int32)})
                    store_1m.append(d1.groupby(["t", "bin"], observed=True)[["buy", "sell", "nb", "ns"]].sum())
    g = pd.concat(parts).groupby(level=[0, 1], observed=True).sum().unstack("tier")
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    return g


MARKET = "futures/um"


def source_complete(acc, key: str, listing_start=None) -> bool:
    """A manifest entry is usable only while its closed 4h rows remain on disk."""
    if acc is None or acc.empty:
        return False
    from agentic_alpha_lab.data.coverage import missing_ranges
    stamp = re.search(r"-(\d{4}-\d{2})(-\d{2})?\.zip$", key)
    first = pd.Timestamp(stamp.group(1) + (stamp.group(2) or "-01"), tz="UTC")
    stop = first + (pd.Timedelta(days=1) if stamp.group(2) else pd.offsets.MonthBegin(1))
    # A symbol's first monthly archive can begin mid-month at listing.
    if first < pd.Timestamp("2026-03-01", tz="UTC"):
        first = max(first, acc.index.min() if listing_start is None else listing_start)
    last = min(stop, pd.Timestamp.now(tz="UTC").floor("4h")) - pd.Timedelta(hours=4)
    if first > last:
        return False
    times = acc.index[(acc.index >= first) & (acc.index <= last)]
    return not missing_ranges((t.value // 1_000_000 for t in times),
                              first.value // 1_000_000, last.value // 1_000_000, 4 * 3600_000)


def run(sym: str, only=None, since=None):
    OUT.mkdir(parents=True, exist_ok=True)
    path, man_p = OUT / f"{sym}_flow_4h.parquet", OUT / f"manifest_{sym}.json"  # one manifest per symbol (parallel runs)
    man = json.loads(man_p.read_text()) if man_p.exists() else {"source": BASE, "tiers_usdt": list(TNAME), "done": {}}
    done = set(man["done"].get(sym, []))
    monthly = [k for k in keys(f"data/{MARKET}/monthly/aggTrades/{sym}/") if re.search(r"-\d{4}-\d{2}\.zip$", k)]
    last = max(re.search(r"(\d{4}-\d{2})\.zip", k).group(1) for k in monthly)
    daily = [k for k in keys(f"data/{MARKET}/daily/aggTrades/{sym}/")
             if re.search(r"-(\d{4}-\d{2})-\d{2}\.zip$", k) and re.search(r"-(\d{4}-\d{2})-\d{2}\.zip$", k).group(1) > last]
    acc = pd.read_parquet(path) if path.exists() else None
    todo = [k for k in monthly + daily if k.rsplit("/", 1)[-1] not in done or not source_complete(acc, k)]
    if only:
        todo = [k for k in todo if any(m in k for m in only)]
    if since:
        todo = [k for k in todo if re.search(r"-(\d{4}-\d{2})(-\d{2})?\.zip$", k).group(1) >= since]
    for k in todo:
        t0 = time.time()
        raw = urllib.request.urlopen(BASE + k, timeout=600).read()
        s1: list = []
        g = aggregate(raw, s1)
        if s1:  # 1m store, one parquet per source file (float32 notionals, int32 counts)
            m1 = pd.concat(s1).groupby(level=[0, 1], observed=True).sum().unstack("bin").fillna(0.0)
            m1.columns = [f"{a}_{b}" for a, b in m1.columns]
            d1 = Path(str(OUT) + "_1m") / sym
            d1.mkdir(parents=True, exist_ok=True)
            m1.astype({c: ("int32" if c.startswith("n") else "float32") for c in m1.columns}).to_parquet(
                d1 / (k.rsplit("/", 1)[-1].replace(".zip", ".parquet")), compression="zstd")
        if not source_complete(g, k, acc.index.min() if acc is not None and len(acc) else None):
            raise RuntimeError(f"{sym}: source archive has incomplete closed 4h bars: {k}")
        # Re-fetching a damaged source must replace its rows, rather than doubling notionals.
        acc = g if acc is None else pd.concat([acc.loc[~acc.index.isin(g.index)], g]).sort_index()
        acc.sort_index().to_parquet(path)
        name = k.rsplit("/", 1)[-1]
        if name not in man["done"].setdefault(sym, []):
            man["done"][sym].append(name)
        man_p.write_text(json.dumps(man, indent=1))
        print(sym, k.rsplit("/", 1)[-1], f"{len(raw) / 1e6:.0f}MB", f"{time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*", default=list(SYMS))
    ap.add_argument("--months", nargs="*", default=None)
    ap.add_argument("--market", choices=["um", "spot"], default="um")
    ap.add_argument("--since", default=None, help="first month YYYY-MM to fetch")
    ap.add_argument("--orders", action="store_true", help="order-level tiers (rebuild swept taker orders); output *_orders dir")
    ap.add_argument("--out", default=None, help="output dir (overrides the default; the 1m store goes to <out>_1m)")
    a = ap.parse_args()
    global MARKET, OUT, ORDER_LEVEL
    if a.market == "spot":
        MARKET, OUT = "spot", Path("data/raw/aggflow_spot_20260928")
    if a.orders:
        ORDER_LEVEL, OUT = True, Path(str(OUT) + "_orders")
    if a.out:
        OUT = Path(a.out)
    for s in a.syms:
        run(s, a.months, a.since)


if __name__ == "__main__":
    main()
