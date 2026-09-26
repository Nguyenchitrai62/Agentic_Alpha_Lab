"""Funding-settlement event study - HYPOTHESIS FORMATION ON PRE-ANCHOR DATA ONLY (descriptive).

Uses only 1m data strictly before 2021-09-24 (the first walk-forward anchor), so the 2021-2026 test years stay unseen
for this idea. For each Binance USD-M settlement S (00/08/16 UTC) and each major, window returns relative to prices at
fixed minutes: pre = close(S-1)/open(S-60) - 1, post1 = close(S+59)/open(S) - 1, post4 = close(S+239)/open(S) - 1,
bucketed by the rate settled at S (known at S): < -0.0001, [-0.0001, 0.0001), [0.0001, 0.0003), >= 0.0003.
Prints mean (bps), t-stat and count per bucket, pooled over the five majors, plus a placebo at the non-settlement
bar opens 04/12/20 UTC.

  python research/diagnostics/funding_settlement/event_study_pre_anchor.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CUT = pd.Timestamp("2021-09-24", tz="UTC")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BUCKETS = [(-1, -0.0001, "neg<-1bp"), (-0.0001, 0.0001, "~0"), (0.0001, 0.0003, "1-3bp"), (0.0003, 1, ">=3bp")]


def load_1m(sym):
    d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_20*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_20*.parquet"
    files = [f for f in sorted(d.glob(pat)) if int(f.stem[-4:]) <= 2021]
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return m[m.index < CUT]


def windows(m, times):
    o, c = m["open"], m["close"]
    def at(s, ts):
        return s.reindex(ts).to_numpy(float)
    pre = at(c, times - pd.Timedelta(minutes=1)) / at(o, times - pd.Timedelta(minutes=60)) - 1
    p1 = at(c, times + pd.Timedelta(minutes=59)) / at(o, times) - 1
    p4 = at(c, times + pd.Timedelta(minutes=239)) / at(o, times) - 1
    return pre, p1, p4


def stats(x):
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return None
    return {"bps": round(1e4 * float(x.mean()), 2), "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2), "n": int(len(x))}


def main():
    rows = []
    for s in SYMS:
        m = load_1m(s)
        f = pd.read_parquet(ROOT / f"data/raw/xs_universe_20260924/{s}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("min")
        rate = pd.Series(f["fundingRate"].to_numpy(float), index=ft).groupby(level=0).last()
        rate = rate[(rate.index < CUT - pd.Timedelta(hours=5)) & (rate.index >= m.index[0] + pd.Timedelta(hours=2))]
        pre, p1, p4 = windows(m, rate.index)
        rows.append(pd.DataFrame({"sym": s, "rate": rate.to_numpy(), "pre": pre, "post1": p1, "post4": p4, "kind": "settle"}))
        plc = rate.index + pd.Timedelta(hours=4)
        pre, p1, p4 = windows(m, plc)
        rows.append(pd.DataFrame({"sym": s, "rate": rate.to_numpy(), "pre": pre, "post1": p1, "post4": p4, "kind": "placebo+4h"}))
    d = pd.concat(rows, ignore_index=True)
    out = {"cut": str(CUT), "note": "pre-anchor only; descriptive"}
    for kind in ("settle", "placebo+4h"):
        for lo, hi, name in BUCKETS:
            g = d[(d.kind == kind) & (d.rate >= lo) & (d.rate < hi)]
            out[f"{kind}|{name}"] = {w: stats(g[w].to_numpy()) for w in ("pre", "post1", "post4")}
            print(kind, name, out[f"{kind}|{name}"], flush=True)
    (Path(__file__).parent / "event_study_pre_anchor.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
