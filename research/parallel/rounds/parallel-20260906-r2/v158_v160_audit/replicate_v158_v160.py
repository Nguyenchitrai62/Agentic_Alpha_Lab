"""Blind v158+v159+v160 audit replication (Part A).
Does NOT read research/.../v158/* nor research/.../v159/* nor
research/.../v160/* nor import any leader
v158/v159/v160/v154/v151/v150/v144/v142/v141/v111 module.
Saved BEFORE opening v158/, v159/ or v160/ for Part B (workspace mapping
listed the parent directory names only; no v158/v159/v160 file was opened
before the Part A save).
Part A code imports no leader module and all formulas are inline from
the assignment text + audited replication code (v154_audit) + raw data +
carry + 1m intraday + Deribit ETH options + FNG daily + CFTC TFF.

Base (per OPENCODE_V158_V160_AUDIT.md):
  your v154 replication (members A, B, D; v150 options features
  definitions).

All members: extra market-wide columns merged on t into the v114 and v103
panels BEFORE the v142 xs step, no xs versions of them, vol models exclude
them; v144 engine rows (0.15 ungoverned, 0.20/0.25 governed, 10 bps 1m
execution).

A1 (v158): books (A + B' + D)/3 where B' has the five v150 BTC options
  features plus the same five from
  data/raw/deribit_opt_20260926/ETH_options_4h.parquet prefixed eth_
  (outer join on t).
A2 (v159): books (A + B + D + G)/4; G features from
  data/raw/fng_20260926/fng_daily.parquet: value for date D available at
  D + 1h; for panel row t use the last value available at t + 4h: fng,
  fng7 = rolling-7 mean of daily values, fng_chg7 = fng - fng.shift(7),
  fng_z = (fng - rolling90 mean(min 60))/rolling90 std(min 60)
  (daily series).
A3 (v160): books (A + B + D + H)/4; H from
  data/raw/cftc_20260926/btc_cme_tff.parquet (dedup report dates): report
  date D usable from D + 4 days; lev = (Lev_Money long - short) /
  Open_Interest_All, am = (Asset_Mgr long - short)/OI; cot_lev_net,
  cot_am_net, *_chg4 = x - x.shift(4), *_z = (x - rolling52 mean(min 26)) /
  rolling52 std(min 26) (weekly series).

Blind choices (frozen before running, logged in replication.json meta):
- v144 direction xs/xr: per bar t xs_c = c - mean_t(c),
  xr_c = rank(pct=True) among 5 majors at t, for c in ret42 ret180
  snr42 snr180 d50 d200 vol_ratio volz f7 on v114 and additionally
  tbr_6 flow_42 tbr_z on v103 (v114 26+18=44, v103 36+24=60).
- B options math verbatim from frozen v154_audit B leg: reindex to complete
  4h grid first->last (flows->0, IVs NaN); net/tot/opt_net6 rolling6 sum min6
  (0->NaN); pcr log clip 1; skew iv_put-iv_call; z roll180 mean(min90)/std(min90,
  ddof1); opt_skew6 roll6 mean(min3); broadcast on t to all 5 syms;
  joined on t to base panels BEFORE the xs step; xs still on BASE /
  BASE+FLOWX only (no xs/xr versions of the 5 opt cols themselves);
  return feats v114 26+5+18=49, v103 36+5+24=65; vol models original
  26/36 sets.
- B' ETH math: identical five-feature computation on ETH_options_4h,
  columns prefixed eth_ (eth_opt_net6, eth_opt_pcr_z, eth_opt_skew6,
  eth_opt_skew_z, eth_opt_act_z); BTC 5 + ETH 5 outer-joined on t
  (union grid); one row per t merged on t into v114+v103 BEFORE xs;
  xs still on BASE/BASE+FLOWX only (no xs/xr of the 10 opt cols);
  return feats v114 26+10+18=54, v103 36+10+24=70; vol models original.
- D coinbase math verbatim from v154_audit D leg (inline, causal): for
  P in (BTC, ETH): Binance spot 4h = concat(spot_4h_2017, spot_4h) on
  open_time, dedup, sorted; Coinbase {P}-USD 1h close of the 1h candle
  opening at T+3h (asof backward, tolerance 2h, else NaN);
  cbp = 1e4*log(cb_close/binance_close); p6 = rolling-6 mean (min 4),
  p42 = rolling-42 mean (min 30), m540/s540 = rolling-540 mean/std of
  cbp (min 270); cb_btc_dev = p6-m540, cb_btc_z = (p6-m540)/s540,
  cb_btc_chg = p6-p42, cb_eth_z/chg likewise; one value per t merged on
  t into v114+v103 BEFORE xs; xs still on BASE/BASE+FLOWX only (no
  xs/xr of cb cols); return feats v114 49, v103 65; vol models original.
- G FNG math (assignment text + manifest, causal): daily fng series sorted
  by date, dedup, ffill none; fng = daily value; fng7 = rolling-7 mean
  (min 7); fng_chg7 = fng - fng.shift(7); fng_z = (fng - rolling90
  mean(min 60))/rolling90 std(min 60, ddof1); availability daily D at
  D+1h (manifest: published D 00:00 UTC, use from +1h); for panel row t
  take last daily with avail <= t+4h (merge_asof backward); one value per
  t merged on t into v114+v103 BEFORE xs; xs on BASE/BASE+FLOWX only
  (no xs/xr of fng cols); return feats v114 26+4+18=48, v103 36+4+24=64;
  vol models original 26/36 sets.
- H COT math (assignment text + manifest, causal): dedup report dates keep
  last, sorted; OI = Open_Interest_All float (0->NaN); lev = (Lev_Money
  long - short)/OI; am = (Asset_Mgr long - short)/OI; cot_lev_net = lev,
  cot_am_net = am; *_chg4 = x - x.shift(4); *_z = (x - rolling52
  mean(min 26))/rolling52 std(min 26, ddof1) (weekly series); availability
  report date D usable from D+4 days (manifest: Saturday 00:00 UTC after
  Tuesday report = D+4d); for panel row t take last weekly with avail <=
  t+4h (merge_asof backward); one value per t merged on t into v114+v103
  BEFORE xs; xs on BASE/BASE+FLOWX only (no xs/xr of cot cols); return
  feats v114 26+6+18=50, v103 36+6+24=66; vol models original.
- pvol trained once on original sets (cutoff-408h, t+44 filter,
  exp(pred) left-join replace) and reused for all six legs.
- Books: 0.25/0.25/0.5 tranch mean/6 own 0.20-cap-2 scales; 2-bar-lag
  returns; ensembles on union index missing->0, then vol recomputed from
  each ensemble books (same rolling-360/min-120 formula) for the v144
  row scalings. v158 = (A+B'+D)/3, v159 = (A+B+D+G)/4, v160 = (A+B+D+H)/4.
- Engine: v141 sequential loop, governor j=i-2, 540-bar peak
  (peak=max(1.0,max)), clip((0.20-DD)/0.10), per-target s cap 2;
  10 bps 1m rule T=t+4h strict through minutes 2..14
  (maker 0.0002 rel -/+0.0010 else taker 0.0005).
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
OPT_ETH_FILE = ROOT / "data/raw/deribit_opt_20260926/ETH_options_4h.parquet"
OPT_FEATS = ["opt_net6", "opt_pcr_z", "opt_skew6", "opt_skew_z", "opt_act_z"]
ETH_OPT_FEATS = ["eth_opt_net6", "eth_opt_pcr_z", "eth_opt_skew6", "eth_opt_skew_z", "eth_opt_act_z"]
OPT10_FEATS = OPT_FEATS + ETH_OPT_FEATS
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
FNG_FILE = ROOT / "data/raw/fng_20260926/fng_daily.parquet"
FNG_FEATS = ["fng", "fng7", "fng_chg7", "fng_z"]
COT_FILE = ROOT / "data/raw/cftc_20260926/btc_cme_tff.parquet"
COT_FEATS = ["cot_lev_net", "cot_am_net", "cot_lev_chg4", "cot_am_chg4", "cot_lev_z", "cot_am_z"]
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT17_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
BTC_1M_DIR = ROOT / "data/raw/btc_intraday_20260924"
MAJ_1M_DIR = ROOT / "data/raw/majors_intraday_20260924"

XS_BASE = ["ret42", "ret180", "snr42", "snr180", "d50", "d200",
           "vol_ratio", "volz", "f7"]
XS_EXTRA103 = ["tbr_6", "flow_42", "tbr_z"]

ROWS_V154 = {
    "reference_t15_ungoverned": {"target": 0.15, "governed": False},
    "t20_governed": {"target": 0.20, "governed": True},
    "primary_t25_governed": {"target": 0.25, "governed": True},
}
ROWS_V158_V160 = ROWS_V154
GOV20 = (0.20, 0.10)


# ---------- options features (v150 spec verbatim, causal; generic file) ----------
def _options_features_from_file(path):
    df = pd.read_parquet(path).copy()
    df["bar"] = pd.to_datetime(df["bar"], utc=True)
    df = df.sort_values("bar").drop_duplicates("bar", keep="last").set_index("bar").sort_index()
    full = pd.date_range(df.index.min(), df.index.max(), freq="4h", tz="UTC")
    df = df.reindex(full)
    for c in ("call_buy", "call_sell", "put_buy", "put_sell", "n_trades"):
        df[c] = df[c].fillna(0.0)
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


def build_options_features():
    return _options_features_from_file(OPT_FILE)


def build_options_bprime():
    """B' 10-col options panel: BTC five + ETH five (prefixed eth_), outer join on t."""
    btc = _options_features_from_file(OPT_FILE)
    eth = _options_features_from_file(OPT_ETH_FILE).rename(
        columns={a: b for a, b in zip(OPT_FEATS, ETH_OPT_FEATS)})
    both = btc.join(eth, how="outer").sort_index()
    both.index.name = "t"
    return both


