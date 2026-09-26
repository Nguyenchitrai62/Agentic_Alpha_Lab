"""v144: deployment v3 = v142 books (cross-sectional features) + v141 realistic engine (registry v144).

Books exactly as v142 (v133 configuration with xs_/xr_ features); simulation exactly as v141 (sequential, v135 10 bps
limit execution on 1m data, v110 drawdown governor on the 90-day peak lagged 2 bars, carry and funding as v104).
Rows: 0.15 ungoverned, 0.20 governed, 0.25 governed (primary). Reference v141 (v133 books): 2.258 / 2.695 / 3.021
%/month, full-path DD 16.25 / 18.9 / 19.59. Target choice is ex post (frontier). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v144/v144_deploy_v3.py
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


v142 = _load("v142", "v142/v142_cross_sectional_features.py")
v135 = _load("v135", "v135/v135_limit_offset.py")
v129, v125, v115, v103, v110 = v142.v129, v142.v125, v142.v115, v142.v103, v142.v110
v99 = v115.v99
PD, D = 6, 0.0010
ROWS = (("reference_t15_ungoverned", 0.15, False), ("t20_governed", 0.20, True), ("primary_t25_governed", 0.25, True))


def books_v142():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p92x = v142.add_xs(p92, v142.BASE)
    ext.v92.FEATS = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92x, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92x)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103x = v142.add_xs(p103, v142.BASE + v142.FLOWX)
    f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103x, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    pv92, _ = v129.vol_predict(p92, f92_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

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
    return p103, books


def simulate(p103, books):
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0).to_numpy()
    o = p103.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    B, cols = books.to_numpy(), list(books.columns)
    st = {s: v135.bar_stats(s).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for s in cols}
    fee_b, rel_b, fee_s, rel_s = (np.zeros(B.shape) for _ in range(4))
    for j, s in enumerate(cols):
        p0, lo_, hi_, p15 = st[s]["p0"].to_numpy(), st[s]["lo"].to_numpy(), st[s]["hi"].to_numpy(), st[s]["p15"].to_numpy()
        have = ~np.isnan(p0)
        p15 = np.where(np.isnan(p15), p0, p15)
        mv = np.where(have, p15 / np.where(have, p0, 1.0) - 1, 0.0)
        fb, fs = have & (lo_ < p0 * (1 - D)), have & (hi_ > p0 * (1 + D))
        fee_b[:, j], rel_b[:, j] = np.where(fb, 0.0002, 0.0005), np.where(fb, -D, mv + 0.0002)
        fee_s[:, j], rel_s[:, j] = np.where(fs, 0.0002, 0.0005), np.where(fs, D, mv - 0.0002)
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    out = {}
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
        out[key] = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
        r = out[key]
        print(key, r["monthly_pct"], "fullDD", r["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"], y["mean_g"]) for y in r["yearly"]], flush=True)
    return out


def main():
    p103, books = books_v142()
    out = {"version": "v144", "offset_bps": 10, **simulate(p103, books)}
    out["reference_v141"] = {"t15": (2.258, 16.25), "t20": (2.695, 18.9), "t25": (3.021, 19.59)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v144_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
