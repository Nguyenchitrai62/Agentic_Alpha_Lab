"""v110: v104 at a higher portfolio vol target with a causal drawdown governor (registry parallel-20260906-r2 / v110).

Books, carry, costs and the portfolio vol estimate are exactly v104. Differences: portfolio vol target 0.25 (primary)
or 0.30 (secondary) instead of 0.15 (cap 2x unchanged), and an exposure multiplier g_t = clip((0.20 - DD_t)/0.10, 0, 1)
where DD_t = 1 - E_{t-2} / max(E over the 90 days up to t-2) is the drawdown of the strategy's own equity using only
returns realized two bars before the decision (same lag as the vol targets). g multiplies both the trend weights and
the carry exposure. Sequential simulation from the start of the OOS span. Reported: yearly and full-path (2021-09-24
to 2026-09-23) max DD. Reference: the ungoverned path at the same target. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v110/v110_dd_governor.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v99 = _load("v99", "v99/v99_candidate.py")
v104 = _load("v104", "v104/v104_candidate.py")
PD = v92.PD
START = pd.Timestamp(v92.ANCHORS[0], tz="UTC")
END = START + pd.Timedelta(days=5 * 365)


def run(panel, books, target, governed, fee, slip):
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (target / vol).clip(upper=v99.CAP).fillna(1.0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    B = books.mul(v99.W_BOOKS * s, axis=0).to_numpy()
    cexp = (v99.W_CARRY * v99.CARRY_LEV * s).to_numpy()
    cr = carry.to_numpy()
    n = len(idx)
    live = (idx >= START) & (idx < END)
    net = np.zeros(n)
    turn = np.zeros(n)
    g = np.ones(n)
    eq = np.ones(n)
    win = 90 * PD
    prev_w = np.zeros(B.shape[1])
    prev_c = 0.0
    for i in range(n):
        if governed and i >= 2:
            j = i - 2
            peak = eq[max(0, j - win + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        w = B[i] * g[i] if live[i] else np.zeros(B.shape[1])
        c = cexp[i] * g[i] if live[i] else 0.0
        turn[i] = np.abs(w - prev_w).sum()
        net[i] = (w * r_next[i]).sum() - turn[i] * (fee + slip) - np.clip(w, 0, None).sum() * 0.00005 + c * cr[i] - abs(c - prev_c) * 2 * 0.0004 / 1.2
        eq[i] = (eq[i - 1] if i else 1.0) * (1 + net[i])
        prev_w, prev_c = w, c
    return pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx)


def summarize(net, turn, g):
    ys = []
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **v92.stats(net[mk], turn[mk]), mean_g=round(float(g[mk].mean()), 3)))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net.index >= START) & (net.index < END)
    eq = (1 + net[full]).cumprod()
    return dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))


def main():
    panel, books = v104.books_v104()
    out = {"version": "v110"}
    for key, target, gov in (("primary_t25_governed", 0.25, True), ("secondary_t30_governed", 0.30, True),
                             ("reference_t25_ungoverned", 0.25, False), ("reference_t15_ungoverned_v104", 0.15, False)):
        res = {}
        for sc, (fee, slip) in v92.SCEN.items():
            res[sc] = summarize(*run(panel, books, target, gov, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "worstYearDD", res[sc]["worst_year_dd"], "fullDD", res[sc]["full_path_dd"],
                  [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"], y["mean_g"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v110_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
