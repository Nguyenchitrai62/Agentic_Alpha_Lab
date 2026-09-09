"""Crawl nen 1m BTCUSDT (Binance USD-M public klines, khong key) cho audit v31.

Chi crawl cac ngay UTC co trade dang mo (holding-covered: entry_date..exit_date
tu trades CSV normal cua majority_1x) — tiet kiem hon full 2023-2026.
Chi doc public + phan tich local; khong dat lenh live.
Thu muc dich MOI opencode_1m_audit_* (gitignored), khong ghi de du lieu cu.
Manifest ghi: danh sach ngay, so dong, nguon, SHA256, gap.
"""

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
COLS = ["open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "num_trades",
        "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def lay_klines(symbol, start_ms, end_ms, thu_lai=6):
    loi = None
    for lan in range(thu_lai):
        try:
            tham_so = {"symbol": symbol, "interval": INTERVAL,
                       "startTime": int(start_ms), "endTime": int(end_ms),
                       "limit": 1500}
            url = API + "?" + urllib.parse.urlencode(tham_so)
            yeu_cau = urllib.request.Request(
                url, headers={"User-Agent": "AgenticAlphaLab-N1M/1.0"})
            with urllib.request.urlopen(yeu_cau, timeout=30) as tra_loi:
                return json.loads(tra_loi.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - mang public, thu lai
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"Khong lay duoc klines startTime={start_ms}: {loi}")


def sha256_file(duong_dan: Path) -> str:
    ham = hashlib.sha256()
    with open(duong_dan, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            ham.update(khoi)
    return ham.hexdigest()


if __name__ == "__main__":
    import torch  # noqa: F401 - thu tu import: torch truoc pandas tren host nay
    import pandas as pd

    p = argparse.ArgumentParser(
        description="Crawl nen 1m BTCUSDT cho cac ngay co trade (public, khong key).")
    p.add_argument("--config", type=Path,
                   default=Path("configs/opencode_v31_1maudit.json"))
    p.add_argument("--outdir", type=Path, default=None,
                   help="Mac dinh data/raw/opencode_1m_audit_YYYYMMDD (thu muc MOI).")
    a = p.parse_args()

    goc = Path(__file__).resolve().parents[1]
    cfg = json.loads((goc / a.config).read_text(encoding="utf-8"))
    trades = pd.read_csv(goc / cfg["base"]["trades_normal"])
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)

    ngay = set()
    for t in trades.itertuples():
        for d in pd.date_range(t.entry_time.floor("D"),
                               t.exit_time.floor("D"), freq="D"):
            ngay.add(d.date().isoformat())
    ngay = sorted(ngay)
    print(f"[plan] {len(trades)} trades -> {len(ngay)} ngay holding-covered "
          f"{ngay[0]}..{ngay[-1]}", flush=True)

    if a.outdir is None:
        hom_nay = datetime.now(timezone.utc).strftime("%Y%m%d")
        thu_muc = goc / "data" / "raw" / f"opencode_1m_audit_{hom_nay}"
    else:
        thu_muc = a.outdir if a.outdir.is_absolute() else goc / a.outdir
    if thu_muc.exists():
        raise FileExistsError(
            f"Thu muc {thu_muc} da ton tai: chon thu muc moi, khong ghi de.")
    thu_muc.mkdir(parents=True)

    tom_tat = {"nguon_api": API, "symbol": SYMBOL, "interval": INTERVAL,
               "ghi_chu_nhan_qua": "Du lieu qua khu (causal). Nhan exploratory.",
               "so_ngay_yeu_cau": len(ngay), "ngay": {}}
    tong_dong = 0
    for i, d in enumerate(ngay):
        bat_dau = pd.Timestamp(d, tz="UTC")
        start_ms = int(bat_dau.timestamp() * 1000)
        end_ms = start_ms + 86400 * 1000 - 1
        tho = lay_klines(SYMBOL, start_ms, end_ms)
        df = pd.DataFrame(tho, columns=COLS)
        for c in ["open", "high", "low", "close", "volume",
                  "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]:
            df[c] = df[c].astype(float)
        df["num_trades"] = df["num_trades"].astype("int64")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df = df.drop_duplicates(subset=["open_time"]).sort_values(
            "open_time").reset_index(drop=True)
        ten_file = thu_muc / f"klines_{SYMBOL}_1m_{d.replace('-', '')}.parquet"
        df.to_parquet(ten_file, index=False)
        thieu = 1440 - len(df)
        tom_tat["ngay"][d] = {"file": ten_file.name, "so_dong": int(len(df)),
                              "thieu_so_voi_1440": int(thieu),
                              "tu": str(df["open_time"].iloc[0]),
                              "den": str(df["open_time"].iloc[-1]),
                              "sha256": sha256_file(ten_file)}
        tong_dong += len(df)
        if (i + 1) % 25 == 0 or (i + 1) == len(ngay):
            print(f"[crawl] {i + 1}/{len(ngay)} {d}: {len(df)} dong "
                  f"(thieu {thieu})", flush=True)
        time.sleep(0.25)

    tom_tat["tong_dong"] = int(tong_dong)
    tom_tat["so_ngay_da_crawl"] = len(ngay)
    tom_tat["so_ngay_thieu_nen"] = sum(
        1 for v in tom_tat["ngay"].values() if v["thieu_so_voi_1440"] != 0)
    (thu_muc / "manifest.json").write_text(
        json.dumps(tom_tat, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"DA GHI {thu_muc}: {tong_dong} dong / {len(ngay)} ngay")
