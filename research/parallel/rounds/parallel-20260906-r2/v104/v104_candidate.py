"""v104 deployment candidate: the v99 wrapper with books = 0.5 * v96 books + 0.5 * v103 long/short book.

All v99 constants unchanged (80% books + 20% funding carry x3, causal 15% portfolio vol target, cap 2x). The v96 books
(v92 long-only + v94 long/short, each with its own 20% vol target) and the v103 book (1d/3d order-flow HGB, v94
weights_ls, own 20% vol target) come from the audited code paths. Hidden-year execution (stricter than v99): each
weight change is a limit at the execution bar's open, filled as maker (0.0002) only if a 1m bar with open_time in
[T+2m, T+14m] trades strictly through it; otherwise taker 0.0005 at the T+15m open plus 0.0002 adverse slippage; a
missing execution-bar 1m open counts as taker at the bar open plus 0.0002 slippage. Registry parallel-20260906-r2 / v104 (track A).

  python research/parallel/rounds/parallel-20260906-r2/v104/v104_candidate.py
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
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v99 = _load("v99", "v99/v99_candidate.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
PD = v92.PD
HIDDEN = v99.HIDDEN


def books_v104():
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = v92.weights_from(pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True), "model")
    p94 = v94.add_targets(v92.build())
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = v94.weights_ls(pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True), True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W103 = v94.weights_ls(pd.concat([v103.train_predict(p103, a, f103)[0] for a in v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W103.index)
    s_lo = v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0)
    s94 = v94.vol_target_scale(p94, W94).reindex(idx).fillna(1.0)
    s103 = v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0)
    v96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(s_lo, axis=0) + 0.5 * W94.reindex(idx).fillna(0.0).mul(s94, axis=0)
    return p92, 0.5 * v96 + 0.5 * W103.reindex(idx).fillna(0.0).mul(s103, axis=0)


def fill_strict(W: pd.DataFrame):
    rel = pd.DataFrame(0.0, index=W.index, columns=W.columns)
    maker = pd.DataFrame(True, index=W.index, columns=W.columns)
    dW = W.diff().fillna(W)
    for s in W.columns:
        m = v99.load_1m(s)
        for t in dW.index[(dW[s].abs() > 1e-9) & (dW.index >= HIDDEN)]:
            T = t + pd.Timedelta(hours=4)
            buy = dW.at[t, s] > 0
            if T not in m.index:
                maker.at[t, s] = False
                rel.at[t, s] = 0.0002 if buy else -0.0002
                continue
            p0 = m.at[T, "open"]
            w = m.loc[T + pd.Timedelta(minutes=2): T + pd.Timedelta(minutes=14)]
            through = (w["low"] < p0).any() if buy else (w["high"] > p0).any()
            if not through:
                T15 = T + pd.Timedelta(minutes=15)
                px = m.at[T15, "open"] if T15 in m.index else p0
                rel.at[t, s] = px / p0 - 1 + (0.0002 if buy else -0.0002)
                maker.at[t, s] = False
    return rel, maker


def main():
    panel, books = books_v104()
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (v99.TARGET / vol).clip(upper=v99.CAP).fillna(1.0)
    Wt = books.mul(v99.W_BOOKS * s, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    out = {"version": "v104"}

    def path(fee, slip, ex=None):
        turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
        dW = Wt.diff().fillna(Wt)
        if ex is None:
            cost = turn * (fee + slip)
        else:
            rel, maker = ex
            rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
            cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=dW.index) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
        net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 \
            + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        return net, turn

    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = path(fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        out[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
        print(sc, out[sc]["monthly_pct"], out[sc]["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    ex = fill_strict(Wt)
    net, turn = path(0.0, 0.0, ex)
    mk = (net.index >= HIDDEN) & (net.index < HIDDEN + pd.Timedelta(days=365))
    orders = (Wt.diff().abs() > 1e-9) & (Wt.index >= HIDDEN)[:, None]
    out["hidden_year_1m_execution_strict"] = dict(**v92.stats(net[mk], turn[mk]), maker_fill_rate=round(float(ex[1][orders].stack().mean()), 3), orders=int(orders.to_numpy().sum()))
    print("hidden-year strict 1m execution", out["hidden_year_1m_execution_strict"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v104_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
