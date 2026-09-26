"""v148: robustness diagnostic of v144 (target 0.25 governed, realistic execution) by stationary block bootstrap (registry v148).

Daily net returns of the v144 primary row over the live span (sum of the six 4h nets per UTC day) are resampled with a
stationary block bootstrap (mean block 30 days, geometric block lengths, numpy default_rng(0)), 5000 paths of 365 days.
Reported: quantiles of the 1-year return and max drawdown, P(max DD > 20%), P(return < 0), P(monthly geometric >= 5%),
also for the 0.15 ungoverned and 0.20 governed rows. Note: resampled paths re-use realised governed returns (the governor
is not re-simulated inside bootstrap paths), so DD tails are conservative estimates. Diagnostic only; fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v148/v148_robustness_bootstrap.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v144", HERE.parent / "v144" / "v144_deploy_v3.py")
v144 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v144)
CAPTURED = []


def bootstrap(daily, n_paths=5000, horizon=365, mean_block=30, seed=0):
    rng = np.random.default_rng(seed)
    x = daily.to_numpy()
    n = len(x)
    rets, dds = np.empty(n_paths), np.empty(n_paths)
    for k in range(n_paths):
        path = np.empty(horizon)
        i = 0
        while i < horizon:
            start = rng.integers(n)
            L = min(rng.geometric(1 / mean_block), horizon - i)
            idx = (start + np.arange(L)) % n
            path[i:i + L] = x[idx]
            i += L
        eq = np.cumprod(1 + path)
        rets[k] = eq[-1] - 1
        dds[k] = np.max(1 - eq / np.maximum.accumulate(eq))
    q = lambda a: {p: round(float(np.quantile(a, p / 100)) * 100, 2) for p in (5, 25, 50, 75, 95)}
    return dict(return_pct_quantiles=q(rets), maxdd_pct_quantiles=q(dds), p_dd_gt_20=round(float((dds > 0.20).mean()), 3),
                p_loss=round(float((rets < 0).mean()), 3), p_monthly_ge_5=round(float(((1 + rets) ** (1 / 12) - 1 >= 0.05).mean()), 3))


def main():
    orig = v144.v110.summarize

    def capture(net, turn, g):
        CAPTURED.append(net.copy())
        return orig(net, turn, g)

    v144.v110.summarize = capture
    p103, books = v144.books_v142()
    res = v144.simulate(p103, books)
    out = {"version": "v148", "rows": {}}
    for (key, _, _), net in zip(v144.ROWS, CAPTURED):
        live = (net.index >= v144.v110.START) & (net.index < v144.v110.END)
        daily = net[live].groupby(net[live].index.floor("D")).apply(lambda r: float(np.prod(1 + r) - 1))
        out["rows"][key] = dict(realised=dict(monthly=res[key]["monthly_pct"], full_path_dd=res[key]["full_path_dd"]), bootstrap=bootstrap(daily))
        print(key, out["rows"][key], flush=True)
    out["primary_bootstrap"] = out["rows"]["primary_t25_governed"]
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v148_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
