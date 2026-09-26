"""Blind v138+v139 audit replication (Part A).
Does NOT read research/.../v138/* nor research/.../v139/*.

Base: audited v132_v133 replication (v133 configuration, 5-asset tranched + pvol).

Blind specs implemented:
A1 (v138): for every v133 model (v92 y H=42; v94 18/42/84; v103 6/18;
  audited cutoffs/embargoes/row filters) fit HGB (v92 params) and
  Ridge(alpha=10) on standardized features: training medians fill NaN, then
  (x - train mean)/train std (std 0 -> 1, population ddof=0), clip +-5,
  remaining NaN -> 0. sd_h = std (population ddof=0) of HGB in-sample
  predictions on standardized training features, sd_r = std of ridge
  in-sample predictions; blend = 0.5*hgb + 0.5*sd_h*ridge/sd_r
  (sd_r 0/nonfinite -> 1). v94/v103 = mean over horizons (per-horizon blend
  then mean). Then v133 pipeline (pvol replace, tranched books, own scales,
  books 0.25/0.25/0.5, sequential v110 engine target 0.15). Report v92 IC per
  anchor for hgb/ridge/blend and three scenarios with full-path DD
  (scenarios reported for blend, hgb-only and ridge-only).
A2 (v139): positioning features from data/raw/um_metrics_20260926/
  {SYM}_metrics.parquet: for each v103-panel 4h row take the last metrics row
  with create_time <= t + 4h - 5min (asof backward, tolerance 4h);
  oi = log(sum_open_interest_value) where >0 else NaN,
  top = log(sum_toptrader_long_short_ratio) where >0 else NaN,
  crowd = log(count_long_short_ratio) where >0 else NaN,
  taker = log(sum_taker_long_short_vol_ratio) where >0 else NaN;
  oi_chg6 = diff(oi,6), oi_chg42 = diff(oi,42),
  z(s) = (s - rolling180 mean(min 90))/rolling180 std(min 90, ddof=1);
  oi_z = z(oi), top_ls = top, top_ls_chg6 = diff(top,6), top_ls_z = z(top),
  crowd_ls_z = z(crowd), taker_ls6 = rolling6 mean(min 3) of taker,
  per asset in time order. 8 features added to v103 features only
  (pos_ prefix); v103 vol forecast uses base features without these;
  v133 pipeline. Report coverage, v103 IC and three scenarios.

Blind choices documented in replication.json meta.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

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

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
UM_DIR = ROOT / "data/raw/um_metrics_20260926"

POS_FEATS = ["pos_oi_chg6", "pos_oi_chg42", "pos_oi_z", "pos_top_ls",
             "pos_top_ls_chg6", "pos_top_ls_z", "pos_crowd_ls_z", "pos_taker_ls6"]


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


def standardize_fit_transform(tr, te):
    med = tr.median()
    tr_m = tr.fillna(med)
    te_m = te.fillna(med)
    mu = tr_m.mean()
    sd = tr_m.std(ddof=0)
    sd = sd.replace(0.0, 1.0).fillna(1.0)
    tr_s = ((tr_m - mu) / sd).clip(-5, 5).fillna(0.0)
    te_s = ((te_m - mu) / sd).clip(-5, 5).fillna(0.0)
    return tr_s, te_s


def fit_hgb_ridge_blend(tr_X, tr_y, te_X):
    tr_s, te_s = standardize_fit_transform(tr_X, te_X)
    mh = HistGradientBoostingRegressor(**HGB)
    mh.fit(tr_s, tr_y)
    mr = Ridge(alpha=10)
    mr.fit(tr_s, tr_y)
    ph_tr = mh.predict(tr_s)
    pr_tr = mr.predict(tr_s)
    sd_h = float(np.std(ph_tr, ddof=0))
    sd_r = float(np.std(pr_tr, ddof=0))
    if not np.isfinite(sd_h):
        sd_h = 0.0
    if (not np.isfinite(sd_r)) or sd_r == 0.0:
        sd_r = 1.0
    ph = mh.predict(te_s)
    pr = mr.predict(te_s)
    blend = 0.5 * ph + 0.5 * sd_h * pr / sd_r
    return ph, pr, blend, sd_h, sd_r, int(len(tr_X))


def train_blend_single(panel, feats, anchor, ycol, embargo_bars, horizon):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * embargo_bars)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    tr = panel[(panel.t < cutoff) & panel[ycol].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (horizon + 1)) < cutoff]
    tr_X, te_X = tr[feats], te[feats]
    tr_y = tr[ycol].to_numpy()
    ph, pr, pb, sdh, sdr, ntr = fit_hgb_ridge_blend(tr_X, tr_y, te_X)
    te = te.copy()
    te["pred_hgb"] = ph
    te["pred_ridge"] = pr
    te["pred_blend"] = pb
    return te, ntr, sdh, sdr


def train_blend_multi(panel, feats, anchor, horizons, embargo_bars):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    te_base = panel[(panel.t >= a) & (panel.t < end)].copy().reset_index(drop=True)
    n_h = len(horizons)
    Ph = np.zeros((len(te_base), n_h))
    Pr = np.zeros((len(te_base), n_h))
    Pb = np.zeros((len(te_base), n_h))
    ntrs, sdhs, sdrs = [], [], []
    for j, h in enumerate(horizons):
        yh = f"y{h}"
        cutoff = a - pd.Timedelta(hours=4 * embargo_bars)
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ph, pr, pb, sdh, sdr, ntr = fit_hgb_ridge_blend(tr[feats], tr[yh].to_numpy(), te_base[feats])
        Ph[:, j], Pr[:, j], Pb[:, j] = ph, pr, pb
        ntrs.append(int(ntr))
        sdhs.append(float(sdh))
        sdrs.append(float(sdr))
    te_base["pred_hgb"] = Ph.mean(axis=1)
    te_base["pred_ridge"] = Pr.mean(axis=1)
    te_base["pred_blend"] = Pb.mean(axis=1)
    for j, h in enumerate(horizons):
        te_base[f"hgb_h{h}"] = Ph[:, j]
        te_base[f"ridge_h{h}"] = Pr[:, j]
        te_base[f"blend_h{h}"] = Pb[:, j]
    return te_base, ntrs, sdhs, sdrs


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
        print(f"pvol {anchor} tr={len(tr)} rho_p={anchors[-1]['spearman_pvol_realized']}", flush=True)
    oos = pd.concat(parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    return oos, anchors


def build_positioning(bars103):
    frames = []
    for sym in SYMS5:
        b = bars103[sym][["open_time"]].copy()
        b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
        b = b.sort_values("open_time").reset_index(drop=True)
        b["target"] = b["open_time"] + pd.Timedelta(hours=4) - pd.Timedelta(minutes=5)
        mp = pd.read_parquet(UM_DIR / f"{sym}_metrics.parquet")
        mp["create_time"] = pd.to_datetime(mp["create_time"], utc=True)
        mp = mp.sort_values("create_time")
        left = b.sort_values("target")
        m = pd.merge_asof(left, mp, left_on="target", right_on="create_time",
                          direction="backward", tolerance=pd.Timedelta(hours=4))
        m = m.sort_values("open_time").reset_index(drop=True)
        oi_raw = m["sum_open_interest_value"].astype(float)
        top_raw = m["sum_toptrader_long_short_ratio"].astype(float)
        crowd_raw = m["count_long_short_ratio"].astype(float)
        taker_raw = m["sum_taker_long_short_vol_ratio"].astype(float)
        oi = np.where(oi_raw > 0, np.log(oi_raw), np.nan)
        top = np.where(top_raw > 0, np.log(top_raw), np.nan)
        crowd = np.where(crowd_raw > 0, np.log(crowd_raw), np.nan)
        taker = np.where(taker_raw > 0, np.log(taker_raw), np.nan)
        oi_s = pd.Series(oi, index=m.index, dtype=float)
        top_s = pd.Series(top, index=m.index, dtype=float)
        crowd_s = pd.Series(crowd, index=m.index, dtype=float)
        taker_s = pd.Series(taker, index=m.index, dtype=float)

        def z(s):
            mu = s.rolling(180, min_periods=90).mean()
            sd = s.rolling(180, min_periods=90).std(ddof=1)
            return (s - mu) / sd

        out = pd.DataFrame({
            "t": pd.to_datetime(m["open_time"], utc=True),
            "sym": sym,
            "pos_oi_chg6": oi_s.diff(6),
            "pos_oi_chg42": oi_s.diff(42),
            "pos_oi_z": z(oi_s),
            "pos_top_ls": top_s,
            "pos_top_ls_chg6": top_s.diff(6),
            "pos_top_ls_z": z(top_s),
            "pos_crowd_ls_z": z(crowd_s),
            "pos_taker_ls6": taker_s.rolling(6, min_periods=3).mean(),
            "_has_metrics": m["create_time"].notna(),
        })
        frames.append(out)
    pos = pd.concat(frames, ignore_index=True)
    pos["t"] = pd.to_datetime(pos["t"], utc=True)
    return pos


def run_tranched(o114_lo, o114_ls, o103, n_assets=5):
    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    return replace_vol


def tranched_scenarios(o_lo_p, o_ls_p, o_103_p):
    Wlo_p = weights_lo_from_oos(o_lo_p, 5)
    W94_p = weights_ls_from_oos(o_ls_p, 5)
    W103_p = weights_ls_from_oos(o_103_p, 5)
    Wlo_t, _ = tranche_mean(Wlo_p)
    W94_t, _ = tranche_mean(W94_p)
    W103_t, _ = tranche_mean(W103_p)
    o_v114 = o_lo_p.pivot_table(index="t", columns="sym", values="open")[list(SYMS5)].sort_index()
    o_v103 = o_103_p.pivot_table(index="t", columns="sym", values="open")[list(SYMS5)].sort_index()
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
        print(f"tranched {sc} monthly={scenarios[sc]['monthly_pct']} fullDD={scenarios[sc]['full_path_dd']}", flush=True)
    return scenarios, int(len(idx)), [str(idx[0]), str(idx[-1])]


def part_a1(panel114, panel103, feats114, feats103, oos114_pvol, oos103_pvol):
    p92_h, p92_r, p92_b = [], [], []
    p94_h, p94_r, p94_b = [], [], []
    p103_h, p103_r, p103_b = [], [], []
    a92, a94, a103 = [], [], []
    for anchor in ANCHORS:
        te92, ntr92, sdh92, sdr92 = train_blend_single(panel114, feats114, anchor, "y", EMB_V92, H_V92)
        ev = te92.dropna(subset=["y"])
        ic_h = spearman(ev["pred_hgb"], ev["y"])
        ic_r = spearman(ev["pred_ridge"], ev["y"])
        ic_b = spearman(ev["pred_blend"], ev["y"])
        a92.append(dict(anchor=anchor, train_rows=int(ntr92), n_pred_rows=int(len(te92)),
                        n_pred_rows_with_y=int(len(ev)),
                        ic_hgb=round(float(ic_h), 4) if np.isfinite(ic_h) else None,
                        ic_ridge=round(float(ic_r), 4) if np.isfinite(ic_r) else None,
                        ic_blend=round(float(ic_b), 4) if np.isfinite(ic_b) else None,
                        sd_h=round(float(sdh92), 6), sd_r=round(float(sdr92), 6)))
        print(f"A1 v92 {anchor} ntr={ntr92} ic_h={a92[-1]['ic_hgb']} ic_r={a92[-1]['ic_ridge']} ic_b={a92[-1]['ic_blend']}", flush=True)
        for tag, lst in (("hgb", p92_h), ("ridge", p92_r), ("blend", p92_b)):
            d = te92[["t", "sym", "open", "rib", "vol42", f"pred_{tag}"]].copy()
            d = d.rename(columns={f"pred_{tag}": "pred"})
            lst.append(d)
        te94, ntrs94, sdhs94, sdrs94 = train_blend_multi(panel114, feats114, anchor, HS_V94, EMB_V94)
        ev94 = te94.dropna(subset=["y42"])
        ic94_h = spearman(ev94["pred_hgb"], ev94["y42"])
        ic94_r = spearman(ev94["pred_ridge"], ev94["y42"])
        ic94_b = spearman(ev94["pred_blend"], ev94["y42"])
        a94.append(dict(anchor=anchor, train_rows_h18=ntrs94[0], train_rows_h42=ntrs94[1],
                        train_rows_h84=ntrs94[2], n_pred_rows=int(len(te94)),
                        n_pred_rows_with_y=int(len(ev94)),
                        ic_hgb=round(float(ic94_h), 4) if np.isfinite(ic94_h) else None,
                        ic_ridge=round(float(ic94_r), 4) if np.isfinite(ic94_r) else None,
                        ic_blend=round(float(ic94_b), 4) if np.isfinite(ic94_b) else None,
                        sd_h=sdhs94, sd_r=sdrs94))
        print(f"A1 v94 {anchor} {ntrs94} ic_h={a94[-1]['ic_hgb']} ic_r={a94[-1]['ic_ridge']} ic_b={a94[-1]['ic_blend']}", flush=True)
        for tag, lst in (("hgb", p94_h), ("ridge", p94_r), ("blend", p94_b)):
            d = te94[["t", "sym", "open", "rib", "vol42", f"pred_{tag}"]].copy()
            d = d.rename(columns={f"pred_{tag}": "pred"})
            lst.append(d)
        te103, ntrs103, sdhs103, sdrs103 = train_blend_multi(panel103, feats103, anchor, HS_V103, EMB_V103)
        ic6_h = spearman(te103["pred_hgb"], te103["y6"])
        ic18_h = spearman(te103["pred_hgb"], te103["y18"])
        ic6_r = spearman(te103["pred_ridge"], te103["y6"])
        ic18_r = spearman(te103["pred_ridge"], te103["y18"])
        ic6_b = spearman(te103["pred_blend"], te103["y6"])
        ic18_b = spearman(te103["pred_blend"], te103["y18"])
        a103.append(dict(anchor=anchor, train_rows_h6=ntrs103[0], train_rows_h18=ntrs103[1],
                         n_pred_rows=int(len(te103)),
                         ic_hgb_vs_y6=round(float(ic6_h), 4) if np.isfinite(ic6_h) else None,
                         ic_hgb_vs_y18=round(float(ic18_h), 4) if np.isfinite(ic18_h) else None,
                         ic_ridge_vs_y6=round(float(ic6_r), 4) if np.isfinite(ic6_r) else None,
                         ic_ridge_vs_y18=round(float(ic18_r), 4) if np.isfinite(ic18_r) else None,
                         ic_blend_vs_y6=round(float(ic6_b), 4) if np.isfinite(ic6_b) else None,
                         ic_blend_vs_y18=round(float(ic18_b), 4) if np.isfinite(ic18_b) else None,
                         sd_h=sdhs103, sd_r=sdrs103))
        print(f"A1 v103 {anchor} {ntrs103} b6={a103[-1]['ic_blend_vs_y6']} b18={a103[-1]['ic_blend_vs_y18']}", flush=True)
        for tag, lst in (("hgb", p103_h), ("ridge", p103_r), ("blend", p103_b)):
            d = te103[["t", "sym", "open", "rib", "vol42", f"pred_{tag}"]].copy()
            d = d.rename(columns={f"pred_{tag}": "pred"})
            lst.append(d)
    oos92_h = pd.concat(p92_h, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos92_r = pd.concat(p92_r, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos92_b = pd.concat(p92_b, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94_h = pd.concat(p94_h, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94_r = pd.concat(p94_r, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94_b = pd.concat(p94_b, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103_h = pd.concat(p103_h, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103_r = pd.concat(p103_r, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103_b = pd.concat(p103_b, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    for df in (oos92_h, oos92_r, oos92_b, oos94_h, oos94_r, oos94_b, oos103_h, oos103_r, oos103_b):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    def rep(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    scenarios = {}
    union = {}
    for tag, o92, o94, o103 in (("hgb", oos92_h, oos94_h, oos103_h),
                                ("ridge", oos92_r, oos94_r, oos103_r),
                                ("blend", oos92_b, oos94_b, oos103_b)):
        o92p, n1 = rep(o92, j114)
        o94p, n2 = rep(o94, j114)
        o103p, n3 = rep(o103, j103)
        sc, ub, span = tranched_scenarios(o92p, o94p, o103p)
        scenarios[tag] = sc
        union[tag] = dict(union_bars=ub, oos_span=span, n_replaced=dict(v114_lo=n1, v114_ls=n2, v103=n3))
    return dict(anchors_v92=a92, anchors_v94=a94, anchors_v103=a103,
                scenarios=scenarios, union=union)


def part_a2(panel103_base, feats103_base, bars103, oos114_pvol, oos103_pvol):
    pos = build_positioning(bars103)
    panel103 = panel103_base.merge(pos[["t", "sym"] + POS_FEATS + ["_has_metrics"]], on=["t", "sym"], how="left")
    n_panel = int(len(panel103))
    n_has = int(panel103["_has_metrics"].fillna(False).sum())
    n_full = int(panel103[POS_FEATS].notna().all(axis=1).sum())
    cov_panel = round(n_full / n_panel, 4) if n_panel else None
    cov_has = round(n_has / n_panel, 4) if n_panel else None
    per_sym = {}
    for s, g in panel103.groupby("sym"):
        per_sym[s] = dict(rows=int(len(g)),
                          full_rows=int(g[POS_FEATS].notna().all(axis=1).sum()),
                          coverage=round(float(g[POS_FEATS].notna().all(axis=1).mean()), 4))
    feats103_aug = feats103_base + POS_FEATS
    p103 = []
    a103 = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_V103)
        te = panel103[(panel103.t >= a) & (panel103.t < end)].copy()
        preds = np.zeros((len(te), len(HS_V103)))
        ntrs = []
        for j, h in enumerate(HS_V103):
            yh = f"y{h}"
            tr = panel103[(panel103.t < cutoff) & panel103[yh].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            ntrs.append(int(len(tr)))
            m = HistGradientBoostingRegressor(**HGB)
            m.fit(tr[feats103_aug], tr[yh])
            preds[:, j] = m.predict(te[feats103_aug])
        te["pred"] = preds.mean(axis=1)
        for j, h in enumerate(HS_V103):
            te[f"pred_h{h}"] = preds[:, j]
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        n_oos = int(len(te))
        n_full_oos = int(te[POS_FEATS].notna().all(axis=1).sum())
        a103.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                         n_pred_rows=n_oos, n_full_pos_rows=n_full_oos,
                         coverage=round(n_full_oos / n_oos, 4) if n_oos else None,
                         ic_vs_y6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                         ic_vs_y18=round(float(ic18), 4) if np.isfinite(ic18) else None))
        print(f"A2 v103 {anchor} {ntrs} cov={a103[-1]['coverage']} ic6={a103[-1]['ic_vs_y6']} ic18={a103[-1]['ic_vs_y18']}", flush=True)
        p103.append(te[["t", "sym", "open", "rib", "vol42", "pred"]].copy())
    oos103_aug = pd.concat(p103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103_aug["t"] = pd.to_datetime(oos103_aug["t"], utc=True)
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    def rep(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    o114_lo_p, n_lo = rep(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o114_ls_p, n_ls = rep(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = rep(oos103_aug.sort_values(["t", "sym"]).reset_index(drop=True), j103)
    scenarios, ub, span = tranched_scenarios(o114_lo_p, o114_ls_p, o103_p)

    def per_asset_ic(oos, pred_col, target_col):
        out = {}
        for s, g in oos.groupby("sym"):
            ic = spearman(g[pred_col], g[target_col])
            out[s] = round(float(ic), 4) if np.isfinite(ic) else None
        pooled = spearman(oos[pred_col], oos[target_col])
        out["_pooled"] = round(float(pooled), 4) if np.isfinite(pooled) else None
        out["_n_rows"] = int(len(oos))
        return out

    ic_asset = dict(vs_y6=per_asset_ic(oos103_aug.dropna(subset=["y6"]) if "y6" in oos103_aug else oos103_aug, "pred", "pred"),
                    )
    # recompute proper ICs with targets from panel
    oos_targets = panel103[["t", "sym", "y6", "y18"]].copy()
    oos_targets["t"] = pd.to_datetime(oos_targets["t"], utc=True)
    oos_eval = oos103_aug.merge(oos_targets, on=["t", "sym"], how="left")
    ic_asset = dict(vs_y6=per_asset_ic(oos_eval.dropna(subset=["y6"]), "pred", "y6"),
                    vs_y18=per_asset_ic(oos_eval.dropna(subset=["y18"]), "pred", "y18"))
    return dict(anchors_v103=a103, feats103_aug=feats103_aug,
                coverage_panel=dict(n_panel_rows=n_panel, n_has_metrics=n_has, n_full_pos=n_full,
                                    coverage_full=cov_panel, coverage_has_metrics=cov_has, per_asset=per_sym),
                ic_per_asset=ic_asset, scenarios=scenarios,
                n_replaced=dict(v114_lo=int(n_lo), v114_ls=int(n_ls), v103=int(n_103)),
                union_bars=int(ub), oos_span=span)


def main():
    panel114, panel103, bars114, bars103 = build_panels(SYMS5)
    feats114 = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                         "fv", "realized_vol", "pred_fv", "pvol")]
    feats103 = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                         "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                         "pred_h6", "pred_h18")]
    print(f"feats114={len(feats114)} feats103={len(feats103)}", flush=True)
    oos114_pvol, a114 = train_pvol(panel114, feats114, bars114)
    oos103_pvol, a103p = train_pvol(panel103, feats103, bars103)
    v138 = part_a1(panel114, panel103, feats114, feats103, oos114_pvol, oos103_pvol)
    v139 = part_a2(panel103, feats103, bars103, oos114_pvol, oos103_pvol)
    out = {
        "version": "v138_v139_audit_replication",
        "anchors": list(ANCHORS),
        "scenarios_spec": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        "v138": v138,
        "v139": v139,
        "anchors_v114_pvol": a114,
        "anchors_v103_pvol": a103p,
        "meta": {
            "v133_base": "5-asset (BTC ETH SOL BNB XRP) v114 extended (Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot_2017 prefix) + v103 base (spot prefix + USD-M + flow); HGB v92 params; v92 H=42 cutoff-102*4h t+43*4h<cutoff; v94 18/42/84 cutoff-144*4h t+(h+1)*4h<cutoff; v103 6/18 cutoff-78*4h; pvol v129 method fv=log roll42 std difflogopen shift-43 cutoff-102*4h t+44*4h<cutoff pvol=exp(pred) left-join replace; tranche_mean 6 phases own 0.20-cap-2 scales W.shift(2) trailing360/min120; books 0.25/0.25/0.5; sequential v110 engine target 0.15 ungoverned; live 2021-09-24..2026-09-23; carry artifacts/research/carry/carry_oos_fee0.0004.parquet",
            "v138_choices": "standardize per anchor-horizon on train only: median fill, (x-mean)/std population ddof=0 std0->1 NaN->1, clip +-5, NaN->0; HGB(v92 params)+Ridge(alpha=10) both on standardized; sd_h/sd_r=population std ddof=0 of in-sample preds on standardized train (sd_r 0/nonfinite->1); blend=0.5*hgb+0.5*sd_h*ridge/sd_r per horizon then mean over horizons for v94/v103; pvol unchanged base; scenarios for hgb/ridge/blend each with full-path DD",
            "v139_choices": "metrics asof backward target=t+4h-5min tolerance 4h per asset; oi=log(sum_open_interest_value>0 else NaN) top=log(sum_toptrader_long_short_ratio) crowd=log(count_long_short_ratio) taker=log(sum_taker_long_short_vol_ratio); diffs per asset time order; z=(s-roll180mean_min90)/roll180std_min90 ddof=1; 8 pos_ feats added to v103 only (HGB raw, NaN native); v103 pvol uses base feats without pos; v92/v94 OOS reused audited CSVs; tranched v133 pipeline",
            "model": HGB,
            "ridge": {"alpha": 10},
            "pos_features": POS_FEATS,
            "data": {"v114_panel": "Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot_2017 prefix where exists",
                     "v103_panel": "spot_2017 prefix + USD-M + flow feats",
                     "metrics": "data/raw/um_metrics_20260926/{SYM}_metrics.parquet 5min 2020-09-01..2026-09-24",
                     "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                     "oos_base_v139_v92_v94": "v113_v114_audit/predictions_v114_v92.csv + predictions_v114_v94.csv"},
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"v138_blend_normal": v138["scenarios"]["blend"]["normal"],
                      "v139_normal": v139["scenarios"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
