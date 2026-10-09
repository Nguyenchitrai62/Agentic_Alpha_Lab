"""Checks for oc_deribitstrike_BTC. Writes REPORT.md + results.json.

Check 1: for sample months (2021-06, 2023-03, 2025-06) rebuild the 4h
  iv_otm_put of data/raw/deribit_opt_20260926 (notional-weighted mean IV of
  OTM puts, strike < index, expiry within 60 days) from the hourly strike
  file and compare (correlation, median abs diff in vol points).
Check 2: coverage per month: trades, instruments, share of hours with at
  least one put trade with 5..9 DTE within 0.85..0.98 of index (weekly
  put-write strikes) and with 20..40 DTE within 0.70..0.90 (protective puts).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

CUR = "BTC"
STRIKE = Path(f"data/raw/deribit_strike_20261007/{CUR}")
REF = Path("data/raw/deribit_opt_20260926") / f"{CUR}_options_4h.parquet"
OUTDIR = Path("research/tournament/oc_deribitstrike_BTC")
SAMPLES = ["2021-06", "2023-03", "2025-06"]


def rebuild_4h_iv(month: str) -> pd.DataFrame:
    f = STRIKE / f"{CUR}_{month}.parquet"
    df = pd.read_parquet(f)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    df["bar"] = df["hour"].dt.floor("4h")
    df["dte"] = (pd.to_datetime(df["expiry"], utc=True) - df["hour"]).dt.total_seconds() / 86400
    m = (df["cp"] == "P") & (df["strike"] < df["vwap_index"]) & (df["dte"] <= 60)
    x = df[m].copy()
    if not x.empty:
        x["notional"] = x["sum_amount"] * x["vwap_index"]
        x["iv_w"] = x["vwap_iv"] * x["notional"]
        g = x.groupby("bar")
        return pd.DataFrame({"iv_rebuilt": g["iv_w"].sum() / g["notional"].sum(),
                             "n_rows": g.size()}).reset_index()
    return pd.DataFrame(columns=["bar", "iv_rebuilt", "n_rows"])


def check1() -> dict:
    ref = pd.read_parquet(REF)
    ref["bar"] = pd.to_datetime(ref["bar"], utc=True)
    out = {}
    for month in SAMPLES:
        rb = rebuild_4h_iv(month)
        m = rb["bar"].dt.strftime("%Y-%m") == month
        # also include bars whose 4h window overlaps the month: use bar month
        r = ref[ref["bar"].dt.strftime("%Y-%m") == month][["bar", "iv_otm_put"]]
        j = r.merge(rb, on="bar", how="inner")
        j = j.dropna(subset=["iv_otm_put", "iv_rebuilt"])
        if len(j):
            corr = float(j["iv_otm_put"].corr(j["iv_rebuilt"])) if j["iv_otm_put"].std() > 0 else float("nan")
            mad = float((j["iv_otm_put"] - j["iv_rebuilt"]).abs().median())
            mean_abs = float((j["iv_otm_put"] - j["iv_rebuilt"]).abs().mean())
            bias = float((j["iv_rebuilt"] - j["iv_otm_put"]).mean())
        else:
            corr = mad = mean_abs = bias = float("nan")
        out[month] = {"n_bars": int(len(j)), "corr": corr, "median_abs_diff": mad,
                      "mean_abs_diff": mean_abs, "bias_rebuilt_minus_ref": bias}
    return out


def check2(months: list[str] | None = None) -> dict:
    files = sorted(STRIKE.glob(f"{CUR}_*.parquet")) if months is None else \
        [STRIKE / f"{CUR}_{m}.parquet" for m in months]
    out = {}
    for f in files:
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        month = f.stem.replace(f"{CUR}_", "")
        if df.empty:
            out[month] = {"trades": 0, "instruments": 0, "hours": 0,
                          "share_weekly_put_hours": 0.0, "share_protective_put_hours": 0.0}
            continue
        df["hour"] = pd.to_datetime(df["hour"], utc=True)
        df["dte"] = (pd.to_datetime(df["expiry"], utc=True) - df["hour"]).dt.total_seconds() / 86400
        df["moneyness"] = df["strike"] / df["vwap_index"]
        hours = df["hour"].nunique()
        puts = df[df["cp"] == "P"]
        w = puts[(puts["dte"] >= 5) & (puts["dte"] <= 9) &
                 (puts["moneyness"] >= 0.85) & (puts["moneyness"] <= 0.98)]
        p = puts[(puts["dte"] >= 20) & (puts["dte"] <= 40) &
                 (puts["moneyness"] >= 0.70) & (puts["moneyness"] <= 0.90)]
        out[month] = {"trades": int(df["n"].sum()), "instruments": int(df["instrument_name"].nunique()),
                      "hours": int(hours),
                      "share_weekly_put_hours": float(w["hour"].nunique() / hours) if hours else 0.0,
                      "share_protective_put_hours": float(p["hour"].nunique() / hours) if hours else 0.0}
    return out


def main():
    c1 = check1()
    c2 = check2()
    all_months = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13)]
    all_months = [m for m in all_months if "2021-01" <= m <= "2026-10"]
    have = sorted(c2)
    missing = [m for m in all_months if m not in have]
    res = {"currency": CUR, "check1_iv_rebuild": c1, "coverage": c2,
           "months_done": have, "months_missing": missing}
    (OUTDIR / "results.json").write_text(json.dumps(res, indent=1))
    lines = ["# oc_deribitstrike_BTC REPORT", "",
             f"Sample months: {', '.join(SAMPLES)}", "",
             "## Check 1: rebuild 4h iv_otm_put (notional-weighted OTM puts, strike<index, DTE<=60)",
             "Ref: data/raw/deribit_opt_20260926/BTC_options_4h.parquet.", ""]
    lines.append("| month | bars | corr | median_abs_diff | mean_abs_diff | bias |")
    lines.append("|---|---|---|---|---|---|")
    for m in SAMPLES:
        r = c1.get(m, {})
        lines.append(f"| {m} | {r.get('n_bars')} | {r.get('corr', float('nan')):.4f} | "
                     f"{r.get('median_abs_diff', float('nan')):.3f} | {r.get('mean_abs_diff', float('nan')):.3f} | "
                     f"{r.get('bias_rebuilt_minus_ref', float('nan')):.3f} |")
    lines += ["", "Expected: small differences (hour-level amount-weighted VWAP re-aggregated by",
              "notional vs trade-level notional weighting; DTE/index sampled hourly vs per trade).",
              "Large/bias differences would need explanation.", "",
              "## Check 2: coverage (per month)", "",
              "| month | trades | instruments | hours | weekly-put-hour share | protective-put-hour share |",
              "|---|---|---|---|---|---|"]
    for m in sorted(c2):
        r = c2[m]
        lines.append(f"| {m} | {r['trades']} | {r['instruments']} | {r['hours']} | "
                     f"{r['share_weekly_put_hours']:.3f} | {r['share_protective_put_hours']:.3f} |")
    lines += ["", "Weekly-put = put trade 5..9 DTE, strike/index 0.85..0.98. "
              "Protective-put = 20..40 DTE, 0.70..0.90.", "",
              "## Cache status", "",
              f"Months done ({len(have)}): {', '.join(have)}",
              f"Months missing ({len(missing)}): {', '.join(missing) if missing else 'none'}", "",
              "## Method",
              "Public history.deribit.com, currency=BTC, kind=option, count=1000, sorting=asc,",
              "paged by timestamp; resume cursor = last timestamp (not +1), de-duplicate on trade_id",
              "(fix vs research/mj/fetch_deribit_options_4h.py, which is NOT edited).",
              "Per (UTC hour, instrument): n, sum amount, amount-weighted VWAP price (coin),",
              "VWAP price USD (price*index), VWAP iv, min/max price, VWAP index, taker buy/sell",
              "amount, block-trade amount. Only DTE <= 100 kept. Monthly files written atomically",
              "(tmp + rename); manifest.json holds sha256 per file + script sha + fetch window.",
              "<= 5 req/s, backoff on 429.", "",
              "## Tests",
              "tests/test_oc_deribitstrike_btc.py: paging de-dup on synthetic equal-timestamp",
              "boundary, instrument-name parsing, hourly aggregation hand case, DTE filter.",
              "Run: .venv/Scripts/python.exe -m pytest tests/test_oc_deribitstrike_btc.py -q", ""]
    (OUTDIR / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
