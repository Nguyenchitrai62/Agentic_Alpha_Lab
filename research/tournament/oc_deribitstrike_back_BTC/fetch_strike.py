"""Fetch Deribit BTC option trades at STRIKE x HOUR level, BACKWARDS from 2026-09.

Copied from research/tournament/oc_deribitstrike_BTC/fetch_strike.py UNCHANGED
except: (1) output folder is data/raw/deribit_strike_20261007_b/BTC, (2) month
order is BACKWARDS from 2026-09 down, stopping when a month already exists
complete in the forward folder data/raw/deribit_strike_20261007/BTC
(re-checked before starting each month).

Source: public, no key:
  https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time
Paging/retry via strike_lib.fetch_window (copied from
research/mj/fetch_deribit_options_4h.py; DO NOT edit research/mj); fixed paging
risk: start = last timestamp (not +1) with de-duplication on trade_id.

Per trade kept: trade_id, timestamp, instrument_name (+parsed expiry/strike/CP),
price (coin), mark_price, iv, index_price, amount, direction, block_trade_id
(if present), liquidation (if present).

Per (UTC hour, instrument): n, sum amount, amount-weighted VWAP price (coin),
VWAP price in USD (price*index), VWAP iv, min/max price, VWAP index_price,
taker buy/sell amount, block-trade amount. ONLY DTE <= 100 kept.

Monthly resumable cache:
  data/raw/deribit_strike_20261007_b/BTC/BTC_YYYY-MM.parquet
Range BACKWARDS from 2026-09 down to where the forward fetcher has reached.
Polite <= 5 req/s, back off on 429.
Only complete months are written (atomic tmp + rename); existing month files
are skipped. manifest.json is rewritten after each month (same schema as the
forward fetcher).

Usage:
  python fetch_strike.py --months 2025-06
  python fetch_strike.py --backwards
  python fetch_strike.py --backwards --stop-at-forward
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strike_lib import aggregate_hourly, fetch_window  # noqa: E402

CUR = "BTC"
OUT = Path("data/raw/deribit_strike_20261007_b") / CUR
FWD = Path("data/raw/deribit_strike_20261007") / CUR
END_EXCLUSIVE = pd.Timestamp(datetime.now(timezone.utc).date(), tz="UTC")  # start of today UTC
START = pd.Timestamp("2021-01-01", tz="UTC")


def month_range(start_m: str | None = None, end_m: str | None = None) -> list[pd.Timestamp]:
    s = pd.Timestamp((start_m or "2021-01") + "-01", tz="UTC")
    e = pd.Timestamp((end_m or END_EXCLUSIVE.strftime("%Y-%m")) + "-01", tz="UTC")
    months = list(pd.date_range(s, e, freq="MS", tz="UTC"))
    return [m for m in months if m >= START and m < END_EXCLUSIVE + pd.offsets.MonthBegin(1)]


def backward_month_list() -> list[pd.Timestamp]:
    """Complete months from latest (2026-09 on 2026-10-07) backwards to 2021-01."""
    months = month_range("2021-01", END_EXCLUSIVE.strftime("%Y-%m"))
    # Keep only complete months (month end <= start of today UTC).
    months = [m for m in months if m + pd.offsets.MonthBegin(1) <= END_EXCLUSIVE]
    return list(reversed(months))


def forward_has_month(ym: str) -> bool:
    """True if the forward fetcher already has month ym complete.

    Complete = file present + non-empty + (listed in forward manifest.json
    or readable parquet with >0 rows). Re-checked before each month.
    """
    f = FWD / f"{CUR}_{ym}.parquet"
    if not f.exists() or f.stat().st_size == 0:
        return False
    try:
        man_p = FWD / "manifest.json"
        if man_p.exists():
            man = json.loads(man_p.read_text())
            months = man.get("months", [])
            names: list[str] = []
            for m in months:
                if isinstance(m, dict):
                    names.append(m.get("file", "") or m.get("month", ""))
                else:
                    names.append(str(m))
            if f.name in names or ym in names:
                # Verify readable with rows before trusting the manifest.
                try:
                    df = pd.read_parquet(f)
                    return len(df) > 0
                except Exception:
                    return False
        df = pd.read_parquet(f)
        return len(df) > 0
    except Exception:
        return False


def fetch_month(s: requests.Session, m0: pd.Timestamp) -> pd.DataFrame:
    m1 = min(m0 + pd.offsets.MonthBegin(1), END_EXCLUSIVE)
    if m1 <= m0:
        return pd.DataFrame()
    t0 = int(m0.timestamp() * 1000)
    t1 = int(m1.timestamp() * 1000) - 1
    trades = fetch_window(s, CUR, t0, t1)
    keep = []
    for t in trades:
        keep.append({
            "trade_id": str(t.get("trade_id")),
            "timestamp": int(t["timestamp"]),
            "instrument_name": t.get("instrument_name"),
            "price": t.get("price"),
            "mark_price": t.get("mark_price"),
            "iv": t.get("iv"),
            "index_price": t.get("index_price"),
            "amount": t.get("amount"),
            "direction": t.get("direction"),
            "block_trade_id": t.get("block_trade_id"),
            "liquidation": t.get("liquidation"),
        })
    return aggregate_hourly(keep)


def write_manifest(extra: dict | None = None):
    files = sorted(OUT.glob(f"{CUR}_*.parquet"))
    entries = []
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        df = pd.read_parquet(f, columns=["hour"])
        entries.append({"file": f.name, "rows": int(len(df)),
                        "sha256": h,
                        "first": str(df["hour"].min()) if len(df) else None,
                        "last": str(df["hour"].max()) if len(df) else None})
    try:
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except Exception:
        script_sha = None
    man = {"currency": CUR,
           "endpoint": "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time",
           "range": [str(START), str(END_EXCLUSIVE)],
           "months": [e["file"] for e in entries],
           "files": entries,
           "script_sha256": script_sha,
           "fetch_window": {"start": str(START), "end_exclusive": str(END_EXCLUSIVE)},
           "direction": "backwards"}
    if extra:
        man.update(extra)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--backwards", action="store_true")
    ap.add_argument("--start", default="2021-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--stop-at-forward", action="store_true", default=True)
    ap.add_argument("--no-stop-at-forward", dest="stop_at_forward",
                    action="store_false")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.months:
        months = [pd.Timestamp(m + "-01", tz="UTC") for m in a.months]
    elif a.backwards or a.all:
        # BACKWARDS: latest complete month first, down to 2021-01.
        months = backward_month_list()
    else:
        months = month_range(a.start, a.end or END_EXCLUSIVE.strftime("%Y-%m"))
    s = requests.Session()
    done, skipped, met_forward = [], [], []
    for m0 in months:
        ym = f"{m0:%Y-%m}"
        # Re-check the forward folder before starting each month.
        if a.stop_at_forward and forward_has_month(ym):
            print(f"meet forward fetcher at {ym}: stop", flush=True)
            met_forward.append(ym)
            break
        f = OUT / f"{CUR}_{ym}.parquet"
        if f.exists() and f.stat().st_size > 0:
            try:
                df0 = pd.read_parquet(f)
                if len(df0):
                    skipped.append(ym)
                    continue
            except Exception:
                pass
        m1 = min(m0 + pd.offsets.MonthBegin(1), END_EXCLUSIVE)
        print(f"fetch {CUR} {ym} [{m0.date()} .. {m1.date()})", flush=True)
        agg = fetch_month(s, m0)
        tmp = f.with_suffix(".tmp.parquet")
        agg.to_parquet(tmp, index=False)
        tmp.rename(f)
        print(f"wrote {f.name} rows={len(agg)}", flush=True)
        done.append(ym)
        write_manifest()
    man = write_manifest()
    print(f"done new={done} skipped={skipped} met_forward={met_forward} "
          f"months_in_cache={len(man['months'])}")


if __name__ == "__main__":
    main()
