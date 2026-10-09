"""Checks for oc_deribitstrike_ETH: rebuild 4h iv_otm_put + coverage.

1. Rebuild the 4h iv_otm_put of data/raw/deribit_opt_20260926 (notional-weighted
   mean IV of OTM puts, strike < index, expiry within 60 days) from the hourly
   strike file and compare (correlation, median abs diff in vol points).
2. Coverage per month: trades, instruments, share of hours with >=1 put trade
   with 5..9 DTE within 0.85..0.98 of index and 20..40 DTE within 0.70..0.90.

Usage: python check_strike.py --months 2021-06 2023-03 2025-06 [--out results_check.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CUR = "ETH"
STRIKE_DIR = Path("data/raw/deribit_strike_20261007") / CUR
REF_4H = Path("data/raw/deribit_opt_20260926") / f"{CUR}_options_4h.parquet"


def rebuild_4h_iv(hourly: pd.DataFrame) -> pd.DataFrame:
    """Rebuild 4h notional-weighted OTM-put IV from hourly strike rows."""
    if hourly.empty:
        return pd.DataFrame(columns=["bar", "iv_rebuilt", "notional"])
    h = hourly.copy()
    h["hour"] = pd.to_datetime(h["hour"], utc=True)
    # OTM put at trade time (approx via hourly VWAP index), expiry within 60d.
    m = (
        (h["cp"] == "P")
        & (h["strike"] < h["vwap_index"])
        & (h["dte_hour"] >= 0)
        & (h["dte_hour"] <= 60)
        & h["vwap_iv"].notna()
    )
    h = h[m].copy()
    if h.empty:
        return pd.DataFrame(columns=["bar", "iv_rebuilt", "notional"])
    h["notional"] = h["sum_amount"] * h["vwap_index"]
    h["bar"] = h["hour"].dt.floor("4h")
    g = h.groupby("bar")
    iv = g.apply(lambda x: float((x["vwap_iv"] * x["notional"]).sum() / x["notional"].sum()), include_groups=False)
    out = pd.DataFrame({"bar": iv.index, "iv_rebuilt": iv.values})
    out["notional"] = g["notional"].sum().values
    return out


def compare_month(ym: str) -> dict:
    f = STRIKE_DIR / f"{CUR}_{ym}.parquet"
    hourly = pd.read_parquet(f)
    ref = pd.read_parquet(REF_4H)
    ref["bar"] = pd.to_datetime(ref["bar"], utc=True)
    m0 = pd.Timestamp(ym + "-01", tz="UTC")
    m1 = m0 + pd.offsets.MonthBegin(1)
    ref_m = ref[(ref["bar"] >= m0) & (ref["bar"] < m1)].copy()
    rb = rebuild_4h_iv(hourly)
    j = ref_m.merge(rb, on="bar", how="inner")
    j = j[j["iv_otm_put"].notna() & j["iv_rebuilt"].notna()].copy()
    n = len(j)
    if n == 0:
        corr, med, mean = float("nan"), float("nan"), float("nan")
    else:
        corr = float(j["iv_otm_put"].corr(j["iv_rebuilt"])) if n > 1 else float("nan")
        diff = (j["iv_rebuilt"] - j["iv_otm_put"]).abs()
        med = float(diff.median())
        mean = float(diff.mean())
    # Coverage
    h = hourly.copy()
    total_trades = int(h["n"].sum()) if len(h) else 0
    n_instr = int(h["instrument_name"].nunique()) if len(h) else 0
    h["hour"] = pd.to_datetime(h["hour"], utc=True)
    hours_in_month = int((m1 - m0).total_seconds() // 3600)
    puts = h[h["cp"] == "P"].copy()
    cov = {}
    if len(puts):
        puts["moneyness"] = puts["strike"] / puts["vwap_index"]
        wk = puts[(puts["dte_hour"] >= 5) & (puts["dte_hour"] <= 9) & (puts["moneyness"] >= 0.85) & (puts["moneyness"] <= 0.98)]
        pr = puts[(puts["dte_hour"] >= 20) & (puts["dte_hour"] <= 40) & (puts["moneyness"] >= 0.70) & (puts["moneyness"] <= 0.90)]
        cov = {
            "hours_total": hours_in_month,
            "hours_weekly_put": int(wk["hour"].nunique()),
            "hours_protective_put": int(pr["hour"].nunique()),
            "share_weekly_put": round(float(wk["hour"].nunique()) / hours_in_month, 4),
            "share_protective_put": round(float(pr["hour"].nunique()) / hours_in_month, 4),
        }
    else:
        cov = {"hours_total": hours_in_month, "hours_weekly_put": 0, "hours_protective_put": 0,
               "share_weekly_put": 0.0, "share_protective_put": 0.0}
    return {
        "month": ym,
        "hour_rows": int(len(hourly)),
        "total_trades": total_trades,
        "instruments": n_instr,
        "iv_compare": {"n_bars": n, "corr": corr, "median_abs_diff": med, "mean_abs_diff": mean},
        "coverage": cov,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    res = [compare_month(ym) for ym in args.months]
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