def join_opt(panel, opt):
    panel = panel.copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    return panel.merge(opt, left_on="t", right_index=True, how="left")


# ---------- FNG features (assignment text + manifest, causal) ----------
def build_fng_daily():
    """Daily FNG indicators on the daily series; avail = date + 1h."""
    df = pd.read_parquet(FNG_FILE).copy()
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.normalize()
    df = df.sort_values("date").drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    fng = df["fng"].astype(float)
    fng7 = fng.rolling(7, min_periods=7).mean()
    fng_chg7 = fng - fng.shift(7)
    mu90 = fng.rolling(90, min_periods=60).mean()
    sd90 = fng.rolling(90, min_periods=60).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        fng_z = (fng - mu90) / sd90
    out = pd.DataFrame({
        "date": df["date"],
        "avail": df["date"] + pd.Timedelta(hours=1),
        "fng": fng.to_numpy(dtype=float),
        "fng7": fng7.to_numpy(dtype=float),
        "fng_chg7": fng_chg7.to_numpy(dtype=float),
        "fng_z": fng_z.to_numpy(dtype=float),
    }).sort_values("avail").reset_index(drop=True)
    return out


def build_fng_asof(unique_t):
    daily = build_fng_daily()
    ut = pd.to_datetime(pd.Series(sorted(pd.to_datetime(unique_t, utc=True))), utc=True)
    left = pd.DataFrame({"t": ut, "t_plus_4h": ut + pd.Timedelta(hours=4)}).sort_values("t_plus_4h")
    j = pd.merge_asof(left, daily, left_on="t_plus_4h", right_on="avail", direction="backward")
    j = j.sort_values("t").reset_index(drop=True)
    feat = pd.DataFrame({
        "t": pd.to_datetime(j["t"], utc=True),
        "fng": j["fng"].to_numpy(dtype=float),
        "fng7": j["fng7"].to_numpy(dtype=float),
        "fng_chg7": j["fng_chg7"].to_numpy(dtype=float),
        "fng_z": j["fng_z"].to_numpy(dtype=float),
    }).drop_duplicates("t").set_index("t").sort_index()
    return feat, daily


