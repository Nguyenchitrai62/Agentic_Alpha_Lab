"""D-forward (round32): crawl + freeze + SEAL forward window PRISTINE.

Nhiem vu: cua so forward SAU 2026-03-23 (research interval ket thuc) toi now (UTC runtime).
- (1) BTCUSDT 5m klines (Binance public klines, no key) -> data/raw/opencode_forward_5m/
      + validation kieu validate_source (monotonic, gap record, KHONG fill).
- (2) Funding-rate history cung range (tai dung pattern scripts/opencode_crawl_funding.py).
- (3) Macro daily SPY/DXY (tai dung pattern scripts/opencode_crawl_macro.py, Yahoo v8).
- (4) Freeze data/processed/opencode_forward_20260323/:
      candles.parquet + funding.parquet + macro.parquet + manifest.json + SEAL.json.

KY LUAT PRISTINE (TUYET DOI): chi kiem tra CAU TRUC (row counts, gap report,
date bounds, schema). KHONG tinh returns/labels/PnL/distributions. KHONG plot gia.

Chi crawl public + local. Khong dat lenh live. Thu muc MOI, khong ghi de.
Tai dung ghi nhan:
  - klines: pattern scripts/opencode_crawl_1m.py (fapi klines + paginate + manifest/SHA)
  - funding: pattern scripts/opencode_crawl_funding.py (fapi fundingRate + gap >9h)
  - macro: pattern scripts/opencode_crawl_macro.py (Yahoo chart v8, SPY + DX-Y.NYB)
  - freeze/validate: pattern src/agentic_alpha_lab/data/training.py::validate_source
    + src/agentic_alpha_lab/data/binance_usdm.py::validate_klines
    + scripts/extend_btc_history.py (giu raw evidence, ghi validation_error, khong fill)
"""

import argparse
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

UA_KLINES = {"User-Agent": "AgenticAlphaLab-D-Forward/1.0"}
UA_FUNDING = {"User-Agent": "AgenticAlphaLab-D-Forward/1.0"}
UA_YAHOO = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
MACRO_SYMBOLS = {"spy": "SPY", "dxy": "DX-Y.NYB"}

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "num_trades",
              "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


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
            req = urllib.request.Request(url, headers=UA_KLINES)
            with urllib.request.urlopen(req, timeout=60) as rep:
                return json.loads(rep.read().decode("utf-8")), url
        except Exception as exc:  # noqa: BLE001 - public net, thu lai
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"Khong lay duoc klines startTime={start_ms}: {loi}")


def lay_funding(start_ms, end_ms, thu_lai=6):
    loi = None
    for lan in range(thu_lai):
        try:
            qs = {"symbol": SYMBOL, "limit": 1000,
                  "startTime": int(start_ms), "endTime": int(end_ms)}
            url = FUNDING_API + "?" + urllib.parse.urlencode(qs)
            req = urllib.request.Request(url, headers=UA_FUNDING)
            with urllib.request.urlopen(req, timeout=30) as rep:
                return json.loads(rep.read().decode("utf-8")), url
        except Exception as exc:  # noqa: BLE001 - public net, thu lai
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"Khong lay duoc funding startTime={start_ms}: {loi}")


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
        except Exception as e:  # noqa: BLE001 - thu host tiep theo
            last_err = f"{host}: {e}"
            time.sleep(2)
    raise RuntimeError(f"fetch {symbol} failed: {last_err}")


