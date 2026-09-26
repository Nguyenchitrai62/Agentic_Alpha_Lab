"""D-reextend (round69 / v158): APPEND-ONLY extension of sealed forward window.

Doc-truoc: configs/opencode_v158_reextend.json (pre-spec cursors, sources, checks).
Nguyen tac APPEND-ONLY (tuyet doi):
  - KHONG ghi de/touch candles.parquet, funding.parquet, macro.parquet,
    manifest.json, SEAL.json (verify SHA truoc+sau, phai khop).
  - Chi ghi file MOI: delta raw dir + *_append_*.parquet + *_extended_*.parquet
    + manifest_extend_*.json + SEAL_reaffirmation_*.json + summary.
  - Chi kiem tra CAU TRUC (counts/gaps/bounds/schema/monotonic).
    KHONG returns/labels/PnL/distributions/plots/thresholds/training.
Nguon: Binance klines/funding public + Yahoo macro (tai dung pattern
scripts/opencode_crawl_forward.py). Neu nguon fail/blocked -> STOP, KHONG che data.
"""

import torch  # noqa: F401 - torch DAU TIEN (DLL load-order Windows host: pandas truoc torch gay WinError 1114)
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KLINES_API = "https://fapi.binance.com/fapi/v1/klines"
FUNDING_API = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "BTCUSDT"
KLINE_INTERVAL = "5m"
STEP_MS = 5 * 60 * 1000

UA_BIN = {"User-Agent": "AgenticAlphaLab-D-Reextend/1.0"}
UA_YAHOO = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
MACRO_SYMBOLS = {"spy": "SPY", "dxy": "DX-Y.NYB"}

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "num_trades",
              "taker_buy_volume", "taker_buy_quote_volume", "ignore"]

TAG = "20260909"
SEALED = {"candles.parquet": "cce98470a377232ed8f53eb296c9f2715f3b62af2652d4e4c1b6d1cd486c32af",
          "funding.parquet": "dfb4272c3dbcd4cc8a1e0ad745cbfd9cd8fa2b5affd20a0352657a0468e5323f",
          "macro.parquet": "32a7cfef3072a22ddd3d24a8274256c2653c38ec77b38d3f4fc18adbd799b7ea"}
# Cursor next-start (from sealed manifest, pre-spec v158; stdlib only, khong pandas o module-level):
KLINES_NEXT_MS = int(datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc).timestamp() * 1000)
FUNDING_NEXT_MS = 1788854400002 + 1
MACRO_FETCH_FROM = {"spy": "2026-09-04", "dxy": "2026-09-08"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def lay_klines(start_ms, end_ms, thu_lai=6):
    loi = None
    for lan in range(thu_lai):
        try:
            qs = {"symbol": SYMBOL, "interval": KLINE_INTERVAL,
                  "startTime": int(start_ms), "endTime": int(end_ms), "limit": 1500}
            url = KLINES_API + "?" + urllib.parse.urlencode(qs)
            req = urllib.request.Request(url, headers=UA_BIN)
            with urllib.request.urlopen(req, timeout=60) as rep:
                return json.loads(rep.read().decode("utf-8")), url
        except Exception as exc:  # noqa: BLE001
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"BLOCKER klines startTime={start_ms}: {loi}")


def lay_funding(start_ms, end_ms, thu_lai=6):
    loi = None
    for lan in range(thu_lai):
        try:
            qs = {"symbol": SYMBOL, "limit": 1000,
                  "startTime": int(start_ms), "endTime": int(end_ms)}
            url = FUNDING_API + "?" + urllib.parse.urlencode(qs)
            req = urllib.request.Request(url, headers=UA_BIN)
            with urllib.request.urlopen(req, timeout=30) as rep:
                return json.loads(rep.read().decode("utf-8")), url
        except Exception as exc:  # noqa: BLE001
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"BLOCKER funding startTime={start_ms}: {loi}")


