"""Deribit strike-level hourly cache for ETH (oc_deribitstrike_ETH).

Source: public Deribit history API, no key:
  https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time
Paging/retry logic copied from research/mj/fetch_deribit_options_4h.py (DO NOT
edit research/mj) with one fix: page with start = last timestamp (inclusive)
and de-duplicate on trade_id, so trades sharing the last millisecond are not
skipped.

Per trade kept: trade_id, timestamp, instrument_name (+ parsed expiry, strike,
C/P), price (coin), mark_price, iv, index_price, amount, direction,
block_trade_id (if present), liquidation (if present).

Aggregation per (UTC hour, instrument): n, sum amount, amount-weighted VWAP
price (coin), VWAP price in USD (price * index), VWAP iv, min/max price, VWAP
index_price, taker buy/sell amount, block-trade amount. ONLY instruments with
days-to-expiry <= 100 at trade time are kept.

Monthly resumable cache: data/raw/deribit_strike_20261007/ETH/ETH_YYYY-MM.parquet
Range 2021-01-01 .. last complete UTC day. Polite: <= 5 req/s, back off on 429.

  python research/tournament/oc_deribitstrike_ETH/fetch_eth_strike.py --months 2021-06
  python research/tournament/oc_deribitstrike_ETH/fetch_eth_strike.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

CUR = "ETH"
ENDPOINT = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
DATA_DIR = Path("data/raw/deribit_strike_20261007") / CUR
HERE = Path(__file__).resolve().parent

MIN_INTERVAL_S = 0.22  # <= ~4.5 req/s, politely under the 5 req/s limit
_last_req_ts = 0.0


def _polite_wait() -> None:
    global _last_req_ts
    dt = time.time() - _last_req_ts
    if dt < MIN_INTERVAL_S:
        time.sleep(MIN_INTERVAL_S - dt)
    _last_req_ts = time.time()


def parse_instrument(name: str):
    """Parse 'ETH-4JUN21-2500-P' -> (expiry_utc_midnight, strike, cp).

    Raises ValueError on unparseable names.
    """
    parts = name.split("-")
    if len(parts) != 4:
        raise ValueError(f"bad instrument name: {name!r}")
    _, exp_s, strike_s, cp = parts
    if cp not in ("C", "P"):
        raise ValueError(f"bad C/P flag: {name!r}")
    try:
        exp = datetime.strptime(exp_s, "%d%b%y").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"bad expiry: {name!r}")
    strike = float(strike_s)
    return exp, strike, cp


def dedup_pages(pages: list[list[dict]]) -> list[dict]:
    """Merge paged trade lists, de-duplicating on trade_id (keep first)."""
    seen: set[str] = set()
    out: list[dict] = []
    for page in pages:
        for t in page:
            tid = t.get("trade_id")
            if tid is None:
                continue
            if tid in seen:
                continue
            seen.add(tid)
            out.append(t)
    return out


def fetch_window(s: requests.Session, cur: str, t0_ms: int, t1_ms: int) -> list[dict]:
    """Fetch all trades in [t0_ms, t1_ms] with inclusive paging + trade_id dedup.

    Paging uses start = last timestamp (NOT +1) so trades sharing the last
    millisecond are not skipped; duplicates are removed on trade_id.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    start = t0_ms
    while True:
        for attempt in range(6):
            try:
                _polite_wait()
                r = s.get(
                    ENDPOINT,
                    params={
                        "currency": cur,
                        "kind": "option",
                        "start_timestamp": start,
                        "end_timestamp": t1_ms,
                        "count": 1000,
                        "sorting": "asc",
                    },
                    timeout=60,
                )
                if r.status_code == 429:
                    time.sleep(2 + 2 * attempt)
                    continue
                res = r.json()["result"]
                break
            except Exception:
                time.sleep(2 + 2 * attempt)
        else:
            raise RuntimeError(f"failed window {t0_ms}..{t1_ms}")
        tr = res.get("trades", [])
        new = 0
        for t in tr:
            tid = t.get("trade_id")
            if tid in seen:
                continue
            seen.add(tid)
            rows.append(t)
            new += 1
        if not res.get("has_more") or not tr:
            return rows
        nxt = tr[-1]["timestamp"]
        if nxt < start:
            raise RuntimeError(f"clock moved backwards in paging {start} -> {nxt}")
        if nxt == start and new == 0:
            # No progress and no new trades: avoid an infinite loop. This can
            # only happen if >1000 trades share one millisecond; stop instead
            # of spinning.
            return rows
        start = nxt


