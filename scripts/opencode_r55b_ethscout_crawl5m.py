"""R55b ETH scout (1/3): crawl ETHUSDT 5m klines Binance public (KHONG key).

- Muc dich: inventory coverage 5m cho ETH-book (hien MISSING; chi co BTC 5m).
  Baseline diagnostic trong scout nay KHONG can 5m (chi can 6h closes);
  crawl nay la coverage inventory cho quyet dinh full-training tuong lai.
- API: https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=5m
  (fallback data-api.binance.vision). Chi GET public, khong dat lenh live.
- Range: 2022-01-01 -> 2026-03-23 UTC (mirror BTC source first_open 2022-01-01
  + dev cutoff 2026-03-23). Ghi thu muc MOI data/raw/opencode_eth_5m_*/
  (khong ghi de) + manifest.json (range/rows/gaps/SHA).
"""
import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOSTS = ["https://api.binance.com", "https://data-api.binance.vision"]
SYMBOL = "ETHUSDT"
INTERVAL = "5m"
STEP_MS = 5 * 60 * 1000


def lay_trang(symbol, interval, start_ms, end_ms, limit=1000, thu_lai=6):
    loi = None
    for lan in range(thu_lai):
        for host in HOSTS:
            try:
                qs = {"symbol": symbol, "interval": interval, "limit": limit,
                      "startTime": int(start_ms)}
                if end_ms is not None:
                    qs["endTime"] = int(end_ms)
                url = host + "/api/v3/klines?" + urllib.parse.urlencode(qs)
                req = urllib.request.Request(url, headers={"User-Agent": "AgenticAlphaLab-ETHScout5m/1.0"})
                with urllib.request.urlopen(req, timeout=30) as rep:
                    return json.loads(rep.read().decode("utf-8")), url
            except Exception as exc:  # noqa: BLE001 - public net, thu host khac
                loi = exc
                continue
        time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"Khong lay duoc {symbol} {interval} startTime={start_ms}: {loi}")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


if __name__ == "__main__":
    import torch  # noqa: F401 - torch truoc pandas (DLL load-order Windows host)
    import pandas as pd

    p = argparse.ArgumentParser(description="Crawl ETHUSDT 5m klines public (no key).")
    p.add_argument("--start", default="2022-01-01T00:00:00Z")
    p.add_argument("--end", default="2026-03-23T00:00:00Z")
    p.add_argument("--outdir", type=Path, default=None)
    a = p.parse_args()

    root = Path(__file__).resolve().parents[1]
    bat_dau = pd.Timestamp(a.start, tz="UTC")
    ket_thuc = pd.Timestamp(a.end, tz="UTC")
    start_ms, end_ms = int(bat_dau.timestamp() * 1000), int(ket_thuc.timestamp() * 1000)

    if a.outdir is None:
        hom_nay = datetime.now(timezone.utc).strftime("%Y%m%d")
        thu_muc = root / "data" / "raw" / f"opencode_eth_5m_{hom_nay}"
    else:
        thu_muc = a.outdir if a.outdir.is_absolute() else root / a.outdir
    if thu_muc.exists():
        raise FileExistsError(f"{thu_muc} da ton tai: chon thu muc moi, khong ghi de.")
    thu_muc.mkdir(parents=True)

    tat_ca, mau = [], None
    con_trot = start_ms
    trang_i = 0
    while True:
        trang, mau = lay_trang(SYMBOL, INTERVAL, con_trot, end_ms)
        if not trang:
            break
        tat_ca.extend(trang)
        trang_i += 1
        if trang_i % 50 == 0:
            print(f"... {len(tat_ca)} bars (page {trang_i})", flush=True)
        cuoi = max(int(r[0]) for r in trang)
        if len(trang) < 1000 or cuoi + STEP_MS >= end_ms:
            break
        con_trot = cuoi + STEP_MS
        time.sleep(0.3)

    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "num_trades",
            "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
    df = pd.DataFrame(tat_ca, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"].astype("int64"), unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_volume", "taker_buy_quote_volume"):
        df[c] = df[c].astype(float)
    df["num_trades"] = df["num_trades"].astype("int64")
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    df = df[(df["open_time"] >= bat_dau) & (df["open_time"] < ket_thuc)].reset_index(drop=True)

    # Verify clock 5m chuan (minute % 5 == 0, giay 0); bar 5m-1ms.
    # Ghi nhan anomaly thay vi abort (scout coverage inventory trung thuc).
    assert bool(((df["open_time"].dt.minute % 5 == 0) & (df["open_time"].dt.second == 0)).all()), "lech clock 5m!"
    khoang = (df["close_time"] - df["open_time"]).dt.total_seconds()
    la_bar = (khoang == 5 * 60 - 0.001)
    so_la = int((~la_bar).sum())
    la_mau = []
    if so_la:
        mau_la = df.loc[~la_bar, ["open_time", "close_time"]].head(10)
        for r in mau_la.itertuples():
            la_mau.append({"open_time": str(r.open_time), "close_time": str(r.close_time)})
        print(f"[canh bao] {so_la} bars khong chuan 5m-1ms (mau: {la_mau})", flush=True)

    ten_file = thu_muc / "eth_ETHUSDT_5m.parquet"
    df.to_parquet(ten_file, index=False)

    chenh = df["open_time"].diff().dt.total_seconds() / 60.0
    gaps = []
    for i, g in enumerate(chenh.iloc[1:], start=1):
        if g != 5.0:
            gaps.append({"tu": str(df["open_time"].iloc[i - 1]), "den": str(df["open_time"].iloc[i]),
                         "cach_phut": round(float(g), 2),
                         "so_bar_5m_thieu_uoc_tinh": int(round(float(g) / 5.0)) - 1})
    manifest = {
        "symbol": SYMBOL, "interval": INTERVAL,
        "range_yeu_cau": [str(bat_dau), str(ket_thuc)],
        "range_thuc_te": [str(df["open_time"].iloc[0]), str(df["open_time"].iloc[-1])],
        "so_dong": int(len(df)),
        "clock": "5m UTC (verified minute%5==0)",
        "ty_le_5m_chuan": float((chenh.iloc[1:] == 5.0).mean()),
        "bars_khong_chuan_5m_1ms": so_la,
        "mau_bars_khong_chuan": la_mau,
        "so_gap": len(gaps), "gaps": gaps[:20],
        "file": ten_file.name, "sha256": sha256_file(ten_file),
        "nguon_mau": (mau.split("startTime")[0] + "startTime=...") if mau else None,
        "ghi_chu": "Coverage inventory cho ETH-book scout (baseline diagnostic khong dung 5m). Nhan exploratory.",
    }
    (thu_muc / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[xong] {len(df)} bars {df['open_time'].iloc[0]} -> {df['open_time'].iloc[-1]}, gap: {len(gaps)}", flush=True)
    print(f"DA GHI {thu_muc}", flush=True)