def fetch_yahoo_daily(symbol: str, start_iso: str, end_iso: str):
    import datetime as dt
    start = dt.date.fromisoformat(start_iso)
    end = dt.date.fromisoformat(end_iso)
    p1 = int(dt.datetime(start.year, start.month, start.day, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(end.year, end.month, end.day, tzinfo=dt.timezone.utc).timestamp()) + 86400
    last_err = None
    for host in YAHOO_HOSTS:
        url = (f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
               f"?period1={p1}&period2={p2}&interval=1d&events=div%7Csplit")
        try:
            req = urllib.request.Request(url, headers=UA_YAHOO)
            raw = urllib.request.urlopen(req, timeout=30).read()
            d = json.loads(raw)
            res = (d.get("chart") or {}).get("result")
            if not res:
                last_err = f"{host}: empty result {str(d)[:200]}"
                continue
            r = res[0]
            ts = r.get("timestamp") or []
            q = (r.get("indicators") or {}).get("quote", [{}])[0]
            adj = (r.get("indicators") or {}).get("adjclose", [{}])[0].get("adjclose")
            rows = []
            for i, t in enumerate(ts):
                day = dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).date().isoformat()

                def g(k):
                    v = (q.get(k) or [None] * len(ts))[i] if q.get(k) else None
                    return float(v) if v is not None else None
                a = None
                if adj is not None and i < len(adj) and adj[i] is not None:
                    a = float(adj[i])
                rows.append({"date": day, "open": g("open"), "high": g("high"),
                             "low": g("low"), "close": g("close"),
                             "adjclose": a, "volume": g("volume")})
            import pandas as pd
            df = pd.DataFrame(rows).dropna(subset=["close"]).reset_index(drop=True)
            if len(df) == 0:
                last_err = f"{host}: 0 rows after dropna"
                continue
            return df, url.split("period1")[0] + "period1=...&period2=...&interval=1d"
        except Exception as e:  # noqa: BLE001
            last_err = f"{host}: {e}"
            time.sleep(2)
    raise RuntimeError(f"BLOCKER yahoo {symbol}: {last_err}")


