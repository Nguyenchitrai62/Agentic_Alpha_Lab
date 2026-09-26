"""v133: deployment v2 = tranched v115 books (v127) with v129 vol-forecast sizing (registry parallel-20260906-r2 / v133).

Books: v92 LO + v94 LS on the v114 extended panel and v103 LS, each with vol42 replaced by the v129 forward-vol
forecast (pvol) in the weight formulas, tranched over the six daily phases (v125), own vol targets; portfolio v115
(0.25/0.25/0.5, 15% target, ungoverned, v110 engine). Reports the three cost scenarios (full-path DD) and the hidden
year with the v104 strict 1m fill rule. Reference: v127 (tranched, vol42): 2.378/2.156/1.879, hidden +30.17% DD 9.98%.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v133/v133_deploy_v2.py
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


v129 = _load("v129", "v129/v129_vol_forecast_sizing.py")
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
v104, v99 = v115.v104, v115.v99
PD = 6


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
    pv92, _ = v129.vol_predict(p92, ext.v92.FEATS, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    W103 = v125.phased(v125.raw_ls(swap(fl, pv103)), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    out = {"version": "v133"}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = p103.pivot_table(index="t", columns="sym", values="open").reindex(idx)
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
    out["hidden_year_1m_execution_strict"] = dict(**v104.v92.stats(net[mk], turn[mk]), maker_fill_rate=round(float(maker[orders].stack().mean()), 3), orders=int(orders.to_numpy().sum()))
    out["reference_v127"] = {"normal": 2.378, "fee_stress": 2.156, "execution_stress": 1.879, "hidden_net_pct": 30.17, "hidden_dd": 9.98}
    print("hidden-year strict", out["hidden_year_1m_execution_strict"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v133_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
