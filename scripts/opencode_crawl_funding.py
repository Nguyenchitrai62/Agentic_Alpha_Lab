"""Crawl lich su funding rate Binance USD-M (public API fapi, khong can key).

Ghi chu tieng Viet cho user:
- Chi backtest local, khong dat lenh live.
- Du lieu funding duoc cong bo moi 8h (00/08/16 UTC). Script nay chi luu du lieu tho.
- Viec join vao decision clock (as-of: moi decision chi dung funding da cong bo
  TRUOC signal_time) nam o script probe opencode_r5d1_fundingfeat.py, khong phai o day.
- Nhan exploratory: du lieu 2023-2026 da mo, khong phai kiem dinh doc lap.
- Thu muc dich moi opencode_funding_* (gitignored), khong ghi de du lieu cu.
- Manifest ghi: range, so dong, nguon, SHA256, khoang trong (gap).
"""

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


API = "https://fapi.binance.com/fapi/v1/fundingRate"


def lay_trang(symbol, start_ms=None, end_ms=None, limit=1000, thu_lai=5):
    """Lay 1 trang fundingRate cho symbol (phan trang theo startTime)."""
    loi = None
    for lan in range(thu_lai):
        try:
            tham_so = {"symbol": symbol, "limit": limit}
            if start_ms is not None:
                tham_so["startTime"] = int(start_ms)
            if end_ms is not None:
                tham_so["endTime"] = int(end_ms)
            url = API + "?" + urllib.parse.urlencode(tham_so)
            yeu_cau = urllib.request.Request(url, headers={"User-Agent": "AgenticAlphaLab-D1/1.0"})
            with urllib.request.urlopen(yeu_cau, timeout=30) as tra_loi:
                return json.loads(tra_loi.read().decode("utf-8")), url
        except Exception as exc:  # noqa: BLE001 - mang public, thu lai
            loi = exc
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"Khong lay duoc {symbol} startTime={start_ms}: {loi}")


def crawl_symbol(symbol, start_ms, end_ms):
    """Crawl toan bo lich su 1 symbol bang cach doi startTime theo fundingTime cuoi."""
    tat_ca = []
    con_trot = start_ms
    nguon_mau = None
    while True:
        trang, nguon_mau = lay_trang(symbol, start_ms=con_trot, end_ms=end_ms)
        if not trang:
            break
        tat_ca.extend(trang)
        cuoi = max(int(r["fundingTime"]) for r in trang)
        if cuoi >= end_ms or len(trang) < 1000:
            # Trang cuoi (< 1000 dong) hoac da cham tran end_ms.
            # Van kiem tra 1 trang nua de chac khong sot (neu vua tron 1000 dong).
            if len(trang) == 1000 and cuoi < end_ms:
                con_trot = cuoi + 1
                time.sleep(0.3)
                continue
            break
        con_trot = cuoi + 1
        time.sleep(0.3)
    return tat_ca, (nguon_mau or API + "?symbol=" + symbol)


def sha256_file(duong_dan: Path) -> str:
    ham = hashlib.sha256()
    with open(duong_dan, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            ham.update(khoi)
    return ham.hexdigest()


def phan_tich_gap(df):
    """Tim khoang trong > 9h (lich 8h chuan + dung sai). Tra ve danh sach gap."""
    if len(df) < 2:
        return []
    chenh = df["funding_time"].diff().dt.total_seconds() / 3600.0
    gaps = []
    for i, gio in enumerate(chenh.iloc[1:], start=1):
        if gio > 9.0:
            gaps.append(
                {
                    "tu": str(df["funding_time"].iloc[i - 1]),
                    "den": str(df["funding_time"].iloc[i]),
                    "cach_gio": round(float(gio), 2),
                    "so_ky_8h_thieu_uoc_tinh": int(round(float(gio) / 8.0)) - 1,
                }
            )
    return gaps


if __name__ == "__main__":
    import torch  # noqa: F401 - thu tu import: torch truoc pandas tren host nay
    import pandas as pd

    p = argparse.ArgumentParser(description="Crawl funding rate Binance fapi (public, khong key).")
    p.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    p.add_argument("--start", default="2022-01-01T00:00:00Z")
    p.add_argument("--end", default=None, help="Mac dinh: thoi diem hien tai UTC.")
    p.add_argument("--outdir", type=Path, default=None,
                   help="Mac dinh data/raw/opencode_funding_YYYYMMDD (thu muc MOI).")
    a = p.parse_args()

    goc = Path(__file__).resolve().parents[1]
    bat_dau = pd.Timestamp(a.start, tz="UTC")
    ket_thuc = pd.Timestamp(a.end, tz="UTC") if a.end else pd.Timestamp.now(tz="UTC")
    start_ms = int(bat_dau.timestamp() * 1000)
    end_ms = int(ket_thuc.timestamp() * 1000)

    if a.outdir is None:
        hom_nay = datetime.now(timezone.utc).strftime("%Y%m%d")
        thu_muc = goc / "data" / "raw" / f"opencode_funding_{hom_nay}"
    else:
        thu_muc = a.outdir if a.outdir.is_absolute() else goc / a.outdir
    if thu_muc.exists():
        raise FileExistsError(f"Thu muc {thu_muc} da ton tai: chon thu muc moi, khong ghi de.")
    thu_muc.mkdir(parents=True)

    tom_tat = {"nguon_api": API, "bat_dau_yeu_cau": str(bat_dau), "ket_thuc_yeu_cau": str(ket_thuc),
               "ghi_chu_nhan_qua": "Du lieu qua khu (causal o buoc join). Nhan exploratory.",
               "symbols": {}}
    for symbol in a.symbols:
        print(f"[crawl] {symbol} tu {bat_dau} den {ket_thuc} ...", flush=True)
        tho, nguon_mau = crawl_symbol(symbol, start_ms, end_ms)
        df = pd.DataFrame(tho)
        if len(df) == 0:
            raise SystemExit(f"API tra ve rong cho {symbol}: dung lai de kiem tra.")
        df["fundingTime"] = df["fundingTime"].astype("int64")
        df["funding_time"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
        df["fundingRate"] = df["fundingRate"].astype(float)
        df = df.drop_duplicates(subset=["fundingTime"]).sort_values("fundingTime").reset_index(drop=True)
        cols = ["symbol", "fundingTime", "funding_time", "fundingRate", "markPrice"]
        if "rateType" in df.columns:
            cols.append("rateType")
        df = df[[c for c in cols if c in df.columns]]
        ten_file = thu_muc / f"funding_{symbol}.parquet"
        df.to_parquet(ten_file, index=False)
        gaps = phan_tich_gap(df)
        tom_tat["symbols"][symbol] = {
            "file": ten_file.name,
            "so_dong": int(len(df)),
            "tu": str(df["funding_time"].iloc[0]),
            "den": str(df["funding_time"].iloc[-1]),
            "nguon_mau": nguon_mau.split("startTime")[0] + "startTime=...&limit=1000",
            "sha256": sha256_file(ten_file),
            "so_gap_lon_hon_9h": len(gaps),
            "gaps": gaps[:20],
            "ty_le_8h_chuan": float(((df["funding_time"].diff().dt.total_seconds() / 3600.0).iloc[1:] - 8.0).abs().le(0.05).mean()),
        }
        print(f"[xong] {symbol}: {len(df)} dong {df['funding_time'].iloc[0]} -> {df['funding_time'].iloc[-1]}, "
              f"gap>9h: {len(gaps)}", flush=True)

    (thu_muc / "manifest.json").write_text(json.dumps(tom_tat, indent=2, ensure_ascii=False))
    print(f"DA GHI {thu_muc}")
