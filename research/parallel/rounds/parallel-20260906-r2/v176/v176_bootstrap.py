"""v176 bootstrap (DIAGNOSTIC, like v148): stationary block bootstrap of v176 daily net returns.

Rebuilds the v176 net series (same code path), then draws 2000 one-year paths (365 days) by block bootstrap with
mean block 20 days from the 5-year live span; reports the distribution of 1-year return, max DD, and the shares with
DD > 20% and with >= 5%/month. Also the same for v170 books alone. Nothing is tuned.

  python research/parallel/rounds/parallel-20260906-r2/v176/v176_bootstrap.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v176 = _load("v176b", HERE / "v176_total_vol_target.py")
er, v171, v172, v175, v170, v110 = v176.er, v176.v171, v176.v172, v176.v175, v176.v170, v176.v110


def net_series(books, ctx, sleeve_unit):
    captured = {}
    orig = v110.summarize

    def grab(net, turn, g):
        captured["net"] = net
        return orig(net, turn, g)

    v176.v110.summarize = grab
    try:
        v176.run_total(books, ctx, sleeve_unit)
    finally:
        v176.v110.summarize = orig
    return captured["net"]


def boot(daily, n=2000, days=365, block=20, seed=0):
    rng = np.random.default_rng(seed)
    x = daily.to_numpy()
    N = len(x)
    rets, dds = [], []
    for _ in range(n):
        idx = []
        while len(idx) < days:
            s = rng.integers(N)
            L = rng.geometric(1 / block)
            idx.extend(((s + np.arange(L)) % N).tolist())
        path = x[idx[:days]]
        eq = np.cumprod(1 + path)
        rets.append(eq[-1] - 1)
        dds.append(float(np.max(1 - eq / np.maximum.accumulate(eq))))
    rets, dds = np.array(rets), np.array(dds)
    monthly = (1 + rets) ** (1 / 12) - 1
    return dict(median_1y_pct=round(100 * float(np.median(rets)), 1), p10_1y_pct=round(100 * float(np.quantile(rets, 0.1)), 1),
                median_dd_pct=round(100 * float(np.median(dds)), 1), p90_dd_pct=round(100 * float(np.quantile(dds, 0.9)), 1),
                p_dd_gt_20=round(float((dds > 0.20).mean()), 3), p_monthly_ge_5=round(float((monthly >= 0.05).mean()), 3),
                p_loss=round(float((rets < 0).mean()), 3))


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    ev = v175.limit_returns(G, cols, A)
    del A
    sleeve, _, _ = v171.sleeve_walk_forward(G, ev)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    out = {"note": "DIAGNOSTIC block bootstrap of daily net returns over the 5-year live span"}
    for key, su in (("v176", sleeve / v176.S_REF), ("v170_books_alone", sleeve * 0.0)):
        net = net_series(books, ctx, su)
        live = net[(net.index >= v110.START) & (net.index < v110.END)]
        daily = live.groupby(live.index.floor("D")).apply(lambda r: float(np.prod(1 + r) - 1))
        out[key] = boot(daily)
        print(key, out[key], flush=True)
    (HERE / "v176_bootstrap.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
