"""oc_liq: first look at the live liquidation stream (descriptive note only).

Reads (small, all fit in RAM many times over; klines fetched per coin, one at a
time, float32, windows only):
  data/raw/liquidations_live/{binance,bybit}/<SYM>/<date>.parquet
  data/raw/liquidations_live/_coverage/{venue}/<date>.parquet
  Binance USD-M public REST klines ONLY for burst windows (1m [m-30,m+30]) and
  the 4h history needed for sigma_4h (~365 bars) of involved coins.
Writes: results.json (+ REPORT.md rendered separately).
Usage: .venv/Scripts/python.exe research/tournament/oc_liq/liq_note.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
LIQ = ROOT / "data/raw/liquidations_live"
OUT = Path(__file__).resolve().parent / "results.json"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
VENUES = ("binance", "bybit")
RUNGS = (2.5, 3.0, 3.5, 4.0)
BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines"
KCOLS = ["open_time", "open", "high", "low", "close", "volume",
         "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore"]


# ------------------------------------------------------------- pure helpers
def minute_floor(ms: pd.Series | np.ndarray) -> pd.Series:
    ms = pd.to_numeric(pd.Series(ms), errors="coerce")
    return (ms // 60_000 * 60_000).astype("int64")


def coverage_gaps(cov: pd.DataFrame, gap_s: float = 60.0) -> pd.DataFrame:
    """Consecutive coverage intervals with a gap > gap_s seconds."""
    c = cov.sort_values("start_ms").reset_index(drop=True)
    nxt = c["start_ms"].shift(-1)
    gap = (nxt - c["end_ms"]) / 1000.0
    g = c.assign(next_start_ms=nxt, gap_s=gap)
    return g[g["gap_s"] > gap_s].reset_index(drop=True)


def sigma_and_rungs(opens_4h: pd.Series, t_bar: pd.Timestamp) -> tuple[float, float, dict]:
    """sigma_4h = std of 360 4h open-to-open returns ending at T-4h (dip-sleeve rule).

    opens_4h: float series indexed by bar open time (UTC). Returns
    (open_T, sigma, {k: level}). Raises KeyError if T missing, ValueError if
    fewer than 120 history returns (same floor as dip_sleeve_forward.py).
    """
    t_bar = pd.Timestamp(t_bar)
    t_bar = t_bar.tz_convert("UTC") if t_bar.tzinfo is not None else t_bar.tz_localize("UTC")
    t_prev = t_bar - pd.Timedelta(hours=4)
    o = opens_4h.sort_index()
    open_t = float(o.loc[t_bar])
    hist = o.pct_change()[o.index <= t_prev].tail(360)
    hist = hist.dropna()
    if hist.count() < 120:
        raise ValueError(f"only {hist.count()} history returns before {t_bar}")
    sig = float(hist.std())
    return open_t, sig, {k: open_t * (1 - k * sig) for k in RUNGS}


def burst_table(liq: pd.DataFrame) -> pd.DataFrame:
    """Per (minute, venue, symbol): notional, count, long/short split."""
    g = liq.assign(minute=minute_floor(liq["event_time"]))
    out = g.groupby(["minute", "venue", "symbol"], as_index=False).agg(
        notional_usd=("notional_usd", "sum"), n=("notional_usd", "size"),
        long_notional=("notional_usd", lambda s: float(s[g.loc[s.index, "side"] == "long"].sum())),
        short_notional=("notional_usd", lambda s: float(s[g.loc[s.index, "side"] == "short"].sum())),
        max_single=("notional_usd", "max"))
    return out.sort_values("notional_usd", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------- REST (windows only)
def fetch_klines(sym: str, interval: str, start_ms: int, end_ms: int,
                 session: requests.Session) -> pd.DataFrame:
    rows: list[list] = []
    cursor = int(start_ms)
    while cursor < int(end_ms):
        r = session.get(BINANCE_KLINES, params={"symbol": sym, "interval": interval,
                                                "startTime": cursor, "endTime": int(end_ms),
                                                "limit": 1500}, timeout=60)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = int(batch[-1][0]) + 1
        if len(batch) < 1500:
            break
    if not rows:
        return pd.DataFrame()
    k = pd.DataFrame(rows, columns=KCOLS)
    k["open_time"] = pd.to_datetime(k["open_time"].astype("int64"), unit="ms", utc=True)
    for c in ("open", "high", "low", "close"):
        k[c] = k[c].astype("float32")
    return k.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def bar_open_4h(minute_utc: pd.Timestamp) -> pd.Timestamp:
    h = int(minute_utc.hour) // 4 * 4
    return minute_utc.tz_convert("UTC").floor("D") + pd.Timedelta(hours=h)


# ------------------------------------------------------------- main
def main() -> dict:
    sess = requests.Session()
    # ---- liquidations: one coin file at a time (float32 notional path) ----
    parts: list[pd.DataFrame] = []
    files_read: list[str] = []
    for venue in VENUES:
        for sym in SYMS:  # one coin at a time
            for p in sorted((LIQ / venue / sym).glob("*.parquet")):
                d = pd.read_parquet(p, columns=["venue", "symbol", "side", "raw_side",
                                                "price", "qty", "notional_usd",
                                                "event_time", "recv_time"])
                d["price"] = d["price"].astype("float32")
                d["qty"] = d["qty"].astype("float32")
                d["notional_usd"] = d["notional_usd"].astype("float32")
                parts.append(d)
                files_read.append(str(p.relative_to(ROOT)))
                del d
    liq = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    del parts
    liq["day"] = pd.to_datetime(liq["event_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    liq = liq.sort_values("event_time").reset_index(drop=True)

    # ---- per day/venue/coin ----
    by_day = liq.groupby(["day", "venue", "symbol"], as_index=False).agg(
        rows=("notional_usd", "size"), notional_usd=("notional_usd", "sum"),
        max_single=("notional_usd", "max"),
        long_share=("side", lambda s: float((s == "long").mean())))

    # ---- coverage ----
    cov_rows, gaps = [], []
    for venue in VENUES:
        for p in sorted((LIQ / "_coverage" / venue).glob("*.parquet")):
            c = pd.read_parquet(p)
            c["file"] = p.name
            cov_rows.append(c)
            g = coverage_gaps(c)
            for _, r in g.iterrows():
                gaps.append({"venue": venue, "file": p.name,
                             "gap_start_utc": datetime.fromtimestamp(float(r["end_ms"]) / 1000,
                                                                     tz=timezone.utc).isoformat(),
                             "gap_end_utc": datetime.fromtimestamp(float(r["next_start_ms"]) / 1000,
                                                                    tz=timezone.utc).isoformat() if pd.notna(r["next_start_ms"]) else None,
                             "gap_s": round(float(r["gap_s"]), 1)})
            del c
    cov = pd.concat(cov_rows, ignore_index=True) if cov_rows else pd.DataFrame()
    del cov_rows
    cov_summary = []
    if len(cov):
        for (venue, f), c in cov.groupby(["venue", "file"]):
            s, e = int(c["start_ms"].min()), int(c["end_ms"].max())
            cov_summary.append({"venue": venue, "file": f, "intervals": len(c),
                                "covered_h": round(float((c["end_ms"] - c["start_ms"]).sum()) / 3.6e6, 2),
                                "span_start_utc": datetime.fromtimestamp(s / 1000, tz=timezone.utc).isoformat(),
                                "span_end_utc": datetime.fromtimestamp(e / 1000, tz=timezone.utc).isoformat()})

    # ---- size distribution ----
    q = liq["notional_usd"].quantile([0.5, 0.9, 0.99, 1.0]).to_dict() if len(liq) else {}
    size = {"n": int(len(liq)),
            "total_notional_usd": round(float(liq["notional_usd"].sum()), 1) if len(liq) else 0.0,
            "quantiles": {str(k): round(float(v), 1) for k, v in q.items()},
            "by_venue": {v: {str(k): round(float(x), 1) for k, x in
                             liq.loc[liq["venue"] == v, "notional_usd"].quantile([0.5, 0.9, 0.99, 1.0]).to_dict().items()}
                         for v in VENUES},
            "by_side": {s: {"n": int((liq["side"] == s).sum()),
                            "notional": round(float(liq.loc[liq["side"] == s, "notional_usd"].sum()), 1)}
                        for s in ("long", "short")},
            "hist_edges": [0, 100, 1000, 10000, 100000, 1000000],
            "hist_counts": (np.histogram(liq["notional_usd"].to_numpy(dtype="float64"),
                                         bins=[0, 100, 1e3, 1e4, 1e5, 1e6, np.inf])[0].tolist()
                            if len(liq) else [])}

    # ---- burst minutes ----
    bursts = burst_table(liq)
    top5 = bursts.head(5).copy()
    top5["minute_utc"] = pd.to_datetime(top5["minute"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- price path + rung touch for the top-5 minutes only (one coin at a time) ----
    burst_detail = []
    kline_cache_4h: dict[str, pd.DataFrame] = {}
    for _, b in top5.iterrows():
        sym, m_ms = str(b["symbol"]), int(b["minute"])
        m = pd.Timestamp(m_ms, unit="ms", tz="UTC")
        t_bar = bar_open_4h(m)
        entry: dict = {"minute_utc": pd.Timestamp(m_ms, unit="ms", tz="UTC").isoformat(),
                       "venue": str(b["venue"]), "symbol": sym,
                       "burst_notional_usd": round(float(b["notional_usd"]), 1),
                       "burst_n": int(b["n"]),
                       "long_notional": round(float(b["long_notional"]), 1),
                       "short_notional": round(float(b["short_notional"]), 1),
                       "max_single": round(float(b["max_single"]), 1),
                       "bar_open_4h_utc": t_bar.isoformat()}
        try:
            if sym not in kline_cache_4h:  # one coin at a time; ~365 4h bars
                t0 = int((t_bar - pd.Timedelta(hours=4 * 400)).value // 10**6)
                t1 = int((t_bar + pd.Timedelta(hours=4)).value // 10**6)
                kline_cache_4h[sym] = fetch_klines(sym, "4h", t0, t1, sess)
            k4 = kline_cache_4h[sym]
            o = k4.set_index("open_time")["open"].astype("float64")
            open_t, sig, levels = sigma_and_rungs(o, t_bar)
            m0 = int((m - pd.Timedelta(minutes=30)).value // 10**6)
            m1 = int((m + pd.Timedelta(minutes=31)).value // 10**6)
            k1 = fetch_klines(sym, "1m", m0, m1, sess)  # ~61 klines, this minute only
            row = k1[k1["open_time"] == m.floor("min")]
            entry.update({"open_T": round(float(open_t), 3), "sigma_4h": round(float(sig), 6),
                          "rung_levels": {str(k): round(float(v), 3) for k, v in levels.items()}})
            if len(row):
                lo, opx = float(row["low"].iloc[0]), float(row["open"].iloc[0])
                dist_sig = (float(open_t) - lo) / (float(open_t) * float(sig)) if sig > 0 else None
                entry.update({"burst_min_open": round(opx, 3), "burst_min_low": round(lo, 3),
                              "burst_min_high": round(float(row["high"].iloc[0]), 3),
                              "burst_min_close": round(float(row["close"].iloc[0]), 3),
                              "dip_sigma_distance": round(float(dist_sig), 3) if dist_sig is not None else None,
                              "rungs_touched": sorted([k for k, v in levels.items() if lo < v])})
                path = k1.set_index("open_time")["close"].astype("float64")
                entry["path_rebased_pct"] = {t.isoformat(): round(float(c / opx - 1) * 100, 3)
                                             for t, c in path.items()}
            else:
                entry["note"] = "burst minute missing from 1m klines"
            del k1
        except Exception as exc:  # REST or history failure must not kill the note
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        burst_detail.append(entry)
    for sym in list(kline_cache_4h):
        del kline_cache_4h[sym]

    res = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "venue_note": ("binance forceOrder: at most ONE event/symbol/s (snapshot of that second); "
                       "bybit allLiquidation: every liquidation batched per 500ms. "
                       "Counts/notionals are NOT directly comparable across venues."),
        "files_read": files_read,
        "n_rows": int(len(liq)),
        "by_day_venue_coin": by_day.to_dict("records"),
        "coverage_summary": cov_summary,
        "coverage_gaps_over_60s": gaps,
        "size_distribution": size,
        "top5_burst_minutes": top5.to_dict("records"),
        "burst_detail": burst_detail,
        " verdict_hint": "descriptive only; N≈1.5 days is too little history for any test",
    }
    res = {k.strip(): v for k, v in res.items()}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(f"oc_liq: n={len(liq)} files={len(files_read)} gaps={len(gaps)} "
          f"top1={top5.iloc[0]['minute_utc'] if len(top5) else None} -> {OUT}")
    return res


if __name__ == "__main__":
    main()
