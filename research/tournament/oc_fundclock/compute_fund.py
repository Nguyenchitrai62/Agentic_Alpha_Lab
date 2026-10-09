"""oc_fundclock gate computation (frozen PLAN.md definitions).

One coin at a time (premium 1m close float32) -> P(S) per settlement
(60m TWAP ending 1h before S) -> per-anchor q90 over [A-97d, A-7d) ->
gate table gates_std.parquet {(T,sym): gate} + thresholds.json.

Causality: premium bars ending <= S-60m only; P(S) timestamped S-1h;
gate at T=S uses only data <= S-1h < T. Premium bars >= 2026-09-24 dropped.

Usage:
  python compute_fund.py
Resume-safe per-coin caches in tmp/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fund_rule import ANCH5, anchor_of, gate_flag, premium_twap_before

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREM = ROOT / "data/raw/binance_premium_20260928"
TMP = HERE / "tmp"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
CUTOFF_PREM = pd.Timestamp("2026-09-24 00:00", tz="UTC")
WIN = pd.Timedelta(days=90)
EMBARGO = pd.Timedelta(days=7)
MIN_POOL = 50


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    anch_ns = np.array([a.value for a in anch], dtype=np.int64)

    thresholds: dict[str, dict] = {}
    per_coin_flags: dict[str, pd.DataFrame] = {}
    for coin in COINS:
        cache = TMP / f"pred_{coin}.parquet"
        if cache.exists():
            df = pd.read_parquet(cache)
            print(f"{coin}: loaded cache {len(df)} settlements", flush=True)
        else:
            f = pd.read_parquet(PREM / f"{coin}_funding.parquet",
                                columns=["calc_time", "last_funding_rate"])
            s = pd.to_datetime(f["calc_time"], utc=True)
            order = np.argsort(s.values.astype("datetime64[ns]").astype(np.int64),
                               kind="stable")
            s = s.iloc[order].reset_index(drop=True)
            # premium 1m close only, float32, before cutoff
            p = pd.read_parquet(PREM / f"{coin}_premium_1m.parquet",
                                columns=["open_time", "close"])
            p["open_time"] = pd.to_datetime(p["open_time"], utc=True)
            p = p[p["open_time"] < CUTOFF_PREM].sort_values("open_time")
            prem_ns = p["open_time"].values.astype("datetime64[ns]").astype(np.int64)
            prem_close = p["close"].to_numpy(dtype=np.float32)
            del p
            s_ns = s.values.astype("datetime64[ns]").astype(np.int64)
            s_floor = (s_ns // np.int64(60 * 10**9)) * np.int64(60 * 10**9)
            pred = premium_twap_before(prem_ns, prem_close, s_floor)
            df = pd.DataFrame({"S": s, "pred": pred})
            df.to_parquet(cache, index=False)
            print(f"{coin}: built P(S) n={len(df)} "
                  f"finite={int(np.isfinite(pred).sum())}", flush=True)
        per_coin_flags[coin] = df

    # thresholds per anchor-coin over [A-97d, A-7d)
    for i, A in enumerate(anch):
        lo = A - WIN - EMBARGO
        hi = A - EMBARGO
        for coin in COINS:
            df = per_coin_flags[coin]
            m = (df["S"] >= lo) & (df["S"] < hi) & np.isfinite(df["pred"].to_numpy())
            pool = df.loc[m, "pred"].to_numpy(dtype=float)
            key = str(A.date())
            thresholds.setdefault(key, {})
            if len(pool) >= MIN_POOL:
                q90 = float(np.quantile(pool, 0.90))
            else:
                q90 = float("nan")
            thresholds[key][coin] = {"q90": q90, "n_pool": int(len(pool))}
    (TMP / "thresholds.json").write_text(json.dumps(thresholds, indent=1))
    print("thresholds:", json.dumps(thresholds, indent=1), flush=True)

    # flags per settlement, then gate table on 4h settlement grid
    rows = []
    for coin in COINS:
        df = per_coin_flags[coin]
        S_ns = pd.to_datetime(df["S"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        y = anchor_of(S_ns, anch_ns)
        qv = np.array([thresholds[str(anch[i].date())][coin]["q90"] for i in y])
        pred = df["pred"].to_numpy(dtype=float)
        flag = np.zeros(len(df), dtype=bool)
        for i in range(5):
            m = y == i
            flag[m] = gate_flag(pred[m], float(
                thresholds[str(anch[i].date())][coin]["q90"]))
        # keep only settlement-hour grid bars that are on the 4h standard grid
        # (T.hour in {0,8,16}, minute 0) and T < CUTOFF
        T = pd.to_datetime(df["S"], utc=True)
        # settlement calc_time has ms offsets; gate bar T = floored hour
        Tf = T.dt.floor("h")
        keep = (Tf.dt.hour.isin([0, 8, 16]) & (Tf.dt.minute == 0)
                & (Tf < CUTOFF))
        for t, fl in zip(Tf[keep], flag[keep.to_numpy()]):
            rows.append({"T": t, "sym": coin, "gate": bool(fl)})
    g = pd.DataFrame(rows)
    # pivot to (T x sym) bool, settlement times only; other 4h bars gate False
    piv = g.pivot_table(index="T", columns="sym", values="gate",
                        aggfunc="max").fillna(False).astype(bool)
    for c in COINS:
        if c not in piv.columns:
            piv[c] = False
    piv = piv[COINS].sort_index()
    piv.to_parquet(TMP / "gates_wide.parquet")
    # also long form for tests
    g.to_parquet(TMP / "gates_std.parquet", index=False)
    # per-year shares
    shares = {}
    for i, A in enumerate(anch):
        m = (piv.index >= A) & (piv.index < A + pd.Timedelta(days=365))
        sub = piv.loc[m] if m.sum() else piv.iloc[0:0]
        shares[str(A.date())] = {
            c: round(float(sub[c].mean()) if len(sub) else 0.0, 6) for c in COINS
        } | {"n_bars": int(m.sum())}
    print("gate shares per year (settlement-bar basis):",
          json.dumps(shares, indent=1), flush=True)
    print(f"gates: {int(piv.to_numpy().sum())} flagged (T,sym) of {piv.size}",
          flush=True)


if __name__ == "__main__":
    main()
