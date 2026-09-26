"""v181: out-of-universe test of the frozen dip-rebound ladder on six other perps (registry v181; research only).

Why: the dip-rebound effect (v171-v180) was found and refined on the five majors over 2021-2026; the rules were not
fitted on other assets. If the effect is a real market mechanism (liquidation overshoot) and not data-mining on the
majors, the FROZEN v178 ladder should also earn on liquid perps it has never seen. Trading stays majors-only (user rule);
this is evidence only.
Fixed before running (nothing is re-chosen):
- Assets: DOGEUSDT, ADAUSDT, LINKUSDT, LTCUSDT, AVAXUSDT, TRXUSDT (Binance USD-M 1m archive; 4h opens and funding from
  data/raw/xs_universe_20260924).
- Rule exactly v178/v179: rungs 2.5/3/3.5/4 sigma below open(T), sigma = std of 360 4h open-to-open returns ending at t,
  resting bids live in minutes 16..238, maker 0.0002 fill at the bid on a 1m trade-through, exit at open(T+4h) with
  taker 0.0005 and slippage max(2 bps, 0.25 * range/open of that minute), long pays the funding settled at T+4h.
  Stress costs: maker 0.0004, taker 0.0007 + 5 bps.
- Per anchor year (the five 2021-2025 anchors, 365 days each) and per asset: rung fills, mean net rung return (bps),
  and the equal-rung sleeve (0.25/4 per rung per asset, all six assets) net % and DD.
- PRE-REGISTERED SUCCESS CRITERION: pooled mean net rung return > 0 in at least 4 of the 5 anchor years under normal
  costs AND pooled mean > 0 over all years under stress costs.

  python research/parallel/rounds/parallel-20260906-r2/v181/v181_out_of_universe.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
XS = ROOT / "data/raw/xs_universe_20260924"
M1 = ROOT / "data/raw/alts_intraday_20260926"
SYMS = ("DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT")
RUNGS = (2.5, 3.0, 3.5, 4.0)
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
START = pd.Timestamp("2020-02-01", tz="UTC")


def cube(G, sym):
    starts = G + pd.Timedelta(hours=4)
    n = len(G)
    A = {k: np.full((n, 240), np.nan) for k in ("open", "high", "low")}
    pos = pd.Series(np.arange(n), index=starts)
    files = sorted(M1.glob(f"{sym}_1m_20*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time")
    T = m["open_time"].dt.floor("4h")
    i = pos.reindex(T).to_numpy()
    ok = ~np.isnan(i)
    off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
    for k in A:
        A[k][i[ok].astype(int), off[ok]] = m[k].to_numpy(float)[ok]
    return A


def rung_returns(G, sym, maker, taker, extra):
    k4 = pd.read_parquet(XS / f"{sym}_4h.parquet")
    o = pd.Series(k4["open"].to_numpy(float), index=pd.to_datetime(k4["open_time"], utc=True)).reindex(G)
    o1, o2 = o.shift(-1).to_numpy(), o.shift(-2).to_numpy()
    sig = o.pct_change().rolling(360, min_periods=120).std().to_numpy()
    f = pd.read_parquet(XS / f"{sym}_funding.parquet")
    ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
    fund = f.groupby(ft)["fundingRate"].sum().reindex(G).fillna(0.0).shift(-2).fillna(0.0).to_numpy()
    A = cube(G, sym)
    low = A["low"][:, 16:239]
    xr = np.full(len(G), np.nan)
    xr[:-1] = (A["high"][1:, 0] - A["low"][1:, 0]) / A["open"][1:, 0]
    s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr)) + extra
    out = []
    for k in RUNGS:
        lim = o1 * (1 - k * sig)
        filled = (np.nan_to_num(low, nan=np.inf) < lim[:, None]).any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        r = o2 * (1 - s_out) / lim - 1 - maker - taker - fund
        out.append(np.where(filled, r, np.nan))
    return np.stack(out)  # [rung, bar]


def main():
    G = pd.date_range(START, pd.Timestamp("2026-09-23 20:00", tz="UTC"), freq="4h")
    res = {"version": "v181", "assets": SYMS, "rungs": RUNGS}
    for key, maker, taker, extra in (("normal", 0.0002, 0.0005, 0.0), ("stress", 0.0004, 0.0007, 0.0005)):
        per = {s: rung_returns(G, s, maker, taker, extra) for s in SYMS}
        years = []
        for a in ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = np.asarray((G >= a0) & (G < a0 + pd.Timedelta(days=365)))
            vals = np.concatenate([per[s][:, mk].ravel() for s in SYMS])
            vals = vals[np.isfinite(vals)]
            bar = sum(np.nansum(per[s][:, mk], axis=0) for s in SYMS) * 0.25 / len(RUNGS)
            eq = np.cumprod(1 + bar)
            years.append(dict(anchor=a, fills=int(vals.size), mean_bps=round(1e4 * float(vals.mean()), 1) if vals.size else None,
                              sleeve_net_pct=round(100 * float(eq[-1] - 1), 2),
                              sleeve_dd_pct=round(100 * float(np.max(1 - eq / np.maximum.accumulate(eq))), 2),
                              per_asset_bps={s: (round(1e4 * float(np.nanmean(per[s][:, mk])), 1) if np.isfinite(per[s][:, mk]).any() else None) for s in SYMS}))
        allv = np.concatenate([per[s][:, np.asarray(G >= pd.Timestamp(ANCHORS[0], tz="UTC"))].ravel() for s in SYMS])
        allv = allv[np.isfinite(allv)]
        res[key] = {"years": years, "pooled_mean_bps": round(1e4 * float(allv.mean()), 1), "pooled_fills": int(allv.size)}
        for y in years:
            print(key, y, flush=True)
        print(key, "pooled", res[key]["pooled_mean_bps"], "bps over", res[key]["pooled_fills"], flush=True)
    pos_years = sum(1 for y in res["normal"]["years"] if (y["mean_bps"] or 0) > 0)
    res["criterion"] = {"normal_positive_years": pos_years, "stress_pooled_bps": res["stress"]["pooled_mean_bps"],
                        "pass": bool(pos_years >= 4 and res["stress"]["pooled_mean_bps"] > 0)}
    print("criterion", res["criterion"], flush=True)
    raw = json.dumps(res, indent=1, default=str)
    (HERE / "v181_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