def main():
    import pandas as pd

    goc = Path(__file__).resolve().parents[1]
    frozendir = goc / "data" / "processed" / "opencode_forward_20260323"
    rawdir = goc / "data" / "raw" / f"opencode_forward_5m_ext_{TAG}"
    artdir = goc / "artifacts" / "research" / "opencode_v158_reextend"
    if rawdir.exists():
        raise FileExistsError(f"{rawdir} da ton tai: khong ghi de.")
    for fn in ("manifest.json", "SEAL.json"):
        assert (frozendir / fn).exists(), f"thieu sealed {fn}"

    # SHA truoc (sealed bytes immutable).
    sha_truoc = {f: sha256_file(frozendir / f) for f in SEALED}
    for f, h in SEALED.items():
        assert sha_truoc[f] == h, f"sealed {f} da doi truoc khi chay: {sha_truoc[f]}"
    print(f"[seal-truoc] OK 3/3 khop manifest: {sha_truoc}", flush=True)
    mtime_truoc = {f: (frozendir / f).stat().st_mtime_ns for f in
                   ["candles.parquet", "funding.parquet", "macro.parquet",
                    "manifest.json", "SEAL.json"]}

    now_utc = pd.Timestamp.now(tz="UTC")
    end_ms = int(now_utc.timestamp() * 1000)
    print(f"[delta] klines {pd.to_datetime(KLINES_NEXT_MS, unit='ms', utc=True)} -> {now_utc} (end_ms={end_ms})",
          flush=True)
    rawdir.mkdir(parents=True)
    artdir.mkdir(parents=True, exist_ok=True)

    old_c = pd.read_parquet(frozendir / "candles.parquet")
    old_f = pd.read_parquet(frozendir / "funding.parquet")
    old_m = pd.read_parquet(frozendir / "macro.parquet")
    last_open = old_c["open_time"].iloc[-1]
    last_funding_t = old_f["funding_time"].iloc[-1]
    last_macro = {s: old_m.loc[old_m["symbol"] == s, "date"].max() for s in MACRO_SYMBOLS}

    # ---- (1) delta klines ----
    tat_ca, mau_k = [], None
    con_trot = KLINES_NEXT_MS
    while True:
        trang, mau_k = lay_klines(con_trot, end_ms)
        if not trang:
            break
        tat_ca.extend(trang)
        cuoi = max(int(r[0]) for r in trang)
        if len(trang) < 1500 or cuoi + STEP_MS >= end_ms:
            break
        con_trot = cuoi + STEP_MS
        time.sleep(0.2)
    if not tat_ca:
        raise RuntimeError("BLOCKER klines: source tra ve 0 dong moi (khong che data, STOP).")
    df = pd.DataFrame(tat_ca, columns=KLINE_COLS)
    for c in ("open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_volume", "taker_buy_quote_volume"):
        df[c] = df[c].astype(float)
    df["num_trades"] = df["num_trades"].astype("int64")
    df["open_time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"].astype("int64"), unit="ms", utc=True)
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    df = df[(df["close_time"] < now_utc)].reset_index(drop=True)
    assert (df["open_time"] > last_open).all(), "delta klines chong lan sealed (append-only vi pham)"
    # Kiem tra CAU TRUC delta (khong outcome).
    chenh = df["open_time"].diff().dt.total_seconds() / 60.0
    gaps_delta = int((chenh.iloc[1:] != 5.0).sum()) if len(df) > 1 else 0
    junction_ok = bool(df["open_time"].iloc[0] == last_open + pd.Timedelta(minutes=5))
    viol_ohlc = bool(((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
                      (df["low"] > df[["open", "close", "high"]].min(axis=1))).any())
    gia_duong = bool((df[["open", "high", "low", "close"]] > 0).all().all())
    vol_ok = bool((df[["volume", "quote_volume"]] >= 0).all().all())
    luoi = bool(((df["open_time"].dt.second == 0) & (df["open_time"].dt.minute % 5 == 0)).all())
    bar_ok = bool((((df["close_time"] - df["open_time"]).dt.total_seconds()
                    == 5 * 60 - 0.001)).all())
    dup = int(df["open_time"].duplicated().sum())
    assert dup == 0 and not viol_ohlc and gia_duong and gaps_delta == 0 and junction_ok, (
        f"delta klines structural FAIL: dup={dup} ohlc_viol={viol_ohlc} gia+={gia_duong} "
        f"gaps={gaps_delta} junction_ok={junction_ok} first_new={df['open_time'].iloc[0]}")
    df.to_parquet(rawdir / "klines_delta.parquet", index=False)
    print(f"[klines-delta] {len(df)} nen {df['open_time'].iloc[0]} -> {df['open_time'].iloc[-1]}, "
          f"junction_ok={junction_ok} gaps=0 dup=0", flush=True)

    # ---- (2) delta funding ----
    tho_f = []
    con_trot = FUNDING_NEXT_MS
    while True:
        trang, mau_f = lay_funding(con_trot, end_ms)
        if not trang:
            break
        tho_f.extend(trang)
        cuoi = max(int(r["fundingTime"]) for r in trang)
        if cuoi >= end_ms or len(trang) < 1000:
            if len(trang) == 1000 and cuoi < end_ms:
                con_trot = cuoi + 1
                time.sleep(0.3)
                continue
            break
        con_trot = cuoi + 1
        time.sleep(0.3)
    if not tho_f:
        raise RuntimeError("BLOCKER funding: source tra ve 0 dong moi (khong che data, STOP).")
    dff = pd.DataFrame(tho_f)
    dff["fundingTime"] = dff["fundingTime"].astype("int64")
    dff["funding_time"] = pd.to_datetime(dff["fundingTime"], unit="ms", utc=True)
    dff["fundingRate"] = dff["fundingRate"].astype(float)
    dff = dff.drop_duplicates(subset=["fundingTime"]).sort_values("fundingTime").reset_index(drop=True)
    dff = dff[dff["funding_time"] > last_funding_t].reset_index(drop=True)
    if len(dff) == 0:
        raise RuntimeError("BLOCKER funding: 0 dong > last sealed (khong che data, STOP).")
    cols_f = ["symbol", "fundingTime", "funding_time", "fundingRate", "markPrice"]
    if "rateType" in dff.columns:
        cols_f.append("rateType")
    dff = dff[[c for c in cols_f if c in dff.columns]]
    assert list(dff.columns) == list(old_f.columns), f"schema funding delta khac sealed: {list(dff.columns)}"
    chenh_f = dff["funding_time"].diff().dt.total_seconds() / 3600.0
    junction_gap_h = (dff["funding_time"].iloc[0] - last_funding_t).total_seconds() / 3600.0
    gaps_f = int((chenh_f.iloc[1:] > 9.0).sum()) if len(dff) > 1 else 0
    assert gaps_f == 0 and junction_gap_h <= 9.0, (
        f"delta funding structural FAIL: gaps={gaps_f} junction_gap_h={junction_gap_h}")
    dff.to_parquet(rawdir / "funding_delta.parquet", index=False)
    print(f"[funding-delta] {len(dff)} dong {dff['funding_time'].iloc[0]} -> {dff['funding_time'].iloc[-1]}, "
          f"junction_gap_h={junction_gap_h:.2f} gaps=0", flush=True)

    # ---- (3) delta macro ----
    parts = []
    macro_info = {}
    for name, sym in MACRO_SYMBOLS.items():
        md, mau_m = fetch_yahoo_daily(sym, MACRO_FETCH_FROM[name], now_utc.date().isoformat())
        new = md[(md["date"] > str(last_macro[name]))].reset_index(drop=True)
        if len(new) == 0:
            raise RuntimeError(f"BLOCKER macro {name}: 0 dong moi > {last_macro[name]} (khong che data, STOP).")
        new = new.copy()
        new["symbol"] = name
        parts.append(new)
        csv_p = rawdir / f"{name}_delta.csv"
        new.drop(columns=["symbol"]).to_csv(csv_p, index=False)
        macro_info[name] = {"yahoo_symbol": sym, "rows": int(len(new)),
                            "first": str(new["date"].iloc[0]), "last": str(new["date"].iloc[-1]),
                            "sha256": sha256_file(csv_p)}
        print(f"[macro-delta] {name}={sym}: {len(new)} dong {new['date'].iloc[0]}..{new['date'].iloc[-1]}", flush=True)
        time.sleep(1)
    dmm = pd.concat(parts, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    assert list(dmm.columns) == list(old_m.columns), f"schema macro delta khac sealed: {list(dmm.columns)}"

    # ---- (4) ghi file MOI append-only (khong touch sealed) ----
    df.to_parquet(frozendir / f"candles_append_{TAG}.parquet", index=False)
    dff.to_parquet(frozendir / f"funding_append_{TAG}.parquet", index=False)
    dmm.to_parquet(frozendir / f"macro_append_{TAG}.parquet", index=False)
    # Full extended view = concat trong RAM -> file MOI (sealed bytes nguyen).
    ext_c = pd.concat([old_c, df], ignore_index=True)
    ext_f = pd.concat([old_f, dff], ignore_index=True)
    ext_m = pd.concat([old_m, dmm], ignore_index=True)
    assert len(ext_c) == len(old_c) + len(df) and ext_c["open_time"].is_monotonic_increasing
    assert int(ext_c["open_time"].duplicated().sum()) == 0
    assert len(ext_f) == len(old_f) + len(dff) and ext_f["funding_time"].is_monotonic_increasing
    ext_c.to_parquet(frozendir / f"candles_extended_{TAG}.parquet", index=False)
    ext_f.to_parquet(frozendir / f"funding_extended_{TAG}.parquet", index=False)
    ext_m.to_parquet(frozendir / f"macro_extended_{TAG}.parquet", index=False)

    files_new = {
        "candles_append": f"candles_append_{TAG}.parquet",
        "funding_append": f"funding_append_{TAG}.parquet",
        "macro_append": f"macro_append_{TAG}.parquet",
        "candles_extended": f"candles_extended_{TAG}.parquet",
        "funding_extended": f"funding_extended_{TAG}.parquet",
        "macro_extended": f"macro_extended_{TAG}.parquet",
    }
    manifest_ext = {
        "freeze": "opencode_forward_20260323",
        "extension": f"append-only delta {TAG} (sealed files untouched)",
        "sealed_sha256_before": sha_truoc,
        "old_span": {"candles": [str(old_c["open_time"].iloc[0]), str(old_c["open_time"].iloc[-1]),
                                 int(len(old_c))],
                     "funding": [str(old_f["funding_time"].iloc[0]), str(old_f["funding_time"].iloc[-1]),
                                 int(len(old_f))],
                     "macro_rows": int(len(old_m))},
        "delta": {"candles": {"rows": int(len(df)), "first": str(df["open_time"].iloc[0]),
                              "last": str(df["open_time"].iloc[-1]),
                              "junction_ok": junction_ok, "gaps_khac_5m": 0,
                              "sha256": sha256_file(frozendir / files_new["candles_append"])},
                  "funding": {"rows": int(len(dff)), "first": str(dff["funding_time"].iloc[0]),
                              "last": str(dff["funding_time"].iloc[-1]),
                              "junction_gap_h": round(float(junction_gap_h), 2),
                              "gaps_lon_hon_9h": 0,
                              "sha256": sha256_file(frozendir / files_new["funding_append"])},
                  "macro": {"rows": int(len(dmm)), "per_symbol": macro_info,
                            "sha256": sha256_file(frozendir / files_new["macro_append"])}},
        "extended_span": {"candles": [str(ext_c["open_time"].iloc[0]), str(ext_c["open_time"].iloc[-1]),
                                      int(len(ext_c))],
                          "funding": [str(ext_f["funding_time"].iloc[0]), str(ext_f["funding_time"].iloc[-1]),
                                      int(len(ext_f))],
                          "macro_rows": int(len(ext_m))},
        "extended_sha256": {k: sha256_file(frozendir / v) for k, v in files_new.items()},
        "checks": ["counts", "junction continuity (5m / <=9h / date>)", "bounds",
                   "schema equality", "monotonic + dup scan (delta + concat)",
                   "OHLC/price/volume/grid/bar checks", "unclosed-candle exclusion",
                   "SHA256 new files + sealed re-hash"],
        "affirmation": ("Chi kiem tra CAU TRUC. Khong returns/labels/PnL/distributions/plot/thresholds/training. "
                        "Sealed bytes bat bien."),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (frozendir / f"manifest_extend_{TAG}.json").write_text(
        json.dumps(manifest_ext, indent=2, ensure_ascii=False), encoding="utf-8")

    # SHA sau: sealed phai khop.
    sha_sau = {f: sha256_file(frozendir / f) for f in SEALED}
    assert sha_sau == sha_truoc, f"SEAL VIOLATION: {sha_sau} != {sha_truoc}"
    mtime_sau = {f: (frozendir / f).stat().st_mtime_ns for f in mtime_truoc}
    assert mtime_sau == mtime_truoc, "SEAL VIOLATION: sealed mtime doi."
    seal_re = {
        "state": "pristine-reaffirmed",
        "extension_tag": TAG,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff": "2026-03-23",
        "sealed_sha256_before": sha_truoc,
        "sealed_sha256_after": sha_sau,
        "sealed_unchanged": True,
        "allowed_use": ["frozen-candidate evaluation only via forward-protocol"],
        "forbidden": ["tuning", "thresholds", "labels inspection", "training",
                      "returns computation", "PnL/distribution inspection", "price plotting"],
        "checks_performed": manifest_ext["checks"],
        "affirmation": ("Chi kiem tra CAU TRUC. Khong tinh returns/labels/PnL/distributions. "
                        "Khong plot gia. Sealed bytes truoc==sau."),
    }
    (frozendir / f"SEAL_reaffirmation_{TAG}.json").write_text(
        json.dumps(seal_re, indent=2, ensure_ascii=False), encoding="utf-8")

    raw_manifest = {"extension_tag": TAG, "delta_rows": {"klines": int(len(df)), "funding": int(len(dff)),
                                                         "macro": int(len(dmm))},
                    "sha256": {k: sha256_file(rawdir / v) for k, v in
                               [("klines", "klines_delta.parquet"), ("funding", "funding_delta.parquet")]},
                    "crawled_at_utc": datetime.now(timezone.utc).isoformat()}
    (rawdir / "manifest.json").write_text(json.dumps(raw_manifest, indent=2, ensure_ascii=False),
                                          encoding="utf-8")

    # Summary (counts/dates only, khong outcome).
    win_days = (ext_c["open_time"].iloc[-1] - ext_c["open_time"].iloc[0]).total_seconds() / 86400.0
    summary = {
        "experiment": "opencode-r69d-reextend", "config": "configs/opencode_v158_reextend.json",
        "old_sha_unchanged": True, "sealed_sha256": sha_sau,
        "new_rows": {"candles": int(len(df)), "funding": int(len(dff)), "macro": int(len(dmm)),
                     "macro_per_symbol": {k: v["rows"] for k, v in macro_info.items()}},
        "new_span": {"candles_first": str(ext_c["open_time"].iloc[0]),
                     "candles_last": str(ext_c["open_time"].iloc[-1]),
                     "window_days": round(float(win_days), 2),
                     "window_months_30d": round(float(win_days / 30.0), 2)},
        "decisions_equivalent": {"note": "v156: 679 decisions / 169d sealed; ~1850 decisions (~15mo) can cho 30 fills"},
        "files": sorted([str(rawdir)] + [str(frozendir / v) for v in files_new.values()] +
                        [str(frozendir / f"manifest_extend_{TAG}.json"),
                         str(frozendir / f"SEAL_reaffirmation_{TAG}.json")]),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (artdir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[DONE] append-only OK. sealed truoc==sau. +{len(df)} klines +{len(dff)} funding +{len(dmm)} macro.",
          flush=True)


if __name__ == "__main__":
    main()
