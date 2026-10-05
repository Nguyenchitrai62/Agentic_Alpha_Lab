"""oc_liqlive: DATA-PREP loader for the live liquidation stream (no outcome research).

Reads (small; one file at a time; no network; no 1m klines; no fills/harness):
  data/raw/liquidations_live/{binance,bybit}/<SYM>/YYYY-MM-DD.parquet
  data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet
Writes (this folder only):
  results.json, aggregates_1m.parquet, aggregates_4h.parquet
Usage: .venv/Scripts/python.exe research/tournament/oc_liqlive/load_liq.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
LIQ = ROOT / "data/raw/liquidations_live"
OUT_DIR = Path(__file__).resolve().parent
RES = OUT_DIR / "results.json"
AGG1M = OUT_DIR / "aggregates_1m.parquet"
AGG4H = OUT_DIR / "aggregates_4h.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
VENUES = ("binance", "bybit")
LIQ_COLUMNS = ["venue", "symbol", "side", "raw_side", "price", "qty",
               "notional_usd", "event_time", "recv_time"]
LIQ_KEY = ["venue", "symbol", "event_time", "raw_side", "price", "qty"]
MIN_MS = 60_000
H4_MS = 4 * 3_600_000


# ------------------------------------------------------------- pure helpers
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


def skew_summary(lag: pd.Series) -> dict:
    x = pd.to_numeric(lag, errors="coerce").dropna()
    if not len(x):
        return {"n": 0}
    q = x.quantile([0.01, 0.5, 0.99]).to_dict()
    return {"n": int(len(x)), "p1": round(float(q[0.01]), 1),
            "median": round(float(q[0.5]), 1), "p99": round(float(q[0.99]), 1),
            "share_negative": round(float((x < 0).mean()), 4)}


def aggregate_event_table(liq: pd.DataFrame) -> pd.DataFrame:
    """Per (bucket_ms, venue, symbol): counts + long/short notionals.

    Expects columns: bucket_ms, venue, symbol, side, notional_usd.
    Buckets with no liquidations are NOT created here (the caller adds the
    zero-filled covered panel); every emitted row is an observed bucket.
    """
    g = liq.groupby(["bucket_ms", "venue", "symbol"], as_index=False).agg(
        n=("notional_usd", "size"),
        total_notional=("notional_usd", "sum"),
        max_single=("notional_usd", "max"))
    ls = liq[liq["side"] == "long"].groupby(
        ["bucket_ms", "venue", "symbol"])["notional_usd"].sum()
    ss = liq[liq["side"] == "short"].groupby(
        ["bucket_ms", "venue", "symbol"])["notional_usd"].sum()
    g["n_long"] = g.set_index(["bucket_ms", "venue", "symbol"]).index.map(
        liq[liq["side"] == "long"].groupby(["bucket_ms", "venue", "symbol"]).size()).fillna(0).astype(int).to_numpy()
    g["n_short"] = (g["n"] - g["n_long"]).astype(int)
    g["long_notional"] = g.set_index(["bucket_ms", "venue", "symbol"]).index.map(ls).fillna(0.0).astype(float).to_numpy()
    g["short_notional"] = g.set_index(["bucket_ms", "venue", "symbol"]).index.map(ss).fillna(0.0).astype(float).to_numpy()
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
def list_liq_files() -> list[Path]:
    files: list[Path] = []
    for venue in VENUES:
        for sym in SYMS:
            files.extend(sorted((LIQ / venue / sym).glob("*.parquet")))
    return files


def load_liquidations() -> tuple[pd.DataFrame, list[str], list[dict]]:
    """One file at a time -> tidy frame + relative paths + per-file layout."""
    parts: list[pd.DataFrame] = []
    files_read: list[str] = []
    layout: list[dict] = []
    for p in list_liq_files():
        d = pd.read_parquet(p, columns=LIQ_COLUMNS)
        layout.append({
            "file": str(p.relative_to(ROOT)),
            "venue": str(d["venue"].iloc[0]) if len(d) else p.parent.parent.name,
            "symbol": p.parent.name,
            "day": p.stem,
            "rows": int(len(d)),
            "event_min_utc": ms_to_utc(int(d["event_time"].min())) if len(d) else None,
            "event_max_utc": ms_to_utc(int(d["event_time"].max())) if len(d) else None,
        })
        if len(d):
            parts.append(d[LIQ_COLUMNS])
        files_read.append(str(p.relative_to(ROOT)))
        del d
    liq = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=LIQ_COLUMNS)
    del parts
    if len(liq):
        liq["event_time"] = liq["event_time"].astype("int64")
        liq["recv_time"] = liq["recv_time"].astype("int64")
        liq = liq.sort_values("event_time").reset_index(drop=True)
    return liq, files_read, layout


def load_coverage() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for venue in VENUES:
        for p in sorted((LIQ / "_coverage" / venue).glob("*.parquet")):
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
    liq, files_read, layout = load_liquidations()
    cov = load_coverage()

    # ---- schema check ----
    schema: dict = {"expected_columns": LIQ_COLUMNS, "ok": True, "issues": []}
    if len(liq):
        if set(liq.columns) != set(LIQ_COLUMNS):
            schema["ok"] = False
            schema["issues"].append(f"columns={sorted(liq.columns)}")
        bad_side = int((~liq["side"].isin(["long", "short"])).sum())
        bad_px = int(((~np.isfinite(liq["price"].to_numpy(dtype="float64"))) | (liq["price"] <= 0)).sum())
        bad_qty = int(((~np.isfinite(liq["qty"].to_numpy(dtype="float64"))) | (liq["qty"] <= 0)).sum())
        notion = liq["price"].to_numpy(dtype="float64") * liq["qty"].to_numpy(dtype="float64")
        rel = np.abs(notion - liq["notional_usd"].to_numpy(dtype="float64")) / np.maximum(notion, 1e-9)
        bad_not = int((rel > 1e-4).sum())
        schema.update({"bad_side": bad_side, "bad_price": bad_px, "bad_qty": bad_qty,
                       "bad_notional": bad_not})
        if bad_side or bad_px or bad_qty or bad_not:
            schema["ok"] = False
            schema["issues"].append("value violations (see counts)")
        # venue/side vocabulary (Bybit Buy/Sell; Binance BUY/SELL)
        schema["raw_side_values"] = sorted(liq["raw_side"].astype(str).unique().tolist())
        schema["symbols_seen"] = sorted(liq["symbol"].astype(str).unique().tolist())

    # ---- duplicates (collector key) ----
    dupes = {"n_rows": int(len(liq)), "n_dup_keys": 0, "n_dup_rows": 0}
    if len(liq):
        key = liq[LIQ_KEY].astype(str).agg("|".join, axis=1)
        vc = key.value_counts()
        dupes["n_dup_keys"] = int((vc > 1).sum())
        dupes["n_dup_rows"] = int((vc[vc > 1] - 1).sum())

    # ---- clock skew ----
    skew = {}
    if len(liq):
        lag = liq["recv_time"].astype("int64") - liq["event_time"].astype("int64")
        skew["all"] = skew_summary(lag)
        for v in VENUES:
            m = liq["venue"] == v
            if m.any():
                skew[v] = skew_summary(lag[m])

    # ---- coverage summary + gaps ----
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

    # ---- per day / venue / symbol (majors order) ----
    by_day: list[dict] = []
    if len(liq):
        liq["day"] = pd.to_datetime(liq["event_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        g = liq.groupby(["day", "venue", "symbol"], as_index=False).agg(
            rows=("notional_usd", "size"), total_notional=("notional_usd", "sum"),
            max_single=("notional_usd", "max"),
            long_share=("side", lambda s: float((s == "long").mean())),
            event_min=("event_time", "min"), event_max=("event_time", "max"))
        order = {s: i for i, s in enumerate(SYMS)}
        g["sord"] = g["symbol"].map(order).fillna(99).astype(int)
        g = g.sort_values(["day", "venue", "sord"]).drop(columns="sord")
        for r in g.to_dict("records"):
            r["event_min_utc"] = ms_to_utc(int(r.pop("event_min")))
            r["event_max_utc"] = ms_to_utc(int(r.pop("event_max")))
            r["total_notional"] = round(float(r["total_notional"]), 1)
            r["max_single"] = round(float(r["max_single"]), 1)
            r["long_share"] = round(float(r["long_share"]), 4)
            by_day.append(r)

    # ---- 1m + 4h aggregates (observed + zero-filled covered panel) ----
    agg1m = pd.DataFrame(columns=["bucket_ms", "venue", "symbol", "n", "n_long",
                                  "n_short", "long_notional", "short_notional",
                                  "total_notional", "max_single", "covered"])
    agg4h = agg1m.copy()
    top1m: list[dict] = []
    if len(liq) and len(cov):
        liq1 = liq.assign(bucket_ms=minute_floor_ms(liq["event_time"]))
        obs1 = aggregate_event_table(liq1[["bucket_ms", "venue", "symbol", "side", "notional_usd"]])
        cov_min = covered_minutes_per_venue(cov)
        panel = {(m, v, s): True for v, mins in cov_min.items()
                 for m in mins for s in SYMS}
        panel_df = pd.DataFrame([{"bucket_ms": m, "venue": v, "symbol": s}
                                 for (m, v, s) in panel])
        agg1m = panel_df.merge(obs1, on=["bucket_ms", "venue", "symbol"], how="left")
        for c in ("n", "n_long", "n_short"):
            agg1m[c] = agg1m[c].fillna(0).astype(int)
        for c in ("total_notional", "long_notional", "short_notional", "max_single"):
            agg1m[c] = agg1m[c].fillna(0.0).astype(float)
        agg1m["covered"] = True
        agg1m["bucket_utc"] = pd.to_datetime(agg1m["bucket_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        agg1m = agg1m.sort_values(["bucket_ms", "venue", "symbol"]).reset_index(drop=True)
        del panel_df, liq1, obs1

        liq4 = liq.assign(bucket_ms=floor_4h_ms(liq["event_time"]))
        obs4 = aggregate_event_table(liq4[["bucket_ms", "venue", "symbol", "side", "notional_usd"]])
        bars = sorted({int(b // H4_MS * H4_MS) for mins in cov_min.values() for b in mins})
        panel4 = pd.DataFrame([{"bucket_ms": b, "venue": v, "symbol": s}
                               for b in bars for v in cov_min for s in SYMS])
        # covered fraction per (bar, venue)
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
        panel4["covered_frac"] = [ _frac(int(b), str(v)) for b, v in zip(panel4["bucket_ms"], panel4["venue"])]
        panel4 = panel4[panel4["covered_frac"] > 0].reset_index(drop=True)
        agg4h = panel4.merge(obs4, on=["bucket_ms", "venue", "symbol"], how="left")
        for c in ("n", "n_long", "n_short"):
            agg4h[c] = agg4h[c].fillna(0).astype(int)
        for c in ("total_notional", "long_notional", "short_notional", "max_single"):
            agg4h[c] = agg4h[c].fillna(0.0).astype(float)
        agg4h["covered"] = agg4h["covered_frac"] > 0
        agg4h["bucket_utc"] = pd.to_datetime(agg4h["bucket_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        agg4h = agg4h.sort_values(["bucket_ms", "venue", "symbol"]).reset_index(drop=True)
        del liq4, obs4, panel4

        nz = agg1m[agg1m["n"] > 0].sort_values("total_notional", ascending=False).head(10)
        for r in nz.to_dict("records"):
            top1m.append({"minute_utc": r["bucket_utc"], "venue": r["venue"], "symbol": r["symbol"],
                          "notional_usd": round(float(r["total_notional"]), 1), "n": int(r["n"]),
                          "long_notional": round(float(r["long_notional"]), 1),
                          "short_notional": round(float(r["short_notional"]), 1),
                          "max_single": round(float(r["max_single"]), 1)})

    if len(agg1m):
        AGG1M.parent.mkdir(parents=True, exist_ok=True)
        agg1m.to_parquet(AGG1M, index=False)
    if len(agg4h):
        agg4h.to_parquet(AGG4H, index=False)

    res = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": ("DATA-PREP only: tidy loader + coverage/quality + 1m/4h aggregates. "
                       "No dip-fill join, no forward returns, no PnL, no PROMISING verdict."),
        "venue_note": ("binance forceOrder: at most ONE event/symbol/s (snapshot of that second); "
                       "bybit allLiquidation: every liquidation batched per 500ms. "
                       "Counts/notionals are NOT directly comparable across venues. "
                       "side=long means a LONG position was liquidated (forced SELL)."),
        "files_read": files_read,
        "file_layout": layout,
        "n_rows": int(len(liq)),
        "event_span_utc": [ms_to_utc(int(liq["event_time"].min())), ms_to_utc(int(liq["event_time"].max()))] if len(liq) else [],
        "schema": schema,
        "duplicates": dupes,
        "clock_skew_lag_ms": skew,
        "coverage_summary": cov_summary,
        "coverage_gaps_over_60s": gaps,
        "by_day_venue_symbol": by_day,
        "agg_1m": {"rows": int(len(agg1m)), "minutes_with_liq": int((agg1m.groupby(['bucket_ms','venue'])['n'].sum() > 0).sum()) if len(agg1m) else 0,
                   "parquet": "aggregates_1m.parquet" if len(agg1m) else None, "top10_minutes": top1m},
        "agg_4h": {"rows": int(len(agg4h)), "parquet": "aggregates_4h.parquet" if len(agg4h) else None,
                   "bars": agg4h[["bucket_utc", "venue", "symbol", "n", "long_notional",
                                  "short_notional", "total_notional", "covered_frac"]].to_dict("records") if len(agg4h) else []},
    }
    RES.write_text(json.dumps(res, indent=1, default=str))
    print(f"oc_liqlive: n={len(liq)} files={len(files_read)} gaps={len(gaps)} "
          f"dup_rows={dupes['n_dup_rows']} agg1m={len(agg1m)} agg4h={len(agg4h)} -> {RES}")
    return res


if __name__ == "__main__":
    main()
