"""Strike-level Deribit option trade library (oc_deribitstrike_BTC).

Pure helpers (no network) shared by fetch_strike.py and the pytest file.
Paging/retry code is copied from research/mj/fetch_deribit_options_4h.py
(DO NOT edit research/mj) with one fix: page with start = last timestamp
(not +1) and de-duplicate on trade_id.
"""

from __future__ import annotations

import time

import pandas as pd

URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"


def parse_instrument(name: str) -> dict:
    """Parse 'BTC-4JUN21-41000-C' -> expiry (UTC midnight), strike, cp.

    Raises ValueError on malformed names.
    """
    parts = str(name).split("-")
    if len(parts) != 4:
        raise ValueError(f"bad instrument name: {name!r}")
    _cur, exp_s, strike_s, cp = parts
    if cp not in ("C", "P"):
        raise ValueError(f"bad C/P flag: {name!r}")
    try:
        strike = float(strike_s)
    except ValueError:
        raise ValueError(f"bad strike: {name!r}")
    try:
        expiry = pd.to_datetime(exp_s, format="%d%b%y", utc=True)
    except Exception:
        raise ValueError(f"bad expiry: {name!r}")
    if not (expiry == expiry):  # NaT check
        raise ValueError(f"bad expiry: {name!r}")
    return {"expiry": expiry, "strike": strike, "cp": cp}


def dedup_pages(pages: list[list[dict]]) -> list[dict]:
    """Merge paged trade lists, de-duplicating on trade_id (keep first)."""
    seen: dict[str, dict] = {}
    for page in pages:
        for t in page:
            tid = str(t.get("trade_id"))
            if tid not in seen:
                seen[tid] = t
    return list(seen.values())


def next_start(last_ts: int, prev_start: int | None, n_new: int) -> int:
    """Paging helper: normally resume at last timestamp; if a page added
    no new trades and the cursor did not move, advance by 1 ms to guarantee
    progress (avoids infinite loop on duplicate-only pages)."""
    if n_new == 0 and prev_start is not None and last_ts == prev_start:
        return last_ts + 1
    return last_ts


def fetch_window(s, cur: str, t0: int, t1: int, polite_s: float = 0.25) -> list[dict]:
    """Fetch [t0, t1] ms inclusive, paging with start = last timestamp and
    de-duplicating on trade_id. Polite: sleep `polite_s` between requests,
    back off on 429. Returns de-duplicated trade dicts in time order."""
    rows: list[dict] = []
    seen: set[str] = set()
    start = t0
    while True:
        for attempt in range(6):
            try:
                if polite_s:
                    time.sleep(polite_s)
                r = s.get(URL, params={"currency": cur, "kind": "option",
                                       "start_timestamp": start, "end_timestamp": t1,
                                       "count": 1000, "sorting": "asc"}, timeout=60)
                if r.status_code == 429:
                    time.sleep(2 + 2 * attempt)
                    continue
                res = r.json()["result"]
                break
            except Exception:
                time.sleep(2 + 2 * attempt)
        else:
            raise RuntimeError(f"failed window {t0} {t1}")
        tr = res.get("trades", [])
        n_new = 0
        for t in tr:
            tid = str(t.get("trade_id"))
            if tid not in seen:
                seen.add(tid)
                rows.append(t)
                n_new += 1
        if not res.get("has_more") or not tr:
            rows.sort(key=lambda t: (int(t.get("timestamp", 0)), str(t.get("trade_id"))))
            return rows
        last_ts = int(tr[-1]["timestamp"])
        start = next_start(last_ts, start, n_new)


