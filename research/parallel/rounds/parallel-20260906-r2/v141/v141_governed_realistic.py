"""v141: v133 books + v135 realistic 1m execution (10 bps limits) + v110 drawdown governor at higher risk (registry v141).

Sequential simulation over the live span [2021-09-24, +1825 days): portfolio scale s = min(target/vol, 2) (vol from
the ungated books + carry as v115); governor g_i = clip((0.20 - DD_{i-2})/0.10, 0, 1) on the 90-day equity peak (v110);
w_i = 0.8*s_i*books_i*g_i, carry exposure 0.6*s_i*g_i. Each weight change is executed with the v135 rule at d = 10 bps
(maker at the limit on trade-through in minutes 2..14, else taker at the minute-15 open + 2 bps; missing bar = taker at
the open + 2 bps); long funding 0.00005/bar on long gross; carry costs as v104. Targets 0.15 (ungoverned reference =
v137 row), 0.20 and 0.25 (governed; primary 0.25). Reporting frontier: target choice is ex post. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v141/v141_governed_realistic.py
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
PD, D = 6, 0.0010
ROWS = (("reference_t15_ungoverned", 0.15, False), ("t20_governed", 0.20, True), ("primary_t25_governed", 0.25, True))


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
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0).to_numpy()
    o = p103.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    B = books.to_numpy()
    cols = list(books.columns)
    # per asset/bar execution terms for buys and sells (v135 rule, d = 10 bps)
    st = {s: v135.bar_stats(s).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for s in cols}
    fee_b, rel_b, fee_s, rel_s = (np.zeros(B.shape) for _ in range(4))
    for j, s in enumerate(cols):
        p0, lo_, hi_, p15 = st[s]["p0"].to_numpy(), st[s]["lo"].to_numpy(), st[s]["hi"].to_numpy(), st[s]["p15"].to_numpy()
        have = ~np.isnan(p0)
        p15 = np.where(np.isnan(p15), p0, p15)
        mv = np.where(have, p15 / np.where(have, p0, 1.0) - 1, 0.0)
        fb = have & (lo_ < p0 * (1 - D))
        fs = have & (hi_ > p0 * (1 + D))
        fee_b[:, j], rel_b[:, j] = np.where(fb, 0.0002, 0.0005), np.where(fb, -D, mv + 0.0002)
        fee_s[:, j], rel_s[:, j] = np.where(fs, 0.0002, 0.0005), np.where(fs, D, mv - 0.0002)
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    out = {"version": "v141", "offset_bps": 10}
    for key, target, gov in ROWS:
        s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
        n = len(idx)
        net, turn, g, eq = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n)
        prev_w, prev_c = np.zeros(B.shape[1]), 0.0
        for i in range(n):
            if gov and i >= 2:
                j = i - 2
                peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            w = v99.W_BOOKS * s[i] * B[i] * g[i] if live[i] else np.zeros(B.shape[1])
            c = v99.W_CARRY * v99.CARRY_LEV * s[i] * g[i] if live[i] else 0.0
            dw = w - prev_w
            buy = dw > 0
            cost = np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i]) + dw * np.where(buy, rel_b[i], rel_s[i]))
            turn[i] = np.abs(dw).sum()
            net[i] = (w * r_next[i]).sum() - cost - np.clip(w, 0, None).sum() * 0.00005 + c * carry[i] - abs(c - prev_c) * 2 * 0.0004 / 1.2
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + net[i])
            prev_w, prev_c = w, c
        res = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
        out[key] = res
        print(key, res["monthly_pct"], "fullDD", res["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"], y["mean_g"]) for y in res["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v141_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
