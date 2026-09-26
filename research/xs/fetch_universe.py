"""xs W13: multi-coin USD-M universe download.

Per OPENCODE_XS_W13_UNIVERSE.md:
1. List USDT-margined PERPETUAL contracts + onboardDate from exchangeInfo;
   also probe delisted/settled (status != TRADING) symbols for klines.
2. Rank by quote volume from ticker/24hr (as-of today, survivorship-biased);
   take top 60 plus included delisted symbols.
3. Download 4h + 1d klines from max(onboardDate, 2019-09-08) to latest closed
   bar via agentic_alpha_lab.data.binance_usdm.fetch_klines, plus full funding
   history (/fapi/v1/fundingRate, paginated, 0.2s sleep).
4. Save {SYM}_{4h,1d,funding}.parquet + manifest.json with onboardDate,
   status, first/last bar, rows, gaps, SHA-256 and the selection caveat.

Rate limits: sleeps + retry with backoff on 429/418/5xx.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from agentic_alpha_lab.data.binance_usdm import INTERVAL_MS, fetch_klines, validate_klines

EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "xs_universe_20260924"
EARLIEST = datetime(2019, 9, 8, tzinfo=timezone.utc)
TOP_N = 60
FUNDING_PAGE_SLEEP = 0.2

CAVEAT = (
    "Universe ranked by current 24h quoteVolume from /fapi/v1/ticker/24hr "
    "(labeled '30-day' in the assignment; ranking uses the live 24h snapshot, "
    "optionally scaled x30 which preserves rank). Ranking is as-of download day "
    "and therefore survivorship-biased: delisted/settled symbols are absent from "
    "the ticker and were added separately via klines probing. Do not treat this "
    "as a point-in-time universe."
)


def get_with_retry(session: requests.Session, url: str, params: dict | None = None,
                   max_retries: int = 7, timeout: int = 60) -> requests.Response:
    backoff = 2.0
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            continue
        if resp.status_code in (429, 418) or 500 <= resp.status_code < 600:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            time.sleep(wait)
            backoff = min(backoff * 2, 60.0)
            if attempt == max_retries - 1:
                resp.raise_for_status()
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable retry loop")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_funding_full(symbol: str, start_ms: int, end_ms: int,
                       session: requests.Session) -> pd.DataFrame:
    rows: list[dict] = []
    cursor = start_ms
    while True:
        params = {"symbol": symbol.upper(), "startTime": cursor, "endTime": end_ms, "limit": 1000}
        try:
            resp = get_with_retry(session, FUNDING_URL, params=params)
            batch = resp.json()
        except Exception as e:
            # Some delisted symbols return errors on funding; record empty with note
            if "funding_error" not in [r.get("_k") for r in rows]:
                pass
            raise
        if not batch:
            break
        rows.extend(batch)
        last_t = int(batch[-1]["fundingTime"])
        if len(batch) < 1000:
            break
        nxt = last_t + 1
        if nxt <= cursor:
            raise RuntimeError("funding pagination did not advance")
        cursor = nxt
        time.sleep(FUNDING_PAGE_SLEEP)
    if not rows:
        return pd.DataFrame(columns=["symbol", "fundingTime", "fundingRate", "markPrice", "rateType"])
    df = pd.DataFrame(rows)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    if "markPrice" in df.columns:
        df["markPrice"] = pd.to_numeric(df["markPrice"], errors="coerce")
    df = df.drop_duplicates(subset=["fundingTime"], keep="last").sort_values("fundingTime").reset_index(drop=True)
    return df


def gaps_count(times: pd.Series, interval: str) -> int:
    if len(times) < 2:
        return 0
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    diffs = times.sort_values().diff().dropna()
    return int((diffs > expected).sum())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    # 1. exchangeInfo
    info = get_with_retry(session, EXCHANGE_INFO_URL).json()
    server_ms = int(info.get("serverTime", int(time.time() * 1000)))
    now_utc = datetime.fromtimestamp(server_ms / 1000, tz=timezone.utc)
    all_syms = info.get("symbols", [])
    perp_usdt = [s for s in all_syms
                 if s.get("contractType") == "PERPETUAL" and s.get("marginAsset") == "USDT"]
    trading = [s for s in perp_usdt if s.get("status") == "TRADING"]
    nontrading = [s for s in perp_usdt if s.get("status") != "TRADING"]
    print(f"PERP-USDT total={len(perp_usdt)} TRADING={len(trading)} non-TRADING={len(nontrading)}")

    # 2. ticker/24hr ranking snapshot
    tick = get_with_retry(session, TICKER_URL).json()
    ticker_fetched_at = now_utc.isoformat()
    tmap = {t["symbol"]: t for t in tick if "symbol" in t}
    ranked: list[tuple[str, float]] = []
    for s in trading:
        sym = s["symbol"]
        qv = float(tmap[sym]["quoteVolume"]) if sym in tmap and tmap[sym].get("quoteVolume") else float("nan")
        ranked.append((sym, qv))
    ranked.sort(key=lambda x: (x[1] != x[1], -(x[1] if x[1] == x[1] else 0)))  # NaN last
    top60 = [(sym, qv) for sym, qv in ranked[:TOP_N]]
    print("Top 5 by 24h quoteVolume:", top60[:5])

    # Probe delisted/settled symbols: include if klines endpoint returns rows
    included_delisted: list[dict] = []
    excluded_delisted: list[dict] = []
    for s in nontrading:
        sym = s["symbol"]
        try:
            r = get_with_retry(session, "https://fapi.binance.com/fapi/v1/klines",
                               params={"symbol": sym, "interval": "1d", "limit": 1})
            batch = r.json()
            ok = isinstance(batch, list) and len(batch) > 0
        except Exception as e:
            ok = False
            batch = str(e)[:200]
        rec = {"symbol": sym, "status": s.get("status"), "onboardDate": s.get("onboardDate")}
        if ok:
            included_delisted.append(rec)
        else:
            rec["reason"] = "klines not returned"
            excluded_delisted.append(rec)
        time.sleep(0.05)
    print(f"delisted included={len(included_delisted)} excluded={len(excluded_delisted)}")

    symbols = [sym for sym, _ in top60] + [d["symbol"] for d in included_delisted]
    info_by_sym = {s["symbol"]: s for s in perp_usdt}

    manifest_symbols: dict[str, dict] = {}
    manifest_symbols["_universe_note"] = {"caveat": CAVEAT}  # type: ignore[assignment]

    # Persist selection snapshot
    selection = {
        "ticker_fetched_at": ticker_fetched_at,
        "ranking_metric": "quoteVolume_24h (x30 rank-equivalent for '30-day' label)",
        "top_n": TOP_N,
        "top60": [{"symbol": sym, "quoteVolume_24h": qv,
                   "quoteVolume_30d_est": qv * 30 if qv == qv else None} for sym, qv in top60],
        "included_delisted": included_delisted,
        "excluded_delisted": excluded_delisted,
        "caveat": CAVEAT,
    }
    (OUT_DIR / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")

    # 3. downloads
    end_dt = now_utc
    for i, sym in enumerate(symbols, 1):
        meta = info_by_sym.get(sym, {})
        onboard_ms = meta.get("onboardDate")
        onboard_dt = (datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
                      if onboard_ms else EARLIEST)
        start_dt = max(onboard_dt, EARLIEST)
        status = meta.get("status", "UNKNOWN")
        print(f"[{i}/{len(symbols)}] {sym} status={status} start={start_dt.date()}", flush=True)
        entry: dict = {
            "symbol": sym,
            "status": status,
            "onboardDate": onboard_dt.isoformat() if onboard_ms else None,
            "onboardDate_ms": onboard_ms,
            "klines_start": start_dt.isoformat(),
        }
        # klines with outer retry (resume: reuse existing files)
        for interval in ("4h", "1d"):
            out_path = OUT_DIR / f"{sym}_{interval}.parquet"
            if out_path.exists() and out_path.stat().st_size > 0:
                try:
                    frame = pd.read_parquet(out_path)
                    if len(frame) > 0:
                        q = validate_klines(frame, interval)
                        entry[f"{interval}"] = {
                            "rows": int(len(frame)),
                            "first_open": pd.to_datetime(frame['open_time']).min().isoformat(),
                            "last_close": pd.to_datetime(frame['close_time']).max().isoformat(),
                            "missing_intervals": gaps_count(pd.to_datetime(frame["open_time"], utc=True), interval),
                            "zero_volume_rows": int((frame["volume"] == 0).sum()),
                            "sha256": sha256_of(out_path),
                            "quality_first_open": q.first_open_time,
                            "quality_last_close": q.last_close_time,
                        }
                        continue
                except Exception:
                    pass  # fall through to re-download
            for attempt in range(4):
                try:
                    frame = fetch_klines(symbol=sym, interval=interval,
                                         start=start_dt, end=end_dt, session=session)
                    frame.to_parquet(out_path, index=False)
                    break
                except Exception as e:
                    print(f"  {interval} attempt {attempt + 1} failed: {str(e)[:200]}")
                    time.sleep(2 ** attempt * 2)
            else:
                entry[f"{interval}_error"] = "download failed after retries"
                continue
            frame = pd.read_parquet(out_path)
            q = validate_klines(frame, interval)
            entry[f"{interval}"] = {
                "rows": int(len(frame)),
                "first_open": pd.to_datetime(frame['open_time']).min().isoformat(),
                "last_close": pd.to_datetime(frame['close_time']).max().isoformat(),
                "missing_intervals": gaps_count(pd.to_datetime(frame["open_time"], utc=True), interval),
                "zero_volume_rows": int((frame["volume"] == 0).sum()),
                "sha256": sha256_of(out_path),
                "quality_first_open": q.first_open_time,
                "quality_last_close": q.last_close_time,
            }
            time.sleep(0.2)
        # funding full history (resume: reuse existing file)
        fout = OUT_DIR / f"{sym}_funding.parquet"
        if fout.exists() and fout.stat().st_size > 0:
            try:
                fdf = pd.read_parquet(fout)
                if len(fdf):
                    entry["funding"] = {
                        "rows": int(len(fdf)),
                        "first": pd.to_datetime(fdf["fundingTime"]).min().isoformat(),
                        "last": pd.to_datetime(fdf["fundingTime"]).max().isoformat(),
                        "sha256": sha256_of(fout),
                    }
                else:
                    entry["funding"] = {"rows": 0, "note": "no funding rows (cached)",
                                        "sha256": sha256_of(fout)}
                manifest_symbols[sym] = entry
                time.sleep(0.05)
                continue
            except Exception:
                pass  # fall through to re-download
        try:
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            fdf = fetch_funding_full(sym, start_ms, end_ms, session)
            # normalize columns even if empty
            fdf.to_parquet(fout, index=False)
            if len(fdf):
                entry["funding"] = {
                    "rows": int(len(fdf)),
                    "first": pd.to_datetime(fdf["fundingTime"]).min().isoformat(),
                    "last": pd.to_datetime(fdf["fundingTime"]).max().isoformat(),
                    "sha256": sha256_of(fout),
                }
            else:
                entry["funding"] = {"rows": 0, "note": "no funding rows returned",
                                    "sha256": sha256_of(fout)}
        except Exception as e:
            entry["funding_error"] = str(e)[:500]
            # write empty placeholder so file set is complete
            pd.DataFrame(columns=["symbol", "fundingTime", "fundingRate",
                                  "markPrice", "rateType"]).to_parquet(fout, index=False)
            entry["funding"] = {"rows": 0, "note": f"error: {str(e)[:200]}",
                                "sha256": sha256_of(fout)}
            time.sleep(1.0)
        manifest_symbols[sym] = entry
        time.sleep(0.2)

    # 4. manifest
    del manifest_symbols["_universe_note"]
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "server_time_at_selection": now_utc.isoformat(),
        "source": "binance_usdm_rest (fapi.binance.com)",
        "quote": "Binance USD-M",
        "earliest_start": EARLIEST.isoformat(),
        "intervals": ["4h", "1d"],
        "universe_selection_caveat": CAVEAT,
        "counts": {
            "perp_usdt_total": len(perp_usdt),
            "trading": len(trading),
            "nontrading": len(nontrading),
            "top_n": TOP_N,
            "included_delisted": len(included_delisted),
            "universe_total": len(symbols),
        },
        "execution_assumptions": {
            "klines": "closed bars only (fetch_klines filters close_time < serverTime)",
            "funding_pagination": "limit=1000, forward from klines_start, sleep 0.2s",
            "rate_limits": "sleep + retry with backoff on 429/418/5xx",
        },
        "symbols": manifest_symbols,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done. Universe={len(symbols)} files in {OUT_DIR}")


if __name__ == "__main__":
    main()
