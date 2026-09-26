"""cx W18: cross-exchange funding-spread study (descriptive only; no trading claims).

Reads data/raw/cx_funding_20260925/{binance,bybit,okx}_{BTC,ETH,SOL,BNB,XRP}.parquet,
checks settlement grids, aligns per-settlement spreads s = rate_A - rate_B per
exchange pair, and reports per development year (< 2025-09-14 conclusions only):
mean|s|, mean s, share |s| > 0.01% / 0.03%, autocorr of s at lags 1/3/9, and the
annualised gross yield (per unit notional, 3 settlements/day -> x1095) of holding
short-A/long-B (or reverse) by the sign of the PREVIOUS settlement spread, plus the
same with a 7-settlement trailing-mean sign. Settlements >= 2025-09-24 are reported
as one aggregate bucket labelled hidden (not used for conclusions).

Outputs (artifacts/research/cx/): funding_spread_by_year.csv,
settlement_intervals.csv, SUMMARY.md. Never looks at price forward returns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

IN_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "cx_funding_20260925"
OUT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "cx"

BASES = ["BTC", "ETH", "SOL", "BNB", "XRP"]
EXCHS = ["binance", "bybit", "okx"]
PAIRS = [("binance", "bybit"), ("binance", "okx"), ("bybit", "okx")]

DEV_END = pd.Timestamp("2025-09-14", tz="UTC")
HIDDEN_START = pd.Timestamp("2025-09-24", tz="UTC")
SET_PER_YEAR = 3 * 365  # 8-hour settlements


def snap_to_8h(ts: pd.Series) -> pd.Series:
    unix = ts.astype("int64") // 10**9
    slot = np.round(unix / (8 * 3600)) * (8 * 3600)
    return pd.to_datetime(slot.astype("int64"), unit="s", utc=True)


def load_series(exch: str, base: str) -> tuple[pd.Series, pd.DataFrame]:
    df = pd.read_parquet(IN_DIR / f"{exch}_{base}.parquet")
    t = pd.to_datetime(df["fundingTime"], utc=True).dropna()
    r = pd.to_numeric(df["fundingRate"], errors="coerce")
    f = pd.DataFrame({"t": t, "r": r}).dropna().sort_values("t")
    raw = f["t"]
    diffs_h = raw.diff().dt.total_seconds().dropna() / 3600 if len(raw) > 1 else pd.Series([], dtype=float)
    off_min = (raw.astype("int64") // 10**9 % (8 * 3600)) / 60
    off_min = np.minimum(off_min, 480 - off_min)
    n_offgrid = int((off_min > 15).sum())
    check = pd.DataFrame([{
        "exchange": exch, "base": base, "n": int(len(raw)),
        "first": raw.min().isoformat() if len(raw) else None,
        "last": raw.max().isoformat() if len(raw) else None,
        "median_interval_h": float(diffs_h.median()) if len(diffs_h) else float("nan"),
        "share_on_8h_grid": float((off_min <= 15).mean()) if len(raw) else float("nan"),
        "distinct_utc_hours": ",".join(map(str, sorted(raw.dt.hour.unique().tolist()))) if len(raw) else "",
        "n_offgrid_dropped": n_offgrid,
    }])
    keep = (off_min <= 15).to_numpy()
    f = f.iloc[keep].reset_index(drop=True)
    raw = f["t"]
    slot = snap_to_8h(raw.reset_index(drop=True))
    s = pd.Series(f["r"].to_numpy(), index=slot).groupby(level=0).last().sort_index()
    s.index.name = "slot"
    return s, check


def metrics(s: pd.Series) -> dict:
    n = int(len(s))
    out: dict = {"n": n}
    if n == 0:
        return out | {"mean_abs_s": np.nan, "mean_s": np.nan, "share_gt_0p01pct": np.nan,
                      "share_gt_0p03pct": np.nan, "ac1": np.nan, "ac3": np.nan, "ac9": np.nan,
                      "yield_ann_prev_sign": np.nan, "yield_ann_trail7": np.nan}
    v = s.to_numpy(float)
    out["mean_abs_s"] = float(np.mean(np.abs(v)))
    out["mean_s"] = float(np.mean(v))
    out["share_gt_0p01pct"] = float(np.mean(np.abs(v) > 0.0001))
    out["share_gt_0p03pct"] = float(np.mean(np.abs(v) > 0.0003))
    for lag, key in ((1, "ac1"), (3, "ac3"), (9, "ac9")):
        out[key] = float(s.autocorr(lag)) if n > lag + 1 else float("nan")
    prev = np.sign(np.concatenate([[np.nan], v[:-1]]))
    realized = prev * v
    m = prev != 0
    m = m & ~np.isnan(realized)
    out["yield_ann_prev_sign"] = float(np.mean(realized[m]) * SET_PER_YEAR) if m.sum() else float("nan")
    tr = pd.Series(v).rolling(7, min_periods=7).mean().shift(1).to_numpy()
    sig7 = np.sign(tr)
    r7 = sig7 * v
    m7 = (sig7 != 0) & ~np.isnan(r7)
    out["yield_ann_trail7"] = float(np.mean(r7[m7]) * SET_PER_YEAR) if m7.sum() else float("nan")
    return out


def main() -> None:
    assert IN_DIR.exists(), f"missing {IN_DIR}; run fetch_funding.py first"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    series: dict[tuple[str, str], pd.Series] = {}
    checks: list[pd.DataFrame] = []
    for base in BASES:
        for exch in EXCHS:
            s, ck = load_series(exch, base)
            series[(exch, base)] = s
            checks.append(ck)
    pd.concat(checks, ignore_index=True).to_csv(OUT_DIR / "settlement_intervals.csv", index=False)

    rows: list[dict] = []
    for base in BASES:
        for ea, eb in PAIRS:
            a, b = series[(ea, base)], series[(eb, base)]
            both = pd.DataFrame({"a": a, "b": b}).dropna()
            n_a_only = int(len(a) - len(both))
            n_b_only = int(len(b) - len(both))
            if len(both) == 0:
                continue
            s = (both["a"] - both["b"]).rename("s")
            dev = s[s.index < DEV_END]
            hid = s[s.index >= HIDDEN_START]
            for year, grp in dev.groupby(dev.index.year):
                m = metrics(grp)
                rows.append({"base": base, "pair": f"{ea}-{eb}", "exch_A": ea, "exch_B": eb,
                             "period": "development", "year": int(year),
                             "n_both": m["n"], "n_A_only_total": n_a_only, "n_B_only_total": n_b_only,
                             **{k: v for k, v in m.items() if k != "n"}})
            mh = metrics(hid)
            rows.append({"base": base, "pair": f"{ea}-{eb}", "exch_A": ea, "exch_B": eb,
                         "period": "hidden", "year": "hidden_20250924_onwards",
                         "n_both": mh["n"], "n_A_only_total": n_a_only, "n_B_only_total": n_b_only,
                         **{k: v for k, v in mh.items() if k != "n"}})
    tbl = pd.DataFrame(rows).sort_values(["base", "pair", "period", "year"]).reset_index(drop=True)
    tbl.to_csv(OUT_DIR / "funding_spread_by_year.csv", index=False)
    print(f"wrote {len(tbl)} rows to {OUT_DIR / 'funding_spread_by_year.csv'}")


if __name__ == "__main__":
    main()
