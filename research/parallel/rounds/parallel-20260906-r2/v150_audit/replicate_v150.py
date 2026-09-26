"""Blind v150 audit replication (Part A).
Does NOT read research/.../v150/*.

Base (per OPENCODE_V150_AUDIT.md): v144 replication (v144 = v142 books +
v141 engine, audited in v141_v142/v148_v149 audits).

Options bars = data/raw/deribit_opt_20260926/BTC_options_4h.parquet
(column bar = UTC 4h bar start), reindexed to a complete 4h grid from the
first to the last bar (missing flows/trades -> 0, IVs NaN):
  net = put_buy - put_sell - call_buy + call_sell
  tot = sum of the four
  opt_net6 = rolling-6 sum(net) / rolling-6 sum(tot) (0 -> NaN)
  pcr = log(max(put_buy+put_sell,1)/max(call_buy+call_sell,1))
  skew = iv_otm_put - iv_otm_call
  z(s) = (s - rolling180 mean(min 90)) / rolling180 std(min 90)
  opt_pcr_z = z(pcr)
  opt_skew6 = rolling-6 mean(min 3) of skew
  opt_skew_z = z(skew)
  opt_act_z = z(log(max(n_trades,1)))
Left-join on t (options bar start == panel row open time) to the v114 panel
and to the v103 panel before the v142 xs step (no xs versions); all return
models use them; vol models do NOT. v144 engine otherwise.

Blind choices (frozen before running, logged in replication.json meta):
- opt_net6 uses rolling(6).sum() with min_periods=6 for both legs
  (spec gives no min; full-window is the strict reading).
- z uses pandas rolling(180).mean(min_periods=90)/std(min_periods=90),
  ddof=1 (pandas default), strictly causal (current + past only).
- opt_skew6 uses rolling(6).mean(min_periods=3).
- Options features are market-wide (BTC options): joined on t to ALL syms
  at the same bar (same value for every sym at t). Left join; rows with
  t before the options history keep NaN (HGB handles NaN natively).
- No xs_/xr_ features anywhere (spec: "no xs versions").
- Return feats: v114 26 + 5 opt = 31; v103 36 + 5 opt = 41.
- Vol feats: original sets (v114 26, v103 36), no opt, no xs.
- Rows use v144 labels: reference_t15_ungoverned (0.15, ungoverned),
  t20_governed (0.20, governed), primary_t25_governed (0.25, governed).
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
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=1825)
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102
HS_V94 = (18, 42, 84)
EMB_V94 = 144
HS_V103 = (6, 18)
EMB_V103 = 78
H_V92 = 42
EMB_V92 = 102
GOV_WIN = 540
D10 = 0.0010

OPT_FILE = ROOT / "data/raw/deribit_opt_20260926/BTC_options_4h.parquet"
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT17_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
BTC_1M_DIR = ROOT / "data/raw/btc_intraday_20260924"
MAJ_1M_DIR = ROOT / "data/raw/majors_intraday_20260924"

ROWS = {
    "reference_t15_ungoverned": {"target": 0.15, "governed": False},
    "t20_governed": {"target": 0.20, "governed": True},
    "primary_t25_governed": {"target": 0.25, "governed": True},
}


# ---------- options features (spec verbatim, causal) ----------
def build_options_features():
    df = pd.read_parquet(OPT_FILE).copy()
    df["bar"] = pd.to_datetime(df["bar"], utc=True)
    df = df.sort_values("bar").drop_duplicates("bar", keep="last").set_index("bar").sort_index()
    full = pd.date_range(df.index.min(), df.index.max(), freq="4h", tz="UTC")
    df = df.reindex(full)
    for c in ("call_buy", "call_sell", "put_buy", "put_sell", "n_trades"):
        df[c] = df[c].fillna(0.0)
    # IVs stay NaN where missing (spec)
    net = df["put_buy"] - df["put_sell"] - df["call_buy"] + df["call_sell"]
    tot = df["call_buy"] + df["call_sell"] + df["put_buy"] + df["put_sell"]
    net6 = net.rolling(6, min_periods=6).sum()
    tot6 = tot.rolling(6, min_periods=6).sum()
    opt_net6 = net6 / tot6.replace(0.0, np.nan)
    pcr = np.log(np.maximum(df["put_buy"] + df["put_sell"], 1.0) / np.maximum(df["call_buy"] + df["call_sell"], 1.0))
    skew = df["iv_otm_put"] - df["iv_otm_call"]

    def z(s):
        mu = s.rolling(180, min_periods=90).mean()
        sd = s.rolling(180, min_periods=90).std(ddof=1)
        return (s - mu) / sd

    opt_pcr_z = z(pcr)
    opt_skew6 = skew.rolling(6, min_periods=3).mean()
    opt_skew_z = z(skew)
    opt_act_z = z(np.log(np.maximum(df["n_trades"], 1.0)))
    out = pd.DataFrame({"opt_net6": opt_net6, "opt_pcr_z": opt_pcr_z, "opt_skew6": opt_skew6,
                        "opt_skew_z": opt_skew_z, "opt_act_z": opt_act_z}, index=full)
    out.index.name = "t"
    return out


def join_opt(panel, opt):
    panel = panel.copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    return panel.merge(opt, left_on="t", right_index=True, how="left")


# ---------- weights ----------
def weights_lo_from_oos(oos):
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
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    return W


def weights_ls_from_oos(oos):
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
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
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


# ---------- panels (audited v144 base, inline) ----------
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
    if not (SPOT17_DIR / f"{sym}_spot_4h_2017.parquet").exists():
        s4, s1 = b.iloc[:0].copy(), d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT17_DIR / f"{sym}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT17_DIR / f"{sym}_spot_1d_2017.parquet")
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


def build_panels():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    rows114, rows103, bars = [], [], {}
    for i, s in enumerate(SYMS):
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        bars[s] = b
        x114 = features_base(b, d, f, with_flow=False)
        x114["asset"] = i
        x114["t"] = b["open_time"]
        x114["open"] = b["open"].astype(float).to_numpy()
        x114["sym"] = s
        x114["bar"] = np.arange(len(b))
        rows114.append(x114)
        b2, d2, f2 = load_base(s)
        x103 = features_base(b2, d2, f2, with_flow=True)
        x103["asset"] = i
        x103["t"] = b2["open_time"]
        x103["open"] = b2["open"].astype(float).to_numpy()
        x103["sym"] = s
        x103["bar"] = np.arange(len(b2))
        rows103.append(x103)
    panel114 = pd.concat(rows114, ignore_index=True)
    btc = panel114[panel114.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel114 = panel114.join(btc, on="t")
    panel103 = pd.concat(rows103, ignore_index=True)
    btc3 = panel103[panel103.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel103 = panel103.join(btc3, on="t")
    return panel114, panel103, bars


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def train_pvol(panel, feats, bars):
    fv_map = {}
    for s in SYMS:
        b = bars[s]
        lo = np.log(b["open"].astype(float))
        r = lo.diff()
        s42 = r.rolling(42).std(ddof=1)
        fv_map[s] = (np.log(s42.shift(-43)).to_numpy(), s42.shift(-43).to_numpy())
    panel = panel.copy()
    panel["fv"] = np.nan
    panel["realized_vol"] = np.nan
    for s in SYMS:
        m = panel["sym"] == s
        fv_arr, rv_arr = fv_map[s]
        tmp = pd.DataFrame({"t": bars[s]["open_time"].to_numpy(), "fv": fv_arr, "rv": rv_arr})
        tmp["t"] = pd.to_datetime(tmp["t"], utc=True)
        j = panel.loc[m, ["t"]].merge(tmp, on="t", how="left")
        panel.loc[m, "fv"] = j["fv"].to_numpy()
        panel.loc[m, "realized_vol"] = j["rv"].to_numpy()
    anchors, parts = [], []
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


def train_v92(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V92)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB)
    m.fit(tr[feats], tr["y"])
    te["pred"] = m.predict(te[feats])
    return te, int(len(tr))


def train_v94(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V94)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V94)))
    ntrs = []
    for j, h in enumerate(HS_V94):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    return te, ntrs


def train_v103(panel, feats, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    return te, ntrs


# ---------- 1m execution (10 bps rule, audited v141/v144) ----------
def load_1m_exec(sym):
    if sym == "BTCUSDT":
        files = sorted(BTC_1M_DIR.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(MAJ_1M_DIR.glob(f"{sym}_1m_20*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in files],
                   ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.sort_values("open_time").drop_duplicates("open_time", keep="last").sort_values("open_time")
    return m.set_index("open_time").sort_index()


def precompute_exec_frames(idx, syms):
    T = idx + pd.Timedelta(hours=4)
    p0_df = pd.DataFrame(index=idx, columns=syms, dtype=float)
    p15_df = pd.DataFrame(index=idx, columns=syms, dtype=float)
    lo_df = pd.DataFrame(index=idx, columns=syms, dtype=float)
    hi_df = pd.DataFrame(index=idx, columns=syms, dtype=float)
    for s in syms:
        m = load_1m_exec(s)
        o = m["open"].astype(float)
        l = m["low"].astype(float)
        h = m["high"].astype(float)
        p0_arr = o.reindex(T).to_numpy()
        p15_arr = o.reindex(T + pd.Timedelta(minutes=15)).to_numpy()
        low_cols, high_cols = [], []
        for k in range(2, 15):
            low_cols.append(l.reindex(T + pd.Timedelta(minutes=k)).to_numpy())
            high_cols.append(h.reindex(T + pd.Timedelta(minutes=k)).to_numpy())
        low_mat = np.column_stack(low_cols)
        high_mat = np.column_stack(high_cols)
        with np.errstate(all="ignore"):
            lo_arr = np.nanmin(low_mat, axis=1)
            hi_arr = np.nanmax(high_mat, axis=1)
        lo_arr[np.isnan(low_mat).all(axis=1)] = np.nan
        hi_arr[np.isnan(high_mat).all(axis=1)] = np.nan
        p0_df[s] = p0_arr
        p15_df[s] = p15_arr
        lo_df[s] = lo_arr
        hi_df[s] = hi_arr
        print(f"exec precompute {s} p0_cov={float(np.mean(~np.isnan(p0_arr))):.3f}", flush=True)
    for df in (p0_df, p15_df, lo_df, hi_df):
        df.index = idx
    return p0_df, lo_df, hi_df, p15_df


def run_governed_10bps(o_vals, books_vals, carry_vals, s_vals, live_mask,
                       p0, lo, hi, p15, governed):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    has_p0 = ~(np.isnan(p0))
    net = np.zeros(n)
    turn = np.zeros(n)
    garr = np.ones(n)
    E = np.ones(n)
    e_hist = np.ones(n)
    prev_w = np.zeros(k)
    prev_c = 0.0
    e_prev = 1.0
    maker_orders = 0
    total_orders = 0
    carry_rate = 2 * 0.0004 / 1.2
    for i in range(n):
        if live_mask[i]:
            if governed and i >= 2:
                j = i - 2
                lo_w = max(0, j - (GOV_WIN - 1))
                peak = float(np.max(e_hist[lo_w: j + 1]))
                peak = max(1.0, peak)
                ej = float(e_hist[j])
                dd = 1.0 - ej / peak if peak > 0 else 0.0
                gi = (0.20 - dd) / 0.10
                gi = 1.0 if gi > 1.0 else (0.0 if gi < 0.0 else gi)
            else:
                gi = 1.0
            si = s_vals[i]
            w = W_BOOKS * si * books_vals[i] * gi
            c = W_CARRY * CARRY_LEV * si * gi
        else:
            gi = 1.0
            w = np.zeros(k)
            c = 0.0
        dw = w - prev_w
        tcost = 0.0
        for a in range(k):
            x = float(dw[a])
            if abs(x) < 1e-12:
                continue
            buy = x > 0
            p0a = p0[i, a]
            if np.isnan(p0a):
                fee = 0.0005
                rel = 0.0002 if buy else -0.0002
            elif buy:
                if lo[i, a] < p0a * (1 - D10):
                    fee, rel = 0.0002, -D10
                else:
                    fee = 0.0005
                    p15a = p15[i, a] if not np.isnan(p15[i, a]) else p0a
                    rel = p15a / p0a - 1 + 0.0002
            else:
                if hi[i, a] > p0a * (1 + D10):
                    fee, rel = 0.0002, D10
                else:
                    fee = 0.0005
                    p15a = p15[i, a] if not np.isnan(p15[i, a]) else p0a
                    rel = p15a / p0a - 1 - 0.0002
            tcost += abs(x) * fee + x * rel
            if live_mask[i]:
                total_orders += 1
                if fee == 0.0002 and not np.isnan(p0a):
                    if (buy and lo[i, a] < p0a * (1 - D10)) or ((not buy) and hi[i, a] > p0a * (1 + D10)):
                        maker_orders += 1
        gross = float(np.sum(w * fwd[i]))
        fund = float(np.sum(np.maximum(w, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * carry_rate)
        ni = gross - tcost - fund + cgross - ccost
        ei = e_prev * (1.0 + ni)
        net[i] = ni
        turn[i] = float(np.sum(np.abs(dw)))
        garr[i] = gi
        E[i] = ei
        e_hist[i] = ei
        prev_w, prev_c, e_prev = w, c, ei
    maker_rate = maker_orders / total_orders if total_orders else float("nan")
    return net, turn, garr, E, maker_rate, total_orders


def summarize_row(net_s, turn_s, g_s, maker_rate, orders_live):
    ys = yearly(net_s, turn_s)
    gmeans = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        m = (net_s.index >= a0) & (net_s.index < a0 + pd.Timedelta(days=365))
        gm = float(g_s[m].mean()) if m.sum() else float("nan")
        gmeans.append(dict(anchor=a, mean_g=round(gm, 4), n_bars=int(m.sum())))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(
        yearly=ys,
        mean_g_per_anchor_year=gmeans,
        monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
        worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
        full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
        maker_fill_rate=round(float(maker_rate), 3) if np.isfinite(maker_rate) else None,
        orders_live=int(orders_live),
        fills_live=int((turn_s[full] > 1e-6).sum()),
    )


def build_books_from_oos(o114_lo, o114_ls, o103_df, j114, j103):
    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    o114_lo_p, n_lo = replace_vol(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o114_ls_p, n_ls = replace_vol(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = replace_vol(o103_df.sort_values(["t", "sym"]).reset_index(drop=True), j103)
    Wlo_raw = weights_lo_from_oos(o114_lo_p)
    W94_raw = weights_ls_from_oos(o114_ls_p)
    W103_raw = weights_ls_from_oos(o103_p)
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    Wlo_t, _ = tranche_mean(Wlo_raw)
    W94_t, _ = tranche_mean(W94_raw)
    W103_t, _ = tranche_mean(W103_raw)
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
    return dict(idx=idx, o=o, books=books_t, carry=carry_s, vol=vol,
                n_replaced=dict(v114_lo=int(n_lo), v114_ls=int(n_ls), v103=int(n_103)))


def run_rows(ctx, p0_df, lo_df, hi_df, p15_df):
    idx = ctx["idx"]
    o = ctx["o"]
    books = ctx["books"]
    carry_s = ctx["carry"]
    vol = ctx["vol"]
    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    cols = list(o.columns)
    p0 = p0_df.reindex(idx)[cols].to_numpy(dtype=float)
    lo = lo_df.reindex(idx)[cols].to_numpy(dtype=float)
    hi = hi_df.reindex(idx)[cols].to_numpy(dtype=float)
    p15 = p15_df.reindex(idx)[cols].to_numpy(dtype=float)
    rows = {}
    for key, cfg in ROWS.items():
        s = (cfg["target"] / vol).clip(upper=CAP).fillna(1.0)
        s = s.replace([np.inf, -np.inf], CAP).fillna(1.0)
        s_vals = s.to_numpy(dtype=float)
        net, turn, garr, E, maker_rate, orders = run_governed_10bps(
            o_vals, books_vals, carry_vals, s_vals, live_mask, p0, lo, hi, p15, cfg["governed"])
        summ = summarize_row(pd.Series(net, index=idx), pd.Series(turn, index=idx),
                             pd.Series(garr, index=idx), maker_rate, orders)
        rows[key] = summ
        print(f"v150 {key} monthly={summ['monthly_pct']} fullDD={summ['full_path_dd']}", flush=True)
    return rows


def main():
    opt = build_options_features()
    print(f"opt grid {len(opt)} {opt.index.min()} -> {opt.index.max()}", flush=True)
    print(f"opt NaN counts: {opt.isna().sum().to_dict()}", flush=True)
    panel114, panel103, bars = build_panels()
    feats114_base = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                              "fv", "realized_vol", "pred_fv", "pvol")]
    feats103_base = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                              "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                              "pred_h6", "pred_h18")]
    assert len(feats114_base) == 26, len(feats114_base)
    assert len(feats103_base) == 36, len(feats103_base)
    # vol models: original sets, no opt
    oos114_pvol, a114 = train_pvol(panel114, feats114_base, bars)
    bars103 = {s: load_base(s)[0] for s in SYMS}
    oos103_pvol, a103 = train_pvol(panel103, feats103_base, bars103)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    # return panels: base + opt (no xs)
    panel114o = join_opt(panel114, opt)
    panel103o = join_opt(panel103, opt)
    assert all(c in panel114o.columns for c in OPT_FEATS)
    feats114o = feats114_base + OPT_FEATS
    feats103o = feats103_base + OPT_FEATS
    assert len(feats114o) == 31 and len(feats103o) == 41

    a92, a94, a103x = [], [], []
    p92, p94, p103 = [], [], []
    for anchor in ANCHORS:
        te92, ntr92 = train_v92(panel114o, feats114o, anchor)
        ev = te92.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        a92.append(dict(anchor=anchor, train_rows=int(ntr92), n_pred_rows=int(len(te92)),
                        n_pred_rows_with_y=int(len(ev)), ic=round(rho, 4)))
        p92.append(te92)
        print("v150 v92", anchor, ntr92, round(rho, 4), flush=True)
        te94, ntrs94 = train_v94(panel114o, feats114o, anchor)
        ev94 = te94.dropna(subset=["y42"])
        rho94 = float(spearmanr(ev94["pred"], ev94["y42"]).statistic) if len(ev94) > 2 else float("nan")
        a94.append(dict(anchor=anchor, train_rows_h18=ntrs94[0], train_rows_h42=ntrs94[1],
                        train_rows_h84=ntrs94[2], n_pred_rows=int(len(te94)),
                        n_pred_rows_with_y=int(len(ev94)), ic_mean_vs_h42=round(rho94, 4)))
        p94.append(te94)
        print("v150 v94", anchor, ntrs94, round(rho94, 4), flush=True)
        te103, ntrs103 = train_v103(panel103o, feats103o, anchor)
        ic6 = spearman(te103["pred"], te103["y6"])
        ic18 = spearman(te103["pred"], te103["y18"])
        a103x.append(dict(anchor=anchor, train_rows_h6=ntrs103[0], train_rows_h18=ntrs103[1],
                          n_pred_rows=int(len(te103)),
                          ic_vs_y6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                          ic_vs_y18=round(float(ic18), 4) if np.isfinite(ic18) else None))
        p103.append(te103)
        print("v150 v103", anchor, ntrs103, round(float(ic6), 4), round(float(ic18), 4), flush=True)
    oos92 = pd.concat(p92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94 = pd.concat(p94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103 = pd.concat(p103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    ctx = build_books_from_oos(oos92, oos94, oos103, j114, j103)
    idx = ctx["idx"]
    p0_df, lo_df, hi_df, p15_df = precompute_exec_frames(idx, list(SYMS))
    rows = run_rows(ctx, p0_df, lo_df, hi_df, p15_df)

    out = {
        "version": "v150_audit_replication",
        "anchors": list(ANCHORS),
        "live": {"start": str(START), "end_exclusive": str(END), "days": 1825,
                 "union_bars": int(len(idx)), "oos_span": [str(idx[0]), str(idx[-1])]},
        "rows_spec": {k: v for k, v in ROWS.items()},
        "rows": rows,
        "n_replaced": ctx["n_replaced"],
        "anchors_v92": a92, "anchors_v94": a94, "anchors_v103": a103x,
        "anchors_v114_pvol": a114, "anchors_v103_pvol": a103,
        "feats114_base_n": len(feats114_base), "feats103_base_n": len(feats103_base),
        "feats114o": feats114o, "feats103o": feats103o,
        "opt": {"file": str(OPT_FILE), "bars": int(len(opt)),
                "first": str(opt.index.min()), "last": str(opt.index.max()),
                "nan_counts": {k: int(v) for k, v in opt.isna().sum().items()}},
        "meta": {
            "spec": "options bars reindexed to complete 4h grid first->last (missing flows/trades->0, IVs NaN); net=put_buy-put_sell-call_buy+call_sell; tot=sum four; opt_net6=rolling6sum(net)/rolling6sum(tot) (0->NaN, min6); pcr=log(max(put,1)/max(call,1)); skew=iv_otm_put-iv_otm_call; z=(s-roll180mean(min90))/roll180std(min90,ddof1); opt_pcr_z=z(pcr); opt_skew6=roll6mean(min3)(skew); opt_skew_z=z(skew); opt_act_z=z(log(max(n_trades,1))); left-join on t to v114+v103 panels before xs (no xs); return models use 5 opt feats; vol models do not; v144 engine otherwise",
            "fetch_alignment": "fetch_deribit_options_4h.py: bar=ts.floor(4h), fetch windows [w0, w0+4h-1ms] per 4h bar, aggregate groupby bar; trades in [T,T+4h) only -> bar T; join on t means opt bar T used at panel row open T (close T+4h-1ms), same timing as OHLCV of bar t; causal with 2-bar execution lag",
            "choices": "opt_net6 min_periods=6 both legs; z ddof=1; opt features broadcast on t to all 5 syms (market-wide BTC options); HGB v92 h42 cutoff-408h / v94 h18/42/84 cutoff-576h / v103 h6/h18 cutoff-312h on all non-target cols (31/41); pvol original-set cutoff-408h t+44 filter exp(pred) left-join replace; books 0.25/0.25/0.5 tranch mean/6 own 0.20-cap-2 scales; v141 sequential governor j=i-2 540-bar peak clip((0.20-DD)/0.10); 10bps 1m execution T=t+4h strict through minutes 2..14",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({r: v["monthly_pct"] for r, v in rows.items()}, indent=2))


if __name__ == "__main__":
    main()
