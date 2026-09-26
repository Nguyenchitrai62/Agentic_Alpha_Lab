"""v135: limit-price offset execution for the v133 portfolio, 1m data 2021-2026 (registry parallel-20260906-r2 / v135).

Orders = weight changes of the v133 portfolio (tranched books, vol-forecast sizing, 15% target). An order decided at bar
t executes in bar T = t + 4h. Buy limit at p0*(1-d), sell limit at p0*(1+d), p0 = 1m open at T. Maker fill (fee 0.0002,
price = limit) if any 1m bar with open_time in [T+2m, T+14m] trades strictly through the limit (low < limit for buys,
high > limit for sells); otherwise taker (fee 0.0005) at the T+15m 1m open (p0 if missing) with 0.0002 adverse slippage;
a missing T bar = taker at p0 + 0.0002. d = 0 reproduces the v104 strict rule. d in (0, 5, 10, 20) bps.
Selection rule (fixed): choose d with the highest mean yearly net over the 2021-2024 anchor years; report every d for all
five anchor years, the chosen d's hidden year (2025 anchor) and its full-path DD. Carry and funding as v104.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v135/v135_limit_offset.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
v104, v99 = v115.v104, v115.v99
PD = 6
OFFSETS = (0.0, 0.0005, 0.0010, 0.0020)


def load_1m(sym):
    d = Path("data/raw/btc_intraday_20260924") if sym == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
    pat = "klines_1m_20*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_20*.parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").sort_values("open_time")


def bar_stats(sym):
    """Per 4h execution bar T: p0 (1m open at T), lo/hi over minutes 2..14, p15 (1m open at T+15m)."""
    m = load_1m(sym)
    T = m["open_time"].dt.floor("4h")
    off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int)
    p0 = m[off == 0].set_index(T[off == 0])["open"]
    w = m[(off >= 2) & (off <= 14)]
    lo = w.groupby(T[(off >= 2) & (off <= 14)])["low"].min()
    hi = w.groupby(T[(off >= 2) & (off <= 14)])["high"].max()
    p15 = m[off == 15].set_index(T[off == 15])["open"]
    return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "p15": p15})


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
    s = (0.15 / vol).clip(upper=v99.CAP).fillna(1.0)
    Wt = books.mul(v99.W_BOOKS * s, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    dW = Wt.diff().fillna(Wt)
    stats = {sym: bar_stats(sym).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for sym in Wt.columns}
    out = {"version": "v135", "offsets_bps": [d * 1e4 for d in OFFSETS], "by_offset": {}}
    live = (idx >= pd.Timestamp(v129.v115.v104.v92.ANCHORS[0], tz="UTC"))
    for d in OFFSETS:
        cost = pd.Series(0.0, index=idx)
        maker_n = tot_n = 0
        for sym in Wt.columns:
            st, x = stats[sym], dW[sym]
            buy = x > 0
            lim = np.where(buy, st["p0"] * (1 - d), st["p0"] * (1 + d))
            filled = np.where(buy, st["lo"] < lim, st["hi"] > lim) & st["p0"].notna().to_numpy()
            p15 = st["p15"].fillna(st["p0"])
            taker_rel = np.where(st["p0"].notna(), p15 / st["p0"] - 1, 0.0) + np.where(buy, 0.0002, -0.0002)
            rel = np.where(filled, np.where(buy, -d, d), taker_rel)
            fee = np.where(filled, 0.0002, 0.0005)
            c = x.abs() * fee + x * rel
            cost = cost.add(pd.Series(np.nan_to_num(c), index=idx), fill_value=0.0)
            act = (x.abs() > 1e-9) & live
            maker_n += int((filled & act.to_numpy()).sum()); tot_n += int(act.sum())
        net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        turn = dW.abs().sum(axis=1)
        yearly = []
        for a in v129.v115.v104.v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v104.v92.stats(net[mk], turn[mk])))
        full = live & (idx < v110.END)
        eq = (1 + net[full]).cumprod()
        out["by_offset"][f"{d * 1e4:.0f}bps"] = dict(yearly=yearly, maker_rate=round(maker_n / max(tot_n, 1), 3),
                                                     mean_net_2021_2024=round(float(np.mean([y["net_pct"] for y in yearly[:4]])), 2),
                                                     full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))
        r = out["by_offset"][f"{d * 1e4:.0f}bps"]
        print(f"offset {d * 1e4:.0f}bps maker {r['maker_rate']} mean21-24 {r['mean_net_2021_2024']} fullDD {r['full_path_dd']}",
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    best = max(out["by_offset"], key=lambda k: out["by_offset"][k]["mean_net_2021_2024"])
    out["chosen_offset"] = best
    out["chosen_hidden_year"] = out["by_offset"][best]["yearly"][4]
    print("chosen", best, "hidden year", out["chosen_hidden_year"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v135_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
