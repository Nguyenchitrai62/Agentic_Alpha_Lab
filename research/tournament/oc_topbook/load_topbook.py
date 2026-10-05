"""oc_topbook: DATA-PREP loader for the live top-of-book stream (no outcome research).

Reads (one file at a time; no network; no 1m klines; no fills/harness):
  data/raw/topbook_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet
  data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet (uptime proxy;
    same collector process; there is no _coverage dir under topbook_live/)
Writes (this folder only):
  results.json, aggregates_1m.parquet, aggregates_4h.parquet
Usage: .venv/Scripts/python.exe research/tournament/oc_topbook/load_topbook.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BOOK = ROOT / "data/raw/topbook_live"
COV = ROOT / "data/raw/liquidations_live/_coverage"
OUT_DIR = Path(__file__).resolve().parent
RES = OUT_DIR / "results.json"
AGG1M = OUT_DIR / "aggregates_1m.parquet"
AGG4H = OUT_DIR / "aggregates_4h.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
VENUES = ("binance", "bybit")
BOOK_COLUMNS = ["venue", "symbol", "sample_time", "quote_time", "bid",
                "bid_qty", "ask", "ask_qty", "recv_time"]
BOOK_KEY = ["venue", "symbol", "sample_time"]
WIDE_BPS = 5.0
MIN_MS = 60_000
H4_MS = 4 * 3_600_000


# ------------------------------------------------------------- pure helpers
def spread_bps(bid: pd.Series | np.ndarray, ask: pd.Series | np.ndarray) -> pd.Series:
    b = pd.to_numeric(pd.Series(bid), errors="coerce").to_numpy(dtype="float64")
    a = pd.to_numeric(pd.Series(ask), errors="coerce").to_numpy(dtype="float64")
    mid = (a + b) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / mid * 1e4
    return pd.Series(out)


def sizes_usd(bid: pd.Series, bid_qty: pd.Series,
              ask: pd.Series, ask_qty: pd.Series) -> tuple[pd.Series, pd.Series]:
    b = pd.to_numeric(pd.Series(bid), errors="coerce").to_numpy(dtype="float64")
    bq = pd.to_numeric(pd.Series(bid_qty), errors="coerce").to_numpy(dtype="float64")
    a = pd.to_numeric(pd.Series(ask), errors="coerce").to_numpy(dtype="float64")
    aq = pd.to_numeric(pd.Series(ask_qty), errors="coerce").to_numpy(dtype="float64")
    return pd.Series(b * bq), pd.Series(a * aq)


def valid_mask(df: pd.DataFrame) -> pd.Series:
    num = df[["bid", "bid_qty", "ask", "ask_qty"]].apply(pd.to_numeric, errors="coerce")
    ok = np.isfinite(num.to_numpy()).all(axis=1)
    return pd.Series(ok & (df["bid"].to_numpy(dtype="float64") > 0)
                     & (df["ask"].to_numpy(dtype="float64") > 0)
                     & (df["bid_qty"].to_numpy(dtype="float64") > 0)
                     & (df["ask_qty"].to_numpy(dtype="float64") > 0)
                     & (df["ask"].to_numpy(dtype="float64") > df["bid"].to_numpy(dtype="float64")),
                     index=df.index)


def minute_floor_ms(ms: pd.Series | np.ndarray) -> pd.Series:
    ms = pd.to_numeric(pd.Series(ms), errors="coerce")
    return (ms // MIN_MS * MIN_MS).astype("int64")


def floor_4h_ms(ms: pd.Series | np.ndarray) -> pd.Series:
    ms = pd.to_numeric(pd.Series(ms), errors="coerce")
    return (ms // H4_MS * H4_MS).astype("int64")


def ms_to_utc(ms: int) -> str:
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).isoformat()


def coverage_gaps(cov: pd.DataFrame, gap_ms: int = 60_000) -> pd.DataFrame:
    """Consecutive coverage intervals (same venue) with a gap > gap_ms."""
    c = cov.sort_values("start_ms").reset_index(drop=True)
    nxt = c["start_ms"].shift(-1)
    gap_ms_col = (nxt - c["end_ms"])
    g = c.assign(next_start_ms=nxt, gap_ms=gap_ms_col)
    return g[g["gap_ms"] > gap_ms].reset_index(drop=True)


def lag_summary(lag: pd.Series) -> dict:
    x = pd.to_numeric(lag, errors="coerce").dropna()
    if not len(x):
        return {"n": 0}
    q = x.quantile([0.01, 0.5, 0.99]).to_dict()
    return {"n": int(len(x)), "p1": round(float(q[0.01]), 1),
            "median": round(float(q[0.5]), 1), "p99": round(float(q[0.99]), 1),
            "share_negative": round(float((x < 0).mean()), 4)}


def aggregate_book_table(d: pd.DataFrame) -> pd.DataFrame:
    """Per (bucket_ms, venue, symbol): spread/size stats over valid rows.

    Expects columns: bucket_ms, venue, symbol, spread_bps, bid_usd, ask_usd.
    Buckets with no valid rows are NOT created here (the caller adds the
    zero-filled covered panel); every emitted row is an observed bucket.
    """
    g = d.groupby(["bucket_ms", "venue", "symbol"], as_index=False).agg(
        n=("spread_bps", "size"),
        spread_mean_bps=("spread_bps", "mean"),
        spread_max_bps=("spread_bps", "max"),
        bid_usd_mean=("bid_usd", "mean"),
        ask_usd_mean=("ask_usd", "mean"))
    wide = d.assign(wide=(d["spread_bps"] > WIDE_BPS).astype(int)).groupby(
        ["bucket_ms", "venue", "symbol"])["wide"].mean()
    g["frac_wide"] = g.set_index(["bucket_ms", "venue", "symbol"]).index.map(wide).fillna(0.0).astype(float).to_numpy()
    return g


def covered_minutes_per_venue(cov: pd.DataFrame) -> dict[str, set[int]]:
    """Minute starts (UTC ms) intersecting any coverage interval, per venue."""
    out: dict[str, set[int]] = {}
    for venue, c in cov.groupby("venue"):
        mins: set[int] = set()
        for s, e in zip(c["start_ms"].to_numpy(), c["end_ms"].to_numpy()):
            s, e = int(s), int(e)
            if e <= s:
                continue
            m = s // MIN_MS * MIN_MS
            while m < e:
                mins.add(m)
                m += MIN_MS
        out[str(venue)] = mins
    return out


# ------------------------------------------------------------- loading
def list_book_files() -> list[Path]:
    files: list[Path] = []
    for venue in VENUES:
        for sym in SYMS:
            files.extend(sorted((BOOK / venue / sym).glob("*.parquet")))
    return files


def load_coverage() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for venue in VENUES:
        for p in sorted((COV / venue).glob("*.parquet")):
            c = pd.read_parquet(p, columns=["venue", "start_ms", "end_ms"])
            c["file"] = p.name
            rows.append(c)
            del c
    cov = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["venue", "start_ms", "end_ms", "file"])
    del rows
    if len(cov):
        cov["start_ms"] = cov["start_ms"].astype("int64")
        cov["end_ms"] = cov["end_ms"].astype("int64")
        cov = cov.sort_values(["venue", "start_ms"]).reset_index(drop=True)
    return cov


# ------------------------------------------------------------- main
def main() -> dict:
    files = list_book_files()
    cov = load_coverage()

    # ---- per-file layout + quality, one file at a time; accumulate small tables ----
    layout: list[dict] = []
    files_read: list[str] = []
    per_file_1m: list[pd.DataFrame] = []
    per_day_rows: list[dict] = []  # per (file) pooled stats for the day table
    venue_coin_parts: dict[tuple[str, str], list[pd.DataFrame]] = {}
    n_rows = 0
    n_invalid = 0
    n_dup_rows_total = 0
    n_dup_keys_total = 0
    tmin: int | None = None
    tmax: int | None = None
    qlag_all: list[pd.Series] = []
    rlag_all: list[pd.Series] = []
    sample_gaps: list[dict] = []  # own sample_time diffs > 60 s, per (venue,symbol,day)
    schema_ok = True
    schema_issues: list[str] = []
    seen_symbols: set[str] = set()
    cols_seen: set[str] | None = None

    for p in files:
        venue = p.parent.parent.name
        symbol = p.parent.name
        day = p.stem
        d = pd.read_parquet(p)  # small (~45k rows)
        if cols_seen is None:
            cols_seen = set(d.columns)
            if set(d.columns) != set(BOOK_COLUMNS):
                schema_ok = False
                schema_issues.append(f"columns={sorted(d.columns)}")
        elif set(d.columns) != set(BOOK_COLUMNS):
            schema_ok = False
            schema_issues.append(f"{p.name}: columns={sorted(d.columns)}")
        seen_symbols.add(str(d["symbol"].iloc[0]) if len(d) else symbol)
        n = int(len(d))
        n_rows += n
        if n:
            st = d["sample_time"].astype("int64")
            tmin = int(st.min()) if tmin is None else min(tmin, int(st.min()))
            tmax = int(st.max()) if tmax is None else max(tmax, int(st.max()))
            med_dt = float(st.sort_values().diff().median())
            qlag = (d["quote_time"].astype("int64") - st)
            rlag = (d["recv_time"].astype("int64") - st)
            qlag_all.append(qlag)
            rlag_all.append(rlag)
            # own sample gaps > 60 s within this file
            s_sorted = st.sort_values().to_numpy()
            diffs = np.diff(s_sorted)
            for i in np.where(diffs > 60_000)[0]:
                sample_gaps.append({"venue": venue, "symbol": symbol, "day": day,
                                    "gap_start_utc": ms_to_utc(int(s_sorted[i])),
                                    "gap_end_utc": ms_to_utc(int(s_sorted[i + 1])),
                                    "gap_s": round(float(diffs[i]) / 1000, 1)})
            # duplicates on collector key within file
            key = d[BOOK_KEY].astype(str).agg("|".join, axis=1)
            vc = key.value_counts()
            dk = int((vc > 1).sum())
            dr = int((vc[vc > 1] - 1).sum())
            n_dup_keys_total += dk
            n_dup_rows_total += dr
            # validity + derived
            vm = valid_mask(d)
            n_invalid += int((~vm).sum())
            v = d[vm].copy()
            v["spread_bps"] = spread_bps(v["bid"], v["ask"]).to_numpy()
            bu, au = sizes_usd(v["bid"], v["bid_qty"], v["ask"], v["ask_qty"])
            v["bid_usd"] = bu.to_numpy()
            v["ask_usd"] = au.to_numpy()
            sp = v["spread_bps"].to_numpy(dtype="float64")
            per_day_rows.append({"venue": venue, "symbol": symbol, "day": day, "n": n,
                                 "n_valid": int(len(v)), "n_invalid": int((~vm).sum()),
                                 "spread_mean": float(np.mean(sp)) if len(v) else None,
                                 "spread_med": float(np.median(sp)) if len(v) else None,
                                 "spread_p99": float(np.quantile(sp, 0.99)) if len(v) else None,
                                 "spread_max": float(np.max(sp)) if len(v) else None,
                                 "frac_wide": float((sp > WIDE_BPS).mean()) if len(v) else None,
                                 "bid_usd_med": float(np.median(v["bid_usd"].to_numpy())) if len(v) else None,
                                 "ask_usd_med": float(np.median(v["ask_usd"].to_numpy())) if len(v) else None})
            layout.append({"file": str(p.relative_to(ROOT)), "venue": venue, "symbol": symbol,
                           "day": day, "rows": n, "n_valid": int(len(v)), "n_invalid": int((~vm).sum()),
                           "dup_keys": dk, "dup_rows_extra": dr,
                           "sample_min_utc": ms_to_utc(int(st.min())), "sample_max_utc": ms_to_utc(int(st.max())),
                           "median_dt_ms": round(med_dt, 1),
                           "quote_sample_lag_med_ms": round(float(qlag.median()), 1),
                           "quote_sample_lag_p99_ms": round(float(qlag.quantile(0.99)), 1)})
            # per-file 1m observed aggregates (small)
            if len(v):
                v1 = v.assign(bucket_ms=minute_floor_ms(v["sample_time"]))
                per_file_1m.append(aggregate_book_table(
                    v1[["bucket_ms", "venue", "symbol", "spread_bps", "bid_usd", "ask_usd"]]))
                venue_coin_parts.setdefault((venue, symbol), []).append(
                    v[["spread_bps", "bid_usd", "ask_usd"]])
                del v1
            del v, vm, key, vc, qlag, rlag
        else:
            layout.append({"file": str(p.relative_to(ROOT)), "venue": venue, "symbol": symbol,
                           "day": day, "rows": 0})
        files_read.append(str(p.relative_to(ROOT)))
        del d

    schema = {"expected_columns": BOOK_COLUMNS, "ok": bool(schema_ok), "issues": schema_issues,
              "symbols_seen": sorted(seen_symbols), "n_invalid_excluded": int(n_invalid)}
    dupes = {"n_rows": int(n_rows), "n_dup_keys": int(n_dup_keys_total),
             "n_dup_rows_extra": int(n_dup_rows_total)}
    lags = {}
    if qlag_all:
        q = pd.concat(qlag_all, ignore_index=True)
        lags["quote_minus_sample_ms"] = lag_summary(q)
        del q
    if rlag_all:
        r = pd.concat(rlag_all, ignore_index=True)
        lags["recv_minus_sample_ms"] = lag_summary(r)
        del r

    # ---- coverage summary + gaps (liquidation-stream proxy, same collector) ----
    cov_summary: list[dict] = []
    gaps: list[dict] = []
    if len(cov):
        for (venue, f), c in cov.groupby(["venue", "file"]):
            s, e = int(c["start_ms"].min()), int(c["end_ms"].max())
            cov_summary.append({"venue": str(venue), "file": str(f),
                                "intervals": int(len(c)),
                                "covered_h": round(float((c["end_ms"] - c["start_ms"]).sum()) / 3.6e6, 2),
                                "span_start_utc": ms_to_utc(s), "span_end_utc": ms_to_utc(e)})
        for venue, c in cov.groupby("venue"):
            for _, r in coverage_gaps(c).iterrows():
                gaps.append({"venue": str(venue),
                             "gap_start_utc": ms_to_utc(int(r["end_ms"])),
                             "gap_end_utc": ms_to_utc(int(r["next_start_ms"])),
                             "gap_s": round(float(r["gap_ms"]) / 1000, 1)})

    # ---- venue comparison per coin (pooled valid rows) ----
    venue_cmp: list[dict] = []
    for sym in SYMS:
        row: dict = {"symbol": sym}
        for v in VENUES:
            parts = venue_coin_parts.get((v, sym), [])
            if parts:
                sp = pd.concat([x["spread_bps"] for x in parts], ignore_index=True).to_numpy(dtype="float64")
                bu = pd.concat([x["bid_usd"] for x in parts], ignore_index=True).to_numpy(dtype="float64")
                au = pd.concat([x["ask_usd"] for x in parts], ignore_index=True).to_numpy(dtype="float64")
                row[v] = {"n": int(len(sp)), "spread_mean": round(float(np.mean(sp)), 4),
                          "spread_med": round(float(np.median(sp)), 4),
                          "spread_p99": round(float(np.quantile(sp, 0.99)), 4),
                          "spread_max": round(float(np.max(sp)), 4),
                          "frac_wide": round(float((sp > WIDE_BPS).mean()), 6),
                          "bid_usd_med": round(float(np.median(bu)), 0),
                          "ask_usd_med": round(float(np.median(au)), 0)}
            else:
                row[v] = {"n": 0}
        a, b = row["binance"].get("spread_mean"), row["bybit"].get("spread_mean")
        row["bybit_over_binance_mean_ratio"] = (round(float(b / a), 3)
                                                if a and b and a > 0 else None)
        venue_cmp.append(row)
    del venue_coin_parts

    # ---- 1m + 4h aggregates ----
    agg1m = pd.DataFrame(columns=["bucket_ms", "venue", "symbol", "n", "spread_mean_bps",
                                  "spread_max_bps", "bid_usd_mean", "ask_usd_mean",
                                  "frac_wide", "covered"])
    agg4h = pd.DataFrame(columns=["bucket_ms", "venue", "symbol", "n", "spread_mean_bps",
                                  "spread_max_bps", "bid_usd_mean", "ask_usd_mean",
                                  "frac_wide", "covered_frac"])
    if per_file_1m and len(cov):
        obs1 = pd.concat(per_file_1m, ignore_index=True)
        # re-aggregate across day files (same minute can span two day files)
        wide_n = obs1.assign(_w=obs1["frac_wide"] * obs1["n"])
        g = obs1.groupby(["bucket_ms", "venue", "symbol"], as_index=False).agg(
            n=("n", "sum"), spread_max_bps=("spread_max_bps", "max"))
        mean = obs1.assign(_sm=obs1["spread_mean_bps"] * obs1["n"],
                           _bm=obs1["bid_usd_mean"] * obs1["n"],
                           _am=obs1["ask_usd_mean"] * obs1["n"]).groupby(
            ["bucket_ms", "venue", "symbol"])[["_sm", "_bm", "_am"]].sum()
        g = g.set_index(["bucket_ms", "venue", "symbol"])
        g["_sm"] = mean["_sm"]
        g["_bm"] = mean["_bm"]
        g["_am"] = mean["_am"]
        g["spread_mean_bps"] = g["_sm"] / g["n"]
        g["bid_usd_mean"] = g["_bm"] / g["n"]
        g["ask_usd_mean"] = g["_am"] / g["n"]
        wsum = wide_n.groupby(["bucket_ms", "venue", "symbol"])["_w"].sum()
        g["frac_wide"] = (wsum / g["n"]).astype(float)
        obs1 = g.reset_index().drop(columns=["_sm", "_bm", "_am"])
        del g, mean, wsum, wide_n

        cov_min = covered_minutes_per_venue(cov)
        panel = pd.DataFrame([{"bucket_ms": m, "venue": v, "symbol": s}
                              for v, mins in cov_min.items() for m in mins for s in SYMS])
        agg1m = panel.merge(obs1, on=["bucket_ms", "venue", "symbol"], how="left")
        agg1m["n"] = agg1m["n"].fillna(0).astype(int)
        for c in ("spread_mean_bps", "spread_max_bps", "bid_usd_mean", "ask_usd_mean", "frac_wide"):
            agg1m[c] = agg1m[c].fillna(0.0).astype(float)
        agg1m["covered"] = True
        agg1m["bucket_utc"] = pd.to_datetime(agg1m["bucket_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        agg1m = agg1m.sort_values(["bucket_ms", "venue", "symbol"]).reset_index(drop=True)
        del panel, obs1

        # 4h: re-bucket the 1m observed rows (row-weighted by n seconds)
        obs4 = agg1m[agg1m["n"] > 0].copy()
        obs4["bucket_ms"] = floor_4h_ms(obs4["bucket_ms"]).astype("int64")
        wide_n4 = (obs4["frac_wide"] * obs4["n"])
        g4 = obs4.groupby(["bucket_ms", "venue", "symbol"], as_index=False).agg(
            n=("n", "sum"), spread_max_bps=("spread_max_bps", "max"))
        m4 = obs4.assign(_sm=obs4["spread_mean_bps"] * obs4["n"],
                         _bm=obs4["bid_usd_mean"] * obs4["n"],
                         _am=obs4["ask_usd_mean"] * obs4["n"]).groupby(
            ["bucket_ms", "venue", "symbol"])[["_sm", "_bm", "_am"]].sum()
        g4 = g4.set_index(["bucket_ms", "venue", "symbol"])
        g4["_sm"] = m4["_sm"]
        g4["_bm"] = m4["_bm"]
        g4["_am"] = m4["_am"]
        g4["spread_mean_bps"] = g4["_sm"] / g4["n"]
        g4["bid_usd_mean"] = g4["_bm"] / g4["n"]
        g4["ask_usd_mean"] = g4["_am"] / g4["n"]
        w4 = wide_n4.groupby([obs4["bucket_ms"], obs4["venue"], obs4["symbol"]]).sum()
        w4.index.names = ["bucket_ms", "venue", "symbol"]
        g4["frac_wide"] = (w4 / g4["n"]).astype(float)
        obs4 = g4.reset_index().drop(columns=["_sm", "_bm", "_am"])
        del g4, m4, w4, wide_n4

        bars = sorted({int(b // H4_MS * H4_MS) for mins in cov_min.values() for b in mins})
        panel4 = pd.DataFrame([{"bucket_ms": b, "venue": v, "symbol": s}
                               for b in bars for v in cov_min for s in SYMS])
        iv = {v: sorted(zip(c["start_ms"].to_numpy(), c["end_ms"].to_numpy()))
              for v, c in cov.groupby("venue")}

        def _frac(b: int, v: str) -> float:
            lo, hi = int(b), int(b) + H4_MS
            ov = 0
            for s, e in iv.get(v, []):
                s, e = int(s), int(e)
                if e > lo and s < hi:
                    ov += min(e, hi) - max(s, lo)
            return round(ov / H4_MS, 4)

        panel4["covered_frac"] = [_frac(int(b), str(v)) for b, v in zip(panel4["bucket_ms"], panel4["venue"])]
        panel4 = panel4[panel4["covered_frac"] > 0].reset_index(drop=True)
        agg4h = panel4.merge(obs4, on=["bucket_ms", "venue", "symbol"], how="left")
        agg4h["n"] = agg4h["n"].fillna(0).astype(int)
        for c in ("spread_mean_bps", "spread_max_bps", "bid_usd_mean", "ask_usd_mean", "frac_wide"):
            agg4h[c] = agg4h[c].fillna(0.0).astype(float)
        agg4h["bucket_utc"] = pd.to_datetime(agg4h["bucket_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        agg4h = agg4h.sort_values(["bucket_ms", "venue", "symbol"]).reset_index(drop=True)
        del obs4, panel4
    del per_file_1m

    if len(agg1m):
        agg1m.to_parquet(AGG1M, index=False)
    if len(agg4h):
        agg4h.to_parquet(AGG4H, index=False)

    res = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": ("DATA-PREP only: tidy loader + schema/coverage/quality + 1m/4h spread/depth "
                       "aggregates. No dip-fill join, no forward returns, no PnL, no PROMISING verdict."),
        "collector_note": ("Backend backend/liquidations.py samples latest best bid/ask ~1/s "
                           "(Binance <sym>@bookTicker, Bybit tickers.{SYM} bid1/ask1). "
                           "Topbook files carry no _coverage dir; uptime is proxied by the "
                           "liquidation-stream _coverage (same process) + own sample_time gaps. "
                           "spread_bps=(ask-bid)/mid*1e4; sizes in USD=price*qty; wide=spread>5bps."),
        "files_read": files_read,
        "file_layout": layout,
        "n_rows": int(n_rows),
        "sample_span_utc": [ms_to_utc(int(tmin)), ms_to_utc(int(tmax))] if tmin is not None else [],
        "schema": schema,
        "duplicates": dupes,
        "lags_ms": lags,
        "coverage_summary_liq_proxy": cov_summary,
        "coverage_gaps_over_60s_liq_proxy": gaps,
        "sample_gaps_over_60s_own": sample_gaps,
        "by_day_venue_symbol": per_day_rows,
        "venue_spread_comparison": venue_cmp,
        "agg_1m": {"rows": int(len(agg1m)),
                   "minutes_with_rows": int((agg1m.groupby(["bucket_ms", "venue"])["n"].sum() > 0).sum()) if len(agg1m) else 0,
                   "parquet": "aggregates_1m.parquet" if len(agg1m) else None},
        "agg_4h": {"rows": int(len(agg4h)), "parquet": "aggregates_4h.parquet" if len(agg4h) else None,
                   "bars": agg4h[["bucket_utc", "venue", "symbol", "n", "spread_mean_bps",
                                   "spread_max_bps", "bid_usd_mean", "ask_usd_mean",
                                   "frac_wide", "covered_frac"]].to_dict("records") if len(agg4h) else []},
    }
    RES.write_text(json.dumps(res, indent=1, default=str))
    print(f"oc_topbook: n={n_rows} invalid={n_invalid} files={len(files_read)} "
          f"gaps_proxy={len(gaps)} gaps_own={len(sample_gaps)} "
          f"dup_rows={n_dup_rows_total} agg1m={len(agg1m)} agg4h={len(agg4h)} -> {RES}")
    return res


if __name__ == "__main__":
    main()