def main():
    import torch  # noqa: F401 - torch truoc pandas (DLL load-order Windows host)
    import pandas as pd

    p = argparse.ArgumentParser(description="Crawl+freeze forward window PRISTINE (public, no key).")
    p.add_argument("--start", default="2026-03-23T00:00:00Z")
    p.add_argument("--end", default=None, help="Mac dinh: now UTC tai runtime.")
    p.add_argument("--rawdir", type=Path, default=Path("data/raw/opencode_forward_5m"))
    p.add_argument("--frozendir", type=Path, default=Path("data/processed/opencode_forward_20260323"))
    a = p.parse_args()

    goc = Path(__file__).resolve().parents[1]
    rawdir = a.rawdir if a.rawdir.is_absolute() else goc / a.rawdir
    frozendir = a.frozendir if a.frozendir.is_absolute() else goc / a.frozendir
    if rawdir.exists():
        raise FileExistsError(f"{rawdir} da ton tai: khong ghi de.")
    if frozendir.exists():
        raise FileExistsError(f"{frozendir} da ton tai: khong ghi de.")

    bat_dau = pd.Timestamp(a.start, tz="UTC")
    assert bat_dau == pd.Timestamp("2026-03-23T00:00:00Z"), "forward start phai > cutoff 2026-03-23"
    ket_thuc = pd.Timestamp(a.end, tz="UTC") if a.end else pd.Timestamp.now(tz="UTC")
    start_ms, end_ms = int(bat_dau.timestamp() * 1000), int(ket_thuc.timestamp() * 1000)
    print(f"[forward] range yeu cau: {bat_dau} -> {ket_thuc} (UTC runtime)", flush=True)

    rawdir.mkdir(parents=True)

    # ---- (1) 5m klines ----
    tat_ca, mau_k = [], None
    con_trot = start_ms
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
    df = pd.DataFrame(tat_ca, columns=KLINE_COLS)
    for c in ("open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_volume", "taker_buy_quote_volume"):
        df[c] = df[c].astype(float)
    df["num_trades"] = df["num_trades"].astype("int64")
    df["open_time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"].astype("int64"), unit="ms", utc=True)
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    # Chi giu forward window + loai nen chua dong (close_time >= now tai runtime).
    now_utc = pd.Timestamp.now(tz="UTC")
    df = df[(df["open_time"] >= bat_dau) & (df["close_time"] < now_utc)].reset_index(drop=True)

    # Kiem tra CAU TRUC kieu validate_klines/validate_source (khong tinh outcome).
    chenh_phut = df["open_time"].diff().dt.total_seconds() / 60.0
    gaps_5m = []
    for i, g in enumerate(chenh_phut.iloc[1:], start=1):
        if g != 5.0:
            gaps_5m.append({"tu": str(df["open_time"].iloc[i - 1]),
                            "den": str(df["open_time"].iloc[i]),
                            "cach_phut": round(float(g), 2),
                            "so_nen_5m_thieu_uoc_tinh": int(round(float(g) / 5.0)) - 1})
    viol_ohlc = bool(((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
                      (df["low"] > df[["open", "close", "high"]].min(axis=1))).any())
    gia_duong = bool((df[["open", "high", "low", "close"]] > 0).all().all())
    vol_hople = bool((df[["volume", "quote_volume"]] >= 0).all().all())
    huu_han = bool(df[["open", "high", "low", "close", "volume", "quote_volume"]].apply(
        lambda s: s.map(lambda x: x is not None and float(x) == float(x)
                        and abs(float(x)) != float("inf"))).all().all())
    luoi_5m = bool(((df["open_time"].dt.second == 0) & (df["open_time"].dt.minute % 5 == 0)).all())
    bar_chuan = bool((((df["close_time"] - df["open_time"]).dt.total_seconds()
                       == 5 * 60 - 0.001)).all())
    dup_open = int(df["open_time"].duplicated().sum())
    ty_le_5m = float((chenh_phut.iloc[1:] == 5.0).mean()) if len(df) > 1 else 1.0
    # validate_source pattern: contiguous 5m. Ghi loi thay vi fill.
    validation_error = None
    if dup_open or viol_ohlc or not gia_duong or gaps_5m:
        validation_error = (f"validate_source-style: duplicates={dup_open}, "
                            f"ohlc_viol={viol_ohlc}, gaps={len(gaps_5m)} (KHONG fill)")
    klines_file = rawdir / "klines_BTCUSDT_5m.parquet"
    df.to_parquet(klines_file, index=False)
    print(f"[klines] {len(df)} nen {df['open_time'].iloc[0]} -> {df['open_time'].iloc[-1]}, "
          f"gap!=5m: {len(gaps_5m)}, dup={dup_open}, ohlc_viol={viol_ohlc}", flush=True)

    # ---- (2) funding ----
    tho_f, mau_f = [], None
    con_trot = start_ms
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
    dff = pd.DataFrame(tho_f)
    dff["fundingTime"] = dff["fundingTime"].astype("int64")
    dff["funding_time"] = pd.to_datetime(dff["fundingTime"], unit="ms", utc=True)
    dff["fundingRate"] = dff["fundingRate"].astype(float)
    dff = dff.drop_duplicates(subset=["fundingTime"]).sort_values("fundingTime").reset_index(drop=True)
    dff = dff[dff["funding_time"] >= bat_dau].reset_index(drop=True)
    cols_f = ["symbol", "fundingTime", "funding_time", "fundingRate", "markPrice"]
    if "rateType" in dff.columns:
        cols_f.append("rateType")
    dff = dff[[c for c in cols_f if c in dff.columns]]
    chenh_f = dff["funding_time"].diff().dt.total_seconds() / 3600.0
    gaps_f = []
    for i, gio in enumerate(chenh_f.iloc[1:], start=1):
        if gio > 9.0:
            gaps_f.append({"tu": str(dff["funding_time"].iloc[i - 1]),
                           "den": str(dff["funding_time"].iloc[i]),
                           "cach_gio": round(float(gio), 2),
                           "so_ky_8h_thieu_uoc_tinh": int(round(float(gio) / 8.0)) - 1})
    ty_le_8h = float((chenh_f.iloc[1:] - 8.0).abs().le(0.05).mean()) if len(dff) > 1 else 1.0
    funding_file = rawdir / "funding_BTCUSDT.parquet"
    dff.to_parquet(funding_file, index=False)
    print(f"[funding] {len(dff)} dong {dff['funding_time'].iloc[0]} -> {dff['funding_time'].iloc[-1]}, "
          f"gap>9h: {len(gaps_f)}", flush=True)

    # ---- (3) macro SPY/DXY ----
    macro_info = {}
    for name, sym in MACRO_SYMBOLS.items():
        md, mau_m = fetch_yahoo_daily(sym, bat_dau.date().isoformat(), ket_thuc.date().isoformat())
        md = md[(md["date"] >= bat_dau.date().isoformat())].reset_index(drop=True)
        csv_p = rawdir / f"{name}.csv"
        pq_p = rawdir / f"{name}.parquet"
        md.to_csv(csv_p, index=False)
        md.to_parquet(pq_p, index=False)
        macro_info[name] = {"yahoo_symbol": sym, "rows": int(len(md)),
                            "first": str(md["date"].iloc[0]), "last": str(md["date"].iloc[-1]),
                            "csv": csv_p.name, "parquet": pq_p.name,
                            "sha256": sha256_file(csv_p),
                            "nguon_mau": mau_m}
        print(f"[macro] {name}={sym}: {len(md)} dong {md['date'].iloc[0]}..{md['date'].iloc[-1]}", flush=True)
        time.sleep(1)

    raw_manifest = {
        "nhiem_vu": "D-forward round32: crawl forward window PRISTINE",
        "range_yeu_cau": [str(bat_dau), str(ket_thuc)],
        "klines": {"nguon_api": KLINES_API, "symbol": SYMBOL, "interval": KLINE_INTERVAL,
                   "file": klines_file.name, "so_dong": int(len(df)),
                   "tu": str(df["open_time"].iloc[0]), "den": str(df["open_time"].iloc[-1]),
                   "last_close_time": str(df["close_time"].iloc[-1]),
                   "nguon_mau": (mau_k.split("startTime")[0] + "startTime=...") if mau_k else None,
                   "sha256": sha256_file(klines_file),
                   "trung_open_time": dup_open, "ty_le_5m_chuan": ty_le_5m,
                   "so_gap_khac_5m": len(gaps_5m), "gaps": gaps_5m[:50],
                   "ohlc_viol": viol_ohlc, "gia_duong": gia_duong,
                   "volume_hop_le": vol_hople, "huu_han": huu_han,
                   "luoi_5m_chuan": luoi_5m, "bar_5m_chuan": bar_chuan,
                   "validation_error": validation_error,
                   "tai_dung": "pattern scripts/opencode_crawl_1m.py + validate src/.../training.py::validate_source"},
        "funding": {"nguon_api": FUNDING_API, "symbol": SYMBOL, "file": funding_file.name,
                    "so_dong": int(len(dff)), "tu": str(dff["funding_time"].iloc[0]),
                    "den": str(dff["funding_time"].iloc[-1]),
                    "nguon_mau": (mau_f.split("startTime")[0] + "startTime=...") if mau_f else None,
                    "sha256": sha256_file(funding_file),
                    "so_gap_lon_hon_9h": len(gaps_f), "gaps": gaps_f[:50],
                    "ty_le_8h_chuan": ty_le_8h,
                    "tai_dung": "pattern scripts/opencode_crawl_funding.py"},
        "macro": {"nguon": "Yahoo Finance Chart API v8 (free, no key)",
                  "tai_dung": "pattern scripts/opencode_crawl_macro.py",
                  "files": macro_info},
        "ghi_chu_nhan_qua": "Du lieu tho forward-window; join causal o buoc forward-protocol sau nay.",
        "crawled_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (rawdir / "manifest.json").write_text(json.dumps(raw_manifest, indent=2, ensure_ascii=False),
                                          encoding="utf-8")

    # ---- (4) Freeze ----
    frozendir.mkdir(parents=True)
    candles_f = frozendir / "candles.parquet"
    funding_f = frozendir / "funding.parquet"
    macro_f = frozendir / "macro.parquet"
    df.to_parquet(candles_f, index=False)
    dff.to_parquet(funding_f, index=False)
    parts = []
    for name in MACRO_SYMBOLS:
        m = pd.read_parquet(rawdir / f"{name}.parquet")
        m = m.copy()
        m["symbol"] = name
        parts.append(m)
    pd.concat(parts, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True).to_parquet(
        macro_f, index=False)

    manifest = {
        "freeze": "opencode_forward_20260323",
        "range_yeu_cau": [str(bat_dau), str(ket_thuc)],
        "candles": {"file": "candles.parquet", "rows": int(len(df)),
                    "first_open_time": str(df["open_time"].iloc[0]),
                    "last_open_time": str(df["open_time"].iloc[-1]),
                    "last_close_time": str(df["close_time"].iloc[-1]),
                    "gaps_khac_5m": len(gaps_5m), "sha256": sha256_file(candles_f),
                    "schema": list(map(str, df.columns))},
        "funding": {"file": "funding.parquet", "rows": int(len(dff)),
                    "first": str(dff["funding_time"].iloc[0]),
                    "last": str(dff["funding_time"].iloc[-1]),
                    "gaps_lon_hon_9h": len(gaps_f), "sha256": sha256_file(funding_f),
                    "schema": list(map(str, dff.columns))},
        "macro": {"file": "macro.parquet",
                  "rows": int(sum(v["rows"] for v in macro_info.values())),
                  "per_symbol": {k: {"rows": v["rows"], "first": v["first"], "last": v["last"]}
                                 for k, v in macro_info.items()},
                  "sha256": sha256_file(macro_f)},
        "source": {"klines": KLINES_API, "funding": FUNDING_API,
                   "macro": "Yahoo Finance Chart API v8",
                   "raw_dir": "data/raw/opencode_forward_5m",
                   "tai_dung_scripts": ["scripts/opencode_crawl_1m.py",
                                        "scripts/opencode_crawl_funding.py",
                                        "scripts/opencode_crawl_macro.py"]},
        "validation_error_klines": validation_error,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (frozendir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    seal = {
        "state": "pristine",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff": "2026-03-23",
        "allowed_use": ["frozen-candidate evaluation only via forward-protocol"],
        "forbidden": ["tuning", "thresholds", "labels inspection", "training",
                      "returns computation", "PnL/distribution inspection", "price plotting"],
        "checks_performed": [
            "row counts per source (klines/funding/macro)",
            "gap report per source (5m grid / 8h funding / daily macro bounds)",
            "date bounds first/last per source within requested range",
            "schema check (required columns present)",
            "monotonic open_time, duplicate scan",
            "OHLC bounds + positive-price + non-negative-volume scan",
            "UTC 5m grid alignment + bar-length check",
            "unclosed-candle exclusion (close_time < now UTC)",
            "SHA256 per frozen file",
        ],
        "affirmation": ("Chi kiem tra CAU TRUC. Khong tinh returns/labels/PnL/"
                        "distributions. Khong plot gia."),
    }
    (frozendir / "SEAL.json").write_text(json.dumps(seal, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"DA GHI {rawdir} va FREEZE {frozendir} (SEAL: pristine)", flush=True)


if __name__ == "__main__":
    main()