def join_fng(panel, fg):
    panel = panel.copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    return panel.merge(fg, left_on="t", right_index=True, how="left")


# ---------- COT features (assignment text + manifest, causal) ----------
def build_cot_weekly():
    """Weekly COT net positioning; avail = report date + 4 days (Saturday 00:00 UTC)."""
    df = pd.read_parquet(COT_FILE).copy()
    rep = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"], utc=True).dt.normalize()
    df["rep"] = rep
    df = df.sort_values("rep").drop_duplicates("rep", keep="last").sort_values("rep").reset_index(drop=True)
    oi = df["Open_Interest_All"].astype(float).replace(0.0, np.nan)
    lev = (df["Lev_Money_Positions_Long_All"].astype(float) - df["Lev_Money_Positions_Short_All"].astype(float)) / oi
    am = (df["Asset_Mgr_Positions_Long_All"].astype(float) - df["Asset_Mgr_Positions_Short_All"].astype(float)) / oi
    lev = lev.replace([np.inf, -np.inf], np.nan)
    am = am.replace([np.inf, -np.inf], np.nan)
    lev_chg4 = lev - lev.shift(4)
    am_chg4 = am - am.shift(4)

    def wz(s):
        mu = s.rolling(52, min_periods=26).mean()
        sd = s.rolling(52, min_periods=26).std(ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return (s - mu) / sd

    lev_z = wz(lev)
    am_z = wz(am)
    out = pd.DataFrame({
        "rep": df["rep"],
        "avail": df["rep"] + pd.Timedelta(days=4),
        "cot_lev_net": lev.to_numpy(dtype=float),
        "cot_am_net": am.to_numpy(dtype=float),
        "cot_lev_chg4": lev_chg4.to_numpy(dtype=float),
        "cot_am_chg4": am_chg4.to_numpy(dtype=float),
        "cot_lev_z": lev_z.to_numpy(dtype=float),
        "cot_am_z": am_z.to_numpy(dtype=float),
    }).sort_values("avail").reset_index(drop=True)
    return out


def build_cot_asof(unique_t):
    weekly = build_cot_weekly()
    ut = pd.to_datetime(pd.Series(sorted(pd.to_datetime(unique_t, utc=True))), utc=True)
    left = pd.DataFrame({"t": ut, "t_plus_4h": ut + pd.Timedelta(hours=4)}).sort_values("t_plus_4h")
    j = pd.merge_asof(left, weekly, left_on="t_plus_4h", right_on="avail", direction="backward")
    j = j.sort_values("t").reset_index(drop=True)
    feat = pd.DataFrame({
        "t": pd.to_datetime(j["t"], utc=True),
        "cot_lev_net": j["cot_lev_net"].to_numpy(dtype=float),
        "cot_am_net": j["cot_am_net"].to_numpy(dtype=float),
        "cot_lev_chg4": j["cot_lev_chg4"].to_numpy(dtype=float),
        "cot_am_chg4": j["cot_am_chg4"].to_numpy(dtype=float),
        "cot_lev_z": j["cot_lev_z"].to_numpy(dtype=float),
        "cot_am_z": j["cot_am_z"].to_numpy(dtype=float),
    }).drop_duplicates("t").set_index("t").sort_index()
    return feat, weekly


def join_cot(panel, cw):
    panel = panel.copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    return panel.merge(cw, left_on="t", right_index=True, how="left")


# ---------- coinbase premium features (v111 spec verbatim, causal) ----------
def cb_premium(asset: str) -> pd.DataFrame:
    cb = pd.read_parquet(CB_DIR / f"{asset}-USD_1h.parquet")[["open_time", "close"]].rename(columns={"close": "cb"})
    cb["open_time"] = pd.to_datetime(cb["open_time"], utc=True)
    parts = [pd.read_parquet(SPOT17_DIR / f"{asset}USDT_spot_4h_2017.parquet"),
             pd.read_parquet(SPOT17_DIR / f"{asset}USDT_spot_4h.parquet")]
    bn = pd.concat([p[["open_time", "close"]] for p in parts], ignore_index=True)
    bn["open_time"] = pd.to_datetime(bn["open_time"], utc=True)
    bn = bn.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
    j = pd.merge_asof(bn, cb.sort_values("open_time"), left_on="key", right_on="open_time",
                      direction="backward", tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
    p = pd.DataFrame({"t": bn["open_time"], "cbp": 1e4 * np.log(j["cb"].astype(float) / j["close"].astype(float))})
    p6 = p["cbp"].rolling(6, min_periods=4).mean()
    p42 = p["cbp"].rolling(42, min_periods=30).mean()
    m540 = p["cbp"].rolling(540, min_periods=270).mean()
    s540 = p["cbp"].rolling(540, min_periods=270).std()
    return pd.DataFrame({"t": p["t"], "dev": p6 - m540, "z": (p6 - m540) / s540, "chg": p6 - p42})


def build_coinbase_features():
    b = cb_premium("BTC")
    e = cb_premium("ETH")
    feat = pd.DataFrame({"t": b["t"], "cb_btc_dev": b["dev"], "cb_btc_z": b["z"], "cb_btc_chg": b["chg"]})
    feat = feat.merge(pd.DataFrame({"t": e["t"], "cb_eth_z": e["z"], "cb_eth_chg": e["chg"]}), on="t", how="left")
    feat["t"] = pd.to_datetime(feat["t"], utc=True)
    feat = feat.drop_duplicates("t").set_index("t").sort_index()
    return feat


def join_cb(panel, cb):
    panel = panel.copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    return panel.merge(cb, left_on="t", right_index=True, how="left")


def add_xs_xr(panel, cols):
    panel = panel.copy()
    for col in cols:
        mu = panel.groupby("t")[col].transform("mean")
        panel[f"xs_{col}"] = panel[col] - mu
        panel[f"xr_{col}"] = panel.groupby("t")[col].transform(lambda s: s.rank(pct=True))
    return panel


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
        m_ = HistGradientBoostingRegressor(**HGB)
        m_.fit(tr[feats], tr["fv"])
        te["pred_fv"] = m_.predict(te[feats])
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
    m_ = HistGradientBoostingRegressor(**HGB)
    m_.fit(tr[feats], tr["y"])
    te["pred"] = m_.predict(te[feats])
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
        m_ = HistGradientBoostingRegressor(**HGB)
        m_.fit(tr[feats], tr[yh])
        preds[:, j] = m_.predict(te[feats])
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
        m_ = HistGradientBoostingRegressor(**HGB)
        m_.fit(tr[feats], tr[yh])
        preds[:, j] = m_.predict(te[feats])
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
                       p0, lo, hi, p15, governed, gov_target=0.20, gov_den=0.10):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
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
                gi = (gov_target - dd) / gov_den
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


def run_rows(ctx, p0_df, lo_df, hi_df, p15_df, rows_spec, gov_target, gov_den, tag):
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
    for key, cfg in rows_spec.items():
        s = (cfg["target"] / vol).clip(upper=CAP).fillna(1.0)
        s = s.replace([np.inf, -np.inf], CAP).fillna(1.0)
        s_vals = s.to_numpy(dtype=float)
        net, turn, garr, E, maker_rate, orders = run_governed_10bps(
            o_vals, books_vals, carry_vals, s_vals, live_mask, p0, lo, hi, p15,
            cfg["governed"], gov_target=gov_target, gov_den=gov_den)
        summ = summarize_row(pd.Series(net, index=idx), pd.Series(turn, index=idx),
                             pd.Series(garr, index=idx), maker_rate, orders)
        rows[key] = summ
        print(f"{tag} {key} monthly={summ['monthly_pct']} fullDD={summ['full_path_dd']}", flush=True)
    return rows


def train_leg_v92_v94_v103(panel114x, feats114x, panel103x, feats103x, tag):
    a92, a94, a103 = [], [], []
    p92, p94, p103 = [], [], []
    for anchor in ANCHORS:
        te92, ntr92 = train_v92(panel114x, feats114x, anchor)
        ev = te92.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        a92.append(dict(anchor=anchor, train_rows=int(ntr92), n_pred_rows=int(len(te92)),
                        n_pred_rows_with_y=int(len(ev)), ic=round(rho, 4)))
        p92.append(te92)
        print(f"{tag} v92", anchor, ntr92, round(rho, 4), flush=True)
        te94, ntrs94 = train_v94(panel114x, feats114x, anchor)
        ev94 = te94.dropna(subset=["y42"])
        rho94 = float(spearmanr(ev94["pred"], ev94["y42"]).statistic) if len(ev94) > 2 else float("nan")
        a94.append(dict(anchor=anchor, train_rows_h18=ntrs94[0], train_rows_h42=ntrs94[1],
                        train_rows_h84=ntrs94[2], n_pred_rows=int(len(te94)),
                        n_pred_rows_with_y=int(len(ev94)), ic_mean_vs_h42=round(rho94, 4)))
        p94.append(te94)
        print(f"{tag} v94", anchor, ntrs94, round(rho94, 4), flush=True)
        te103, ntrs103 = train_v103(panel103x, feats103x, anchor)
        ic6 = spearman(te103["pred"], te103["y6"])
        ic18 = spearman(te103["pred"], te103["y18"])
        a103.append(dict(anchor=anchor, train_rows_h6=ntrs103[0], train_rows_h18=ntrs103[1],
                         n_pred_rows=int(len(te103)),
                         ic_vs_y6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                         ic_vs_y18=round(float(ic18), 4) if np.isfinite(ic18) else None))
        p103.append(te103)
        print(f"{tag} v103", anchor, ntrs103, round(float(ic6), 4), round(float(ic18), 4), flush=True)
    oos92 = pd.concat(p92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos94 = pd.concat(p94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos103 = pd.concat(p103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    return oos92, oos94, oos103, a92, a94, a103


def ensemble_ctx(ctxs, divisor):
    idx_u = ctxs[0]["idx"]
    for c in ctxs[1:]:
        idx_u = idx_u.union(c["idx"])
    idx_u = idx_u.sort_values()
    acc = None
    for c in ctxs:
        b = c["books"].reindex(idx_u).fillna(0.0)
        acc = b if acc is None else acc + b
    books_ens = acc / divisor
    o_ens = ctxs[0]["o"].reindex(idx_u).ffill()
    carry_ens = ctxs[0]["carry"].reindex(idx_u).fillna(0.0)
    ret1 = o_ens / o_ens.shift(1) - 1
    realized = W_BOOKS * (books_ens.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_ens.shift(1)
    vol_ens = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    return dict(idx=idx_u, o=o_ens, books=books_ens, carry=carry_ens, vol=vol_ens)


def main():
    opt = build_options_features()
    print(f"opt grid {len(opt)} {opt.index.min()} -> {opt.index.max()}", flush=True)
    print(f"opt NaN counts: {opt.isna().sum().to_dict()}", flush=True)
    opt10 = build_options_bprime()
    print(f"opt10 grid {len(opt10)} {opt10.index.min()} -> {opt10.index.max()}", flush=True)
    print(f"opt10 NaN counts: {opt10.isna().sum().to_dict()}", flush=True)
    cbf = build_coinbase_features()
    print(f"cb grid {len(cbf)} {cbf.index.min()} -> {cbf.index.max()}", flush=True)
    print(f"cb NaN counts: {cbf.isna().sum().to_dict()}", flush=True)
    panel114, panel103, bars = build_panels()
    # panels store tz-aware; build asof on tz-aware unique times
    uniq_tz = pd.to_datetime(pd.Series(sorted(set(pd.to_datetime(panel114['t'], utc=True).tolist() + pd.to_datetime(panel103['t'], utc=True).tolist()))), utc=True)
    fgf, fng_daily = build_fng_asof(uniq_tz)
    print(f"fng daily {len(fng_daily)} {fng_daily['date'].min()} -> {fng_daily['date'].max()}", flush=True)
    print(f"fng asof {len(fgf)} {fgf.index.min()} -> {fgf.index.max()}", flush=True)
    print(f"fng NaN counts: {fgf.isna().sum().to_dict()}", flush=True)
    cotf, cot_weekly = build_cot_asof(uniq_tz)
    print(f"cot weekly {len(cot_weekly)} {cot_weekly['rep'].min()} -> {cot_weekly['rep'].max()}", flush=True)
    print(f"cot asof {len(cotf)} {cotf.index.min()} -> {cotf.index.max()}", flush=True)
    print(f"cot NaN counts: {cotf.isna().sum().to_dict()}", flush=True)
    feats114_base = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                              "fv", "realized_vol", "pred_fv", "pvol")]
    feats103_base = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                              "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                              "pred_h6", "pred_h18")]
    assert len(feats114_base) == 26, len(feats114_base)
    assert len(feats103_base) == 36, len(feats103_base)
    # pvol once on original sets (shared by all six legs)
    oos114_pvol, a114 = train_pvol(panel114, feats114_base, bars)
    bars103 = {s: load_base(s)[0] for s in SYMS}
    oos103_pvol, a103 = train_pvol(panel103, feats103_base, bars103)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    # ---- A: v144 direction (xs/xr) ----
    panel114x = add_xs_xr(panel114, XS_BASE)
    panel103x = add_xs_xr(panel103, XS_BASE + XS_EXTRA103)
    feats114x = [c for c in panel114x.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103x = [c for c in panel103x.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18")]
    assert len(feats114x) == 44, len(feats114x)
    assert len(feats103x) == 60, len(feats103x)
    oos92_A, oos94_A, oos103_A, a92_A, a94_A, a103_A = train_leg_v92_v94_v103(
        panel114x, feats114x, panel103x, feats103x, "A/v144")
    ctxA = build_books_from_oos(oos92_A, oos94_A, oos103_A, j114, j103)

    # ---- B: BTC options merged BEFORE xs; xs on base cols only ----
    panel114ob = join_opt(panel114, opt)
    panel103ob = join_opt(panel103, opt)
    panel114B = add_xs_xr(panel114ob, XS_BASE)
    panel103B = add_xs_xr(panel103ob, XS_BASE + XS_EXTRA103)
    feats114B = [c for c in panel114B.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103B = [c for c in panel103B.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18")]
    assert len(feats114B) == 49, len(feats114B)
    assert len(feats103B) == 65, len(feats103B)
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in feats114B)
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in feats103B)
    assert not any(c.startswith("xs_eth_") or c.startswith("xr_eth_") for c in feats114B)
    oos92_B, oos94_B, oos103_B, a92_B, a94_B, a103_B = train_leg_v92_v94_v103(
        panel114B, feats114B, panel103B, feats103B, "B/opt-xs")
    ctxB = build_books_from_oos(oos92_B, oos94_B, oos103_B, j114, j103)

    # ---- Bp: BTC+ETH options (10 cols) merged BEFORE xs ----
    panel114obp = join_opt(panel114, opt10)
    panel103obp = join_opt(panel103, opt10)
    panel114Bp = add_xs_xr(panel114obp, XS_BASE)
    panel103Bp = add_xs_xr(panel103obp, XS_BASE + XS_EXTRA103)
    feats114Bp = [c for c in panel114Bp.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                             "fv", "realized_vol", "pred_fv", "pvol")]
    feats103Bp = [c for c in panel103Bp.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                             "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                             "pred_h6", "pred_h18")]
    assert len(feats114Bp) == 54, len(feats114Bp)
    assert len(feats103Bp) == 70, len(feats103Bp)
    assert all(f in feats114Bp for f in OPT10_FEATS)
    assert all(f in feats103Bp for f in OPT10_FEATS)
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in feats114Bp)
    assert not any(c.startswith("xs_eth_") or c.startswith("xr_eth_") for c in feats114Bp)
    assert not any(c.startswith("xs_opt_") or c.startswith("xr_opt_") for c in feats103Bp)
    assert not any(c.startswith("xs_eth_") or c.startswith("xr_eth_") for c in feats103Bp)
    oos92_Bp, oos94_Bp, oos103_Bp, a92_Bp, a94_Bp, a103_Bp = train_leg_v92_v94_v103(
        panel114Bp, feats114Bp, panel103Bp, feats103Bp, "Bp/btceth-xs")
    ctxBp = build_books_from_oos(oos92_Bp, oos94_Bp, oos103_Bp, j114, j103)

    # ---- D: coinbase merged BEFORE xs; xs on base cols only ----
    panel114cb = join_cb(panel114, cbf)
    panel103cb = join_cb(panel103, cbf)
    cover = {s: round(float(g[CB_FEATS].notna().all(axis=1).mean()), 3)
             for s, g in panel103cb.groupby("sym")}
    first_full = {s: str(g.loc[g[CB_FEATS].notna().all(axis=1), "t"].min())
                  for s, g in panel103cb.groupby("sym")}
    print("coinbase coverage", cover, flush=True)
    print("coinbase first full", first_full, flush=True)
    panel114D = add_xs_xr(panel114cb, XS_BASE)
    panel103D = add_xs_xr(panel103cb, XS_BASE + XS_EXTRA103)
    feats114D = [c for c in panel114D.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103D = [c for c in panel103D.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18")]
    assert len(feats114D) == 49, len(feats114D)
    assert len(feats103D) == 65, len(feats103D)
    assert all(f in feats114D for f in CB_FEATS)
    assert all(f in feats103D for f in CB_FEATS)
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in feats114D)
    assert not any(c.startswith("xs_cb_") or c.startswith("xr_cb_") for c in feats103D)
    oos92_D, oos94_D, oos103_D, a92_D, a94_D, a103_D = train_leg_v92_v94_v103(
        panel114D, feats114D, panel103D, feats103D, "D/cb-xs")
    ctxD = build_books_from_oos(oos92_D, oos94_D, oos103_D, j114, j103)

    # ---- G: FNG merged BEFORE xs; xs on base cols only ----
    panel114fg = join_fng(panel114, fgf)
    panel103fg = join_fng(panel103, fgf)
    fng_cover = {s: round(float(g[FNG_FEATS].notna().all(axis=1).mean()), 4)
                 for s, g in panel103fg.groupby("sym")}
    print("fng coverage", fng_cover, flush=True)
    panel114G = add_xs_xr(panel114fg, XS_BASE)
    panel103G = add_xs_xr(panel103fg, XS_BASE + XS_EXTRA103)
    feats114G = [c for c in panel114G.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103G = [c for c in panel103G.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18")]
    assert len(feats114G) == 48, len(feats114G)
    assert len(feats103G) == 64, len(feats103G)
    assert all(f in feats114G for f in FNG_FEATS)
    assert all(f in feats103G for f in FNG_FEATS)
    assert not any(c.startswith("xs_fng") or c.startswith("xr_fng") for c in feats114G)
    assert not any(c.startswith("xs_fng") or c.startswith("xr_fng") for c in feats103G)
    oos92_G, oos94_G, oos103_G, a92_G, a94_G, a103_G = train_leg_v92_v94_v103(
        panel114G, feats114G, panel103G, feats103G, "G/fng-xs")
    ctxG = build_books_from_oos(oos92_G, oos94_G, oos103_G, j114, j103)

    # ---- H: COT merged BEFORE xs; xs on base cols only ----
    panel114ct = join_cot(panel114, cotf)
    panel103ct = join_cot(panel103, cotf)
    cot_cover = {s: round(float(g[COT_FEATS].notna().all(axis=1).mean()), 4)
                 for s, g in panel103ct.groupby("sym")}
    print("cot coverage", cot_cover, flush=True)
    panel114H = add_xs_xr(panel114ct, XS_BASE)
    panel103H = add_xs_xr(panel103ct, XS_BASE + XS_EXTRA103)
    feats114H = [c for c in panel114H.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                           "fv", "realized_vol", "pred_fv", "pvol")]
    feats103H = [c for c in panel103H.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                           "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                           "pred_h6", "pred_h18")]
    assert len(feats114H) == 50, len(feats114H)
    assert len(feats103H) == 66, len(feats103H)
    assert all(f in feats114H for f in COT_FEATS)
    assert all(f in feats103H for f in COT_FEATS)
    assert not any(c.startswith("xs_cot_") or c.startswith("xr_cot_") for c in feats114H)
    assert not any(c.startswith("xs_cot_") or c.startswith("xr_cot_") for c in feats103H)
    oos92_H, oos94_H, oos103_H, a92_H, a94_H, a103_H = train_leg_v92_v94_v103(
        panel114H, feats114H, panel103H, feats103H, "H/cot-xs")
    ctxH = build_books_from_oos(oos92_H, oos94_H, oos103_H, j114, j103)

    # ---- ensembles: v158=(A+Bp+D)/3, v159=(A+B+D+G)/4, v160=(A+B+D+H)/4 ----
    ctx158 = ensemble_ctx([ctxA, ctxBp, ctxD], 3)
    ctx159 = ensemble_ctx([ctxA, ctxB, ctxD, ctxG], 4)
    ctx160 = ensemble_ctx([ctxA, ctxB, ctxD, ctxH], 4)
    idx_union = ctx158["idx"].union(ctx159["idx"]).union(ctx160["idx"]).sort_values()
    p0_df, lo_df, hi_df, p15_df = precompute_exec_frames(idx_union, list(SYMS))
    rowsA = run_rows(ctxA, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "A")
    rowsB = run_rows(ctxB, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "B")
    rowsBp = run_rows(ctxBp, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "Bp")
    rowsD = run_rows(ctxD, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "D")
    rowsG = run_rows(ctxG, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "G")
    rowsH = run_rows(ctxH, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "H")
    rows158 = run_rows(ctx158, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "v158")
    rows159 = run_rows(ctx159, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "v159")
    rows160 = run_rows(ctx160, p0_df, lo_df, hi_df, p15_df, ROWS_V158_V160, GOV20[0], GOV20[1], "v160")

    out = {
        "version": "v158_v160_audit_replication",
        "anchors": list(ANCHORS),
        "live": {"start": str(START), "end_exclusive": str(END), "days": 1825,
                 "union_bars": int(len(idx_union)), "oos_span": [str(idx_union[0]), str(idx_union[-1])]},
        "rows_spec": {k: {"target": v["target"], "governed": v["governed"],
                          "gov_target": GOV20[0], "gov_den": GOV20[1]} for k, v in ROWS_V158_V160.items()},
        "A_v144": {"rows": rowsA, "n_replaced": ctxA["n_replaced"]},
        "B_opt_xs": {"rows": rowsB, "n_replaced": ctxB["n_replaced"]},
        "Bp_btceth_xs": {"rows": rowsBp, "n_replaced": ctxBp["n_replaced"]},
        "D_cb": {"rows": rowsD, "n_replaced": ctxD["n_replaced"],
                 "coverage": cover, "first_full": first_full},
        "G_fng": {"rows": rowsG, "n_replaced": ctxG["n_replaced"], "coverage": fng_cover},
        "H_cot": {"rows": rowsH, "n_replaced": ctxH["n_replaced"], "coverage": cot_cover},
        "v158": {"rows": rows158,
                 "overlap_ABpD": int(ctxA["idx"].intersection(ctxBp["idx"]).intersection(ctxD["idx"]).size),
                 "idxA": int(len(ctxA["idx"])), "idxBp": int(len(ctxBp["idx"])), "idxD": int(len(ctxD["idx"]))},
        "v159": {"rows": rows159,
                 "overlap_ABDG": int(ctxA["idx"].intersection(ctxB["idx"]).intersection(ctxD["idx"]).intersection(ctxG["idx"]).size),
                 "idxA": int(len(ctxA["idx"])), "idxB": int(len(ctxB["idx"])),
                 "idxD": int(len(ctxD["idx"])), "idxG": int(len(ctxG["idx"]))},
        "v160": {"rows": rows160,
                 "overlap_ABDH": int(ctxA["idx"].intersection(ctxB["idx"]).intersection(ctxD["idx"]).intersection(ctxH["idx"]).size),
                 "idxA": int(len(ctxA["idx"])), "idxB": int(len(ctxB["idx"])),
                 "idxD": int(len(ctxD["idx"])), "idxH": int(len(ctxH["idx"]))},
        "anchors_v92_A": a92_A, "anchors_v94_A": a94_A, "anchors_v103_A": a103_A,
        "anchors_v92_B": a92_B, "anchors_v94_B": a94_B, "anchors_v103_B": a103_B,
        "anchors_v92_Bp": a92_Bp, "anchors_v94_Bp": a94_Bp, "anchors_v103_Bp": a103_Bp,
        "anchors_v92_D": a92_D, "anchors_v94_D": a94_D, "anchors_v103_D": a103_D,
        "anchors_v92_G": a92_G, "anchors_v94_G": a94_G, "anchors_v103_G": a103_G,
        "anchors_v92_H": a92_H, "anchors_v94_H": a94_H, "anchors_v103_H": a103_H,
        "anchors_v114_pvol": a114, "anchors_v103_pvol": a103,
        "feats114_base_n": len(feats114_base), "feats103_base_n": len(feats103_base),
        "feats114x": feats114x, "feats103x": feats103x,
        "feats114B": feats114B, "feats103B": feats103B,
        "feats114Bp": feats114Bp, "feats103Bp": feats103Bp,
        "feats114D": feats114D, "feats103D": feats103D,
        "feats114G": feats114G, "feats103G": feats103G,
        "feats114H": feats114H, "feats103H": feats103H,
        "opt": {"file": str(OPT_FILE), "bars": int(len(opt)),
                "first": str(opt.index.min()), "last": str(opt.index.max()),
                "nan_counts": {k: int(v) for k, v in opt.isna().sum().items()}},
        "opt10": {"btc_file": str(OPT_FILE), "eth_file": str(OPT_ETH_FILE), "bars": int(len(opt10)),
                  "first": str(opt10.index.min()), "last": str(opt10.index.max()),
                  "nan_counts": {k: int(v) for k, v in opt10.isna().sum().items()}},
        "cb": {"bars": int(len(cbf)), "first": str(cbf.index.min()), "last": str(cbf.index.max()),
               "nan_counts": {k: int(v) for k, v in cbf.isna().sum().items()}},
        "fng": {"file": str(FNG_FILE), "daily_rows": int(len(fng_daily)),
                "first": str(pd.to_datetime(fng_daily['date']).min()), "last": str(pd.to_datetime(fng_daily['date']).max()),
                "asof_rows": int(len(fgf)), "asof_first": str(fgf.index.min()), "asof_last": str(fgf.index.max()),
                "nan_counts": {k: int(v) for k, v in fgf.isna().sum().items()}, "coverage": fng_cover},
        "cot": {"file": str(COT_FILE), "weekly_rows": int(len(cot_weekly)),
                "first": str(pd.to_datetime(cot_weekly['rep']).min()), "last": str(pd.to_datetime(cot_weekly['rep']).max()),
                "asof_rows": int(len(cotf)), "asof_first": str(cotf.index.min()), "asof_last": str(cotf.index.max()),
                "nan_counts": {k: int(v) for k, v in cotf.isna().sum().items()}, "coverage": cot_cover},
        "meta": {
            "A_spec": "v144 xs/xr direction (9+3 base cols, 44/60 feats), pvol original sets, 0.25/0.25/0.5 tranch mean/6 own 0.20-cap-2, gov j=i-2 540-bar peak clip((0.20-DD)/0.10), 10bps 1m T=t+4h minutes 2..14",
            "B_spec": "5 BTC options cols merged on t into v114+v103 BEFORE xs; xs on BASE/BASE+FLOWX only (no xs/xr of opt cols); return 49/65; vol original; v144 engine",
            "Bp_spec": "10 BTC+ETH options cols (eth_ prefix, outer join on t) merged on t into v114+v103 BEFORE xs; xs on BASE/BASE+FLOWX only (no xs/xr of opt/eth cols); return 54/70; vol original; v144 engine",
            "D_spec": "5 coinbase cols merged on t into v114+v103 BEFORE xs (one value per t, asof-backward tol 2h, trailing p6/p42/m540/s540); xs on BASE/BASE+FLOWX only (no xs/xr of cb cols); return v114 49 / v103 65; vol original; v144 engine",
            "G_spec": "4 FNG cols (fng, fng7 roll7 min7, fng_chg7 shift7, fng_z roll90 min60 ddof1) daily D avail D+1h, asof last avail <= t+4h, merged on t BEFORE xs; xs BASE only; return 48/64; vol original",
            "H_spec": "6 COT cols (cot_lev_net, cot_am_net, chg4 shift4, z roll52 min26 ddof1) report D avail D+4d, dedup, asof last avail <= t+4h, merged on t BEFORE xs; xs BASE only; return 50/66; vol original",
            "v158_spec": "books=(A+Bp+D)/3 on union index missing->0, vol recomputed from ensemble books, then v144 engine rows 0.15 ungoverned / 0.20 / 0.25 governed gov20 10bps 1m",
            "v159_spec": "books=(A+B+D+G)/4 on union index missing->0, vol recomputed from ensemble books, then v144 engine rows 0.15 ungoverned / 0.20 / 0.25 governed gov20 10bps 1m",
            "v160_spec": "books=(A+B+D+H)/4 on union index missing->0, vol recomputed from ensemble books, then v144 engine rows 0.15 ungoverned / 0.20 / 0.25 governed gov20 10bps 1m",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"A": {r: v["monthly_pct"] for r, v in rowsA.items()},
                      "B": {r: v["monthly_pct"] for r, v in rowsB.items()},
                      "Bp": {r: v["monthly_pct"] for r, v in rowsBp.items()},
                      "D": {r: v["monthly_pct"] for r, v in rowsD.items()},
                      "G": {r: v["monthly_pct"] for r, v in rowsG.items()},
                      "H": {r: v["monthly_pct"] for r, v in rowsH.items()},
                      "v158": {r: v["monthly_pct"] for r, v in rows158.items()},
                      "v159": {r: v["monthly_pct"] for r, v in rows159.items()},
                      "v160": {r: v["monthly_pct"] for r, v in rows160.items()}}, indent=2))


if __name__ == "__main__":
    main()
