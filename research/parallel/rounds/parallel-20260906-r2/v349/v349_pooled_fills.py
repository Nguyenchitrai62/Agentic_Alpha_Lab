"""v349 building block (no selection input by itself): pooled survivorship-free dip experience under the M3 MANUAL rules.

For the 5 majors + the 30 U2020 alts (v294.universe, training experience only) every 4h holding bar's bracket dip limits at 3.0 and 4.0 sigma_4h
(v293 standalone replica: fill on a 1m trade-through from minute 16, take-profit 1.0 sigma, exchange-native touch stop at 8 sigma (close5 and backstop
both at 8 sigma = a touch stop at 8 sigma), market exit at the next 4h open, engine fees / long funding). Stored per fill: sym, rung, holding-bar
start time and UTC hour, fill and exit time, net return y (TP 1.0 sigma).
Output: artifacts/research/engine_real/v349_pooled_fills_m3.parquet
  python research/parallel/rounds/parallel-20260906-r2/v349/v349_pooled_fills.py
"""
import importlib.util
from pathlib import Path

import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main():
    v294 = L("v294_pf", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    eu = L("engine_user_pf", RD / "engine_user/engine_user.py")
    v293.RUNGS, v293.M_SL, v293.BACKSTOP, v293.ACTIONS = (3.0, 4.0), 8.0, 8.0, (1.0,)
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            d = d.assign(sym=s, bar=[A.t0[j] for j in d.j])
            parts.append(d[["sym", "r", "bar", "t_fill", "t_exit", "y1.0"]])
        print(s, len(d), flush=True)
        if s not in assets:
            del A
    out = pd.concat(parts, ignore_index=True).rename(columns={"y1.0": "y"})
    out["rung"] = out["r"].map({0: 3.0, 1: 4.0})
    out["hour"] = pd.to_datetime(out["bar"], utc=True).dt.hour
    out.drop(columns="r").to_parquet("artifacts/research/engine_real/v349_pooled_fills_m3.parquet", index=False)
    print("saved", len(out))


if __name__ == "__main__":
    main()
