"""v137: risk-dial frontier of the v133 portfolio under the v135 realistic 1m execution (registry v137, track C).

v133 books; portfolio vol target in (0.15, 0.17, 0.19, 0.21) (cap 2); every order executed with the v135 rule at the
chosen 10 bps offset (maker on trade-through in minutes 2..14, else taker at minute 15 + 2 bps); carry/funding as v104.
Reports 5-year monthly geometric net, yearly nets/DDs and full-path DD per target. Reporting frontier only: a target
picked from it is an EX-POST risk-budget choice. Primary row: 0.17. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v137/v137_realistic_frontier.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v135", HERE.parent / "v135" / "v135_limit_offset.py")
v135 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v135)
v129, v125, v115, v103, v110 = v135.v129, v135.v125, v135.v115, v135.v103, v135.v110
v104, v99 = v135.v104, v135.v99
PD, D, TARGETS = 6, 0.0010, (0.15, 0.17, 0.19, 0.21)


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
    books = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = p103.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    stats = {sym: v135.bar_stats(sym).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for sym in books.columns}
    live = idx >= pd.Timestamp(ext.v92.ANCHORS[0], tz="UTC")
    out = {"version": "v137", "offset_bps": 10, "frontier": {}}
    for tgt in TARGETS:
        s = (tgt / vol).clip(upper=v99.CAP).fillna(1.0)
        Wt = books.mul(v99.W_BOOKS * s, axis=0)
        carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
        dW = Wt.diff().fillna(Wt)
        cost = pd.Series(0.0, index=idx)
        for sym in Wt.columns:
            st, x = stats[sym], dW[sym]
            buy = x > 0
            lim = np.where(buy, st["p0"] * (1 - D), st["p0"] * (1 + D))
            filled = np.where(buy, st["lo"] < lim, st["hi"] > lim) & st["p0"].notna().to_numpy()
            p15 = st["p15"].fillna(st["p0"])
            taker_rel = np.where(st["p0"].notna(), p15 / st["p0"] - 1, 0.0) + np.where(buy, 0.0002, -0.0002)
            rel = np.where(filled, np.where(buy, -D, D), taker_rel)
            cost = cost.add(pd.Series(np.nan_to_num(x.abs() * np.where(filled, 0.0002, 0.0005) + x * rel), index=idx), fill_value=0.0)
        net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        turn = dW.abs().sum(axis=1)
        yearly = []
        for a in ext.v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v104.v92.stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        full = live & (idx < v110.END)
        eq = (1 + net[full]).cumprod()
        out["frontier"][f"t{int(round(tgt * 100))}"] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                                                            worst_year_dd=max(y["max_drawdown_percent"] for y in yearly),
                                                            full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))
        r = out["frontier"][f"t{int(round(tgt * 100))}"]
        print(f"target {tgt}", r["monthly_pct"], "fullDD", r["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    out["primary_t17"] = out["frontier"]["t17"]
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v137_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
