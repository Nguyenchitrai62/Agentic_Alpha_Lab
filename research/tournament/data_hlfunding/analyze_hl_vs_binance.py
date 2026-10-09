"""Descriptive HL-vs-Binance funding comparison (data_hlfunding, no trading rule).

Reads ONLY funding data (no price, no returns anywhere):
  data/raw/hyperliquid_20261007/HL_<COIN>_funding_1h.parquet
  data/raw/binance_premium_20260928/<SYM>_funding.parquet (8h settled, 00/08/16 UTC)

Method (pre-registered in PLAN.md):
  HL rows -> 8h window by floor(time, 8h) -> SUM fundingRate per window
  (HL was 8h-cadence May-Jun 2023, hourly after; summing handles both;
  windows with no HL row are skipped, never imputed).
  Join to Binance settled 8h rate on window start; per coin x calendar year:
  n windows, Pearson corr, mean/p90 of spread (HL-Binance, bps),
  opposite-sign share (both legs nonzero). Each year-row uses only that year.

Outputs (ONLY research/tournament/data_hlfunding/):
  hl_vs_binance_8h.csv, REPORT.md, results.json

Run: .venv/Scripts/python.exe research/tournament/data_hlfunding/analyze_hl_vs_binance.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HL_DIR = os.path.join(ROOT, "data", "raw", "hyperliquid_20261007")
BIN_DIR = os.path.join(ROOT, "data", "raw", "binance_premium_20260928")
OUT_DIR = HERE

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
SYM = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT"}


def hl_8h(hl):
    """Sum HL hourly fundingRates into 8h windows. Pure function (tested)."""
    import pandas as pd

    df = hl.copy()
    df["win"] = df["time"].dt.floor("8h")
    g = df.groupby("win")
    out = pd.DataFrame({
        "win": sorted(df["win"].unique()),
        "hl_sum": g["fundingRate"].sum().values,
        "hl_n": g["fundingRate"].size().values,
    })
    return out.sort_values("win").reset_index(drop=True)


def year_stats(d):
    import numpy as np

    n = len(d)
    if n < 3:
        return {"n": n, "corr": float("nan"), "spread_mean_bps": float("nan"),
                "spread_p90_bps": float("nan"), "opp_sign_share": float("nan"),
                "opp_n": 0, "sign_n": 0}
    x = d["hl_sum"].to_numpy(float)
    y = d["bin_sum"].to_numpy(float)
    corr = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 0 and np.std(y) > 0 else float("nan")
    spread = x - y
    nz = (x != 0) & (y != 0)
    opp = float((((x[nz] > 0) != (y[nz] > 0)).mean())) if nz.sum() > 0 else float("nan")
    return {"n": int(n), "corr": corr,
            "spread_mean_bps": float(np.mean(spread) * 1e4),
            "spread_p90_bps": float(np.quantile(spread, 0.90) * 1e4),
            "opp_sign_share": opp, "opp_n": int(((x[nz] > 0) != (y[nz] > 0)).sum()),
            "sign_n": int(nz.sum())}


def main():
    import numpy as np
    import pandas as pd

    cov_rows = []
    all_rows = []
    for coin in COINS:
        hl = pd.read_parquet(os.path.join(HL_DIR, f"HL_{coin}_funding_1h.parquet"))
        bn = pd.read_parquet(os.path.join(BIN_DIR, f"{SYM[coin]}_funding.parquet"))
        bn = bn.rename(columns={"calc_time": "win", "last_funding_rate": "bin_sum"})
        bn["win"] = pd.to_datetime(bn["win"], utc=True).dt.floor("8h")
        h8 = hl_8h(hl)
        m = h8.merge(bn[["win", "bin_sum"]], on="win", how="inner")
        cov_rows.append({"coin": coin, "hl_first": str(hl["time"].iloc[0]),
                         "hl_last": str(hl["time"].iloc[-1]), "hl_rows": int(len(hl)),
                         "hl_windows": int(len(h8)),
                         "hl_1row_windows": int((h8["hl_n"] == 1).sum()),
                         "overlap_first": str(m["win"].iloc[0]) if len(m) else None,
                         "overlap_last": str(m["win"].iloc[-1]) if len(m) else None,
                         "overlap_windows": int(len(m))})
        m["year"] = m["win"].dt.year
        for year, d in m.groupby("year"):
            s = year_stats(d)
            s.update({"coin": coin, "year": int(year)})
            all_rows.append(s)
        s = year_stats(m)
        s.update({"coin": coin, "year": "all"})
        all_rows.append(s)

    desc = pd.DataFrame(all_rows, columns=["coin", "year", "n", "corr", "spread_mean_bps",
                                           "spread_p90_bps", "opp_sign_share", "opp_n", "sign_n"])
    desc.to_csv(os.path.join(OUT_DIR, "hl_vs_binance_8h.csv"), index=False)

    cov = pd.DataFrame(cov_rows)
    res = {"coverage": cov.to_dict(orient="records"),
           "descriptive": desc.to_dict(orient="records"),
           "method": ("HL rows floored to 8h windows and summed; inner join to Binance "
                      "settled 8h funding on window start; no imputation; no price/return input."),
           "inputs": {"hl_dir": "data/raw/hyperliquid_20261007",
                      "binance": "data/raw/binance_premium_20260928/*_funding.parquet"}}
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)

    # console summary (also hand-copied into REPORT.md tables)
    print("=== coverage ===")
    print(cov.to_string(index=False))
    print("=== descriptive (per coin-year) ===")
    with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
        print(desc.to_string(index=False))
    print("saved hl_vs_binance_8h.csv + results.json", flush=True)


if __name__ == "__main__":
    main()
