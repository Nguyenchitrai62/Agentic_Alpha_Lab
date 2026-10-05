"""Tournament inputs (dev-only): bar-open state of every rung row + an hourly OHLCV panel for the 35 coins, minutes < 2025-09-25 only.

Outputs (research/tournament/data/):
  bar_open.parquet : one row per fills_U row (same order, key j / sym / r): features known at the close of minute 0 of the holding bar
                     (the deployed agent's convention: kk = 240 j), all scaled by the coin's sigma_4h:
                     bo_sp30, bo_volreg, bo_trend, bo_btc_sp30, bo_dd24, hour, r1h, r4h, r24h, r72h (log returns ending at kk),
                     rng24 (24h high-low / close), dd7 / du7 (distance to the 7-day high / low), rv24 (std of 1h returns over 24 h / sigma_1h
                     implied by sigma_4h), btc_r4h, btc_r24h, btc_dd24.
  hourly.parquet   : sym, t (hour start), open, high, low, close, volume (sum of 1m volume when the files carry it).
Every quantity at row j uses minutes <= 240 j (the bar's minute 0 close) - nothing later.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "data"
END = pd.Timestamp("2025-09-25", tz="UTC")


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def logret(C, k, n):
    return np.log(C[k] / C[k - n]) if k - n >= 0 and C[k] > 0 and C[k - n] > 0 else np.nan


def main():
    v294 = L("v294_tp", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v293.END = END
    OUT.mkdir(parents=True, exist_ok=True)
    fills = pd.read_parquet(ROOT / "research/diagnostics/phase_agents/fills_U.parquet")
    syms = list(v293.MAJORS) + list(v294.universe())
    btc = v293.Asset("BTCUSDT")
    parts, hourly = [], []
    for s in syms:
        A = btc if s == "BTCUSDT" else v293.Asset(s)
        rows = fills[fills.sym == s]
        feats = []
        for j in rows.j.to_numpy():
            kk = int(j) * 240
            sg = A.sig[j]
            C = A.C
            f = dict(bo_sp30=A.sp30(kk), bo_volreg=A.volreg[j], bo_trend=A.trend[j], bo_btc_sp30=btc.sp30(kk),
                     bo_dd24=np.log(C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, hour=A.t0[j].hour)
            for n, name in ((60, "r1h"), (240, "r4h"), (1440, "r24h"), (4320, "r72h")):
                f[name] = logret(C, kk, n) / sg
            lo24 = np.nanmin(A.L[max(0, kk - 1439): kk + 1]); hi24 = np.nanmax(A.H[max(0, kk - 1439): kk + 1])
            hi7 = np.nanmax(A.H[max(0, kk - 10079): kk + 1]); lo7 = np.nanmin(A.L[max(0, kk - 10079): kk + 1])
            f["rng24"] = (hi24 - lo24) / C[kk] / sg
            f["dd7"], f["du7"] = np.log(C[kk] / hi7) / sg, np.log(C[kk] / lo7) / sg
            h1 = C[max(0, kk - 1440): kk + 1: 60]
            f["rv24"] = np.nanstd(np.diff(np.log(h1))) / (sg / 2) if len(h1) > 3 else np.nan
            f["btc_r4h"], f["btc_r24h"] = logret(btc.C, kk, 240) / btc.sig[j], logret(btc.C, kk, 1440) / btc.sig[j]
            f["btc_dd24"] = np.log(btc.C[kk] / btc.hmax24[kk]) / btc.sig[j] if btc.hmax24[kk] > 0 else np.nan
            feats.append(f)
        parts.append(pd.DataFrame(feats, index=rows.index))
        m = v293.load_1m(s)
        h = m.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        h = h[h.index < END].dropna(how="all").reset_index().rename(columns={"index": "t", "open_time": "t"})
        hourly.append(h.assign(sym=s))
        print("done", s, len(rows), flush=True)
        if s != "BTCUSDT":
            del A
    bo = pd.concat(parts).reindex(fills.index)
    bo.insert(0, "j", fills.j.to_numpy()); bo.insert(1, "sym", fills.sym.to_numpy()); bo.insert(2, "r", fills.r.to_numpy())
    bo.to_parquet(OUT / "bar_open.parquet")
    pd.concat(hourly, ignore_index=True).to_parquet(OUT / "hourly.parquet")
    print("saved", bo.shape)


if __name__ == "__main__":
    main()
