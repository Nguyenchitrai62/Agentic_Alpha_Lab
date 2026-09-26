"""Blind v136+v137 audit replication (Part A).
Does NOT read research/.../v136/* nor research/.../v137/*.

Base (per OPENCODE_V136_V137_AUDIT.md):
  audited v132_v133 (v133 configuration) and v135 (1m bar stats,
  limit-offset execution) replications.

A1 (v136): for every return model of v133 (v92 on target y H=42 with v92
  embargo 102; each v94 horizon 18/42/84 with v94 embargo 144=max(H)+60;
  each v103 horizon 6/18 with embargo 78) and anchor: training rows as the
  audited code (t < cutoff, target notna, t+(h+1)*4h < cutoff); val =
  training rows with t >= cutoff-730d (pandas .sample(20000, random_state=0)
  if >20000); inner-train = training rows with t+(h+1)*4h < val_start -
  embargo*4h. HGB (v92 params) on inner-train, sklearn permutation_importance
  on val with scoring=make_scorer(Spearman pred vs target), n_repeats=3,
  random_state=0; keep features with mean importance > 0 (top 5 by importance
  if fewer than 5); refit on all training rows with kept features.
  v94/v103 predictions = mean over horizons. Then v133 pipeline (pvol swap
  by v129 method unchanged, tranching, portfolio target 0.15). Report
  kept-feature counts and three scenarios.
  Blind choice: pvol models are NOT feature-selected (assignment lists only
  v92/v94/v103 return models); pvol retrained by the audited v129 method.
A2 (v137): v133 books (audited OOS CSVs + pvol swap, tranched, own scales);
  portfolio target in (0.15,0.17,0.19,0.21); execution with the v135 rule at
  d=10bps; report monthly, yearly, full-path DD per target (0.15 must equal
  the v135 10bps row).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import make_scorer

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0),
        "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102
HS_V94 = (18, 42, 84)
EMB_V94 = 144
HS_V103 = (6, 18)
EMB_V103 = 78
H_V92 = 42
EMB_V92 = 102
TARGETS_V137 = (0.15, 0.17, 0.19, 0.21)
D_V137_BPS = 10

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


def spearman_score_fn(y_true, y_pred):
    m = pd.DataFrame({"a": np.asarray(y_true, dtype=float),
                      "b": np.asarray(y_pred, dtype=float)}).dropna()
    if len(m) < 3:
        return 0.0
    with np.errstate(all="ignore"):
        r = spearmanr(m["a"], m["b"]).statistic
    return float(r) if np.isfinite(r) else 0.0


SPEARMAN_SCORER = make_scorer(spearman_score_fn)


# ---------- weights/scales/engine (audited v133 path) ----------
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


# ---------- panels (audited v129/v135 method: v114 extended, v103 base) ----------
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
    rows114, rows103 = [], []
    bars114, bars103 = {}, {}
    for i, s in enumerate(SYMS):
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        bars114[s] = b
        x = features_base(b, d, f, with_flow=False)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows114.append(x)
        b2, d2, f2 = load_base(s)
        bars103[s] = b2
        x2 = features_base(b2, d2, f2, with_flow=True)
        x2["asset"] = i
        x2["t"] = b2["open_time"]
        x2["open"] = b2["open"].astype(float).to_numpy()
        x2["sym"] = s
        x2["bar"] = np.arange(len(b2))
        rows103.append(x2)
    panel114 = pd.concat(rows114, ignore_index=True)
    btc = panel114[panel114.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel114 = panel114.join(btc, on="t")
    panel103 = pd.concat(rows103, ignore_index=True)
    btc2 = panel103[panel103.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel103 = panel103.join(btc2, on="t")
    return panel114, panel103, bars114, bars103


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def train_pvol(panel, feats, bars):
    fv_map = {}
    for s, b in bars.items():
        lo = np.log(b["open"].astype(float))
        r = lo.diff()
        s42 = r.rolling(42).std(ddof=1)
        fv_map[s] = (np.log(s42.shift(-43)).to_numpy(), s42.shift(-43).to_numpy())
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


# ---------- v136 selection ----------
def select_and_predict(panel, feats, target_col, h, embargo, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * embargo)
    tr_all = panel[(panel.t < cutoff) & panel[target_col].notna()]
    tr_all = tr_all[tr_all.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
    val_start = cutoff - pd.Timedelta(days=730)
    val = tr_all[tr_all.t >= val_start].copy()
    n_val_full = int(len(val))
    if len(val) > 20000:
        val = val.sample(20000, random_state=0)
    inner = tr_all[tr_all.t + pd.Timedelta(hours=4 * (h + 1)) < val_start - pd.Timedelta(hours=4 * embargo)]
    m0 = HistGradientBoostingRegressor(**HGB)
    m0.fit(inner[feats], inner[target_col])
    pi = permutation_importance(m0, val[feats], val[target_col], scoring=SPEARMAN_SCORER,
                                n_repeats=3, random_state=0)
    means = np.asarray(pi.importances_mean, dtype=float)
    order = np.argsort(-means, kind="stable")
    keep_idx = [i for i in order if means[i] > 0]
    if len(keep_idx) < 5:
        keep_idx = list(order[:5])
    kept = [feats[i] for i in keep_idx]
    m = HistGradientBoostingRegressor(**HGB)
    m.fit(tr_all[kept], tr_all[target_col])
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    te["pred"] = m.predict(te[kept])
    te[f"pred_h{h}"] = te["pred"]
    info = dict(anchor=anchor, target=target_col, h=int(h), embargo=int(embargo),
                train_rows=int(len(tr_all)), val_rows_full=int(n_val_full),
                val_rows_used=int(len(val)), inner_rows=int(len(inner)),
                n_pred_rows=int(len(te)), kept_features=list(kept),
                n_kept=int(len(kept)),
                importances={f: round(float(v), 6) for f, v in zip(feats, means)})
    print(f"sel {target_col} h={h} {anchor} tr={len(tr_all)} inner={len(inner)} "
          f"val={len(val)}/{n_val_full} kept={len(kept)}", flush=True)
    return te, info


def part_a1_v136(panel114, feats114, panel103, feats103):
    infos = {"v92": [], "v94": {}, "v103": {}}
    for h in HS_V94:
        infos["v94"][str(h)] = []
    for h in HS_V103:
        infos["v103"][str(h)] = []
    p92, p94_by_h, p103_by_h = [], {h: [] for h in HS_V94}, {h: [] for h in HS_V103}
    for anchor in ANCHORS:
        te92, i92 = select_and_predict(panel114, feats114, "y", H_V92, EMB_V92, anchor)
        infos["v92"].append(i92)
        p92.append(te92)
        for h in HS_V94:
            te, ii = select_and_predict(panel114, feats114, f"y{h}", h, EMB_V94, anchor)
            infos["v94"][str(h)].append(ii)
            p94_by_h[h].append(te[["t", "sym", "open", "rib", "vol42", f"pred_h{h}"]].copy())
        for h in HS_V103:
            te, ii = select_and_predict(panel103, feats103, f"y{h}", h, EMB_V103, anchor)
            infos["v103"][str(h)].append(ii)
            p103_by_h[h].append(te[["t", "sym", "open", "rib", "vol42", f"pred_h{h}"]].copy())
    oos92 = pd.concat(p92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    # mean over horizons for v94/v103
    parts94 = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        frames = []
        for h in HS_V94:
            df = pd.concat(p94_by_h[h], ignore_index=True)
            df = df[(pd.to_datetime(df["t"], utc=True) >= a) & (pd.to_datetime(df["t"], utc=True) < end)]
            frames.append(df.set_index(["t", "sym"])[f"pred_h{h}"])
        mean_pred = sum(frames) / len(frames)
        base = pd.concat(p94_by_h[HS_V94[0]], ignore_index=True)
        base = base[(pd.to_datetime(base["t"], utc=True) >= a) & (pd.to_datetime(base["t"], utc=True) < end)].set_index(["t", "sym"]).sort_index()
        base["pred"] = mean_pred.reindex(base.index).to_numpy()
        parts94.append(base.reset_index())
    oos94 = pd.concat(parts94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    parts103 = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        frames = []
        for h in HS_V103:
            df = pd.concat(p103_by_h[h], ignore_index=True)
            df = df[(pd.to_datetime(df["t"], utc=True) >= a) & (pd.to_datetime(df["t"], utc=True) < end)]
            frames.append(df.set_index(["t", "sym"])[f"pred_h{h}"])
        mean_pred = sum(frames) / len(frames)
        base = pd.concat(p103_by_h[HS_V103[0]], ignore_index=True)
        base = base[(pd.to_datetime(base["t"], utc=True) >= a) & (pd.to_datetime(base["t"], utc=True) < end)].set_index(["t", "sym"]).sort_index()
        base["pred"] = mean_pred.reindex(base.index).to_numpy()
        parts103.append(base.reset_index())
    oos103 = pd.concat(parts103, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    for df in (oos92, oos94, oos103):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    return oos92, oos94, oos103, infos


def build_tranched_books(oos_lo, oos_ls, oos_103, j114, j103):
    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    o_lo_p, n_lo = replace_vol(oos_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o_ls_p, n_ls = replace_vol(oos_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o_103_p, n_103 = replace_vol(oos_103.sort_values(["t", "sym"]).reset_index(drop=True), j103)
    Wlo_raw = weights_lo_from_oos(o_lo_p)
    W94_raw = weights_ls_from_oos(o_ls_p)
    W103_raw = weights_ls_from_oos(o_103_p)
    o_v114 = oos_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = oos_103.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
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
    return books_t, o, idx, dict(v114_lo=int(n_lo), v114_ls=int(n_ls), v103=int(n_103))


# ---------- v135 1m execution (audited path, d=10bps for v137) ----------
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


def run_offset(Wt, o, carry_s, s_hv, p0_df, lo_df, hi_df, p15_df, d_bps):
    d = d_bps / 10000.0
    dW = Wt.diff().fillna(Wt)
    buy = dW > 0
    sell = dW < 0
    has_p0 = p0_df.notna()
    lim_buy = p0_df * (1 - d)
    lim_sell = p0_df * (1 + d)
    maker_buy = has_p0 & buy & (lo_df < lim_buy)
    maker_sell = has_p0 & sell & (hi_df > lim_sell)
    maker = (maker_buy | maker_sell)
    fee = pd.DataFrame(np.where(maker.to_numpy(), 0.0002, 0.0005), index=Wt.index, columns=Wt.columns)
    p15_eff = p15_df.where(p15_df.notna(), p0_df)
    slip = p15_eff / p0_df - 1.0
    slip = slip.where(has_p0, 0.0).fillna(0.0)
    rel_maker = pd.DataFrame(np.where(buy.to_numpy(), -d, np.where(sell.to_numpy(), d, 0.0)),
                             index=Wt.index, columns=Wt.columns)
    rel_taker = pd.DataFrame(np.where(buy.to_numpy(), slip.to_numpy() + 0.0002,
                                      np.where(sell.to_numpy(), slip.to_numpy() - 0.0002, 0.0)),
                             index=Wt.index, columns=Wt.columns)
    rel = rel_maker.where(maker, rel_taker)
    rel = rel.where(dW.abs() > 1e-9, 0.0)
    fee = fee.where(dW.abs() > 1e-9, 0.0)
    cost = (dW.abs() * fee).sum(axis=1) + (dW * rel).sum(axis=1)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    gross_pos = (Wt * r_next).sum(axis=1)
    long_gross = Wt.clip(lower=0).sum(axis=1)
    carry_exp = 0.6 * s_hv
    net = (gross_pos - cost - long_gross * 0.00005 + carry_exp * carry_s
           - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2)
    turn = dW.abs().sum(axis=1)
    return net, turn, maker, dW, cost


def summarize_offset(net, turn, maker, dW):
    ys = yearly(net, turn)
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = np.asarray(net.index >= START) & np.asarray(net.index < END)
    eq = (1 + net[full]).cumprod()
    live = np.asarray(net.index >= START)
    live_orders_mask = (dW.abs() > 1e-9) & live[:, None]
    mv = maker[live_orders_mask].stack()
    maker_rate = round(float(mv.mean()) if len(mv) else float("nan"), 3)
    orders_live = int(np.asarray(live_orders_mask).sum())
    fills_live = int((turn[np.asarray(net.index >= START)] > 1e-6).sum())
    mk = np.asarray(net.index >= HIDDEN) & np.asarray(net.index < HIDDEN + pd.Timedelta(days=365))
    hid_ge = np.asarray(net.index >= HIDDEN)[:, None]
    hid_lt = np.asarray(net.index < HIDDEN + pd.Timedelta(days=365))[:, None]
    hid_orders_mask = (dW.abs() > 1e-9) & hid_ge & hid_lt
    mh = maker[hid_orders_mask].stack()
    maker_hidden = round(float(mh.mean()) if len(mh) else float("nan"), 3)
    hid = stats(net[mk], turn[mk])
    hid.update(maker_fill_rate=maker_hidden,
               orders_hidden_year=int(((dW.abs() > 1e-9).to_numpy()[mk]).sum()),
               fills_hidden_year=int((turn[mk] > 1e-6).sum()))
    return dict(yearly=ys,
                monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
                maker_fill_rate=maker_rate,
                orders_live=orders_live,
                fills_live=fills_live,
                hidden_year=hid)


def main():
    panel114, panel103, bars114, bars103 = build_panels()
    feats114 = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                         "fv", "realized_vol", "pred_fv", "pvol")]
    feats103 = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42", "y84",
                                                         "y", "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                         "pred_h6", "pred_h18")]
    assert len(feats114) == 26, len(feats114)
    assert len(feats103) == 36, len(feats103)
    # pvol by audited v129 method (unchanged for v136; base for v137)
    oos114_pvol, a114 = train_pvol(panel114, feats114, bars114)
    oos103_pvol, a103 = train_pvol(panel103, feats103, bars103)
    j114 = oos114_pvol[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    # A1 v136: selection + refit, then v133 pipeline at target 0.15
    oos92_s, oos94_s, oos103_s, infos = part_a1_v136(panel114, feats114, panel103, feats103)
    books_s, o_s, idx_s, nrep_s = build_tranched_books(oos92_s, oos94_s, oos103_s, j114, j103)
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx_s)["carry"].astype(float).fillna(0.0)
    ret1 = o_s / o_s.shift(1) - 1
    realized = W_BOOKS * (books_s.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15 = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    live_mask = np.asarray((idx_s >= START) & (idx_s < END))
    o_vals = o_s.to_numpy(dtype=float)
    books_vals = books_s.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s15.to_numpy(dtype=float)
    scenarios = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        scenarios[sc] = summarize_seq(pd.Series(net, index=idx_s), pd.Series(turn, index=idx_s))
        print(f"v136 {sc} monthly={scenarios[sc]['monthly_pct']} fullDD={scenarios[sc]['full_path_dd']}", flush=True)
    kept_counts = {"v92": [i["n_kept"] for i in infos["v92"]]}
    for h in HS_V94:
        kept_counts[f"v94_h{h}"] = [i["n_kept"] for i in infos["v94"][str(h)]]
    for h in HS_V103:
        kept_counts[f"v103_h{h}"] = [i["n_kept"] for i in infos["v103"][str(h)]]

    # A2 v137: v133 books from audited OOS CSVs + same pvol, target sweep, v135 exec d=10bps
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    books_b, o_b, idx_b, nrep_b = build_tranched_books(o114_lo, o114_ls, o103_df, j114, j103)
    carry_b = carry.reindex(idx_b)["carry"].astype(float).fillna(0.0)
    p0_df, lo_df, hi_df, p15_df = precompute_exec_frames(idx_b, list(SYMS))
    ret1_b = o_b / o_b.shift(1) - 1
    targets = {}
    for tgt in TARGETS_V137:
        realized_h = W_BOOKS * (books_b.shift(2) * ret1_b).sum(axis=1) + W_CARRY * CARRY_LEV * carry_b.shift(1)
        vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s_hv = (tgt / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
        Wt = books_b.mul(W_BOOKS * s_hv, axis=0)
        net, turn, maker, dW, cost = run_offset(Wt, o_b, carry_b, s_hv, p0_df, lo_df, hi_df, p15_df, D_V137_BPS)
        summ = summarize_offset(pd.Series(net, index=idx_b), pd.Series(turn, index=idx_b), maker, dW)
        targets[str(tgt)] = summ
        print(f"v137 target={tgt} monthly={summ['monthly_pct']} fullDD={summ['full_path_dd']} "
              f"maker={summ['maker_fill_rate']} hidden={summ['hidden_year']['net_pct']}", flush=True)

    out = {
        "version": "v136_v137_audit_replication",
        "anchors": list(ANCHORS),
        "scenarios_spec": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        "v136": {"kept_counts": kept_counts, "kept_detail": infos,
                 "scenarios": scenarios, "n_replaced": nrep_s,
                 "feats114_n": len(feats114), "feats103_n": len(feats103),
                 "union_bars": int(len(idx_s)), "oos_span": [str(idx_s[0]), str(idx_s[-1])]},
        "v137": {"targets": list(TARGETS_V137), "d_bps": D_V137_BPS,
                 "per_target": targets, "n_replaced": nrep_b,
                 "union_bars": int(len(idx_b)), "oos_span": [str(idx_b[0]), str(idx_b[-1])]},
        "anchors_v114_pvol": a114,
        "anchors_v103_pvol": a103,
        "meta": {
            "v136_spec": "v92 y H42 embargo102; v94 h18/42/84 embargo144=max+60; v103 h6/18 embargo78; train rows as audited; val=t>=cutoff-730d sample20000; inner=t+(h+1)*4h<val_start-embargo*4h; HGB v92 params; permutation_importance val scoring make_scorer(Spearman) n_repeats3 rs0; keep mean>0 else top5; refit all train rows; v94/v103 mean over horizons; v133 pipeline pvol swap tranching portfolio 0.15",
            "v136_choices": "pvol NOT selected (assignment lists only return models); pvol retrained v129 method; weights N=5 LO/LS; tranche mean/6; own 0.20-cap-2 scales; books 0.25/0.25/0.5; sequential engine target 0.15 ungoverned; carry artifacts/research/carry/carry_oos_fee0.0004.parquet",
            "v137_spec": "v133 books (audited OOS CSVs + same pvol swap, tranche, own scales); portfolio target in (0.15,0.17,0.19,0.21); v135 rule d=10bps (p0 minute0, lo/hi offsets2..14, p15 minute15, maker fee0.0002 rel-/+d else taker 0.0005 rel p15/p0-1 +/-0.0002); 0.15 must equal v135 10bps row",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"v136_normal": scenarios["normal"],
                      "v137_0.15": targets["0.15"]["hidden_year"],
                      "kept_counts": kept_counts}, indent=2))


if __name__ == "__main__":
    main()
