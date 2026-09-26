"""v125: tranched daily rebalancing of the v115 books (registry parallel-20260906-r2 / v125, track C).

Each book's audited weight rule keeps every 6th 4h row (one arbitrary rebalance hour). v125 averages the 6 phase-shifted
versions (keep rows with position % 6 == phase for phase 0..5, forward-filled, then mean), i.e. 1/6 of each book is
rebalanced every 4h -> removes rebalance-hour timing luck without raising turnover much. Applied to v92 LO, v94 LS
(v114 panel) and v103 LS; each tranched book gets its own vol target (computed on the tranched weights), portfolio =
v115 primary (0.25/0.25/0.5, 15% target, ungoverned, v110 engine). Reference: phase 0 only (= v115). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v125/v125_tranching.py
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


v115 = _load("v115", "v115/v115_candidate.py")
v103, v110 = v115.v103, v115.v110
PD, SYMS = 6, 5


def raw_lo(df):
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = (g["pred"].clip(lower=0) / 0.5).where(g["rib"] != -1, 0.0).clip(upper=1.0)
        W[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    n_assets = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(W.abs().sum(axis=1).clip(lower=1e-9), axis=0).mul(W.abs().sum(axis=1).gt(0), axis=0)
    return W.mul((n_assets / SYMS).clip(upper=1.0), axis=0)


def raw_ls(df):
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        long_ = (g["pred"].clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != -1, 0.0)
        short = ((-g["pred"]).clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != 1, 0.0)
        W[s] = (long_ - short) / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    gross, active = W.abs().sum(axis=1), W.ne(0).sum(axis=1)
    return W.div(gross.where(gross > 0, 1.0), axis=0).mul((active / SYMS).clip(upper=1.0), axis=0)


def phased(W, phases):
    pos = np.arange(len(W))
    return sum(W.where(pd.Series(pos % PD == ph, index=W.index), np.nan).ffill().fillna(0.0) for ph in phases) / len(phases)


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    R_lo, R_ls, R_fl = raw_lo(lo), raw_ls(ls), raw_ls(fl)
    assert np.allclose(phased(R_lo, [0]).to_numpy(), ext.v92.weights_from(lo, "model").to_numpy())
    assert np.allclose(phased(R_ls, [0]).to_numpy(), ext.v94.weights_ls(ls, True).to_numpy())
    out = {"version": "v125"}
    for key, phases in (("primary_tranched", list(range(PD))), ("reference_phase0_v115", [0])):
        W_lo, W94, W103 = phased(R_lo, phases), phased(R_ls, phases), phased(R_fl, phases)
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
        res = {}
        for sc, (fee, slip) in ext.v92.SCEN.items():
            res[sc] = v110.summarize(*v110.run(p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103, 0.15, False, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v125_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