def aggregate_hourly(trades: list[dict]) -> pd.DataFrame:
    """Aggregate raw trades to one row per (UTC hour, instrument)."""
    if not trades:
        return pd.DataFrame()
    d = pd.DataFrame(trades)
    for col in ("trade_id", "timestamp", "instrument_name", "price", "index_price", "amount"):
        if col not in d.columns:
            raise ValueError(f"missing column {col}")
    d = d.dropna(subset=["trade_id", "timestamp", "instrument_name"]).copy()
    d["timestamp"] = d["timestamp"].astype("int64")
    d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
    # Parse instrument -> expiry / strike / cp
    exps, strikes, cps = [], [], []
    ok = []
    for name in d["instrument_name"]:
        try:
            e, s, c = parse_instrument(str(name))
            exps.append(pd.Timestamp(e))
            strikes.append(s)
            cps.append(c)
            ok.append(True)
        except ValueError:
            exps.append(pd.NaT)
            strikes.append(float("nan"))
            cps.append(None)
            ok.append(False)
    d["expiry"] = exps
    d["strike"] = strikes
    d["cp"] = cps
    d = d[ok].copy()
    if d.empty:
        return pd.DataFrame()
    d["dte_trade"] = (d["expiry"] - d["ts"]).dt.total_seconds() / 86400.0
    # Keep ONLY instruments with days-to-expiry <= 100 at trade time (also drop
    # already-expired trades with negative DTE).
    d = d[(d["dte_trade"] >= 0) & (d["dte_trade"] <= 100)].copy()
    if d.empty:
        return pd.DataFrame()
    d["price"] = d["price"].astype(float)
    d["index_price"] = d["index_price"].astype(float)
    d["amount"] = d["amount"].astype(float)
    d["iv"] = pd.to_numeric(d.get("iv"), errors="coerce")
    d["hour"] = d["ts"].dt.floor("h")
    d["usd_price"] = d["price"] * d["index_price"]
    d["direction"] = d.get("direction")
    d["has_block"] = d["block_trade_id"].notna() if "block_trade_id" in d.columns else False

    rows = []
    for (hour, name), g in d.groupby(["hour", "instrument_name"]):
        amt = g["amount"].to_numpy(dtype=float)
        tot = float(amt.sum())
        if tot <= 0:
            continue
        px = g["price"].to_numpy(dtype=float)
        idx = g["index_price"].to_numpy(dtype=float)
        usd = g["usd_price"].to_numpy(dtype=float)
        ivmask = g["iv"].notna().to_numpy()
        iv_w = float((g.loc[ivmask, "iv"] * g.loc[ivmask, "amount"]).sum() / g.loc[ivmask, "amount"].sum()) if ivmask.any() else float("nan")
        dirs = g["direction"].to_numpy() if "direction" in g.columns else []
        buy = float(g.loc[g["direction"] == "buy", "amount"].sum()) if "direction" in g.columns else 0.0
        sell = float(g.loc[g["direction"] == "sell", "amount"].sum()) if "direction" in g.columns else 0.0
        block_amt = float(g.loc[g["has_block"].to_numpy(), "amount"].sum())
        exp = g["expiry"].iloc[0]
        rows.append(
            {
                "hour": hour,
                "instrument_name": name,
                "expiry": exp,
                "strike": float(g["strike"].iloc[0]),
                "cp": str(g["cp"].iloc[0]),
                "dte_hour": (exp - hour).total_seconds() / 86400.0,
                "n": int(len(g)),
                "sum_amount": tot,
                "vwap_price": float((px * amt).sum() / tot),
                "vwap_price_usd": float((usd * amt).sum() / tot),
                "vwap_iv": iv_w,
                "min_price": float(px.min()),
                "max_price": float(px.max()),
                "vwap_index": float((idx * amt).sum() / tot),
                "taker_buy_amount": buy,
                "taker_sell_amount": sell,
                "block_amount": block_amt,
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(["hour", "instrument_name"]).reset_index(drop=True)
    return out


def month_bounds(ym: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    m0 = pd.Timestamp(ym + "-01", tz="UTC")
    m1 = m0 + pd.offsets.MonthBegin(1)
    return m0, m1


def fetch_month(s: requests.Session, ym: str, end_cap: pd.Timestamp) -> pd.DataFrame:
    """Fetch one calendar month (clipped to end_cap) and aggregate hourly."""
    m0, m1 = month_bounds(ym)
    m1 = min(m1, end_cap)
    if m0 >= m1:
        return pd.DataFrame()
    aggs = []
    # Per-day windows keep memory bounded and progress visible.
    for w0 in pd.date_range(m0, m1, freq="D", inclusive="left", tz="UTC"):
        w1 = min(w0 + pd.Timedelta(days=1), m1)
        t0 = int(w0.timestamp() * 1000)
        t1 = int(w1.timestamp() * 1000) - 1
        tr = fetch_window(s, CUR, t0, t1)
        a = aggregate_hourly(tr)
        if len(a):
            aggs.append(a)
        print(f"{CUR} {ym} day {w0:%Y-%m-%d} trades={len(tr)} hourrows={sum(len(x) for x in aggs)}", flush=True)
    if not aggs:
        return pd.DataFrame()
    full = pd.concat(aggs, ignore_index=True)
    # Merge duplicate (hour, instrument) in case of day-boundary overlap.
    full = full.sort_values(["hour", "instrument_name"]).reset_index(drop=True)
    return full


def last_complete_day_utc() -> pd.Timestamp:
    now = pd.Timestamp.now(tz="UTC")
    return now.normalize()  # start of today UTC; data covers days strictly before


def month_list(start_ym: str, end_cap: pd.Timestamp) -> list[str]:
    m0 = pd.Timestamp(start_ym + "-01", tz="UTC")
    months = []
    m = m0
    while m < end_cap:
        months.append(f"{m:%Y-%m}")
        m = m + pd.offsets.MonthBegin(1)
    return months


def write_month_atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def update_manifest(script_sha: str, fetch_start: str, fetch_end: str) -> dict:
    files = sorted(DATA_DIR.glob(f"{CUR}_*.parquet"))
    months = []
    total = 0
    per_file = {}
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        per_file[f.name] = h
        try:
            df = pd.read_parquet(f)
            n = len(df)
        except Exception:
            n = -1
        total += max(n, 0)
        ym = f.stem.replace(f"{CUR}_", "")
        m0, m1 = month_bounds(ym)
        complete = m1 <= last_complete_day_utc() + pd.Timedelta(seconds=1)
        months.append({"month": ym, "file": f.name, "rows": n, "sha256": h, "complete": bool(complete)})
    man = {
        "currency": CUR,
        "endpoint": ENDPOINT,
        "fetch_start": fetch_start,
        "fetch_end": fetch_end,
        "months": months,
        "rows": total,
        "sha256_per_file": per_file,
        "script_sha256": script_sha,
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="*", default=None, help="YYYY-MM list to fetch")
    ap.add_argument("--all", action="store_true", help="fetch 2021-01 .. last complete UTC day")
    ap.add_argument("--skip-complete", action="store_true", default=True)
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    end_cap = last_complete_day_utc()
    if args.all:
        yms = month_list("2021-01", end_cap)
    elif args.months:
        yms = list(args.months)
    else:
        ap.error("pass --months YYYY-MM ... or --all")
        return

    try:
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except Exception:
        script_sha = "unknown"

    s = requests.Session()
    fetch_start_iso = pd.Timestamp.now(tz="UTC").isoformat()
    done, skipped = [], []
    for ym in yms:
        out = DATA_DIR / f"{CUR}_{ym}.parquet"
        m0, m1 = month_bounds(ym)
        is_complete_month = m1 <= end_cap
        if args.skip_complete and out.exists() and is_complete_month:
            # Verify the file reads before skipping.
            try:
                pd.read_parquet(out)
                skipped.append(ym)
                print(f"skip complete {ym}", flush=True)
                continue
            except Exception:
                print(f"re-fetch corrupt {ym}", flush=True)
        df = fetch_month(s, ym, end_cap)
        if len(df) == 0:
            # Write an empty but valid frame so resume logic sees the month was
            # attempted; only treat full months as complete.
            df = pd.DataFrame(
                columns=[
                    "hour", "instrument_name", "expiry", "strike", "cp", "dte_hour", "n",
                    "sum_amount", "vwap_price", "vwap_price_usd", "vwap_iv", "min_price",
                    "max_price", "vwap_index", "taker_buy_amount", "taker_sell_amount",
                    "block_amount",
                ]
            )
        write_month_atomic(df, out)
        done.append((ym, len(df)))
        print(f"wrote {out.name} rows={len(df)}", flush=True)

    fetch_end_iso = pd.Timestamp.now(tz="UTC").isoformat()
    man = update_manifest(script_sha, fetch_start_iso, fetch_end_iso)
    print(json.dumps({"done": done, "skipped": skipped, "rows": man["rows"]}, indent=1))


if __name__ == "__main__":
    main()
