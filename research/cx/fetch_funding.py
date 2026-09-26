"""cx W18: cross-exchange funding history for majors (BTC/ETH/SOL/BNB/XRP USDT-margined linear perps).

Per OPENCODE_CX_W18_FUNDING.md:
- Bybit full funding history via /v5/market/funding/history (paginate backwards by endTime).
- OKX funding history via /api/v5/public/funding-rate-history (paginate via after; only ~3 months may exist; range recorded).
- Binance already local: data/raw/xs_universe_20260924/{SYM}_funding.parquet (copied normalized into cx folder).
- One parquet per exchange/symbol in data/raw/cx_funding_20260925/ + manifest.json with ranges and SHA-256.
- Sleep 0.2 s between calls; retry with backoff; never writes outside the workspace.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BYBIT_URL = "https://api.bybit.com/v5/market/funding/history"
OKX_URL = "https://www.okx.com/api/v5/public/funding-rate-history"

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "cx_funding_20260925"
BINANCE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "xs_universe_20260924"

SYMBOLS = {
    "BTC": {"bybit": "BTCUSDT", "okx": "BTC-USDT-SWAP", "binance": "BTCUSDT"},
    "ETH": {"bybit": "ETHUSDT", "okx": "ETH-USDT-SWAP", "binance": "ETHUSDT"},
    "SOL": {"bybit": "SOLUSDT", "okx": "SOL-USDT-SWAP", "binance": "SOLUSDT"},
    "BNB": {"bybit": "BNBUSDT", "okx": "BNB-USDT-SWAP", "binance": "BNBUSDT"},
    "XRP": {"bybit": "XRPUSDT", "okx": "XRP-USDT-SWAP", "binance": "XRPUSDT"},
}

PAGE_SLEEP = 0.2


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
            try:
                wait = float(retry_after) if retry_after else backoff
            except ValueError:
                wait = backoff
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


def fetch_bybit_full(symbol: str, session: requests.Session) -> pd.DataFrame:
    rows: list[dict] = []
    cursor = int(time.time() * 1000)
    seen_min: int | None = None
    for _page in range(600):
        params = {"category": "linear", "symbol": symbol, "limit": 200, "endTime": cursor}
        resp = get_with_retry(session, BYBIT_URL, params=params)
        body = resp.json()
        if body.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={body.get('retCode')} msg={body.get('retMsg')}")
        batch = body.get("result", {}).get("list", [])
        if not batch:
            break
        rows.extend(batch)
        ts = [int(r["fundingRateTimestamp"]) for r in batch]
        page_min, page_max = min(ts), max(ts)
        if seen_min is not None and page_min >= seen_min:
            break
        seen_min = page_min if seen_min is None else min(seen_min, page_min)
        if len(batch) < 200:
            break
        nxt = page_min - 1
        if nxt >= cursor:
            raise RuntimeError("bybit pagination did not advance")
        cursor = nxt
        time.sleep(PAGE_SLEEP)
    if not rows:
        return pd.DataFrame(columns=["exchange", "base", "exchange_symbol", "fundingTime", "fundingRate"])
    df = pd.DataFrame(rows)
    df["fundingTime"] = pd.to_datetime(df["fundingRateTimestamp"].astype("int64"), unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df.dropna(subset=["fundingTime", "fundingRate"])
    df = df.drop_duplicates(subset=["fundingTime"], keep="last").sort_values("fundingTime").reset_index(drop=True)
    return df[["fundingTime", "fundingRate"]]


def fetch_okx_full(inst_id: str, session: requests.Session) -> pd.DataFrame:
    rows: list[dict] = []
    after: str | None = None
    seen_min: int | None = None
    for _page in range(600):
        params: dict = {"instId": inst_id, "limit": "100"}
        if after is not None:
            params["after"] = after
        resp = get_with_retry(session, OKX_URL, params=params)
        body = resp.json()
        if body.get("code") != "0":
            raise RuntimeError(f"okx code={body.get('code')} msg={body.get('msg')}")
        batch = body.get("data", [])
        if not batch:
            break
        rows.extend(batch)
        ts = [int(r["fundingTime"]) for r in batch]
        page_min = min(ts)
        if seen_min is not None and page_min >= seen_min:
            break
        seen_min = page_min if seen_min is None else min(seen_min, page_min)
        if len(batch) < 100:
            break
        after = str(page_min)
        time.sleep(PAGE_SLEEP)
    if not rows:
        return pd.DataFrame(columns=["fundingTime", "fundingRate"])
    df = pd.DataFrame(rows)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df.dropna(subset=["fundingTime", "fundingRate"])
    df = df.drop_duplicates(subset=["fundingTime"], keep="last").sort_values("fundingTime").reset_index(drop=True)
    return df[["fundingTime", "fundingRate"]]


def load_binance_normalized(binance_sym: str) -> pd.DataFrame:
    src = BINANCE_DIR / f"{binance_sym}_funding.parquet"
    df = pd.read_parquet(src)
    out = pd.DataFrame({
        "fundingTime": pd.to_datetime(df["fundingTime"], utc=True),
        "fundingRate": pd.to_numeric(df["fundingRate"], errors="coerce"),
    }).dropna().drop_duplicates(subset=["fundingTime"], keep="last")
    return out.sort_values("fundingTime").reset_index(drop=True)


def main() -> None:
    assert OUT_DIR.resolve().is_relative_to(Path(__file__).resolve().parents[2]), "must stay in workspace"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest_files: dict[str, dict] = {}
    okx_notes: dict[str, str] = {}

    for base, syms in SYMBOLS.items():
        # Bybit (resume: reuse existing non-empty file)
        bybit_path = OUT_DIR / f"bybit_{base}.parquet"
        if not (bybit_path.exists() and bybit_path.stat().st_size > 0):
            df = fetch_bybit_full(syms["bybit"], session)
            df.insert(0, "exchange_symbol", syms["bybit"])
            df.insert(0, "base", base)
            df.insert(0, "exchange", "bybit")
            df.to_parquet(bybit_path, index=False)
            time.sleep(PAGE_SLEEP)
        bdf = pd.read_parquet(bybit_path)
        manifest_files[bybit_path.name] = {
            "exchange": "bybit", "base": base, "exchange_symbol": syms["bybit"],
            "rows": int(len(bdf)),
            "first": pd.to_datetime(bdf["fundingTime"]).min().isoformat() if len(bdf) else None,
            "last": pd.to_datetime(bdf["fundingTime"]).max().isoformat() if len(bdf) else None,
            "sha256": sha256_of(bybit_path),
        }

        # OKX (resume: reuse existing non-empty file)
        okx_path = OUT_DIR / f"okx_{base}.parquet"
        if not (okx_path.exists() and okx_path.stat().st_size > 0):
            df = fetch_okx_full(syms["okx"], session)
            df.insert(0, "exchange_symbol", syms["okx"])
            df.insert(0, "base", base)
            df.insert(0, "exchange", "okx")
            df.to_parquet(okx_path, index=False)
            time.sleep(PAGE_SLEEP)
        odf = pd.read_parquet(okx_path)
        if len(odf):
            okx_notes[base] = (
                f"OKX returned {len(odf)} settlements "
                f"{pd.to_datetime(odf['fundingTime']).min().isoformat()}.."
                f"{pd.to_datetime(odf['fundingTime']).max().isoformat()} "
                "(OKX history is truncated to the recent window; range recorded as returned)."
            )
        else:
            okx_notes[base] = "OKX returned 0 rows."
        manifest_files[okx_path.name] = {
            "exchange": "okx", "base": base, "exchange_symbol": syms["okx"],
            "rows": int(len(odf)),
            "first": pd.to_datetime(odf["fundingTime"]).min().isoformat() if len(odf) else None,
            "last": pd.to_datetime(odf["fundingTime"]).max().isoformat() if len(odf) else None,
            "sha256": sha256_of(okx_path),
            "note": okx_notes[base],
        }

        # Binance normalized copy (source of truth stays in xs_universe_20260924)
        bin_path = OUT_DIR / f"binance_{base}.parquet"
        if not (bin_path.exists() and bin_path.stat().st_size > 0):
            ndf = load_binance_normalized(syms["binance"])
            ndf.insert(0, "exchange_symbol", syms["binance"])
            ndf.insert(0, "base", base)
            ndf.insert(0, "exchange", "binance")
            ndf.to_parquet(bin_path, index=False)
        ndf = pd.read_parquet(bin_path)
        manifest_files[bin_path.name] = {
            "exchange": "binance", "base": base, "exchange_symbol": syms["binance"],
            "rows": int(len(ndf)),
            "first": pd.to_datetime(ndf["fundingTime"]).min().isoformat() if len(ndf) else None,
            "last": pd.to_datetime(ndf["fundingTime"]).max().isoformat() if len(ndf) else None,
            "sha256": sha256_of(bin_path),
            "source": f"data/raw/xs_universe_20260924/{syms['binance']}_funding.parquet",
        }

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assignment": "OPENCODE_CX_W18_FUNDING.md",
        "symbols": SYMBOLS,
        "endpoints": {
            "bybit": BYBIT_URL + "?category=linear&symbol=<SYM>&limit=200&endTime=<ms> (backward by endTime)",
            "okx": OKX_URL + "?instId=<INST>&limit=100&after=<ms> (backward by after)",
            "binance_source": "data/raw/xs_universe_20260924/{SYM}_funding.parquet",
        },
        "rate_limits": "sleep 0.2 s between calls; retry with backoff on 429/418/5xx",
        "okx_range_notes": okx_notes,
        "files": manifest_files,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done. {len(manifest_files)} files in {OUT_DIR}")


if __name__ == "__main__":
    main()
