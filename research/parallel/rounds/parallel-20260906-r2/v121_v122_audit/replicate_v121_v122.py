"""Blind v121+v122 audit replication (Part A). Does NOT read research/.../v121/* nor v122/*.

Base (per OPENCODE_V121_V122_AUDIT.md): audited v115 replication (books, v110 engine,
target 0.15 ungoverned).

A1 (v121): v103 panel (v92 base + spot prefix + 10 flow feats, 36 feats) with
  horizons y6,y18, embargo 78 bars (cutoff=anchor-78*4h, rows need t+(h+1)*4h<cutoff).
  For each horizon and member m=0..9: training calendar days (UTC floor of t,
  sorted unique) sampled without replacement, size int(0.7*n_days),
  numpy default_rng(m).choice; all rows of chosen days;
  HGB(max_depth 4, lr 0.03, max_iter 400, min_samples_leaf 300, l2 1.0,
  max_features 0.7, random_state m); pred = mean of 20 member predictions.
  Report IC, bagged LS book (own vol target) and v115 portfolio with it (0.25/0.25/0.5).

A2 (v122): on the v114 panel (extended Bitstamp+Coinbase history, v92 features)
  y168 = clip(log(open[t+169]/open[t+1])/(vol42*sqrt(168)), +-4) per asset;
  HGB (v92 params, seed 0) on the v94 feature list (26 feats),
  cutoff = anchor-228*4h, rows need t+169*4h < cutoff;
  LS book = v94 weights_ls with own v94 vol scale (v114 panel).
  Portfolio books = 0.2 v92 LO + 0.2 v94 LS + 0.4 v103 LS + 0.2 y168 LS
  (each with own scale, union index from first v103 t), v110 engine target 0.15
  ungoverned. Report IC, book and portfolio results.

Blind choices (fixed before running, documented):
 - v103 panel built exactly as audited v103_v105 replicate (v92 features + flow,
   spot prefix, BTC context); v114 panel built exactly as audited v113_v114
   replicate (Coinbase+Bitstamp prepend, v92 features, BTC context).
 - Bag day sampling: days = sorted unique UTC floor('D') of tr.t for that
   horizon; rng = numpy default_rng(m) fresh per (h,m); chosen =
   rng.choice(days, size=int(0.7*n_days), replace=False); tr_m = rows whose
   floor day isin chosen. Same seed m for y6 and y18 gives same RNG sequence
   but populations/sizes differ slightly (documented).
 - v115 legs (v92 LO, v94 LS, v103 LS) recomputed from audited OOS CSVs with
   inline audited formulas (no retraining, replay only); y168/bag legs retrained
   per spec. Scales target 0.20 cap 2 (W.shift(2), trailing 360/min-120, NaN->1).
 - Portfolio wrapper s target 0.15 (realized=0.8*sum(books.shift(2)*ret1)+
   0.6*carry.shift(1), rolling-360/min-120*sqrt(2190), cap 2, NaN->1),
   live [2021-09-24,2026-09-23), v110 sequential engine ungoverned, 3 scenarios.
 - No v121/v122/v115/v114/v103/v110/v92/v94 leader module imported.
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
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
TARGET = 0.15

BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"

HS_V103 = (6, 18)
EMBARGO_V103 = 78
HGB_BAG = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
               l2_regularization=1.0, max_features=0.7)
HGB_V92 = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
               l2_regularization=1.0, random_state=0)
FLOW_FEATS = ["tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z",
              "tsize_z", "ntr_z", "rng6", "clv6"]
EMBARGO_Y168 = 228
H_Y168 = 168


# ---------- base loaders (audited v103_v105 / v113_v114 logic, inline) ----------
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


def v92_features(b, d, f):
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
    v42 = vol42.to_numpy()
    for h in (6, 18, 42):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (v42 * np.sqrt(h)), -4, 4)
    return x


def add_flow(b, x):
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
    x["rng6"] = hl.rolling(6).mean() / x["vol42"]
    rng = (b["high"].astype(float) - b["low"].astype(float))
    clv = (b["close"].astype(float) - b["low"].astype(float)) / rng
    clv = clv.where(rng != 0, np.nan)
    x["clv6"] = clv.rolling(6).mean() - 0.5
    return x


def build_v103_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_base(s)
        x = v92_features(b, d, f)
        x = add_flow(b, x)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


# ---- v114 extended panel (audited v113_v114 logic) ----
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


def build_v114_panel():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    rows = []
    for i, s in enumerate(SYMS):
        b0, d0, f = load_base(s)
        if s in agg:
            a4, a1 = agg[s]
            b = pd.concat([a4[a4["open_time"] < b0["open_time"].min()], b0], ignore_index=True).sort_values("open_time").reset_index(drop=True)
            d = pd.concat([a1[a1["open_time"] < d0["open_time"].min()], d0], ignore_index=True).sort_values("open_time").reset_index(drop=True)
        else:
            b, d = b0, d0
        x = v92_features(b, d, f)
        # y168 per asset
        o = b["open"].astype(float).to_numpy()
        n = len(b)
        fwd = np.full(n, np.nan)
        if n > 1 + H_Y168:
            fwd[: n - 1 - H_Y168] = np.log(o[1 + H_Y168:] / o[1: n - H_Y168])
        x["y168"] = np.clip(fwd / (x["vol42"].to_numpy() * np.sqrt(H_Y168)), -4, 4)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


# ---------- shared book/engine math (audited v115 logic) ----------
def weights_lo(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def weights_ls(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


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


def simulate_standalone(o, W, scale, fee, slip):
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0) if isinstance(scale, pd.Series) else W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip):
    n, k = o_vals.shape[0], o_vals.shape[1]
    fwd = np.full_like(o_vals, 0.0)
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
        ni = gross - tcost - fund + cgross - ccost
        net[i] = ni
        turn[i] = float(np.sum(np.abs(w - prev_w)))
        prev_w, prev_c = w, c
    return net, turn


def summarize_seq(net_s, turn_s):
    ys = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net_s.index >= a0) & (net_s.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **stats(net_s[mk], turn_s[mk])))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(
        yearly=ys,
        monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
        worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
        full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
    )


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def portfolio_seq(books, o, carry_s, target=0.15):
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s = (target / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    live_mask = np.asarray((books.index >= START) & (books.index < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s.to_numpy(dtype=float)
    res = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        res[sc] = summarize_seq(pd.Series(net, index=books.index), pd.Series(turn, index=books.index))
        print(f"portfolio t{TARGET} {sc} monthly={res[sc]['monthly_pct']} worstDD={res[sc]['worst_year_dd']} fullDD={res[sc]['full_path_dd']}", flush=True)
    return res, s


def main():
    print("building v103 panel...", flush=True)
    panel103 = build_v103_panel()
    feats103 = [c for c in panel103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    print(f"v103 panel {len(panel103)} rows, {len(feats103)} feats", flush=True)

    # ---- A1 bag ----
    oos_bag_parts, ic_bag = [], {}
    for a in ANCHORS:
        at = pd.Timestamp(a, tz="UTC")
        cutoff = at - pd.Timedelta(hours=4 * EMBARGO_V103)
        te = panel103[(panel103.t >= at) & (panel103.t < at + pd.Timedelta(days=365))].copy()
        preds = np.zeros((len(te), 20))
        rows = {}
        j = 0
        for h in HS_V103:
            yh = f"y{h}"
            tr = panel103[(panel103.t < cutoff) & panel103[yh].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            rows[h] = int(len(tr))
            day = pd.to_datetime(tr["t"], utc=True).dt.floor("D")
            days = np.sort(day.unique())
            n_days = len(days)
            size = int(0.7 * n_days)
            rows[f"n_days_h{h}"] = int(n_days)
            rows[f"sample_days_h{h}"] = int(size)
            tr_day = day
            for m in range(10):
                rng = np.random.default_rng(m)
                chosen = rng.choice(days, size=size, replace=False)
                tr_m = tr[tr_day.isin(chosen)]
                mdl = HistGradientBoostingRegressor(**HGB_BAG, random_state=m)
                mdl.fit(tr_m[feats103], tr_m[yh])
                preds[:, j] = mdl.predict(te[feats103])
                j += 1
        te["pred"] = preds.mean(axis=1)
        oos_bag_parts.append(te)
        ic_bag[a] = dict(train_rows=rows,
                         ic_y6=round(spearman(te["pred"], te["y6"]), 4),
                         ic_y18=round(spearman(te["pred"], te["y18"]), 4),
                         ic_y42=round(spearman(te["pred"], te["y42"]), 4))
        print(a, ic_bag[a], flush=True)
    oos_bag = pd.concat(oos_bag_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o_bag = oos_bag.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    W_bag = weights_ls(oos_bag)
    s_bag = vol_scale(o_bag, W_bag)
    book_bag = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = simulate_standalone(o_bag, W_bag, s_bag, fee, slip)
        ys = []
        for an in ANCHORS:
            a0 = pd.Timestamp(an, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            ys.append(dict(anchor=an, **stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
        full = (net.index >= START) & (net.index < END)
        eq = (1 + net[full]).cumprod()
        book_bag[sc] = dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                            worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                            full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))
        print("v121 bag book", sc, book_bag[sc]["monthly_pct"], book_bag[sc]["worst_year_dd"], flush=True)

    # v115 portfolio with bag (0.25/0.25/0.5)
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    W_lo = weights_lo(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94 = weights_ls(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    s_lo = vol_scale(o_v114, W_lo.reindex(o_v114.index).fillna(0.0))
    s94 = vol_scale(o_v114, W94.reindex(o_v114.index).fillna(0.0))
    s_bag_o = vol_scale(o_bag, W_bag.reindex(o_bag.index).fillna(0.0))
    idx = W_lo.index.union(W94.index).union(W_bag.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
    b_bag = W_bag.reindex(idx).fillna(0.0).mul(s_bag_o.reindex(idx).fillna(1.0), axis=0)
    books121 = 0.25 * b_lo + 0.25 * b94 + 0.5 * b_bag
    o121 = o_v103.reindex(idx).sort_index()
    books121 = books121[o121.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry121 = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    port121, s121 = portfolio_seq(books121, o121, carry121)

    # ---- A2 y168 ----
    print("building v114 panel...", flush=True)
    panel114 = build_v114_panel()
    feats94 = [c for c in panel114.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    print(f"v114 panel {len(panel114)} rows, {len(feats94)} feats", flush=True)
    oos168_parts, ic168 = [], {}
    for a in ANCHORS:
        at = pd.Timestamp(a, tz="UTC")
        cutoff = at - pd.Timedelta(hours=4 * EMBARGO_Y168)
        tr = panel114[(panel114.t < cutoff) & panel114["y168"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H_Y168 + 1)) < cutoff]
        te = panel114[(panel114.t >= at) & (panel114.t < at + pd.Timedelta(days=365))].copy()
        mdl = HistGradientBoostingRegressor(**HGB_V92)
        mdl.fit(tr[feats94], tr["y168"])
        te["pred"] = mdl.predict(te[feats94])
        oos168_parts.append(te)
        ev = te.dropna(subset=["y168"])
        ic168[a] = dict(train_rows=int(len(tr)), n_pred_rows=int(len(te)),
                        n_pred_with_y168=int(len(ev)),
                        ic_y168=round(float(spearmanr(ev["pred"], ev["y168"]).statistic) if len(ev) > 2 else float("nan"), 4))
        print(a, ic168[a], flush=True)
    oos168 = pd.concat(oos168_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o114_full = panel114.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    # restrict opens to OOS span for weights (weights_ls uses oos index anyway)
    W168 = weights_ls(oos168)
    o168 = oos168.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    s168 = vol_scale(o168, W168)
    book168 = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = simulate_standalone(o168, W168, s168, fee, slip)
        ys = []
        for an in ANCHORS:
            a0 = pd.Timestamp(an, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            ys.append(dict(anchor=an, **stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
        full = (net.index >= START) & (net.index < END)
        eq = (1 + net[full]).cumprod()
        book168[sc] = dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                           worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                           full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))
        print("v122 y168 book", sc, book168[sc]["monthly_pct"], flush=True)

    # portfolio 0.2/0.2/0.4/0.2
    W103 = weights_ls(o103_df.sort_values(["t", "sym"]).reset_index(drop=True))
    s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))
    s168_o = vol_scale(o168, W168.reindex(o168.index).fillna(0.0))
    # own scales already computed for lo/94 above; recompute aligned to full union below
    idx2 = W_lo.index.union(W94.index).union(W103.index).union(W168.index).sort_values()
    idx2 = idx2[idx2 >= first_v103]
    bb_lo = W_lo.reindex(idx2).fillna(0.0).mul(s_lo.reindex(idx2).fillna(1.0), axis=0)
    bb94 = W94.reindex(idx2).fillna(0.0).mul(s94.reindex(idx2).fillna(1.0), axis=0)
    bb103 = W103.reindex(idx2).fillna(0.0).mul(s103.reindex(idx2).fillna(1.0), axis=0)
    bb168 = W168.reindex(idx2).fillna(0.0).mul(s168_o.reindex(idx2).fillna(1.0), axis=0)
    books122 = 0.2 * bb_lo + 0.2 * bb94 + 0.4 * bb103 + 0.2 * bb168
    o122 = o_v103.reindex(idx2).sort_index()
    books122 = books122[o122.columns]
    carry122 = carry.reindex(idx2)["carry"].astype(float).fillna(0.0)
    port122, s122 = portfolio_seq(books122, o122, carry122)

    out = {
        "version": "v121_v122_audit_replication",
        "v121": {"ic": ic_bag, "features": feats103, "horizons": list(HS_V103),
                 "bag": {"members": 10, "sample_frac": 0.7, "max_features": 0.7},
                 "book_bagged_LS_own_scale": book_bag,
                 "portfolio_v115_with_bag_025_025_05_t15_ungoverned": port121},
        "v122": {"ic": ic168, "features": feats94, "target": "y168",
                 "cutoff_rule": "cutoff=anchor-228*4h; rows need t+169*4h<cutoff",
                 "book_y168_LS_own_scale": book168,
                 "portfolio_02_02_04_02_t15_ungoverned": port122},
        "meta": {
            "anchors": list(ANCHORS),
            "target": TARGET,
            "governed": False,
            "union_bars_v121": int(len(idx)),
            "n_live_bars_v121": int(((idx >= START) & (idx < END)).sum()),
            "union_bars_v122": int(len(idx2)),
            "n_live_bars_v122": int(((idx2 >= START) & (idx2 < END)).sum()),
            "oos_span": [str(idx[0]), str(idx[-1])],
            "first_v103_t": str(first_v103),
            "books121_spec": "books=0.25*b_lo(v114 LO*scale114)+0.25*b94(v114 LS*scale114)+0.5*b_bag(bagged v103 LS*own scale); union t>=first v103 t; opens=v103 OOS",
            "books122_spec": "books=0.2*v92LO+0.2*v94LS+0.4*v103LS+0.2*y168LS (each own 20%-cap-2 scale; v92/v94/y168 on v114 opens, v103 on v103 opens); union t>=first v103 t; opens=v103 OOS",
            "wrapper_spec": "realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1); vol rolling-360/min-120*sqrt(2190); s=min(0.15/vol,2) NaN->1; live [2021-09-24,2026-09-23); ungoverned; w=0.8*s*books c=0.6*s; net=w*fwd-|dw|(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
            "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    oos_bag[["t", "sym", "open", "pred", "y6", "y18", "y42", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v121_bag.csv", index=False)
    oos168[["t", "sym", "open", "pred", "y168", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v122_y168.csv", index=False)
    print(json.dumps({"v121_union": len(idx), "v122_union": len(idx2)}, indent=2))


if __name__ == "__main__":
    main()
