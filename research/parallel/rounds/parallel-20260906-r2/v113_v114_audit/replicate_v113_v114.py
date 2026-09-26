"""Blind v113+v114 audit replication from OPENCODE_V113_V114_AUDIT.md spec.

Reads only raw data under data/raw/* (Binance USD-M, spot prefix, Coinbase 1h,
Bitstamp 1h). Does NOT read research/.../v113/* or research/.../v114/*
(blind until replication.json is saved).

A1 (v113): prepend to BTC and ETH (only rows with open_time before the first
  existing v92 4h/1d bar of that asset) bars aggregated from Coinbase 1h:
  concat(pre2017, main), dedup open_time, UTC resample label/closed left
  (open first, high max, low min, close last, volume sum,
  quote_volume=sum(volume*close)); keep 4h bars with >=3 hourly candles and
  1d bars with >=20; close_time = open_time + rule - 1ms. Other columns NaN.
A2 (v114): as A1 but BTC hourly = Bitstamp rows with open_time >= 2013-01-01
  and before the first Coinbase hour, then the Coinbase hours; ETH as A1.

On each extended panel (v92 features/labels/BTC context) retrain:
  v92 LO book (v92 HGB h=42, cutoff anchor-408h, vol target 0.20 cap 2),
  v94 LS (3x HGB h=18/42/84, cutoff anchor-576h, own vol target),
  v96 blend 0.5*W92*s92 + 0.5*W94*s94 (scale 1, v92 execution/costs).
Report per-anchor IC, train rows, yearly normal/fee/execution net/DD.
Scenarios (v92/v111 convention): normal fee 0.0002; fee_stress 0.0006;
execution_stress 0.0006 + slip 0.0005; funding 0.00005/bar on long gross.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H_V92 = 42
HS = (18, 42, 84)
EMBARGO_V92_BARS = H_V92 + 10 * PD  # 102 bars = 408h
EMBARGO_V94_BARS = 84 + 60  # 144 bars = 576h
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0),
        "execution_stress": (0.0006, 0.0005)}
PAIR = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}


def load_hourly_coinbase(pair):
    pre = pd.read_parquet(CB_DIR / f"{pair}_1h_pre2017.parquet")
    main = pd.read_parquet(CB_DIR / f"{pair}_1h.parquet")
    h = pd.concat([pre, main], ignore_index=True)
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    h = h.sort_values("open_time").drop_duplicates("open_time", keep="last")
    return h.sort_values("open_time").reset_index(drop=True)


def load_hourly_btc_v114(cb_btc):
    bs = pd.read_parquet(BS_FILE)
    bs["open_time"] = pd.to_datetime(bs["open_time"], utc=True)
    first_cb = cb_btc["open_time"].min()
    part = bs[(bs["open_time"] >= pd.Timestamp("2013-01-01", tz="UTC"))
              & (bs["open_time"] < first_cb)].copy()
    h = pd.concat([part, cb_btc], ignore_index=True)
    h = h.sort_values("open_time").drop_duplicates("open_time", keep="last")
    return h.sort_values("open_time").reset_index(drop=True)


def aggregate(hourly, rule):
    """UTC resample label/closed left from 1h candles."""
    h = hourly.sort_values("open_time").copy()
    for c in ("open", "high", "low", "close", "volume"):
        h[c] = h[c].astype(float)
    h["quote"] = h["volume"] * h["close"]
    freq = "4h" if rule == "4h" else "D"
    key = h["open_time"].dt.floor(freq).rename("grp")
    g = h.groupby(key)
    need = 3 if rule == "4h" else 20
    out = pd.DataFrame({
        "open_time": g["open_time"].first().to_numpy(),
        "open": g["open"].first().to_numpy(),
        "high": g["high"].max().to_numpy(),
        "low": g["low"].min().to_numpy(),
        "close": g["close"].last().to_numpy(),
        "volume": g["volume"].sum().to_numpy(),
        "quote_volume": g["quote"].sum().to_numpy(),
        "cnt": g.size().to_numpy(),
    })
    out["open_time"] = pd.to_datetime(out["open_time"], utc=True).dt.floor(freq)
    out = out[out["cnt"] >= need].copy()
    delta = pd.Timedelta(hours=4) if rule == "4h" else pd.Timedelta(days=1)
    out["close_time"] = out["open_time"] + delta - pd.Timedelta(milliseconds=1)
    out = out.sort_values("open_time").reset_index(drop=True)
    return out[["open_time", "open", "high", "low", "close", "volume",
                "quote_volume", "close_time", "cnt"]]


def load_base(sym):
    """v92 base bars: spot prefix (open_time < first USD-M) + USD-M."""
    if sym == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{sym}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{sym}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{sym}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    if not (SPOT_DIR / f"{sym}_spot_4h_2017.parquet").exists():
        s4 = b.iloc[:0].copy()
        s1 = d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    first_4h = b["open_time"].min()
    first_1d = d["open_time"].min()
    pre4 = s4[s4["open_time"] < first_4h].copy()
    pre1 = s1[s1["open_time"] < first_1d].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def extend_asset(sym, base_b, base_d, agg4, agg1):
    first_4h = base_b["open_time"].min()
    first_1d = base_d["open_time"].min()
    add4 = agg4[agg4["open_time"] < first_4h].copy() if agg4 is not None else base_b.iloc[:0].copy()
    add1 = agg1[agg1["open_time"] < first_1d].copy() if agg1 is not None else base_d.iloc[:0].copy()
    b = pd.concat([add4, base_b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([add1, base_d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d


def features(b, d, f):
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()
    for k in (6, 42, 90, 180, 540):
        dk = lc.diff(k)
        x[f"ret{k}"] = dk
        x[f"snr{k}"] = dk / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"].astype(float)
    sma50 = dc.rolling(50).mean()
    sma200 = dc.rolling(200).mean()
    dfe = pd.DataFrame({
        "t": d["close_time"],
        "d50": np.log(dc / sma50),
        "d200": np.log(dc / sma200),
        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0,
                        np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0)),
    })
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index,
                       "f7": fr.rolling(21, min_periods=3).mean().to_numpy(),
                       "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"] = jf["f7"].to_numpy() * 1e4
    x["f30"] = jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    for h in HS:
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(h)), -4, 4)
    x["y"] = x["y42"]
    return x


def build_panel(ext_bars):
    """ext_bars: dict sym -> (b, d, f)."""
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = ext_bars[s]
        x = features(b, d, f)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


FEATS = None


def train_predict_v92(panel, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V92_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB_PARAMS)
    m.fit(tr[FEATS], tr["y"])
    te["pred"] = m.predict(te[FEATS])
    return te, len(tr)


def train_predict_v94(panel, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V94_BARS)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS)))
    ntrs = []
    for j, h in enumerate(HS):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB_PARAMS)
        m.fit(tr[FEATS], tr[yh])
        preds[:, j] = m.predict(te[FEATS])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def weights_lo(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def weights_ls(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        Wdict[s] = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def vol_scale(o, W, target=0.20):
    ret1 = o / o.shift(1) - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (target / vol).clip(upper=2.0).fillna(1.0)
    return scale.replace([np.inf, -np.inf], 2.0).fillna(1.0), book, vol


def simulate(o, W, scale, fee, slip=0.0):
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def yearly(net, turn):
    out = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = anchor
        out.append(st)
    return out


def run_extension(tag, hourly_btc, hourly_eth):
    global FEATS
    agg = {}
    for sym, h in (("BTCUSDT", hourly_btc), ("ETHUSDT", hourly_eth)):
        agg[sym] = (aggregate(h, "4h"), aggregate(h, "1d"))
    ext = {}
    base_info = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        base_info[s] = (str(b0["open_time"].min()), str(d0["open_time"].min()),
                        int(len(b0)), int(len(d0)))
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
    n4 = {s: int(len(ext[s][0])) for s in SYMS}
    n1 = {s: int(len(ext[s][1])) for s in SYMS}
    pre4 = {s: int(n4[s] - base_info[s][2]) for s in ("BTCUSDT", "ETHUSDT")}
    pre1 = {s: int(n1[s] - base_info[s][3]) for s in ("BTCUSDT", "ETHUSDT")}
    panel = build_panel(ext)
    FEATS = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y", "y18", "y42", "y84")]
    o = panel.pivot_table(index="t", columns="sym", values="open").sort_index()
    o = o[list(SYMS)]
    # v92 LO
    v92_anchors, parts92 = [], []
    for anchor in ANCHORS:
        te, ntr = train_predict_v92(panel, anchor)
        ev = te.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        v92_anchors.append(dict(anchor=anchor, train_rows=int(ntr),
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)),
                                ic=round(rho, 4)))
        parts92.append(te)
        print(tag, "v92", anchor, ntr, round(rho, 4), flush=True)
    oos92 = pd.concat(parts92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = weights_lo(oos92)
    o_oos = o.loc[W92.index].copy()
    s92, _, _ = vol_scale(o_oos, W92)
    # v94 LS
    v94_anchors, parts94 = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v94(panel, anchor)
        ev = te.dropna(subset=["y42"])
        rho = float(spearmanr(ev["pred"], ev["y42"]).statistic) if len(ev) > 2 else float("nan")
        v94_anchors.append(dict(anchor=anchor, train_rows_h18=ntrs[0],
                                train_rows_h42=ntrs[1], train_rows_h84=ntrs[2],
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)),
                                ic_mean_vs_h42=round(rho, 4)))
        parts94.append(te)
        print(tag, "v94", anchor, ntrs, round(rho, 4), flush=True)
    oos94 = pd.concat(parts94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W94 = weights_ls(oos94)
    assert (W94.index == W92.index).all(), "v92/v94 OOS index mismatch"
    s94, _, _ = vol_scale(o_oos, W94)
    Wb = 0.5 * W92.mul(s92, axis=0) + 0.5 * W94.mul(s94, axis=0)
    books = {"v92_lo": (W92, s92), "v94_ls": (W94, s94), "v96_blend": (Wb, 1.0)}
    scen_yearly = {}
    scen_nets = {}
    for book_name, (W, sc) in books.items():
        scale = sc if not isinstance(sc, float) else sc
        for scen, (fee, slip) in SCEN.items():
            if book_name == "v96_blend":
                r = (o_oos.shift(-2) / o_oos.shift(-1) - 1).fillna(0.0)
                turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
                funding = W.clip(lower=0).sum(axis=1) * 0.00005
                net = (W * r).sum(axis=1) - turn * (fee + slip) - funding
            else:
                net, turn = simulate(o_oos, W, scale, fee, slip)
            scen_yearly[f"{book_name}_{scen}"] = yearly(net, turn)
            scen_nets[(book_name, scen)] = (net, turn)
    # save CSVs (normal only to limit size; others in json)
    oos92[["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(
        OUT_DIR / f"predictions_{tag}_v92.csv", index=False)
    oos94[["t", "sym", "open", "pred", "pred_h18", "pred_h42", "pred_h84", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / f"predictions_{tag}_v94.csv", index=False)
    for (bn, sc), (net, turn) in scen_nets.items():
        if sc == "normal":
            sc_series = books[bn][1]
            sc_out = sc_series if not isinstance(sc_series, float) else pd.Series(1.0, index=net.index)
            pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values,
                          "scale": sc_out.reindex(net.index).fillna(1.0).values}).to_csv(
                OUT_DIR / f"equity_{tag}_{bn}_{sc}.csv", index=False)
    return dict(anchors_v92=v92_anchors, anchors_v94=v94_anchors,
                yearly=scen_yearly, n4=n4, n1=n1, pre4=pre4, pre1=pre1,
                base_info=base_info,
                agg_counts={s: (int(len(agg[s][0])), int(len(agg[s][1]))) for s in agg})


def main():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    r113 = run_extension("v113", cb_btc, cb_eth)
    r114 = run_extension("v114", bs_btc, cb_eth)
    result = {
        "v113": r113,
        "v114": r114,
        "model": HGB_PARAMS,
        "features": FEATS,
        "assets": list(SYMS),
        "cutoffs_v92": {a: str(pd.Timestamp(a, tz="UTC") - pd.Timedelta(hours=4 * EMBARGO_V92_BARS)) for a in ANCHORS},
        "cutoffs_v94": {a: str(pd.Timestamp(a, tz="UTC") - pd.Timedelta(hours=4 * EMBARGO_V94_BARS)) for a in ANCHORS},
        "scenarios": {k: {"fee": v[0], "slip": v[1], "funding_long_per_4h": 0.00005} for k, v in SCEN.items()},
        "data": {
            "coinbase": "data/raw/coinbase_20260925/{BTC,ETH}-USD_1h_pre2017.parquet + {BTC,ETH}-USD_1h.parquet concat dedup open_time",
            "bitstamp": "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet open_time >= 2013-01-01 and < first Coinbase hour, then Coinbase hours (BTC v114 only)",
            "agg": "UTC floor label/closed left; 4h keep cnt>=3; 1d keep cnt>=20; close_time=open_time+rule-1ms; quote_volume=sum(volume*close); others NaN",
            "prepend_filter": "agg bars with open_time < first existing v92 4h/1d bar per asset (BTC/ETH only); SOL/BNB/XRP = v92 base",
            "usdm": "data/raw/ma_ribbon_20260924 (BTC) + data/raw/xs_universe_20260924 (others)",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar",
        },
        "execution": {
            "v92_lo": "s=min(max(pred,0)/0.5,1) zeroed if rib==-1; raw=s/(vol42*sqrt(2190)); /sum|raw| *min(1,count_pos/5); every 6th bar ffill; vol target 0.20 cap2 (rolling360 min120); W*s earns o[t+2]/o[t+1]-1",
            "v94_ls": "long=min(max(p,0)/0.5,1) zeroed if rib==-1; short=min(max(-p,0)/0.5,1) zeroed if rib==+1; raw=(long-short)/(vol42*sqrt(2190)); /sum|raw| *min(1,count_nz/5); every 6th bar ffill; own vol target 0.20 cap2",
            "v96_blend": "Wc=0.5*W92*s92 + 0.5*W94*s94 (scale 1); net=sum Wc*r_fwd - turn*(fee+slip) - long_gross*0.00005",
        },
        "assumptions": [
            "features identical to v92 5-asset replication (26 feats incl asset id + btc_ prefix); HGB NaN-native.",
            "yearly slices [A,A+365d); 2190 bars/year; OOS 2021-09-24..2026-09-23.",
            "vol scales causal (W.shift(2) book, trailing window, NaN->1); scenarios differ only in fee/slip.",
            "fills = bars with turnover > 1e-6; blend turnover on combined Wc.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk.startswith("anchors")} for k, v in
                      (("v113", r113), ("v114", r114))}, indent=2))


if __name__ == "__main__":
    main()
