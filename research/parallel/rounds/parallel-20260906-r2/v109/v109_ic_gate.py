"""v109: trailing realized-IC gate on the v104 books (registry parallel-20260906-r2 / v109, track A).

For each book (v92 long-only: label y (7d), v94 long/short: label y42, v103 long/short: label y6) and each daily decision
bar tau, IC_tau = pooled Spearman(pred, label) over OOS prediction rows with t >= tau - 60 days and whose label is fully
realized by tau (t + (h+1)*4h <= tau). Multiplier m = clip(IC_tau / 0.10, 0, 1.5); m = 1 when fewer than 200 rows
qualify (start of the OOS span). m is held until the next daily bar.
Portfolio (primary): exactly v104 (books 0.25 v92 + 0.25 v94 + 0.5 v103, each with its own 20% vol target; 80% books
+ 20% carry x3; 15% portfolio vol target cap 2) where the portfolio vol scale is computed from the UNGATED books and
the gate multiplies each book afterwards (so vol targeting cannot undo the gate). Secondary: the gate on the v92 book
alone (v92 vol target, v92 costs). All constants fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v109/v109_ic_gate.py
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
LOOKBACK, IC_FULL, M_CAP, MIN_ROWS = pd.Timedelta(days=60), 0.10, 1.5, 200


def ic_gate(oos: pd.DataFrame, label: str, h: int, index: pd.Index) -> pd.Series:
    d = oos[["t", "pred", label]].dropna().sort_values("t")
    real = d["t"] + pd.Timedelta(hours=4 * (h + 1))
    taus = index[np.arange(len(index)) % PD == 0]
    m = {}
    for tau in taus:
        sel = d[(d["t"] >= tau - LOOKBACK) & (real <= tau)]
        if len(sel) < MIN_ROWS:
            m[tau] = 1.0
        else:
            ic = sel["pred"].rank().corr(sel[label].rank())
            m[tau] = float(np.clip(ic / IC_FULL, 0.0, M_CAP)) if np.isfinite(ic) else 1.0
    return pd.Series(m).reindex(index).ffill().fillna(1.0)


def yearly(net, turn):
    ys = []
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    return dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in ys))


def main():
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True)
    p94 = v94.add_targets(v92.build())
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in v92.ANCHORS], ignore_index=True)
    W_lo, W94, W103 = v92.weights_from(lo, "model"), v94.weights_ls(ls, True), v94.weights_ls(fl, True)
    idx = W_lo.index.union(W94.index).union(W103.index)
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p94, W94).reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    m_lo, m94, m103 = ic_gate(lo, "y", v92.H, idx), ic_gate(ls, "y42", 42, idx), ic_gate(fl, "y6", 6, idx)
    out = {"version": "v109", "gate_mean_by_year": {}}
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
        out["gate_mean_by_year"][a] = [round(float(x[mk].mean()), 3) for x in (m_lo, m94, m103)]
    print("gate means (v92, v94, v103)", out["gate_mean_by_year"], flush=True)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    gated = 0.25 * b_lo.mul(m_lo, axis=0) + 0.25 * b94.mul(m94, axis=0) + 0.5 * b103.mul(m103, axis=0)
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = p92.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (v99.TARGET / vol).clip(upper=v99.CAP).fillna(1.0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    for name, B in (("primary_v104_gated", gated), ("reference_v104_ungated", books)):
        Wt = B.mul(v99.W_BOOKS * s, axis=0)
        res = {}
        for sc, (fee, slip) in v92.SCEN.items():
            turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
            net = (Wt * r_next).sum(axis=1) - turn * (fee + slip) - Wt.clip(lower=0).sum(axis=1) * 0.00005 \
                + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
            res[sc] = yearly(net, turn)
            print(name, sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
        out[name] = res
    res = {}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(p92, W_lo.reindex(idx).fillna(0.0), v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0) * m_lo, fee, slip)
        res[sc] = yearly(net, turn)
        print("secondary v92 gated", sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["secondary_v92_gated"] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v109_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
