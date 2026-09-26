"""Fetch Deribit public option trades (history.deribit.com, no key) and aggregate them to UTC 4h bars.

For each 4h bar [T, T+4h): notional (amount * index_price, USD) of call buys / call sells / put buys / put sells by the
taker 'direction', trade count, and the notional-weighted mean IV of OTM puts (strike < index) and OTM calls
(strike > index) with expiry within 60 days. Output: data/raw/deribit_opt_20260926/{CUR}_options_4h.parquet
(+ manifest). Resumable: completed months are cached in data/raw/deribit_opt_20260926/cache/.

  python research/mj/fetch_deribit_options_4h.py BTC 2019-01-01
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT = Path("data/raw/deribit_opt_20260926")
URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"


def fetch_window(s, cur, t0, t1):
    rows, start = [], t0
    while True:
        for attempt in range(6):
            try:
                r = s.get(URL, params={"currency": cur, "kind": "option", "start_timestamp": start, "end_timestamp": t1,
                                       "count": 1000, "sorting": "asc"}, timeout=60)
                if r.status_code == 429:
                    time.sleep(2 + 2 * attempt)
                    continue
                res = r.json()["result"]
                break
            except Exception:
                time.sleep(2 + 2 * attempt)
        else:
            raise RuntimeError(f"failed window {t0}")
        tr = res.get("trades", [])
        rows += tr
        if not res.get("has_more") or not tr:
            return rows
        start = tr[-1]["timestamp"] + 1


def aggregate(tr):
    d = pd.DataFrame(tr)
    if d.empty:
        return pd.DataFrame()
    parts = d["instrument_name"].str.split("-", expand=True)
    d["expiry"] = pd.to_datetime(parts[1], format="%d%b%y", utc=True, errors="coerce")
    d["strike"] = parts[2].astype(float)
    d["cp"] = parts[3]
    d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
    d["bar"] = d["ts"].dt.floor("4h")
    d["usd"] = d["amount"].astype(float) * d["index_price"].astype(float)
    d["dte"] = (d["expiry"] - d["ts"]).dt.total_seconds() / 86400
    d["otm_put"] = (d["cp"] == "P") & (d["strike"] < d["index_price"]) & (d["dte"] <= 60)
    d["otm_call"] = (d["cp"] == "C") & (d["strike"] > d["index_price"]) & (d["dte"] <= 60)
    g = d.groupby("bar")
    out = pd.DataFrame({
        "call_buy": d[(d.cp == "C") & (d.direction == "buy")].groupby("bar")["usd"].sum(),
        "call_sell": d[(d.cp == "C") & (d.direction == "sell")].groupby("bar")["usd"].sum(),
        "put_buy": d[(d.cp == "P") & (d.direction == "buy")].groupby("bar")["usd"].sum(),
        "put_sell": d[(d.cp == "P") & (d.direction == "sell")].groupby("bar")["usd"].sum(),
        "n_trades": g.size(),
    })
    for k in ("otm_put", "otm_call"):
        x = d[d[k]]
        out[f"iv_{k}"] = (x["iv"] * x["usd"]).groupby(x["bar"]).sum() / x.groupby("bar")["usd"].sum()
    return out.fillna({"call_buy": 0, "call_sell": 0, "put_buy": 0, "put_sell": 0})


def main():
    cur, start = sys.argv[1], pd.Timestamp(sys.argv[2], tz="UTC")
    end = pd.Timestamp("2026-09-25", tz="UTC")
    cache = OUT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    for m0 in pd.date_range(start, end, freq="MS"):
        f = cache / f"{cur}_{m0:%Y-%m}.parquet"
        if f.exists():
            continue
        m1 = min(m0 + pd.offsets.MonthBegin(1), end)
        aggs = []
        for w0 in pd.date_range(m0, m1, freq="4h", inclusive="left"):
            tr = fetch_window(s, cur, int(w0.timestamp() * 1000), int((w0 + pd.Timedelta(hours=4)).timestamp() * 1000) - 1)
            a = aggregate(tr)
            if len(a):
                aggs.append(a)
        pd.concat(aggs).to_parquet(f) if aggs else pd.DataFrame().to_parquet(f)
        print(cur, f"{m0:%Y-%m}", sum(len(a) for a in aggs), "bars", flush=True)
    full = pd.concat([pd.read_parquet(x) for x in sorted(cache.glob(f"{cur}_*.parquet"))])
    full = full[~full.index.duplicated()].sort_index()
    p = OUT / f"{cur}_options_4h.parquet"
    full.reset_index(names="bar").to_parquet(p, index=False)
    (OUT / f"manifest_{cur}.json").write_text(json.dumps(dict(source=URL, rows=len(full), first=str(full.index.min()), last=str(full.index.max()),
                                                               sha256=hashlib.sha256(p.read_bytes()).hexdigest()), indent=1))
    print("done", len(full))


if __name__ == "__main__":
    main()
