"""v90 bundle builder (LOCAL ONLY, never shipped to Kaggle).

Reads public Binance USD-M 4h klines + funding + 1d klines for
BTC/ETH/SOL/BNB/XRP and packs the causal primitives into ONE .npz file
with a SHA-256 manifest.

Sources (frozen, hash-pinned):
  BTC    : data/raw/ma_ribbon_20260924   (klines_4h, klines_1d, funding)
  others : data/raw/xs_universe_20260924 ({SYM}_4h, {SYM}_1d, {SYM}_funding)

The bundle holds RAW aligned series only. All causal features, labels,
normalization, folds and modelling live in kaggle/train_v90.py (the single
standalone Kaggle script), so nothing here can leak future information:
feature/label construction is as-of-bar-close in the training script.

Causality contract for the bundle: every stored timestamp is a bar
close_time / fundingTime as published; no forward-filled values cross a
close boundary (alignment is merge_asof-backward at train time).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[5]
OUT_DIR = REPO / "research" / "parallel" / "rounds" / "parallel-20260906-r2" / "v90"
BTC_DIR = REPO / "data" / "raw" / "ma_ribbon_20260924"
XS_DIR = REPO / "data" / "raw" / "xs_universe_20260924"

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BUNDLE_NAME = "majors_4h_bundle.npz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ns(ser: pd.Series) -> np.ndarray:
    """UTC timestamps -> int64 ns without tz-aware astype warnings."""
    idx = pd.DatetimeIndex(pd.to_datetime(ser, utc=True)).tz_convert("UTC").tz_localize(None)
    return idx.to_numpy().astype("datetime64[ns]").astype("int64")


def load_klines(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df.sort_values("close_time").drop_duplicates("close_time").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    # Reject bad bars (same rules as TRAINING.md dataset freeze: no NaN /
    # non-finite / inverted OHLC rows are carried silently).
    bad = (
        ~np.isfinite(df[["open", "high", "low", "close", "volume"]].to_numpy()).all(axis=1)
        | (df["low"] > df["high"])
        | (df["close"] <= 0)
    )
    if bad.any():
        raise ValueError(f"{path.name}: {int(bad.sum())} invalid OHLCV rows")
    return df


def load_funding(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df.sort_values("fundingTime").drop_duplicates("fundingTime").reset_index(drop=True)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce").astype("float64")
    df = df[np.isfinite(df["fundingRate"].to_numpy())].reset_index(drop=True)
    return df[["fundingTime", "fundingRate"]]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_files: dict[str, str] = {}

    # Master 4h grid = BTC (ma_ribbon) close_times, monotonic, unique.
    btc4 = load_klines(BTC_DIR / "klines_4h.parquet")
    source_files["data/raw/ma_ribbon_20260924/klines_4h.parquet"] = sha256(BTC_DIR / "klines_4h.parquet")
    grid = _ns(btc4["close_time"])
    if not (np.diff(grid) > 0).all():
        raise ValueError("BTC 4h grid is not strictly increasing")
    grid_ns = grid

    arrays: dict[str, np.ndarray] = {"close_time_4h_ns": grid_ns, "assets": np.array(ASSETS)}
    coverage: dict[str, dict] = {}

    for asset in ASSETS:
        if asset == "BTCUSDT":
            k4 = btc4
            k1 = load_klines(BTC_DIR / "klines_1d.parquet")
            fu = load_funding(BTC_DIR / "funding.parquet")
            source_files["data/raw/ma_ribbon_20260924/klines_1d.parquet"] = sha256(BTC_DIR / "klines_1d.parquet")
            source_files["data/raw/ma_ribbon_20260924/funding.parquet"] = sha256(BTC_DIR / "funding.parquet")
        else:
            p4 = XS_DIR / f"{asset}_4h.parquet"
            p1 = XS_DIR / f"{asset}_1d.parquet"
            pf = XS_DIR / f"{asset}_funding.parquet"
            k4 = load_klines(p4)
            k1 = load_klines(p1)
            fu = load_funding(pf)
            source_files[f"data/raw/xs_universe_20260924/{asset}_4h.parquet"] = sha256(p4)
            source_files[f"data/raw/xs_universe_20260924/{asset}_1d.parquet"] = sha256(p1)
            source_files[f"data/raw/xs_universe_20260924/{asset}_funding.parquet"] = sha256(pf)

        # As-of (backward) alignment of this asset's 4h bars onto the master
        # grid: a grid bar uses the latest asset bar closed at/before it.
        # No forward fill across unclosed bars by construction.
        idx = np.searchsorted(
            _ns(k4["close_time"]), grid_ns, side="right"
        ) - 1
        present = idx >= 0
        take = np.clip(idx, 0, len(k4) - 1)
        block = k4[["open", "high", "low", "close", "volume"]].to_numpy(dtype="float64")[take]
        block[~present] = np.nan
        for j, col in enumerate(("open", "high", "low", "close", "volume")):
            arrays[f"{asset}.{col}"] = block[:, j]

        d1_ct = _ns(k1["close_time"])
        arrays[f"{asset}.daily_close_time_ns"] = d1_ct
        arrays[f"{asset}.daily_close"] = k1["close"].to_numpy(dtype="float64")
        arrays[f"{asset}.funding_time_ns"] = (
            _ns(fu["fundingTime"])
        )
        arrays[f"{asset}.funding_rate"] = fu["fundingRate"].to_numpy(dtype="float64")
        coverage[asset] = {
            "bars_4h": int(present.sum()),
            "grid_4h": int(len(grid)),
            "first_close": str(k4["close_time"].iloc[0]),
            "last_close": str(k4["close_time"].iloc[-1]),
            "daily_rows": int(len(k1)),
            "funding_rows": int(len(fu)),
        }

    bundle_path = OUT_DIR / BUNDLE_NAME
    np.savez_compressed(bundle_path, **arrays)
    manifest = {
        "bundle": BUNDLE_NAME,
        "sha256": sha256(bundle_path),
        "bytes": bundle_path.stat().st_size,
        "grid": {
            "rows": int(len(grid)),
            "first_close": str(btc4["close_time"].iloc[0]),
            "last_close": str(btc4["close_time"].iloc[-1]),
            "assets": ASSETS,
        },
        "coverage": coverage,
        "source_files": source_files,
        "contract": (
            "Raw as-published closes only; features/labels/folds are built "
            "causally (merge_asof backward on availability time) inside "
            "kaggle/train_v90.py. No forward returns for dates >= 2025-09-24 "
            "were computed or inspected while building this bundle."
        ),
    }
    (OUT_DIR / "data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {bundle_path} ({bundle_path.stat().st_size} bytes)")
    print(f"sha256 {manifest['sha256']}")


if __name__ == "__main__":
    main()
