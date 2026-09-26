"""v89: pooled majors HGB predicting 7-day vol-normalized returns, used to size a majors trend book.

Registry: parallel-20260906-r2 / v89 (track A). Five real anchors 2021-09-24..2025-09-24 (expanding),
last = hidden year. Labels realized >= embargo before each anchor. Portfolio scale K for year i is set
from the out-of-sample years before it (K=1 for the first year), so no forward information is used.
Baseline: the same universe/engine with unsized multi-horizon TSMOM signals.

  python research/parallel/rounds/parallel-20260906-r2/v89/v89_pooled_hgb.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
XS = Path("data/raw/xs_universe_20260924")
BTC = Path("data/raw/ma_ribbon_20260924")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6  # 4h bars per day
H = 42  # 7-day horizon
EMBARGO_BARS = H + 10 * PD
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}


def load_asset(s):
    if s == "BTCUSDT":
        b, d = pd.read_parquet(BTC / "klines_4h.parquet"), pd.read_parquet(BTC / "klines_1d.parquet")
        f = pd.read_parquet(BTC / "funding.parquet")
    else:
        b, d = pd.read_parquet(XS / f"{s}_4h.parquet"), pd.read_parquet(XS / f"{s}_1d.parquet")
        f = pd.read_parquet(XS / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    return b.sort_values("open_time").reset_index(drop=True), d.sort_values("open_time").reset_index(drop=True), f.sort_values("fundingTime")


def features(b, d, f):
    c = b["close"]
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()
    for k in (6, 42, 90, 180, 540):
        x[f"ret{k}"] = lc.diff(k)
        x[f"snr{k}"] = lc.diff(k) / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"]
    dfe = pd.DataFrame({"t": d["close_time"], "d50": np.log(dc / dc.rolling(50).mean()), "d200": np.log(dc / dc.rolling(200).mean()),
                        "rib": np.where((dc > dc.rolling(50).mean()) & (dc.rolling(50).mean() > dc.rolling(200).mean()), 1.0,
                                        np.where((dc < dc.rolling(50).mean()) & (dc.rolling(50).mean() < dc.rolling(200).mean()), -1.0, 0.0))})
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"]
    fm = pd.DataFrame({"t": fr.index, "f7": fr.rolling(21, min_periods=3).mean().to_numpy(), "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm, on="t", direction="backward")
    x["f7"], x["f30"] = jf["f7"].to_numpy() * 1e4, jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    y = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H)), -4, 4)
    return x, y


def build():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x, y = features(b, d, f)
        x["asset"] = i
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


FEATS = None


def train_predict(panel, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]  # label realized before the cutoff
    te = panel[(panel.t >= a) & (panel.t < end)]
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    m.fit(tr[FEATS], tr["y"])
    return te.assign(pred=m.predict(te[FEATS])), len(tr)


def weights_from(df, mode):
    """Per-asset weights (fraction of equity) from predictions or TSMOM, risk-parity, gross <= 1, daily rebalance."""
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        if mode == "model":
            sig = g["pred"].clip(lower=0) / 0.5  # 0.5 = one sd-unit edge maps to full size
        else:
            sig = (np.sign(g["ret42"]) + np.sign(g["ret180"])).clip(lower=0) / 2
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        W[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    n_assets = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(W.abs().sum(axis=1).clip(lower=1e-9), axis=0).mul(W.abs().sum(axis=1).gt(0), axis=0)
    W = W.mul((n_assets / len(SYMS)).clip(upper=1.0), axis=0)  # partial exposure when few assets qualify
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def simulate(panel, W, scale, fee, slip):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index)
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    long_funding = Wk.clip(lower=0).sum(axis=1) * 0.0001 * (1 / 2)  # 0.0001 per 8h -> per 4h bar
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - long_funding
    return net, turn


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1])
    return dict(net_pct=round(100 * (g - 1), 2), monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3),
                max_drawdown_percent=round(100 * float(np.max(1 - eq / eq.cummax())), 2),
                sharpe=round(float(net.mean() / net.std() * np.sqrt(PD * 365)), 2) if net.std() > 0 else 0.0,
                fills=int((turn > 1e-6).sum()), months=round(days / 30.4375, 1))


def main():
    global FEATS
    panel = build()
    FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    out = {"version": "v89", "anchors": [], "feature_list": FEATS}
    oos = {"model": [], "tsmom": []}
    for i, anchor in enumerate(ANCHORS):
        te, ntr = train_predict(panel, anchor)
        rec = dict(anchor=anchor, train_rows=ntr, ic=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
        for mode in ("model", "tsmom"):
            W = weights_from(te, mode)
            # portfolio scale from previous OOS years only (DD target 20%, cap 2x); first year K=1
            prev = pd.concat(oos[mode]) if oos[mode] else None
            if prev is None:
                K = 1.0
            else:
                eq = (1 + prev).cumprod()
                K = float(np.floor(min(2.0, 0.20 / max(float(np.max(1 - eq / eq.cummax())), 1e-6)) * 20) / 20)
            net, turn = simulate(panel, W, 1.0, *SCEN["normal"])
            oos[mode].append(net)  # unscaled record for future K
            for sc, (fee, slip) in SCEN.items():
                n2, t2 = simulate(panel, W, K, fee, slip)
                rec[f"{mode}_{sc}"] = stats(n2, t2)
            rec[f"{mode}_K"] = K
        out["anchors"].append(rec)
        print(anchor, "IC", rec["ic"], "| model normal", rec["model_normal"], "K", rec["model_K"], "| tsmom normal", rec["tsmom_normal"], "K", rec["tsmom_K"], flush=True)
    for mode in ("model", "tsmom"):
        for sc in SCEN:
            nets = [a[f"{mode}_{sc}"]["net_pct"] for a in out["anchors"]]
            geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
            out[f"{mode}_{sc}_5y"] = dict(geometric_annual_pct=round(100 * geo, 2), monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                                          worst_year_dd=max(a[f"{mode}_{sc}"]["max_drawdown_percent"] for a in out["anchors"]))
            print(mode, sc, out[f"{mode}_{sc}_5y"])
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v89_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
