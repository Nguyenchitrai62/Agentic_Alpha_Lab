"""v115 deployment candidate: v104 with the v92/v94 books retrained on the v114 extended history.

Books: 0.25 * v92 long-only + 0.25 * v94 long/short (both trained on the v114 panel: Bitstamp 2013 + Coinbase + Binance
history for BTC, Coinbase + Binance for ETH) + 0.5 * v103 order-flow long/short (unchanged), each with its own 20% vol
target. Wrapper: 80% books + 20% carry x3 with the causal portfolio vol target (v110 sequential engine, live span
2021-09-24 + 1825 days). Primary: target 0.15, no governor (= v104 settings). Secondary: target 0.25 with the v110
drawdown governor. Hidden year: strict 1m execution (v104 fill rule) on the primary. Fixed before running.
Registry parallel-20260906-r2 / v115 (track A).

  python research/parallel/rounds/parallel-20260906-r2/v115/v115_candidate.py
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


v114 = _load("v114", "v114/v114_bitstamp_history.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
v104 = _load("v104", "v104/v104_candidate.py")
v110 = _load("v110", "v110/v110_dd_governor.py")
v99 = v104.v99
PD = 6


def books_v115():
    v114.v113.cb_bars = v114.cb_bars_ext  # v114's own v113 instance
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = ext.v92.weights_from(pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True), "model")
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = ext.v94.weights_ls(pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W103 = ext.v94.weights_ls(pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    return p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103


def main():
    panel, books = books_v115()
    out = {"version": "v115"}
    for key, target, gov in (("primary_t15", 0.15, False), ("secondary_t25_governed", 0.25, True)):
        res = {}
        for sc, (fee, slip) in v104.v92.SCEN.items():
            res[sc] = v110.summarize(*v110.run(panel, books, target, gov, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "worstYearDD", res[sc]["worst_year_dd"], "fullDD", res[sc]["full_path_dd"],
                  [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    # hidden-year strict 1m execution for the primary (v104 cost path)
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (0.15 / vol).clip(upper=v99.CAP).fillna(1.0)
    Wt = books.mul(v99.W_BOOKS * s, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    rel, maker = v104.fill_strict(Wt)
    dW = Wt.diff().fillna(Wt)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
    turn = dW.abs().sum(axis=1)
    mk = (idx >= v104.HIDDEN) & (idx < v104.HIDDEN + pd.Timedelta(days=365))
    orders = (dW.abs() > 1e-9) & (idx >= v104.HIDDEN)[:, None]
    out["hidden_year_1m_execution_strict"] = dict(**v104.v92.stats(net[mk], turn[mk]), maker_fill_rate=round(float(maker[orders].stack().mean()), 3))
    print("hidden-year strict 1m execution", out["hidden_year_1m_execution_strict"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v115_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
