"""oc_liqcheck: LIGHT read-only data-quality report of the first days of the live liquidation collector.

Reads (one file at a time, never bulk):
  data/raw/liquidations_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet   (event_time rows)
  data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet       (connected intervals)
  data/raw/topbook_live/{venue}/<SYM>/YYYY-MM-DD.parquet                (sample_time column only)
  Binance USD-M public REST 1m klines ONLY for the top-10 burst-minute windows
  ([m-30, m+30] per burst, ~61 klines each; no bulk download).
Writes (only): research/tournament/oc_liqcheck/{liqcheck.py,results.json,REPORT.md,SUMMARY.md,hourly.csv}.
Descriptive only: no rule, no threshold, no selection, no backtest.

Usage: .venv/Scripts/python.exe research/tournament/oc_liqcheck/liqcheck.py
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
BOOK = ROOT / "data/raw/topbook_live"
OUT_DIR = Path(__file__).resolve().parent
OUT = OUT_DIR / "results.json"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
VENUES = ("binance", "bybit")
GAP_S = 300.0  # >5 min = gap (assignment threshold)
BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines"
KCOLS = ["open_time", "open", "high", "low", "close", "volume",
         "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore"]
LIQ_KEY = ["venue", "symbol", "event_time", "raw_side", "price", "qty"]


# ------------------------------------------------------------- pure helpers (unit tested)
def minute_floor(ms: pd.Series | np.ndarray) -> pd.Series:
    ms = pd.to_numeric(pd.Series(ms), errors="coerce")
    return (ms // 60_000 * 60_000).astype("int64")


def coverage_gaps(cov: pd.DataFrame, gap_s: float = GAP_S) -> pd.DataFrame:
    """Consecutive coverage intervals with a gap > gap_s seconds."""
    c = cov.sort_values("start_ms").reset_index(drop=True)
    nxt = c["start_ms"].shift(-1)
    gap = (nxt - c["end_ms"]) / 1000.0
    g = c.assign(next_start_ms=nxt, gap_s=gap)
    return g[g["gap_s"] > gap_s].reset_index(drop=True)


def burst_table(liq: pd.DataFrame) -> pd.DataFrame:
    """Per (minute, venue, symbol): notional, count, long/short split, max single."""
    g = liq.assign(minute=minute_floor(liq["event_time"]))
    out = g.groupby(["minute", "venue", "symbol"], as_index=False).agg(
        notional_usd=("notional_usd", "sum"), n=("notional_usd", "size"),
        long_notional=("notional_usd", lambda s: float(s[g.loc[s.index, "side"] == "long"].sum())),
        short_notional=("notional_usd", lambda s: float(s[g.loc[s.index, "side"] == "short"].sum())),
        max_single=("notional_usd", "max"))
    return out.sort_values("notional_usd", ascending=False).reset_index(drop=True)


def path_stats(path_rebased_pct: dict) -> dict:
    """Min/max and fixed offsets of a rebased 1m path (descriptive only)."""
    if not path_rebased_pct:
        return {}
    vals = list(path_rebased_pct.values())
    return {"min": round(float(min(vals)), 3), "max": round(float(max(vals)), 3)}


def sanity_frame(d: pd.DataFrame) -> dict:
    """Row-level sanity counters for one liquidation file frame."""
    n = len(d)
    bad_side = int((~d["side"].isin(["long", "short"])).sum()) if n else 0
    bad_raw = 0
    if n:
        ok_raw = ((d["venue"] == "binance") & d["raw_side"].isin(["BUY", "SELL"])) | \
                 ((d["venue"] == "bybit") & d["raw_side"].isin(["Buy", "Sell"]))
        bad_raw = int((~ok_raw).sum())
        map_ok = int((((d["venue"] == "binance") & ((d["raw_side"] == "SELL") == (d["side"] == "long"))) |
                   ((d["venue"] == "bybit") & ((d["raw_side"] == "Buy") == (d["side"] == "long")))).sum())
    else:
        map_ok = 0
    bad_price = int((~(d["price"] > 0)).sum()) if n else 0
    bad_qty = int((~(d["qty"] > 0)).sum()) if n else 0
    inconsistent = 0
    if n:
        expect = (d["price"].astype("float64") * d["qty"].astype("float64")).to_numpy()
        got = d["notional_usd"].astype("float64").to_numpy()
        denom = np.maximum(np.abs(expect), 1e-9)
        inconsistent = int((np.abs(expect - got) / denom > 1e-4).sum())
    mono_ok = bool((d["event_time"].to_numpy()[:-1] <= d["event_time"].to_numpy()[1:]).all()) if n > 1 else True
    dup = int(n - len(d.drop_duplicates(subset=LIQ_KEY))) if n else 0
    return {"n": n, "bad_side": bad_side, "bad_raw_side": bad_raw,
            "side_map_ok": int(map_ok), "bad_price": bad_price, "bad_qty": bad_qty,
            "notional_inconsistent": inconsistent, "event_time_monotonic": mono_ok,
            "dups_in_file": dup}


# ------------------------------------------------------------- REST (burst windows only)
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


# ------------------------------------------------------------- main
def main() -> dict:
    sess = requests.Session()
    files_read: list[str] = []
    liq_parts: list[pd.DataFrame] = []
    per_file: list[dict] = []
    hourly_parts: list[pd.DataFrame] = []

    # ---- liquidations: one coin file at a time ----
    for venue in VENUES:
        for sym in SYMS:
            for p in sorted((LIQ / venue / sym).glob("*.parquet")):
                d = pd.read_parquet(p, columns=["venue", "symbol", "side", "raw_side",
                                                "price", "qty", "notional_usd",
                                                "event_time", "recv_time"])
                san = sanity_frame(d)
                san.update({"file": str(p.relative_to(ROOT)), "venue": venue, "symbol": sym,
                            "day": p.stem,
                            "event_min_utc": pd.to_datetime(int(d["event_time"].min()), unit="ms", utc=True).isoformat() if len(d) else None,
                            "event_max_utc": pd.to_datetime(int(d["event_time"].max()), unit="ms", utc=True).isoformat() if len(d) else None,
                            "lag_median_ms": round(float((d["recv_time"] - d["event_time"]).median()), 1) if len(d) else 0.0,
                            "lag_neg_share": round(float((d["recv_time"] < d["event_time"]).mean()), 4) if len(d) else 0.0})
                per_file.append(san)
                files_read.append(str(p.relative_to(ROOT)))
                d["price"] = d["price"].astype("float32")
                d["qty"] = d["qty"].astype("float32")
                d["notional_usd"] = d["notional_usd"].astype("float32")
                liq_parts.append(d)
                h = pd.to_datetime(d["event_time"], unit="ms", utc=True).dt.floor("h")
                hourly_parts.append(pd.DataFrame({"hour": h, "venue": venue, "symbol": sym,
                                                  "notional_usd": d["notional_usd"].astype("float64").to_numpy()}))
                del d
    liq = pd.concat(liq_parts, ignore_index=True) if liq_parts else pd.DataFrame()
    del liq_parts
    liq = liq.sort_values("event_time").reset_index(drop=True) if len(liq) else liq

    # global dup check across files (midnight-boundary safe)
    global_dups = int(len(liq) - len(liq.drop_duplicates(subset=LIQ_KEY))) if len(liq) else 0

    # ---- rows per feed per hour: liquidations ----
    liq_hourly = (pd.concat(hourly_parts, ignore_index=True) if hourly_parts else pd.DataFrame())
    del hourly_parts
    if len(liq_hourly):
        liq_hourly_agg = liq_hourly.groupby(["hour", "venue", "symbol"], as_index=False).agg(
            rows=("notional_usd", "size"), notional_usd=("notional_usd", "sum"))
        liq_hourly_agg["hour_utc"] = liq_hourly_agg["hour"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        liq_hourly_agg = pd.DataFrame()
    # per-coin per-hour across venues (assignment's "notional per hour per coin")
    if len(liq_hourly):
        coin_hourly = liq_hourly.groupby(
            [liq_hourly["hour"], liq_hourly["symbol"]], as_index=False).agg(
            rows=("notional_usd", "size"), notional_usd=("notional_usd", "sum"))
        coin_hourly["hour_utc"] = coin_hourly["hour"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        coin_hourly = coin_hourly.sort_values("notional_usd", ascending=False).reset_index(drop=True)
    else:
        coin_hourly = pd.DataFrame()

    # ---- per day/venue/coin ----
    if len(liq):
        liq["day"] = pd.to_datetime(liq["event_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        by_day = liq.groupby(["day", "venue", "symbol"], as_index=False).agg(
            rows=("notional_usd", "size"), notional_usd=("notional_usd", "sum"),
            max_single=("notional_usd", "max"),
            long_share=("side", lambda s: float((s == "long").mean())))
    else:
        by_day = pd.DataFrame()

    # ---- coverage: one file at a time ----
    cov_summary, gaps = [], []
    for venue in VENUES:
        for p in sorted((LIQ / "_coverage" / venue).glob("*.parquet")):
            c = pd.read_parquet(p)
            files_read.append(str(p.relative_to(ROOT)))
            s, e = int(c["start_ms"].min()), int(c["end_ms"].max())
            cov_summary.append({"venue": venue, "file": p.name, "intervals": len(c),
                                "covered_h": round(float((c["end_ms"] - c["start_ms"]).sum()) / 3.6e6, 2),
                                "span_start_utc": datetime.fromtimestamp(s / 1000, tz=timezone.utc).isoformat(),
                                "span_end_utc": datetime.fromtimestamp(e / 1000, tz=timezone.utc).isoformat()})
            for _, r in coverage_gaps(c).iterrows():
                gaps.append({"venue": venue, "file": p.name,
                             "gap_start_utc": datetime.fromtimestamp(float(r["end_ms"]) / 1000, tz=timezone.utc).isoformat(),
                             "gap_end_utc": datetime.fromtimestamp(float(r["next_start_ms"]) / 1000, tz=timezone.utc).isoformat() if pd.notna(r["next_start_ms"]) else None,
                             "gap_s": round(float(r["gap_s"]), 1),
                             "gap_h": round(float(r["gap_s"]) / 3600, 2)})
            del c

    # ---- topbook: sample_time column only, one file at a time ----
    book_summary, book_gaps = [], []
    for venue in VENUES:
        for sym in SYMS:
            for p in sorted((BOOK / venue / sym).glob("*.parquet")):
                b = pd.read_parquet(p, columns=["sample_time"])
                files_read.append(str(p.relative_to(ROOT)))
                b = b.sort_values("sample_time").reset_index(drop=True)
                if str(b["sample_time"].dtype).startswith("datetime"):
                    ms = (b["sample_time"].astype("int64") // 10**6).to_numpy()
                else:
                    ms = pd.to_numeric(b["sample_time"], errors="coerce").to_numpy(dtype="float64")
                diff_s = np.diff(ms) / 1000.0 if len(ms) > 1 else np.array([])
                mx = float(diff_s.max()) if len(diff_s) else 0.0
                n_big = int((diff_s > GAP_S).sum()) if len(diff_s) else 0
                # rows per hour for this file
                hh = pd.to_datetime(ms, unit="ms", utc=True).floor("h")
                per_h = pd.Series(hh).value_counts()
                book_summary.append({"venue": venue, "symbol": sym, "file": p.name, "rows": int(len(b)),
                                     "max_sample_gap_s": round(mx, 1), "gaps_over_300s": n_big,
                                     "first_sample_utc": pd.to_datetime(float(ms.min()), unit="ms", utc=True).isoformat() if len(ms) else None,
                                     "last_sample_utc": pd.to_datetime(float(ms.max()), unit="ms", utc=True).isoformat() if len(ms) else None,
                                     "median_rows_per_hour": round(float(per_h.median()), 1) if len(per_h) else 0.0})
                if n_big:
                    idx = np.where(diff_s > GAP_S)[0]
                    for i in idx[:10]:
                        book_gaps.append({"venue": venue, "symbol": sym, "file": p.name,
                                          "gap_start_utc": pd.to_datetime(float(ms[i]), unit="ms", utc=True).isoformat(),
                                          "gap_end_utc": pd.to_datetime(float(ms[i + 1]), unit="ms", utc=True).isoformat(),
                                          "gap_s": round(float(diff_s[i]), 1)})
                del b

    # ---- burst minutes (top 10) ----
    bursts = burst_table(liq) if len(liq) else pd.DataFrame()
    top10 = bursts.head(10).copy() if len(bursts) else bursts
    if len(top10):
        top10["minute_utc"] = pd.to_datetime(top10["minute"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- 1m price path for the top-10 burst minutes only (Binance REST, descriptive) ----
    burst_detail = []
    for _, b in top10.iterrows() if len(top10) else []:
        sym, m_ms = str(b["symbol"]), int(b["minute"])
        m = pd.Timestamp(m_ms, unit="ms", tz="UTC")
        entry: dict = {"minute_utc": m.isoformat(), "venue": str(b["venue"]), "symbol": sym,
                       "burst_notional_usd": round(float(b["notional_usd"]), 1),
                       "burst_n": int(b["n"]),
                       "long_notional": round(float(b["long_notional"]), 1),
                       "short_notional": round(float(b["short_notional"]), 1),
                       "max_single": round(float(b["max_single"]), 1)}
        try:
            m0 = int((m - pd.Timedelta(minutes=30)).value // 10**6)
            m1 = int((m + pd.Timedelta(minutes=31)).value // 10**6)
            k1 = fetch_klines(sym, "1m", m0, m1, sess)  # ~61 klines, this minute only
            row = k1[k1["open_time"] == m.floor("min")] if len(k1) else pd.DataFrame()
            if len(row):
                opx = float(row["open"].iloc[0])
                path = k1.set_index("open_time")["close"].astype("float64")
                reb = {t.isoformat(): round(float(c / opx - 1) * 100, 3) for t, c in path.items()}
                entry.update({"burst_min_open": round(opx, 3),
                              "burst_min_high": round(float(row["high"].iloc[0]), 3),
                              "burst_min_low": round(float(row["low"].iloc[0]), 3),
                              "burst_min_close": round(float(row["close"].iloc[0]), 3),
                              "path_rebased_pct": reb, "path_min_max_pct": path_stats(reb)})
                # fixed offsets (descriptive, no rule): nearest available bar at/after offset
                idx = k1.set_index("open_time").index
                for off in (1, 5, 15, 30):
                    tgt = (m + pd.Timedelta(minutes=off)).floor("min")
                    hit = idx[idx >= tgt]
                    entry[f"ret_plus{off}m_pct"] = round(float(k1.set_index("open_time").loc[hit[0], "close"] / opx - 1) * 100, 3) if len(hit) else None
            else:
                entry["note"] = "burst minute missing from 1m klines"
            del k1
        except Exception as exc:  # REST failure must not kill the report
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        burst_detail.append(entry)

    # ---- readiness estimate: 3 months incl. several 2.5-sigma flushes ----
    # Anchor: collector started 2026-10-04 (first covered day). +3 months -> 2027-01-04.
    # Flush proxy (descriptive): full-sample coin-hour notional distribution; count
    # hours above 2.5x the hourly std proxy is unstable at N~=2.5 days, so report the
    # observed large-hour count and keep the calendar gate.
    n_coin_hours = int(len(coin_hourly)) if len(coin_hourly) else 0
    big_hours = []
    if len(coin_hourly):
        thr = float(coin_hourly["notional_usd"].quantile(0.95))
        big_hours = coin_hourly.head(5)[["hour_utc", "symbol", "rows", "notional_usd"]].to_dict("records")
    else:
        thr = 0.0
    readiness = {
        "collector_start": "2026-10-04",
        "required_history": "at least 3 months incl. several 2.5-sigma flushes",
        "earliest_ready_date": "2027-01-04",
        "rationale": (f"3 calendar months from the 2026-10-04 start = 2027-01-04; "
                      f"with N~2.5 covered days the flush proxy is unstable "
                      f"(n_coin_hours={n_coin_hours}, hourly p95 notional=${thr:,.0f}); "
                      "re-count 2.5-sigma flush hours on covered time only once 3 months exist."),
        "observed_top_coin_hours": big_hours,
    }

    res = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "venue_note": ("binance forceOrder: at most ONE event/symbol/s (snapshot of that second); "
                       "bybit allLiquidation: every liquidation batched per 500ms. "
                       "Counts/notionals are NOT directly comparable across venues."),
        "scope_note": "LIGHT read-only check of data/raw/{liquidations_live,topbook_live}; no collector file modified.",
        "descriptive_only": "no rule, no threshold, no selection, no backtest; burst paths are description, not signal.",
        "files_read": sorted(set(files_read)),
        "n_liq_rows": int(len(liq)),
        "global_dup_keys": global_dups,
        "by_day_venue_coin": by_day.to_dict("records") if len(by_day) else [],
        "per_file_sanity": per_file,
        "liq_rows_per_hour": liq_hourly_agg.to_dict("records") if len(liq_hourly_agg) else [],
        "coin_notional_per_hour_top20": coin_hourly.head(20).to_dict("records") if len(coin_hourly) else [],
        "coverage_summary": cov_summary,
        "coverage_gaps_over_300s": gaps,
        "topbook_summary": book_summary,
        "topbook_gaps_over_300s": book_gaps,
        "top10_burst_minutes": top10.to_dict("records") if len(top10) else [],
        "burst_detail": burst_detail,
        "readiness": readiness,
    }
    OUT.write_text(json.dumps(res, indent=1, default=str))
    # hourly CSV for the VF_COMMON artifacts convention (same folder only)
    if len(liq_hourly_agg):
        csv = liq_hourly_agg[["hour_utc", "venue", "symbol", "rows", "notional_usd"]].copy()
        csv.to_csv(OUT_DIR / "hourly.csv", index=False)
    print(f"oc_liqcheck: n_liq={len(liq)} files={len(set(files_read))} "
          f"cov_gaps={len(gaps)} book_gaps={len(book_gaps)} bursts={len(burst_detail)} -> {OUT}")
    return res


if __name__ == "__main__":
    main()