def aggregate_hourly(trades: list[dict], max_dte: float = 100.0) -> pd.DataFrame:
    """Aggregate raw trades to one row per (UTC hour, instrument).

    Columns: hour, instrument_name, expiry, strike, cp, n, sum_amount,
    vwap_price (coin, amount-weighted), vwap_price_usd (amount-weighted),
    vwap_iv (amount-weighted), min_price, max_price, vwap_index,
    taker_buy_amount, taker_sell_amount, block_amount.
    Keeps ONLY rows with days-to-expiry <= max_dte at trade time.
    """
    if not trades:
        return pd.DataFrame(columns=["hour", "instrument_name", "expiry", "strike", "cp",
                                     "n", "sum_amount", "vwap_price", "vwap_price_usd",
                                     "vwap_iv", "min_price", "max_price", "vwap_index",
                                     "taker_buy_amount", "taker_sell_amount", "block_amount"])
    d = pd.DataFrame(trades)
    for c in ("trade_id", "timestamp", "instrument_name", "price", "iv",
              "index_price", "amount", "direction"):
        if c not in d.columns:
            d[c] = pd.NA
    d = d.dropna(subset=["timestamp", "instrument_name"]).copy()
    d["timestamp"] = d["timestamp"].astype("int64")
    d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
    d["hour"] = d["ts"].dt.floor("h")

    parsed = d["instrument_name"].map(lambda n: _safe_parse(n))
    d["expiry"] = [p[0] for p in parsed]
    d["strike"] = [p[1] for p in parsed]
    d["cp"] = [p[2] for p in parsed]
    d = d[d["expiry"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["hour", "instrument_name", "expiry", "strike", "cp",
                                     "n", "sum_amount", "vwap_price", "vwap_price_usd",
                                     "vwap_iv", "min_price", "max_price", "vwap_index",
                                     "taker_buy_amount", "taker_sell_amount", "block_amount"])
    d["price"] = pd.to_numeric(d["price"], errors="coerce")
    d["iv"] = pd.to_numeric(d["iv"], errors="coerce")
    d["index_price"] = pd.to_numeric(d["index_price"], errors="coerce")
    d["amount"] = pd.to_numeric(d["amount"], errors="coerce")
    d = d.dropna(subset=["price", "index_price", "amount"])
    d = d[d["amount"] > 0]
    if d.empty:
        return pd.DataFrame(columns=["hour", "instrument_name", "expiry", "strike", "cp",
                                     "n", "sum_amount", "vwap_price", "vwap_price_usd",
                                     "vwap_iv", "min_price", "max_price", "vwap_index",
                                     "taker_buy_amount", "taker_sell_amount", "block_amount"])
    d["dte"] = (d["expiry"] - d["ts"]).dt.total_seconds() / 86400.0
    d = d[d["dte"] <= max_dte]
    if d.empty:
        return pd.DataFrame(columns=["hour", "instrument_name", "expiry", "strike", "cp",
                                     "n", "sum_amount", "vwap_price", "vwap_price_usd",
                                     "vwap_iv", "min_price", "max_price", "vwap_index",
                                     "taker_buy_amount", "taker_sell_amount", "block_amount"])
    d["price_usd"] = d["price"] * d["index_price"]
    has_block = "block_trade_id" in d.columns
    if has_block:
        d["_is_block"] = d["block_trade_id"].notna()
    else:
        d["_is_block"] = False
    d["_buy"] = (d["direction"] == "buy").astype(float) * d["amount"]
    d["_sell"] = (d["direction"] == "sell").astype(float) * d["amount"]
    d["_blk"] = d["_is_block"].astype(float) * d["amount"]
    d["_px_amt"] = d["price"] * d["amount"]
    d["_usd_amt"] = d["price_usd"] * d["amount"]
    d["_iv_amt"] = d["iv"] * d["amount"]
    d["_idx_amt"] = d["index_price"] * d["amount"]

    g = d.groupby(["hour", "instrument_name", "expiry", "strike", "cp"], observed=True)
    agg = g.agg(n=("trade_id", "size"), sum_amount=("amount", "sum"),
                px=("_px_amt", "sum"),
                usd=("_usd_amt", "sum"), ivv=("_iv_amt", "sum"),
                min_price=("price", "min"), max_price=("price", "max"),
                idx=("_idx_amt", "sum"), buy=("_buy", "sum"),
                sell=("_sell", "sum"), blk=("_blk", "sum")).reset_index()
    agg["vwap_price"] = agg["px"] / agg["sum_amount"]
    agg["vwap_price_usd"] = agg["usd"] / agg["sum_amount"]
    agg["vwap_iv"] = agg["ivv"] / agg["sum_amount"]
    agg["vwap_index"] = agg["idx"] / agg["sum_amount"]
    out = agg.rename(columns={"buy": "taker_buy_amount", "sell": "taker_sell_amount",
                              "blk": "block_amount"})
    return out[["hour", "instrument_name", "expiry", "strike", "cp", "n",
                "sum_amount", "vwap_price", "vwap_price_usd", "vwap_iv",
                "min_price", "max_price", "vwap_index",
                "taker_buy_amount", "taker_sell_amount", "block_amount"]].sort_values(
        ["hour", "instrument_name"]).reset_index(drop=True)


def _safe_parse(n):
    try:
        p = parse_instrument(n)
        return (p["expiry"], p["strike"], p["cp"])
    except ValueError:
        return (pd.NaT, float("nan"), None)
