"""Stream OKX USDT-margined perpetual trades (public daily archive) and keep taker-ORDER flow aggregates (4h tiers + a 1m store).

Source: https://static.okx.com/cdn/okex/traderecords/trades/daily/YYYYMMDD/{COIN}-USDT-SWAP-trades-YYYY-MM-DD.zip (no account needed;
archive starts 2021-10-01, BNB-USDT-SWAP listed 2022-12-23). Columns: instrument_name, trade_id, side (taker side), price, size
(contracts), created_time (ms). Notional USDT = price * size * contract value (BTC 0.01, ETH 0.1, SOL 1, BNB 0.01, XRP 100).
Early files (until ~2021-11) list every trade twice (BUY and SELL rows with the same trade_id), so the taker side is unknown: trade ids
that appear more than once are dropped, and a day where they are > 1% of the rows is skipped entirely (recorded in the manifest).
Taker orders are rebuilt as on Binance (consecutive trades with the same time and side = one order, notional summed).
Output (same layout as scripts/fetch_aggtrades_flow.py, Binance-style symbol names):
  data/raw/okxflow_20260929/{SYM}_flow_4h.parquet   per UTC 4h bar: {buy,sell,n}_{lt10k,10k_100k,100k_1m,ge1m}
  data/raw/okxflow_20260929_1m/{SYM}/<day>.parquet  per minute: buy / sell notional and order counts in 8 log-size bins
  data/raw/okxflow_20260929/manifest_{SYM}.json     done / missing / skipped days. Resumable; raw files are not kept.

  python scripts/fetch_okx_flow.py [SYM ...] [--since 2021-10-01] [--until 2026-09-28]
"""

from __future__ import annotations

import argparse
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://static.okx.com/cdn/okex/traderecords/trades/daily"
OUT = Path("data/raw/okxflow_20260929")
CT_VAL = {"BTCUSDT": 0.01, "ETHUSDT": 0.1, "SOLUSDT": 1.0, "BNBUSDT": 0.01, "XRPUSDT": 100.0}
START = {"BNBUSDT": "2022-12-23"}
TIERS = (0.0, 1e4, 1e5, 1e6, np.inf)
TNAME = ("lt10k", "10k_100k", "100k_1m", "ge1m")
BINS_1M = (0.0, 1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, np.inf)
BNAME_1M = ("lt1k", "1k_10k", "10k_30k", "30k_100k", "100k_300k", "300k_1m", "1m_3m", "ge3m")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PAUSE_S = 0.2


def _get(url: str) -> bytes | None:
    for k in range(5):
        try:
            return urllib.request.urlopen(url, timeout=300).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(30 * (k + 1))
        except Exception:
            time.sleep(30 * (k + 1))
    raise RuntimeError(f"failed after retries: {url}")


def aggregate(raw: bytes, ct: float):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        d = pd.read_csv(z.open(z.namelist()[0]), usecols=["trade_id", "side", "price", "size", "created_time"])
    n0 = len(d)
    dup = d["trade_id"].duplicated(keep=False)
    if n0 == 0 or dup.mean() > 0.01:
        return None, None, float(dup.mean()) if n0 else 0.0
    d = d[~dup].sort_values(["created_time", "trade_id"])
    sell = d["side"].astype(str).str.lower().eq("sell").to_numpy()
    ts = d["created_time"].to_numpy()
    notional = d["price"].to_numpy(float) * d["size"].to_numpy(float) * ct
    new = np.r_[True, (ts[1:] != ts[:-1]) | (sell[1:] != sell[:-1])]
    oid = np.cumsum(new) - 1
    o = pd.DataFrame({"ts": ts[new], "sell": sell[new], "n": np.bincount(oid, weights=notional)})
    t = pd.to_datetime(o["ts"], unit="ms", utc=True)
    buy_n, sell_n = o["n"].where(~o["sell"], 0.0), o["n"].where(o["sell"], 0.0)
    tier = pd.cut(o["n"], TIERS, right=False, labels=TNAME)
    g = (pd.DataFrame({"t": t.dt.floor("4h"), "tier": tier, "buy": buy_n, "sell": sell_n, "n": 1})
         .groupby(["t", "tier"], observed=True)[["buy", "sell", "n"]].sum().unstack("tier"))
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    b1 = pd.cut(o["n"], BINS_1M, right=False, labels=BNAME_1M)
    m1 = (pd.DataFrame({"t": t.dt.floor("min"), "bin": b1, "buy": buy_n, "sell": sell_n,
                        "nb": (~o["sell"]).astype(np.int32), "ns": o["sell"].astype(np.int32)})
          .groupby(["t", "bin"], observed=True)[["buy", "sell", "nb", "ns"]].sum().unstack("bin").fillna(0.0))
    m1.columns = [f"{a}_{b}" for a, b in m1.columns]
    m1 = m1.astype({c: ("int32" if c.startswith("n") else "float32") for c in m1.columns})
    return g, m1, float(dup.mean())


def run(sym: str, since: str, until: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path, man_p = OUT / f"{sym}_flow_4h.parquet", OUT / f"manifest_{sym}.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {"source": BASE, "ct_val": CT_VAL[sym], "done": [], "missing": [], "skipped": {}}
    seen = set(man["done"]) | set(man["missing"]) | set(man["skipped"])
    d1 = Path(str(OUT) + "_1m") / sym
    d1.mkdir(parents=True, exist_ok=True)
    acc = pd.read_parquet(path) if path.exists() else None
    coin = sym.replace("USDT", "")
    for day in pd.date_range(max(since, START.get(sym, since)), until, freq="D"):
        ds = day.strftime("%Y-%m-%d")
        if ds in seen:
            continue
        t0 = time.time()
        raw = _get(f"{BASE}/{day:%Y%m%d}/{coin}-USDT-SWAP-trades-{ds}.zip")
        if raw is None:
            man["missing"].append(ds)
        else:
            g, m1, dup = aggregate(raw, CT_VAL[sym])
            if g is None:
                man["skipped"][ds] = round(dup, 4)
            else:
                m1.to_parquet(d1 / f"{ds}.parquet", compression="zstd")
                acc = g if acc is None else pd.concat([acc, g]).groupby(level=0).sum()
                acc.sort_index().to_parquet(path)
                man["done"].append(ds)
        man_p.write_text(json.dumps(man, indent=1))
        print(sym, ds, "missing" if raw is None else f"{len(raw) / 1e6:.0f}MB", f"{time.time() - t0:.0f}s", flush=True)
        time.sleep(PAUSE_S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*", default=list(SYMS))
    ap.add_argument("--since", default="2021-10-01")
    ap.add_argument("--until", default=(pd.Timestamp.utcnow() - pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    for s in a.syms:
        run(s, a.since, a.until)


if __name__ == "__main__":
    main()
