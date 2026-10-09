"""oc_fundhold funding thresholds (frozen PLAN.md definitions).

Per-coin settled funding only (no 1m, no premium) -> per-anchor q70/q50 over
settlements in [A-97d, A-7d) -> thresholds.json + per-coin settlement caches.
Causality: last settled funding has calc_time STRICTLY before the timeout open;
thresholds use strictly previous data only (7d embargo). Missing -> NaN (never
extend, never imputed).

Usage:
  python compute_funding.py
Resume-safe per-coin caches in tmp/.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fund_rule import ANCH5, MIN_POOL

ROOT = HERE.parents[2]
PREM = ROOT / "data/raw/binance_premium_20260928"
TMP = HERE / "tmp"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
WIN = pd.Timedelta(days=90)
EMBARGO = pd.Timedelta(days=7)


def main() -> None:
    t0 = time.time()
    TMP.mkdir(parents=True, exist_ok=True)
    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    thresholds: dict[str, dict] = {}
    for coin in COINS:
        cache = TMP / f"settle_{coin}.parquet"
        if cache.exists():
            df = pd.read_parquet(cache)
            print(f"{coin}: loaded cache {len(df)} settlements", flush=True)
        else:
            f = pd.read_parquet(PREM / f"{coin}_funding.parquet",
                                columns=["calc_time", "last_funding_rate"])
            s = pd.to_datetime(f["calc_time"], utc=True)
            r = f["last_funding_rate"].to_numpy(dtype=float)
            order = np.argsort(s.values.astype("datetime64[ns]").astype(np.int64),
                               kind="stable")
            df = pd.DataFrame({"S": s.iloc[order].reset_index(drop=True),
                               "rate": r[order]})
            df.to_parquet(cache, index=False)
            print(f"{coin}: built settle cache n={len(df)} "
                  f"finite={int(np.isfinite(r).sum())}", flush=True)
        for i, A in enumerate(anch):
            lo = A - WIN - EMBARGO
            hi = A - EMBARGO
            m = (df["S"] >= lo) & (df["S"] < hi) & np.isfinite(df["rate"].to_numpy())
            pool = df.loc[m, "rate"].to_numpy(dtype=float)
            key = str(A.date())
            thresholds.setdefault(key, {})
            if len(pool) >= MIN_POOL:
                q70 = float(np.quantile(pool, 0.70))
                q50 = float(np.quantile(pool, 0.50))
            else:
                q70 = float("nan")
                q50 = float("nan")
            thresholds[key][coin] = {"q70": q70, "q50": q50,
                                     "n_pool": int(len(pool))}
        print(f"[{time.time()-t0:.0f}s] {coin} thresholds done", flush=True)
    (TMP / "thresholds.json").write_text(json.dumps(thresholds, indent=1))
    print("thresholds:", json.dumps(thresholds, indent=1), flush=True)


if __name__ == "__main__":
    main()
