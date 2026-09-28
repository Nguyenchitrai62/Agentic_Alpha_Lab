"""Dev-years-only diagnostic: do intrabar taker flows in the 30 minutes BEFORE a dip bid fills predict the bid's result?

Data: the O1 walk-forward dip bids (backend history table orders, source tm_v240, kind 'dip': fill time and net result after fees),
first four walk-forward years only (fills before 2025-09-24); Binance USD-M 1m klines (taker buy quote volume). For a fill at minute f the
window is minutes [f-30, f-1] (known one minute before the fill - a resting bid could be cancelled on it):
  sell_imb   = 1 - 2 * taker_buy_quote / quote_volume over the window (+1 = all taker selling)
  vol_surge  = window quote volume / median 30-minute quote volume of the previous 24 h
  speed      = log return of the window / (sigma_1m * sqrt(30)), sigma_1m = std of 1m returns over the previous 24 h
  trades_surge = window trade count / median 30-minute trade count of the previous 24 h
Reported per year: Spearman correlation with the bid result and the mean result by quintile. Nothing is selected here; a stable,
same-sign relation in all four years would justify a pre-registered cancel rule.

  python research/diagnostics/dip_intrabar/dip_intrabar_dev.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HID = pd.Timestamp("2025-09-24", tz="UTC")


def load_1m(sym: str) -> pd.DataFrame:
    d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_20*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_20*.parquet"
    cols = ["open_time", "close", "quote_volume", "num_trades", "taker_buy_quote_volume"]
    m = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(d.glob(pat)) if 2021 <= int(f.stem[-4:]) <= 2025])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time").sort_index().astype(float)


def main():
    c = sqlite3.connect(ROOT / "artifacts/web/app.db")
    o = pd.read_sql("SELECT symbol, entry_t, pnl_pct FROM orders WHERE source='tm_v240' AND kind='dip' AND pnl_pct IS NOT NULL", c)
    o["t"] = pd.to_datetime(o["entry_t"], unit="ms", utc=True)
    o = o[o.t < HID]
    rows = []
    for sym, g in o.groupby("symbol"):
        m = load_1m(sym)
        r = np.log(m["close"]).diff()
        sig = r.rolling(1440, min_periods=720).std()
        q30 = m["quote_volume"].rolling(30).sum()
        n30 = m["num_trades"].rolling(30).sum()
        tb30 = m["taker_buy_quote_volume"].rolling(30).sum()
        ret30 = np.log(m["close"]).diff(30)
        med_q = q30.rolling(1440, min_periods=720).median().shift(30)
        med_n = n30.rolling(1440, min_periods=720).median().shift(30)
        feat = pd.DataFrame({"sell_imb": 1 - 2 * tb30 / q30, "vol_surge": q30 / med_q, "speed": ret30 / (sig * np.sqrt(30)),
                             "trades_surge": n30 / med_n})
        at = g.t.dt.floor("min") - pd.Timedelta(minutes=1)  # last fully known minute before the fill minute
        f = feat.reindex(at).reset_index(drop=True)
        rows.append(pd.concat([g.reset_index(drop=True)[["symbol", "t", "pnl_pct"]], f], axis=1))
    d = pd.concat(rows, ignore_index=True).dropna()
    d["year"] = [next(y for y in (2024, 2023, 2022, 2021) if t >= pd.Timestamp(f"{y}-09-24", tz="UTC")) for t in d.t]
    out = {"n": len(d), "overall_mean_pct": round(float(d.pnl_pct.mean()), 3), "features": {}}
    for f in ("sell_imb", "vol_surge", "speed", "trades_surge"):
        per = {int(y): round(float(g[[f, "pnl_pct"]].corr(method="spearman").iloc[0, 1]), 3) for y, g in d.groupby("year")}
        qs = pd.qcut(d[f], 5, labels=False, duplicates="drop")
        quint = {int(k): round(float(v), 3) for k, v in d.groupby(qs).pnl_pct.mean().items()}
        quint_year = {int(y): {int(k): round(float(v), 3) for k, v in g.groupby(pd.qcut(g[f], 5, labels=False, duplicates="drop")).pnl_pct.mean().items()}
                      for y, g in d.groupby("year")}
        out["features"][f] = {"spearman_by_year": per, "mean_by_quintile": quint, "mean_by_quintile_by_year": quint_year}
        print(f, "spearman by year", per, "| mean % by quintile", quint, flush=True)
    (Path(__file__).parent / "dip_intrabar_dev.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
