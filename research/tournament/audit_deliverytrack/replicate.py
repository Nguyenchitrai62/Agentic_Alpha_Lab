"""Blind independent replication for audit_deliverytrack.

Reads ONLY research/tournament/oc_cashcarry/results.json and klines, then
recomputes per delivery (08:00 UTC on code date):
  - TWAP 07:30-08:00 UTC (mean of 30 spot 1m closes, open_time 07:30..07:59)
  - 08:00 open (open of 08:00 1m bar)
  - 08:00-08:05 VWAP (quote-volume-weighted over 5 bars 08:00..08:04)
  - 08:15 price (close of 08:15 1m bar)
  - 6-slice schedule (mean of closes at 07:34/07:39/07:44/07:49/07:54/07:59)
Tracking error in bp vs TWAP, plus estimated drag on trade net return.

Venue note: no Binance SPOT 1m exists locally (local 1m archives are
futures/um: data/raw/btc_intraday_20260924, data/raw/majors_intraday_20260924;
local spot is 4h/1h only). Primary replication therefore fetches Binance SPOT
1m for the delivery windows via public REST and caches under tmp/ (no
credentials, market data only). The same metrics are also computed from the
local futures/um 1m as a venue-comparison column.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
CASH = Path("research/tournament/oc_cashcarry/results.json")

SPOT_REST = "https://api.binance.com/api/v3/klines"

# Local futures/um 1m archives (venue comparison only)
BTC_1M = Path("data/raw/btc_intraday_20260924")
MAJ_1M = Path("data/raw/majors_intraday_20260924")


def ms(dt):
    return int(dt.timestamp() * 1000)


def fetch_spot_1m(symbol, day_str):
    """Fetch spot 1m bars 07:00-08:20 UTC for delivery day. Cached to tmp/."""
    cache = TMP / f"spot_1m_{symbol}_{day_str}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    day = datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    import datetime as dtm

    start = day.replace(hour=7, minute=0, second=0)
    end = day.replace(hour=8, minute=20, second=0)
    url = (
        f"{SPOT_REST}?symbol={symbol}&interval=1m"
        f"&startTime={ms(start)}&endTime={ms(end)}&limit=1000"
    )
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "audit/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = json.loads(r.read().decode())
            break
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"spot fetch failed {symbol} {day_str}: {last}")
    cache.write_text(json.dumps({"url": url, "klines": raw}))
    time.sleep(0.3)  # be nice to public endpoint
    return {"url": url, "klines": raw}


def spot_df(symbol, day_str):
    payload = fetch_spot_1m(symbol, day_str)
    rows = []
    for k in payload["klines"]:
        rows.append(
            {
                "open_time": pd.to_datetime(k[0], unit="ms", utc=True),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "quote_volume": float(k[7]),
            }
        )
    df = pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)
    return df


_fut_cache = {}


def fut_df(symbol, year):
    key = (symbol, year)
    if key in _fut_cache:
        return _fut_cache[key]
    if symbol == "BTCUSDT":
        f = BTC_1M / f"klines_1m_{year}.parquet"
    else:
        f = MAJ_1M / f"{symbol}_1m_{year}.parquet"
    df = pd.read_parquet(f)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    _fut_cache[key] = df
    return df


def metrics_from_df(df):
    """df must contain open_time(utc), open, close, volume, quote_volume."""
    df = df.copy()
    df["ts"] = df["open_time"].dt.strftime("%H:%M")
    win = df[(df["open_time"].dt.strftime("%H:%M") >= "07:30") & (df["ts"] < "08:00")]
    assert len(win) == 30, f"expected 30 bars 07:30-07:59, got {len(win)}"
    twap = float(win["close"].mean())
    o0800 = float(df.loc[df["ts"] == "08:00", "open"].iloc[0])
    v5 = df[df["ts"].isin(["08:00", "08:01", "08:02", "08:03", "08:04"])]
    assert len(v5) == 5
    vwap = float(v5["quote_volume"].sum() / v5["volume"].sum())
    p0815 = float(df.loc[df["ts"] == "08:15", "close"].iloc[0])
    sched_times = ["07:34", "07:39", "07:44", "07:49", "07:54", "07:59"]
    sched = df[df["ts"].isin(sched_times)]
    assert len(sched) == 6
    sched_px = float(sched["close"].mean())
    # 25s-delay proxy per slice: close + (next_open - close)*25/60
    df2 = df.set_index("ts")
    delays = []
    for t in sched_times:
        c = float(df2.loc[t, "close"])
        nxt = df2.loc[t, "open"]  # placeholder replaced below
        delays.append(c)
    # next-bar opens: map 07:34->07:35 etc.
    nxt_map = {"07:34": "07:35", "07:39": "07:40", "07:44": "07:45",
               "07:49": "07:50", "07:54": "07:55", "07:59": "08:00"}
    dpx = []
    for t in sched_times:
        c = float(df2.loc[t, "close"])
        o_next = float(df2.loc[nxt_map[t], "open"])
        dpx.append(c + (o_next - c) * 25.0 / 60.0)
    sched_delayed = float(sum(dpx) / len(dpx))
    return {
        "twap": twap,
        "open_0800": o0800,
        "vwap_0800_0805": vwap,
        "px_0815": p0815,
        "sched_6slice": sched_px,
        "sched_6slice_delay25s": sched_delayed,
        "n_win": 30,
    }


def bp(a, b):
    return (a - b) / b * 1e4


def main():
    res = json.loads(CASH.read_text())
    trades = res["trades"]
    print(f"trades: {len(trades)}")
    out_rows = []
    for t in trades:
        coin, delivery = t["coin"], t["delivery"]
        symbol = f"{coin}USDT"
        sdf = spot_df(symbol, delivery)
        m = metrics_from_df(sdf)
        # futures venue comparison
        year = delivery[:4]
        fdf = fut_df(symbol, year)
        day = delivery
        fwin = fdf[
            (fdf["open_time"] >= pd.Timestamp(f"{day} 07:00", tz="UTC"))
            & (fdf["open_time"] <= pd.Timestamp(f"{day} 08:20", tz="UTC"))
        ].copy()
        fm = metrics_from_df(fwin.rename(columns={}))
        # tracking errors vs spot TWAP
        row = {
            "coin": coin,
            "delivery": delivery,
            "spot_twap_0730_0800": m["twap"],
            "spot_open_0800": m["open_0800"],
            "spot_vwap_0800_0805": m["vwap_0800_0805"],
            "spot_px_0815": m["px_0815"],
            "spot_sched_6slice": m["sched_6slice"],
            "spot_sched_6slice_delay25s": m["sched_6slice_delay25s"],
            "te_bp_open_0800": bp(m["open_0800"], m["twap"]),
            "te_bp_vwap_0805": bp(m["vwap_0800_0805"], m["twap"]),
            "te_bp_0815": bp(m["px_0815"], m["twap"]),
            "te_bp_sched": bp(m["sched_6slice"], m["twap"]),
            "te_bp_sched_delay25s": bp(m["sched_6slice_delay25s"], m["twap"]),
            "delay25s_minus_sched_bp": bp(m["sched_6slice_delay25s"], m["sched_6slice"]),
            "fut_twap_0730_0800": fm["twap"],
            "fut_sched_6slice": fm["sched_6slice"],
            "venue_gap_bp_fut_minus_spot_twap": bp(fm["twap"], m["twap"]),
            "venue_gap_bp_fut_minus_spot_sched": bp(fm["sched_6slice"], m["sched_6slice"]),
            # trade context from oc_cashcarry
            "S_del_4h": t["S_del"],
            "ret_alloc": t["ret_alloc"],
        }
        # est. alloc drag of schedule vs TWAP assuming 1x spot notional = alloc-scaled:
        # drag_alloc_bp ~= te_bp_sched * (TWAP / S_entry_proxy); S_entry unknown here
        # per trade entry S_entry available in full trade dict
        row["S_entry"] = t["S_entry"]
        row["est_drag_alloc_bp_sched"] = row["te_bp_sched"] * (m["twap"] / t["S_entry"])
        out_rows.append(row)
        print(
            f"{coin} {delivery} twap={m['twap']:.2f} sched={m['sched_6slice']:.2f} "
            f"te_sched={row['te_bp_sched']:+.2f}bp fut_gap={row['venue_gap_bp_fut_minus_spot_twap']:+.2f}bp"
        )

    import numpy as np

    tes = np.array([r["te_bp_sched"] for r in out_rows])
    summ = {
        "n": len(out_rows),
        "te_sched_bp_mean": float(tes.mean()),
        "te_sched_bp_worst_abs": float(np.abs(tes).max()),
        "te_sched_bp_max": float(tes.max()),
        "te_sched_bp_min": float(tes.min()),
        "n_abs_gt_3bp": int((np.abs(tes) > 3).sum()),
        "n_abs_gt_5bp": int((np.abs(tes) > 5).sum()),
    }
    out = {
        "meta": {
            "source_trades": str(CASH),
            "n_trades": len(trades),
            "delivery_rule": "08:00 UTC on code date",
            "definitions": {
                "twap_0730_0800": "mean of 30 Binance SPOT 1m closes, open_time 07:30..07:59 UTC",
                "open_0800": "open of 08:00 spot 1m bar",
                "vwap_0800_0805": "sum(quote_volume)/sum(volume) over 5 spot 1m bars 08:00..08:04",
                "px_0815": "close of 08:15 spot 1m bar",
                "sched_6slice": "mean of spot 1m closes at 07:34/07:39/07:44/07:49/07:54/07:59",
                "delay25s": "per-slice close+(next_open-close)*25/60, then mean (linear intrabar proxy)",
                "te_bp": "(px-TWAP)/TWAP*1e4",
                "est_drag_alloc_bp": "te_bp_sched*(TWAP/S_entry), 1x-spot-notional proxy",
            },
            "venue": "Binance SPOT REST api.binance.com (public), cached tmp/spot_1m_<SYM>_<DAY>.json; "
            "fut_* columns from local futures/um 1m (btc_intraday/majors_intraday) for comparison",
            "tolerance": "1 bp mean, 3 bp worst (vs oc_deliverytrack)",
        },
        "summary": summ,
        "rows": out_rows,
    }
    (HERE / "replication.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(summ, indent=1))
    print("wrote", HERE / "replication.json")


if __name__ == "__main__":
    main()
