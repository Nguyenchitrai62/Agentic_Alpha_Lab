"""D2-DATA BƯỚC 1: crawl macro daily (Stooq thử trước, fallback Yahoo Finance).

Nhiệm vụ R5-D2 (round5 D2-data): SPX (^SPX/SPY), DXY (DX-Y.NYB/UUP), Vàng (GLD/GC)
giai đoạn 2022-01-01 -> nay, phục vụ regime-conditional probe v24 (exploratory).

Kết quả thực tế (ghi rõ nguồn):
  - Stooq free CSV (https://stooq.com/q/d/l/?s=spy.us&...) BỊ CHẶN trên host này:
    HTTP 404 không header UA; có UA thì trả về trang JS-challenge
    ("This site requires JavaScript to verify your browser") -> không lấy được CSV.
  - Fallback: Yahoo Finance Chart API v8 (free, không key):
    https://query1.finance.yahoo.com/v8/finance/chart/<SYM>?period1=..&period2=..&interval=1d
    Symbols: SPY (proxy ^SPX, ETF thanh khoản), DX-Y.NYB (DXY index),
             UUP (fallback dollar), GLD (vàng ETF), GC=F (vàng future fallback),
             ^GSPC (SPX index, tham khảo).
  - Tất cả đều là dữ liệu OHLC daily quá khứ, public, chỉ dùng cho backtest local.

Causal: file raw là daily close theo ngày giao dịch; bước đặc trưng (v24) join
causal decision ngày T <- macro đóng cửa ngày T-1 trở về trước (strictly past-only).

Output: data/raw/opencode_macro_yahoo_20220101_<YYYYMMDD>/
  spy.csv, dxy.csv (DX-Y.NYB), uup.csv, gld.csv, gcf.csv (GC=F), spx.csv (^GSPC)
  + manifest.json (nguồn, URL mẫu, khoảng ngày, số dòng, sha256, ghi chú Stooq).
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

SYMBOLS = {
    "spy": "SPY",        # proxy ^SPX
    "dxy": "DX-Y.NYB",   # DXY index
    "uup": "UUP",        # fallback dollar
    "gld": "GLD",        # vàng ETF
    "gcf": "GC=F",       # vàng future fallback
    "spx": "^GSPC",      # SPX index tham khảo
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_daily(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    # Yahoo dùng epoch seconds (UTC). end là exclusive -> cộng 1 ngày để bao phủ "nay".
    p1 = int(dt.datetime(start.year, start.month, start.day, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(end.year, end.month, end.day, tzinfo=dt.timezone.utc).timestamp()) + 86400
    last_err = None
    for host in HOSTS:
        url = (f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
               f"?period1={p1}&period2={p2}&interval=1d&events=div%7Csplit")
        try:
            req = urllib.request.Request(url, headers=UA)
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
            df = pd.DataFrame(rows).dropna(subset=["close"]).reset_index(drop=True)
            if len(df) == 0:
                last_err = f"{host}: 0 rows after dropna"
                continue
            return df
        except Exception as e:  # noqa: BLE001 - thử host tiếp theo
            last_err = f"{host}: {e}"
            time.sleep(2)
    raise RuntimeError(f"fetch {symbol} failed: {last_err}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    if a.outdir.exists():
        raise FileExistsError("Không ghi đè thư mục cũ; hãy chọn outdir mới")
    start = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)
    a.outdir.mkdir(parents=True)
    manifest = {"source": "Yahoo Finance Chart API v8 (free, no key)",
                "stooq_note": ("Stooq free CSV bị chặn trên host này (HTTP 404 / "
                               "JS-challenge 'requires JavaScript to verify your browser'), "
                               "không lấy được CSV nên dùng Yahoo, ghi rõ nguồn."),
                "symbols": SYMBOLS,
                "url_template": ("https://query1.finance.yahoo.com/v8/finance/chart/"
                                 "<SYM>?period1=<epoch>&period2=<epoch>&interval=1d"),
                "start": start.isoformat(), "end": end.isoformat(),
                "crawled_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "files": {}}
    for name, sym in SYMBOLS.items():
        df = fetch_daily(sym, start, end)
        csv_p = a.outdir / f"{name}.csv"
        df.to_csv(csv_p, index=False)
        try:
            df.to_parquet(a.outdir / f"{name}.parquet", index=False)
        except Exception:
            pass
        manifest["files"][name] = {"yahoo_symbol": sym, "rows": int(len(df)),
                                   "first": str(df["date"].iloc[0]),
                                   "last": str(df["date"].iloc[-1]),
                                   "csv": csv_p.name,
                                   "sha256": sha256_file(csv_p)}
        print(f"WROTE {csv_p} rows={len(df)} {df['date'].iloc[0]}..{df['date'].iloc[-1]}", flush=True)
        time.sleep(1)
    (a.outdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("WROTE " + str(a.outdir / "manifest.json"))
