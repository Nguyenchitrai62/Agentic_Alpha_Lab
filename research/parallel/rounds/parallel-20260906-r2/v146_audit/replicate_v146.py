"""Blind v146 audit replication (Part A).
Does NOT read research/.../v146/*.

Base (per OPENCODE_V146_AUDIT.md):
  audited v141_v142 replication (its A2 = v144: v142 books + v141 engine)
  and v138_v139 (positioning features).

A: v144 exactly, except the v103 panel gets, before the v142
cross-sectional step, the v139 features oi_chg6, oi_chg42, top_ls_z,
crowd_ls_z, taker_ls6, then xs_c = c - mean over majors at t and
xr_c = rank(pct) at t for those five, and the five raw columns are
DROPPED (only the 10 relative columns enter the v103 model).
The v103 vol model uses the original v103 features.
Rows 0.15 ungoverned, 0.20 and 0.25 governed with 10 bps 1m execution.
Report monthly and full-path DD.

Engine (v144 = v141 wrapper): sequential loop over the 4h index;
  live = [2021-09-24, +1825 days);
  s = min(target/vol, 2), NaN vol -> s = 1;
  governor (targets 0.20, 0.25):
    g_i = clip((0.20 - (1 - E_{i-2}/max E over the 540 bars ending at i-2))/0.10, 0, 1),
    g = 1 for i < 2 and for the ungoverned 0.15 row;
  w = 0.8*s*books*g (0 outside live), c = 0.6*s*g (0 outside live);
  dw = w - w_prev; per asset: buys fee 0.0002 & rel -0.0010 if the bar's
  minutes 2..14 low < p0*(1-0.0010) else fee 0.0005 & rel p15/p0-1+0.0002;
  sells symmetric with high > p0*(1+0.0010), rel +0.0010 or p15/p0-1-0.0002;
  missing p0 -> taker with rel +/-0.0002;
  cost = sum(|dw|*fee + dw*rel);
  net = sum(w*(open[t+2]/open[t+1]-1)) - cost - 0.00005*sum(max(w,0))
    + c*carry - |c - c_prev|*2*0.0004/1.2;
  E_i = E_{i-1}(1+net_i).
  Report monthly, yearly (with mean g), full-path DD per row.
  Rows (blind choice, v144 labels): gated_0.20, gated_0.25, ungoverned_0.15.

v142 cross-section (v144 books): per bar t: xs_c = c - mean_t(c),
  xr_c = percentile rank of c among majors at t (pandas rank(pct=True)),
  for c in ret42 ret180 snr42 snr180 d50 d200 vol_ratio volz f7
  on the v114 panel (v92/v94 models use all columns) and additionally
  tbr_6 flow_42 tbr_z on the v103 panel;
  vol forecasts use the original feature sets; v133 pipeline otherwise,
  with v92/v94/v103 retrained on expanded feature sets and pvol on
  original sets. ICs reported per anchor.

v146 delta (blind choice): v103 panel first gets the 5 v139 positioning
  columns (bare names oi_chg6, oi_chg42, top_ls_z, crowd_ls_z, taker_ls6,
  built exactly as the audited v138_v139 positioning: asof target
  t+4h-5min tolerance 4h per asset, log-where->0, diff(6/42),
  z=(s-roll180mean_min90)/roll180std_min90 ddof=1, taker roll6mean_min3,
  per-asset time order); then the v142 xs/xr step also covers those five;
  then the five raw columns are DROPPED so only the 10 relative columns
  (xs_/xr_ for the five) enter the v103 direction model. v103 pvol uses
  the original v103 features (no positioning, no xs/xr). v114 side is
  v142/v144 exactly.

Blind choices documented in replication.json meta.
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

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT17_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
BTC_1M_DIR = ROOT / "data/raw/btc_intraday_20260924"
MAJ_1M_DIR = ROOT / "data/raw/majors_intraday_20260924"
UM_DIR = ROOT / "data/raw/um_metrics_20260926"

ROWS = {
    "gated_0.20": {"target": 0.20, "governed": True},
    "gated_0.25": {"target": 0.25, "governed": True},
    "ungoverned_0.15": {"target": 0.15, "governed": False},
}
XS_BASE = ["ret42", "ret180", "snr42", "snr180", "d50", "d200",
           "vol_ratio", "volz", "f7"]
XS_EXTRA103 = ["tbr_6", "flow_42", "tbr_z"]
# v139 positioning subset required by the v146 assignment (bare names;
# audited v138_v139 replication uses pos_-prefixed equivalents:
# pos_oi_chg6, pos_oi_chg42, pos_top_ls_z, pos_crowd_ls_z, pos_taker_ls6).
POS_RAW = ["oi_chg6", "oi_chg42", "top_ls_z", "crowd_ls_z", "taker_ls6"]


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


# ---------- panels ----------
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


def add_xs_xr(panel, cols):
    panel = panel.copy()
    for col in cols:
        mu = panel.groupby("t")[col].transform("mean")
        panel[f"xs_{col}"] = panel[col] - mu
        panel[f"xr_{col}"] = panel.groupby("t")[col].transform(lambda s: s.rank(pct=True))
    return panel


def build_positioning_v139_subset(bars103_base):
    """Audited v138_v139 positioning, 5-column subset with bare assignment names.

    For each v103-panel 4h row take the last metrics row with
    create_time <= t + 4h - 5min (asof backward, tolerance 4h), per asset;
    oi = log(sum_open_interest_value) where >0 else NaN,
    top = log(sum_toptrader_long_short_ratio) where >0 else NaN,
    crowd = log(count_long_short_ratio) where >0 else NaN,
    taker = log(sum_taker_long_short_vol_ratio) where >0 else NaN;
    oi_chg6 = diff(oi,6), oi_chg42 = diff(oi,42),
    z(s) = (s - rolling180 mean(min 90))/rolling180 std(min 90, ddof=1);
    top_ls_z = z(top), crowd_ls_z = z(crowd),
    taker_ls6 = rolling6 mean(min 3) of taker, per asset in time order.
    """
    frames = []
    for sym in SYMS:
        b = bars103_base[sym][["open_time"]].copy()
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
            "oi_chg6": oi_s.diff(6),
            "oi_chg42": oi_s.diff(42),
            "top_ls_z": z(top_s),
            "crowd_ls_z": z(crowd_s),
            "taker_ls6": taker_s.rolling(6, min_periods=3).mean(),
            "_has_metrics": m["create_time"].notna(),
        })
        frames.append(out)
    pos = pd.concat(frames, ignore_index=True)
    pos["t"] = pd.to_datetime(pos["t"], utc=True)
    return pos


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


# ---------- 1m execution (10 bps rule) ----------
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
    # per-bar 10bps maker/taker flags (decision t -> execution T=t+4h already aligned)
    has_p0 = ~(np.isnan(p0))
    lim_buy = p0 * (1 - D10)
    lim_sell = p0 * (1 + D10)
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
        # 10bps fill per asset
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
                    # maker only if through condition held
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


def run_rows(ctx, p0_df, lo_df, hi_df, p15_df, tag):
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
        print(f"{tag} {key} monthly={summ['monthly_pct']} fullDD={summ['full_path_dd']} "
              f"maker={summ['maker_fill_rate']} meang={[g['mean_g'] for g in summ['mean_g_per_anchor_year']]}", flush=True)
    return rows


def main():
    panel114, panel103, bars = build_panels()
    feats114 = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                         "fv", "realized_vol", "pred_fv", "pvol")]
    feats103 = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                         "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                         "pred_h6", "pred_h18")]
    oos114_pvol, a114 = train_pvol(panel114, feats114, bars)
    bars103_base = {s: load_base(s)[0] for s in SYMS}
    # v103 bars for pvol must be base (no extension); rebuild fv on base bars
    oos103_pvol, a103 = train_pvol(panel103, feats103, bars103_base)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    # v146 delta: v139 5-feature subset onto the v103 panel BEFORE xs/xr
    pos = build_positioning_v139_subset(bars103_base)
    panel103p = panel103.merge(pos[["t", "sym"] + POS_RAW + ["_has_metrics"]], on=["t", "sym"], how="left")
    n_panel = int(len(panel103p))
    n_has = int(panel103p["_has_metrics"].fillna(False).sum())
    n_full = int(panel103p[POS_RAW].notna().all(axis=1).sum())
    per_sym_cov = {}
    for s, g in panel103p.groupby("sym"):
        per_sym_cov[s] = dict(rows=int(len(g)),
                              full_rows=int(g[POS_RAW].notna().all(axis=1).sum()),
                              coverage=round(float(g[POS_RAW].notna().all(axis=1).mean()), 4))
    print(f"pos coverage full={n_full}/{n_panel} has_metrics={n_has}/{n_panel}", flush=True)

    # v144 (= v142 books) xs/xr exactly, plus the five positioning cols on v103;
    # then DROP the five raw columns (only the 10 relative enter the model).
    panel114x = add_xs_xr(panel114, XS_BASE)
    panel103full = add_xs_xr(panel103p, XS_BASE + XS_EXTRA103 + POS_RAW)
    panel103x = panel103full.drop(columns=POS_RAW)
    feats114x = [c for c in panel114x.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103x = [c for c in panel103x.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18", "_has_metrics")]
    print(f"feats114x={len(feats114x)} feats103x={len(feats103x)}", flush=True)
    a92, a94, a103x = [], [], []
    p92, p94, p103 = [], [], []
    for anchor in ANCHORS:
        te92, ntr92 = train_v92(panel114x, feats114x, anchor)
        ev = te92.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        a92.append(dict(anchor=anchor, train_rows=int(ntr92), n_pred_rows=int(len(te92)),
                        n_pred_rows_with_y=int(len(ev)), ic=round(rho, 4)))
        p92.append(te92)
        print("v146 v92", anchor, ntr92, round(rho, 4), flush=True)
        te94, ntrs94 = train_v94(panel114x, feats114x, anchor)
        ev94 = te94.dropna(subset=["y42"])
        rho94 = float(spearmanr(ev94["pred"], ev94["y42"]).statistic) if len(ev94) > 2 else float("nan")
        a94.append(dict(anchor=anchor, train_rows_h18=ntrs94[0], train_rows_h42=ntrs94[1],
                        train_rows_h84=ntrs94[2], n_pred_rows=int(len(te94)),
                        n_pred_rows_with_y=int(len(ev94)), ic_mean_vs_h42=round(rho94, 4)))
        p94.append(te94)
        print("v146 v94", anchor, ntrs94, round(rho94, 4), flush=True)
        te103, ntrs103 = train_v103(panel103x, feats103x, anchor)
        ic6 = spearman(te103["pred"], te103["y6"])
        ic18 = spearman(te103["pred"], te103["y18"])
        a103x.append(dict(anchor=anchor, train_rows_h6=ntrs103[0], train_rows_h18=ntrs103[1],
                          n_pred_rows=int(len(te103)),
                          ic_vs_y6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                          ic_vs_y18=round(float(ic18), 4) if np.isfinite(ic18) else None))
        p103.append(te103)
        print("v146 v103", anchor, ntrs103, round(float(ic6), 4), round(float(ic18), 4), flush=True)
    oos92x = pd.concat(p92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94x = pd.concat(p94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103x = pd.concat(p103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    # pvol uses ORIGINAL feature sets (already trained above); join onto new OOS
    ctx = build_books_from_oos(oos92x, oos94x, oos103x, j114, j103)
    idx = ctx["idx"]
    p0_df, lo_df, hi_df, p15_df = precompute_exec_frames(idx, list(SYMS))
    rows = run_rows(ctx, p0_df, lo_df, hi_df, p15_df, "v146")

    out = {
        "version": "v146_audit_replication",
        "anchors": list(ANCHORS),
        "live": {"start": str(START), "end_exclusive": str(END), "days": 1825,
                 "union_bars": int(len(idx)), "oos_span": [str(idx[0]), str(idx[-1])]},
        "rows_spec": {k: v for k, v in ROWS.items()},
        "rows": rows,
        "n_replaced": ctx["n_replaced"],
        "anchors_v92": a92, "anchors_v94": a94, "anchors_v103": a103x,
        "anchors_v114_pvol": a114, "anchors_v103_pvol": a103,
        "feats114x_n": len(feats114x), "feats103x_n": len(feats103x),
        "feats114x": feats114x, "feats103x": feats103x,
        "positioning": {
            "raw_columns": list(POS_RAW),
            "raw_dropped": True,
            "relative_columns": [f"xs_{c}" for c in POS_RAW] + [f"xr_{c}" for c in POS_RAW],
            "n_panel_rows": n_panel, "n_has_metrics": n_has, "n_full_pos": n_full,
            "coverage_full": round(n_full / n_panel, 4) if n_panel else None,
            "coverage_has_metrics": round(n_has / n_panel, 4) if n_panel else None,
            "per_asset": per_sym_cov,
        },
        "meta": {
            "v144_spec": "v144 = v142 books (v133 configuration with xs_/xr_ features) + v141 engine (sequential loop; live [2021-09-24,+1825d); s=min(target/vol,2) NaN->1 (vol rolling-360/min-120*sqrt(2190) on 0.8*books+0.6*carry); governor targets 0.20/0.25 g=clip((0.20-(1-E_{i-2}/max540))/0.10,0,1) g=1 i<2 + ungoverned 0.15; w=0.8*s*books*g c=0.6*s*g (0 outside); 10bps limit rule (fee 0.0002 rel -/+0.0010 through minutes 2..14 else fee 0.0005 rel p15/p0-1 +/-0.0002, missing p0 taker +/-0.0002); cost/net/E per assignment",
            "v144_choices": "rows gated_0.20/gated_0.25/ungoverned_0.15; s per target from shared vol; governor peak=max(1.0,max E[j-539..j]) scenario/row-specific sequential; exec T=t+4h p0 minute-0 lo/hi min/max offsets 2..14 p15 minute-15 strict </>; maker rate over live orders",
            "v142_xs_spec": "per bar t xs_c=c-mean_t(c) xr_c=rank(pct=True) among 5 majors for c in ret42 ret180 snr42 snr180 d50 d200 vol_ratio volz f7 on v114 (v92/v94 all columns) + tbr_6 flow_42 tbr_z on v103; vol forecasts original sets",
            "v146_delta": "v103 panel first gets 5 v139 positioning cols (oi_chg6, oi_chg42, top_ls_z, crowd_ls_z, taker_ls6; bare blind names for audited pos_oi_chg6/pos_oi_chg42/pos_top_ls_z/pos_crowd_ls_z/pos_taker_ls6; asof target=t+4h-5min tolerance 4h per asset, log-where->0, diff(6/42), z=(s-roll180mean_min90)/roll180std_min90 ddof=1, taker roll6mean_min3, per-asset time order); xs/xr also cover those five; five raw DROPPED so only the 10 relative cols enter the v103 direction model (feats103x = base + 24 xs/xr + 10 relative = 70); v103 pvol uses original v103 features; v114 side v142/v144 exactly",
            "v146_choices": "HGB v92 h42 cutoff-408h / v94 h18/42/84 cutoff-576h / v103 h6/h18 cutoff-312h on all non-target cols (v114 26+18=44, v103 36+24+10=70 after drop); pvol original-set training reused via left-join replace; rank default average method pct=True per t",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({r: v["monthly_pct"] for r, v in out["rows"].items()}, indent=2))


if __name__ == "__main__":
    main()
