"""Blind v140 audit replication (Part A).
Does NOT read research/.../v140/*.
Base: audited v132_v133 replication (v133 configuration, 5-asset).

Blind spec (OPENCODE_V140_AUDIT.md):
  per asset (time order) r[k]=log(open[k]/open[k-1]);
  for horizon h: R=log(open[t+1+h]/open[t+1]);
  fv=rolling-h std of r shifted by -(h+1) (=std of r[t+2..t+1+h]);
  s_h=clip(R/(fv*sqrt(h)),-4,4), non-finite -> NaN.
  Targets: v92 on s42 (v92 feats, v92 cutoff/embargo 102, rows need s42
    and t+43*4h<cutoff); v94 on s18/s42/s84 (v94 feats = all non-target
    cols excluding y* and s<digits>, v94 embargo 144); v103 on s6/s18
    (v103 feats, embargo 78). HGB v92 params; v94/v103 pred = mean over
    horizons; then v133 pipeline (pvol swap with v129 vol models,
    tranching, portfolio 0.15). Report v92 IC vs s42 and vs y per anchor
    and three scenarios with full-path DD.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent

SYMS5 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0),
        "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102
HS_V94 = (18, 42, 84)
EMB_V94 = 144
HS_V103 = (6, 18)
EMB_V103 = 78
H_V92 = 42
EMB_V92 = 102
HS_S = (6, 18, 42, 84)

BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"


# ---------- shared weight/scale/engine (identical to v132_v133 replication) ----------
def weights_lo_from_oos(oos, n_assets):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wd[s] = sig / (g["vol42"].astype(float) * ANN)
    W = pd.DataFrame(Wd).sort_index().fillna(0.0)
    gross = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_pos / n_assets).clip(upper=1.0), axis=0)
    return W


def weights_ls_from_oos(oos, n_assets):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long_ - short) / (g["vol42"].astype(float) * ANN)
        Wd[s] = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rawW = pd.DataFrame(Wd).sort_index()
    gross = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_nz / n_assets).clip(upper=1.0), axis=0).fillna(0.0)
    return W


def tranche_mean(W_raw):
    phases = []
    for ph in range(PD):
        keep = pd.Series(np.arange(len(W_raw)) % PD == ph, index=W_raw.index)
        phases.append(W_raw.where(keep, np.nan).ffill().fillna(0.0))
    return sum(phases) / len(phases), phases


def vol_scale(o, W, target=0.20):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    sc = (target / vol).clip(upper=CAP).fillna(1.0)
    return sc.replace([np.inf, -np.inf], CAP).fillna(1.0)


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(
        net_pct=round(100 * (g - 1), 2),
        monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
        max_drawdown_percent=round(100 * dd, 2),
        sharpe=round(float(net.mean() / net.std() * ANN), 2) if float(net.std()) > 0 else 0.0,
        fills=int((turn > 1e-6).sum()),
        months=round(days / 30.4375, 1),
    )


def yearly(net, turn):
    out = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = a
        out.append(st)
    return out


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
    prev_w = np.zeros(k)
    prev_c = 0.0
    for i in range(n):
        if live_mask[i]:
            w = W_BOOKS * s_vals[i] * books_vals[i]
            c = W_CARRY * CARRY_LEV * s_vals[i]
        else:
            w = np.zeros(k)
            c = 0.0
        gross = float(np.sum(w * fwd[i]))
        tcost = float(np.sum(np.abs(w - prev_w)) * (fee + slip))
        fund = float(np.sum(np.maximum(w, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * 2 * 0.0004 / 1.2)
        net[i] = gross - tcost - fund + cgross - ccost
        turn[i] = float(np.sum(np.abs(w - prev_w)))
        prev_w, prev_c = w, c
    return net, turn


def summarize_seq(net_s, turn_s):
    ys = yearly(net_s, turn_s)
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


# ---------- panels (identical to v132_v133 replication) ----------
def load_hourly_coinbase(pair):
    pre = pd.read_parquet(CB_DIR / f"{pair}_1h_pre2017.parquet")
    main = pd.read_parquet(CB_DIR / f"{pair}_1h.parquet")
    h = pd.concat([pre, main], ignore_index=True)
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    return h.sort_values("open_time").drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)


def load_hourly_btc_v114(cb_btc):
    bs = pd.read_parquet(BS_FILE)
    bs["open_time"] = pd.to_datetime(bs["open_time"], utc=True)
    first_cb = cb_btc["open_time"].min()
    part = bs[(bs["open_time"] >= pd.Timestamp("2013-01-01", tz="UTC")) & (bs["open_time"] < first_cb)].copy()
    h = pd.concat([part, cb_btc], ignore_index=True)
    return h.sort_values("open_time").drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)


def aggregate(hourly, rule):
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
    return out[["open_time", "open", "high", "low", "close", "volume", "quote_volume", "close_time", "cnt"]].sort_values("open_time").reset_index(drop=True)


def load_base(sym):
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
    if not (SPOT_DIR / f"{sym}_spot_4h_2017.parquet").exists():
        s4, s1 = b.iloc[:0].copy(), d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    pre4 = s4[s4["open_time"] < b["open_time"].min()].copy()
    pre1 = s1[s1["open_time"] < d["open_time"].min()].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def extend_asset(sym, base_b, base_d, agg4, agg1):
    add4 = agg4[agg4["open_time"] < base_b["open_time"].min()].copy() if agg4 is not None else base_b.iloc[:0].copy()
    add1 = agg1[agg1["open_time"] < base_d["open_time"].min()].copy() if agg1 is not None else base_d.iloc[:0].copy()
    b = pd.concat([add4, base_b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([add1, base_d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d


def features_base(b, d, f, with_flow):
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
    if with_flow:
        qv = b["quote_volume"].astype(float).clip(lower=1)
        tbqv = b["taker_buy_quote_volume"].astype(float)
        tbr1 = (tbqv / qv).clip(lower=0, upper=1)
        x["tbr_1"] = tbr1.rolling(1).mean() - 0.5
        x["tbr_6"] = tbr1.rolling(6).mean() - 0.5
        x["tbr_42"] = tbr1.rolling(42).mean() - 0.5
        signed = (2 * tbr1 - 1) * qv
        x["flow_6"] = signed.rolling(6).sum() / qv.rolling(6).sum()
        x["flow_42"] = signed.rolling(42).sum() / qv.rolling(42).sum()
        x["tbr_z"] = (tbr1.rolling(6).mean() - tbr1.rolling(180).mean()) / tbr1.rolling(180).std()
        ntr_raw = b["num_trades"].astype(float).clip(lower=1)
        tsize_raw = np.log(qv / ntr_raw)
        ntr_log = np.log(ntr_raw)
        x["tsize_z"] = (tsize_raw - tsize_raw.rolling(180).mean()) / tsize_raw.rolling(180).std()
        x["ntr_z"] = (ntr_log - ntr_log.rolling(180).mean()) / ntr_log.rolling(180).std()
        hl = np.log(b["high"].astype(float) / b["low"].astype(float))
        x["rng6"] = hl.rolling(6).mean() / vol42
        rng = (b["high"].astype(float) - b["low"].astype(float))
        clv = (b["close"].astype(float) - b["low"].astype(float)) / rng
        clv = clv.where(rng != 0, np.nan)
        x["clv6"] = clv.rolling(6).mean() - 0.5
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    v42 = vol42.to_numpy()
    for h in (6, 18, 42, 84):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (v42 * np.sqrt(h)), -4, 4)
    x["y"] = x["y42"]
    return x


def build_v114_panel(syms):
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    ext = {}
    bars = {}
    for s in syms:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
        bars[s] = b
    rows = []
    for i, s in enumerate(syms):
        b, d, f = ext[s]
        x = features_base(b, d, f, with_flow=False)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel, bars, ext


def build_v103_panel(syms):
    rows = []
    bars = {}
    for i, s in enumerate(syms):
        b, d, f = load_base(s)
        bars[s] = b
        x = features_base(b, d, f, with_flow=True)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel, bars


def build_panels(syms):
    panel114, bars114, _ = build_v114_panel(syms)
    panel103, bars103 = build_v103_panel(syms)
    return panel114, panel103, bars114, bars103


# ---------- v140 forward-sharpe targets ----------
def add_s_targets(panel):
    """Per asset time order: r[k]=log(open[k]/open[k-1]); R=log(open[t+1+h]/open[t+1]);
    fv=rolling-h std of r shifted by -(h+1); s=clip(R/(fv*sqrt(h)),-4,4), non-finite->NaN."""
    panel = panel.copy()
    for h in HS_S:
        panel[f"s{h}"] = np.nan
    for s, idx in panel.groupby("sym").groups.items():
        sub = panel.loc[idx].sort_values("t")
        o = sub["open"].astype(float)
        r = np.log(o / o.shift(1))
        for h in HS_S:
            roll = r.rolling(h, min_periods=h).std(ddof=1)
            fv = roll.shift(-(h + 1))
            R = np.log(o.shift(-(1 + h)) / o.shift(-1))
            with np.errstate(divide="ignore", invalid="ignore"):
                s_h = R / (fv * np.sqrt(h))
            s_h = s_h.clip(lower=-4, upper=4)
            s_h[~np.isfinite(s_h)] = np.nan
            panel.loc[sub.index, f"s{h}"] = s_h.to_numpy()
    return panel


# ---------- training on s targets ----------
def train_v92_s42(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V92)
    tr = panel[(panel.t < cutoff) & panel["s42"].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB)
    m.fit(tr[feats], tr["s42"])
    te["pred"] = m.predict(te[feats])
    return te, int(len(tr))


def train_v94_s(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V94)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V94)))
    ntrs = []
    for j, h in enumerate(HS_V94):
        yh = f"s{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS_V94):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def train_v103_s(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"s{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS_V103):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def add_fv(bars):
    out = {}
    for s, b in bars.items():
        lo = np.log(b["open"].astype(float))
        r = lo.diff()
        s42 = r.rolling(42).std(ddof=1)
        fv = np.log(s42.shift(-43))
        out[s] = (fv.to_numpy(), s42.shift(-43).to_numpy())
    return out


def train_pvol(panel, feats, bars):
    fv_map = add_fv(bars)
    panel = panel.copy()
    panel["fv"] = np.nan
    panel["realized_vol"] = np.nan
    for s in panel["sym"].unique():
        m = panel["sym"] == s
        fv_arr, rv_arr = fv_map[s]
        tmp = pd.DataFrame({"t": bars[s]["open_time"].to_numpy(), "fv": fv_arr, "rv": rv_arr})
        tmp["t"] = pd.to_datetime(tmp["t"], utc=True)
        j = panel.loc[m, ["t"]].merge(tmp, on="t", how="left")
        panel.loc[m, "fv"] = j["fv"].to_numpy()
        panel.loc[m, "realized_vol"] = j["rv"].to_numpy()
    anchors = []
    parts = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_VOL)
        tr = panel[(panel.t < cutoff) & panel["fv"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * 44) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr["fv"])
        te["pred_fv"] = m.predict(te[feats])
        te["pvol"] = np.exp(te["pred_fv"])
        rho_p = spearman(te["pvol"], te["realized_vol"])
        rho_v = spearman(te["vol42"], te["realized_vol"])
        anchors.append(dict(anchor=anchor, train_rows=int(len(tr)), n_pred_rows=int(len(te)),
                            n_eval_rows=int((te["realized_vol"].notna()).sum()),
                            spearman_pvol_realized=round(float(rho_p), 4) if np.isfinite(rho_p) else None,
                            spearman_vol42_realized=round(float(rho_v), 4) if np.isfinite(rho_v) else None))
        parts.append(te)
        print(f"pvol {anchor} tr={len(tr)} rho_p={anchors[-1]['spearman_pvol_realized']} rho_v={anchors[-1]['spearman_vol42_realized']}", flush=True)
    oos = pd.concat(parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    return oos, anchors


def per_asset_ic(oos, pred_col, target_col):
    out = {}
    for s, g in oos.groupby("sym"):
        ic = spearman(g[pred_col], g[target_col])
        out[s] = round(float(ic), 4) if np.isfinite(ic) else None
    pooled = spearman(oos[pred_col], oos[target_col])
    out["_pooled"] = round(float(pooled), 4) if np.isfinite(pooled) else None
    out["_n_rows"] = int(len(oos))
    return out


def main():
    panel114, panel103, bars114, bars103 = build_panels(SYMS5)
    panel114 = add_s_targets(panel114)
    panel103 = add_s_targets(panel103)
    EXCL114 = ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
               "s6", "s18", "s42", "s84",
               "fv", "realized_vol", "pred_fv", "pvol")
    EXCL103 = ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
               "y", "s6", "s18", "s42", "s84",
               "fv", "realized_vol", "pred", "pred_fv", "pvol",
               "pred_h6", "pred_h18", "pred_h42", "pred_h84")
    feats114 = [c for c in panel114.columns if c not in EXCL114]
    feats103 = [c for c in panel103.columns if c not in EXCL103]
    print(f"feats114={len(feats114)} feats103={len(feats103)}", flush=True)
    print(f"feats114={feats114}", flush=True)

    p92, a92 = [], []
    p94, a94 = [], []
    p103, a103 = [], []
    for anchor in ANCHORS:
        te92, ntr92 = train_v92_s42(panel114, feats114, anchor)
        ev_s = te92.dropna(subset=["s42"])
        rho_s = float(spearmanr(ev_s["pred"], ev_s["s42"]).statistic) if len(ev_s) > 2 else float("nan")
        ev_y = te92.dropna(subset=["y"])
        rho_y = float(spearmanr(ev_y["pred"], ev_y["y"]).statistic) if len(ev_y) > 2 else float("nan")
        a92.append(dict(anchor=anchor, train_rows=int(ntr92), n_pred_rows=int(len(te92)),
                        n_pred_rows_with_s42=int(len(ev_s)), n_pred_rows_with_y=int(len(ev_y)),
                        ic_vs_s42=round(rho_s, 4), ic_vs_y=round(rho_y, 4)))
        p92.append(te92)
        print("v92s", anchor, ntr92, round(rho_s, 4), round(rho_y, 4), flush=True)
        te94, ntrs94 = train_v94_s(panel114, feats114, anchor)
        ev94 = te94.dropna(subset=["s42"])
        rho94 = float(spearmanr(ev94["pred"], ev94["s42"]).statistic) if len(ev94) > 2 else float("nan")
        a94.append(dict(anchor=anchor, train_rows_h18=ntrs94[0], train_rows_h42=ntrs94[1],
                        train_rows_h84=ntrs94[2], n_pred_rows=int(len(te94)),
                        n_pred_rows_with_s42=int(len(ev94)), ic_mean_vs_s42=round(rho94, 4)))
        p94.append(te94)
        print("v94s", anchor, ntrs94, round(rho94, 4), flush=True)
        te103, ntrs103 = train_v103_s(panel103, feats103, anchor)
        ic6 = spearman(te103["pred"], te103["s6"])
        ic18 = spearman(te103["pred"], te103["s18"])
        a103.append(dict(anchor=anchor, train_rows_h6=ntrs103[0], train_rows_h18=ntrs103[1],
                         n_pred_rows=int(len(te103)),
                         ic_vs_s6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                         ic_vs_s18=round(float(ic18), 4) if np.isfinite(ic18) else None))
        p103.append(te103)
        print("v103s", anchor, ntrs103, round(float(ic6), 4), round(float(ic18), 4), flush=True)
    oos92 = pd.concat(p92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94 = pd.concat(p94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103 = pd.concat(p103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)

    ic92_s42 = per_asset_ic(oos92.dropna(subset=["s42"]), "pred", "s42")
    ic92_y = per_asset_ic(oos92.dropna(subset=["y"]), "pred", "y")
    ic94_s42 = per_asset_ic(oos94.dropna(subset=["s42"]), "pred", "s42")
    ic103_s6 = per_asset_ic(oos103.dropna(subset=["s6"]), "pred", "s6")
    ic103_s18 = per_asset_ic(oos103.dropna(subset=["s18"]), "pred", "s18")

    # v133 pipeline: pvol swap with v129 vol models, tranching, portfolio 0.15
    oos114_pvol, av114 = train_pvol(panel114, feats114, bars114)
    oos103_pvol, av103 = train_pvol(panel103, feats103, bars103)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    o92_p, n_lo = replace_vol(oos92.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o94_p, n_ls = replace_vol(oos94.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = replace_vol(oos103.sort_values(["t", "sym"]).reset_index(drop=True), j103)
    Wlo_p = weights_lo_from_oos(o92_p, 5)
    W94_p = weights_ls_from_oos(o94_p, 5)
    W103_p = weights_ls_from_oos(o103_p, 5)
    Wlo_t, _ = tranche_mean(Wlo_p)
    W94_t, _ = tranche_mean(W94_p)
    W103_t, _ = tranche_mean(W103_p)
    o_v114 = o92_p.pivot_table(index="t", columns="sym", values="open")[list(SYMS5)].sort_index()
    o_v103 = o103_p.pivot_table(index="t", columns="sym", values="open")[list(SYMS5)].sort_index()
    s_lo_t = vol_scale(o_v114.reindex(Wlo_t.index).ffill(), Wlo_t)
    s94_t = vol_scale(o_v114.reindex(W94_t.index).ffill(), W94_t)
    s103_t = vol_scale(o_v103.reindex(W103_t.index), W103_t)
    idx = Wlo_t.index.union(W94_t.index).union(W103_t.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo_t = Wlo_t.reindex(idx).fillna(0.0).mul(s_lo_t.reindex(idx).fillna(1.0), axis=0)
    b94_t = W94_t.reindex(idx).fillna(0.0).mul(s94_t.reindex(idx).fillna(1.0), axis=0)
    b103_t = W103_t.reindex(idx).fillna(0.0).mul(s103_t.reindex(idx).fillna(1.0), axis=0)
    books_t = 0.25 * b_lo_t + 0.25 * b94_t + 0.5 * b103_t
    o = o_v103.reindex(idx).sort_index()
    books_t = books_t[o.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books_t.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15_t = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books_t.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s15_t.to_numpy(dtype=float)
    scenarios = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        scenarios[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
        print("tranched", sc, scenarios[sc]["monthly_pct"], scenarios[sc]["full_path_dd"], flush=True)

    out = {
        "version": "v140_audit_replication",
        "anchors": list(ANCHORS),
        "scenarios_spec": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        "anchors_v92": a92,
        "anchors_v94": a94,
        "anchors_v103": a103,
        "ic_per_asset": dict(v92_vs_s42=ic92_s42, v92_vs_y=ic92_y, v94_vs_s42=ic94_s42,
                             v103_vs_s6=ic103_s6, v103_vs_s18=ic103_s18),
        "anchors_pvol_v114": av114,
        "anchors_pvol_v103": av103,
        "n_replaced": dict(v92=int(n_lo), v94=int(n_ls), v103=int(n_103)),
        "scenarios": scenarios,
        "feats114": feats114,
        "feats103": feats103,
        "union_bars": int(len(idx)),
        "oos_span": [str(idx[0]), str(idx[-1])],
        "meta": {
            "spec": "per asset time order r=log(open/open[-1]); R=log(open[t+1+h]/open[t+1]); fv=rolling-h std(ddof=1,min=h) of r shift(-(h+1)); s=clip(R/(fv*sqrt(h)),-4,4) non-finite->NaN; v92 s42 cutoff-102h t+43h<cutoff; v94 s18/s42/s84 cutoff-144h t+(h+1)h<cutoff mean; v103 s6/s18 cutoff-78h t+(h+1)h<cutoff mean; HGB v92 params; v133 pipeline 5-asset v114-extended+v103-base pvol-swap tranche 0.25/0.25/0.5 target 0.15 sequential v110",
            "choices": "5-asset universe (v133 config); v114 extended Bitstamp>=2013-01-01+Coinbase BTC/Coinbase ETH + spot_2017 prefix where exists; v103 base + flow feats; feats exclude y*,s*; pvol v129 method fv=log roll42 std shift-43 cutoff-102h t+44h<cutoff exp(pred) left-join replace; tranche_mean + own 0.20-cap-2 scales (W.shift(2) trailing 360/min-120) + sequential engine + carry_oos_fee0.0004",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"anchors_v92": a92, "scenarios": {k: {"m": v["monthly_pct"], "dd": v["full_path_dd"]} for k, v in scenarios.items()}}, indent=2))


if __name__ == "__main__":
    main()
