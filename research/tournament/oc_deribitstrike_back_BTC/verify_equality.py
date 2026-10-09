"""Equality check for oc_deribitstrike_back_BTC: re-fetch one month into tmp/ and
compare row-for-row with the forward fetcher's file for the same month.

Usage:
  python verify_equality.py --month 2025-06
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strike_lib import aggregate_hourly, fetch_window  # noqa: E402

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"
CUR = "BTC"
FWD_DIR = Path("data/raw/deribit_strike_20261007") / CUR


def refetch_month(ym: str) -> pd.DataFrame:
    m0 = pd.Timestamp(ym + "-01", tz="UTC")
    m1 = m0 + pd.offsets.MonthBegin(1)
    t0 = int(m0.timestamp() * 1000)
    t1 = int(m1.timestamp() * 1000) - 1
    s = requests.Session()
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2025-06")
    a = ap.parse_args()
    ym = a.month
    TMP.mkdir(parents=True, exist_ok=True)
    fwd = FWD_DIR / f"{CUR}_{ym}.parquet"
    if not fwd.exists():
        print(f"forward file missing: {fwd}, skip equality check")
        return
    print(f"re-fetch {CUR} {ym} into tmp/", flush=True)
    df = refetch_month(ym)
    out = TMP / f"{CUR}_{ym}.refetch.parquet"
    tmpf = out.with_suffix(".tmp.parquet")
    df.to_parquet(tmpf, index=False)
    tmpf.rename(out)
    print(f"wrote {out} rows={len(df)}", flush=True)
    a_df = pd.read_parquet(fwd)
    b_df = pd.read_parquet(out)
    print(f"forward rows={len(a_df)} refetch rows={len(b_df)}", flush=True)
    print(f"forward cols={list(a_df.columns)}", flush=True)
    print(f"refetch cols={list(b_df.columns)}", flush=True)
    same_cols = list(a_df.columns) == list(b_df.columns)
    print(f"same_column_order={same_cols}", flush=True)
    if not same_cols:
        print("EQUALITY: FAIL (schema differs)", flush=True)
        return
    a_s = a_df.sort_values(["hour", "instrument_name"]).reset_index(drop=True)
    b_s = b_df.sort_values(["hour", "instrument_name"]).reset_index(drop=True)
    if len(a_s) != len(b_s):
        print(f"EQUALITY: FAIL (row count {len(a_s)} vs {len(b_s)})", flush=True)
        return
    # Row-for-row compare with tolerance for float round-trips.
    try:
        pd.testing.assert_frame_equal(a_s, b_s, check_exact=False,
                                      rtol=1e-9, atol=1e-12,
                                      check_dtype=False)
        print("EQUALITY: PASS (row-for-row equal within tolerance)", flush=True)
    except AssertionError as e:
        print(f"EQUALITY: FAIL {str(e)[:2000]}", flush=True)


if __name__ == "__main__":
    main()
