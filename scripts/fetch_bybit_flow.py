"""Stream Bybit USDT-perpetual public trades (public.bybit.com/trading) and keep 4h ORDER-level taker-flow aggregates by size tier.

Each daily csv.gz lists every fill (timestamp in seconds with sub-ms precision, taker side, size, price, foreignNotional in USDT).
Consecutive fills with the same timestamp and side are one taker order (a market order sweeping several levels); per UTC 4h bar and
tier of the ORDER notional (<10k, 10k-100k, 100k-1M, >=1M USDT) the script keeps taker buy / sell notional and the order count - the
same table as the Binance order-level archive (scripts/fetch_aggtrades_flow.py --orders), so the v236 feature formulas apply.
Resumable (one manifest per symbol), raw files are not kept.
Output: data/raw/bybitflow_20260929/{SYM}_flow_4h.parquet, manifest_{SYM}.json

  python scripts/fetch_bybit_flow.py SYM [SYM ...]
"""

from __future__ import annotations

import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://public.bybit.com/trading/"
OUT = Path("data/raw/bybitflow_20260929")
TIERS = (0.0, 1e4, 1e5, 1e6, np.inf)
TNAME = ("lt10k", "10k_100k", "100k_1m", "ge1m")


PAUSE_S = 2.0          # polite pause between files (the CDN answers 403 to bursts)
BLOCK_WAIT_S = 600     # wait after a 403 before retrying
BLOCK_RETRIES = 12


def _get(url: str, timeout: int) -> bytes:
    for attempt in range(BLOCK_RETRIES + 1):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429) or attempt == BLOCK_RETRIES:
                raise
            print(f"HTTP {e.code} (rate limited) - waiting {BLOCK_WAIT_S}s", flush=True)
            time.sleep(BLOCK_WAIT_S)
        except Exception:
            if attempt >= 2:
                raise
            time.sleep(10)
    raise RuntimeError(url)


def day_files(sym: str) -> list[str]:
    html = _get(BASE + sym + "/", 60).decode()
    return sorted(set(re.findall(rf'href="({sym}\d{{4}}-\d{{2}}-\d{{2}}\.csv\.gz)"', html)))


def aggregate(raw: bytes) -> pd.DataFrame:
    d = pd.read_csv(io.BytesIO(gzip.decompress(raw)), usecols=["timestamp", "side", "foreignNotional"])
    d = d.sort_values("timestamp", kind="stable")
    ts, side = d["timestamp"].to_numpy(), d["side"].to_numpy()
    new = np.r_[True, (ts[1:] != ts[:-1]) | (side[1:] != side[:-1])]
    oid = np.cumsum(new)
    g = pd.DataFrame({"oid": oid, "ts": ts, "sell": side == "Sell", "n": d["foreignNotional"].astype(float).to_numpy()})
    o = g.groupby("oid", sort=False).agg(ts=("ts", "first"), sell=("sell", "first"), n=("n", "sum"))
    t = pd.to_datetime(o["ts"], unit="s", utc=True).dt.floor("4h")
    tier = pd.cut(o["n"], TIERS, right=False, labels=TNAME)
    x = pd.DataFrame({"t": t, "tier": tier, "buy": o["n"].where(~o["sell"], 0.0), "sell": o["n"].where(o["sell"], 0.0), "n": 1.0})
    a = x.groupby(["t", "tier"], observed=True)[["buy", "sell", "n"]].sum().unstack("tier")
    a.columns = [f"{k}_{b}" for k, b in a.columns]
    return a


def run(sym: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path, man_p = OUT / f"{sym}_flow_4h.parquet", OUT / f"manifest_{sym}.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {"source": BASE, "tiers_usdt": list(TNAME), "done": []}
    done = set(man["done"])
    acc = pd.read_parquet(path) if path.exists() else None
    for f in [f for f in day_files(sym) if f not in done]:
        t0 = time.time()
        raw = _get(BASE + sym + "/" + f, 600)
        time.sleep(PAUSE_S)
        g = aggregate(raw)
        acc = g if acc is None else pd.concat([acc, g]).groupby(level=0).sum()
        acc.sort_index().to_parquet(path)
        man["done"].append(f)
        man_p.write_text(json.dumps(man))
        print(sym, f, f"{len(raw) / 1e6:.0f}MB", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    for s in sys.argv[1:]:
        run(s)
