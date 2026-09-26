"""Blind v135 audit replication (Part A).
Does NOT read research/.../v135/*, v134/*, v133/* nor v132/*.

Base (per OPENCODE_V135_AUDIT.md):
  audited v132_v133 replication (v133 weights Wt = 0.8*s*books, carry,
  v104 cost path).

A: 1m klines per major: BTC data/raw/btc_intraday_20260924/klines_1m_20*.parquet,
others data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet (dedup open_time).
For each 4h execution bar T (floor 4h):
  p0 = 1m open at minute 0;
  lo/hi = min low / max high over 1m bars with minute offset 2..14;
  p15 = 1m open at minute 15.
Orders dW = Wt.diff() (first row = Wt) decided at t execute at T = t + 4h.
For offset d in (0, 5, 10, 20) bps: buy limit p0*(1-d), sell limit p0*(1+d);
maker (fee 0.0002, price = limit, rel = -d for buys / +d for sells)
  if lo < limit (buy) or hi > limit (sell) and p0 exists;
else taker fee 0.0005 with rel = p15/p0 - 1 (p15 := p0 if missing)
  +0.0002 for buys / -0.0002 for sells;
missing p0 -> taker with rel = +/-0.0002.
cost = |dW|*fee + dW*rel summed over assets.
net = sum(Wt * (open[t+2]/open[t+1]-1)) - cost - 0.00005*long gross
  + 0.6*s*carry - |diff(0.6*s)|*2*0.0004/1.2 (first diff 0).
Yearly stats per anchor, maker rate over live orders (t >= 2021-09-24),
full-path DD over [2021-09-24, +1825 days).
Choose the d with the highest mean net over the first four anchor years;
report its hidden year.
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
OFFSETS_BPS = (0, 5, 10, 20)
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102

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


# ---------- weights (v133 original: shorts where rib != 1) ----------
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


# ---------- panels (v129 method: v114 extended, v103 base) ----------
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
    return x


def add_fv(panel_bars):
    out = {}
    for s, b in panel_bars.items():
        lo = np.log(b["open"].astype(float))
        r = lo.diff()
        s42 = r.rolling(42).std(ddof=1)
        fv = np.log(s42.shift(-43))
        out[s] = (fv.to_numpy(), s42.shift(-43).to_numpy())
    return out


def build_v114_panel():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    bars = {}
    rows = []
    for i, s in enumerate(SYMS):
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        bars[s] = b
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
    fv_map = add_fv(bars)
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
    return panel


def build_v103_panel():
    rows = []
    bars = {}
    for i, s in enumerate(SYMS):
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
    fv_map = add_fv(bars)
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
    return panel


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def train_pvol(panel, feats):
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


# ---------- 1m execution precompute (spec: dedup, T floor 4h) ----------
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
    """For each 4h execution bar T = t + 4h: p0 (minute 0), lo/hi over
    minute offsets 2..14, p15 (minute 15). All aligned as-of T."""
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
        low_cols = []
        high_cols = []
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
        cov = float(np.mean(~np.isnan(p0_arr)))
        print(f"exec precompute {s} p0_cov={cov:.3f}", flush=True)
    # align index (reindex dropped tz name; restore idx)
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
    # taker rel price part: p15/p0 - 1 with p15 := p0 if missing
    p15_eff = p15_df.where(p15_df.notna(), p0_df)
    slip = p15_eff / p0_df - 1.0
    slip = slip.where(has_p0, 0.0).fillna(0.0)
    rel_maker = pd.DataFrame(np.where(buy.to_numpy(), -d, np.where(sell.to_numpy(), d, 0.0)),
                             index=Wt.index, columns=Wt.columns)
    rel_taker = pd.DataFrame(np.where(buy.to_numpy(), slip.to_numpy() + 0.0002,
                                      np.where(sell.to_numpy(), slip.to_numpy() - 0.0002, 0.0)),
                             index=Wt.index, columns=Wt.columns)
    # missing p0 -> taker with rel = +/-0.0002 (slip=0 above already gives that)
    rel = rel_maker.where(maker, rel_taker)
    # orders with zero dW carry no cost regardless
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
    # maker rate over live orders (t >= 2021-09-24)
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
    mean_first4 = round(float(np.mean([y["net_pct"] for y in ys[:4]])), 2)
    return dict(yearly=ys,
                monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
                maker_fill_rate=maker_rate,
                orders_live=orders_live,
                fills_live=fills_live,
                mean_net_first4=mean_first4,
                hidden_year=hid)


def main():
    panel114 = build_v114_panel()
    feats114 = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                         "fv", "realized_vol", "pred_fv", "pvol")]
    panel103 = build_v103_panel()
    feats103 = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                         "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                         "pred_h6", "pred_h18")]
    assert len(feats114) == 26, len(feats114)
    assert len(feats103) == 36, len(feats103)
    oos114, a114 = train_pvol(panel114, feats114)
    oos103_pvol, a103 = train_pvol(panel103, feats103)

    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)

    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    j114 = oos114[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)
    o114_lo_p, n_lo = replace_vol(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o114_ls_p, n_ls = replace_vol(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = replace_vol(o103_df.sort_values(["t", "sym"]).reset_index(drop=True), j103)

    # v133 weights: Wt = 0.8*s*books, carry, v104 cost path base
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
    realized_h = W_BOOKS * (books_t.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s_hv = (0.15 / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    Wt = books_t.mul(W_BOOKS * s_hv, axis=0)

    # limit-offset execution for d in (0, 5, 10, 20) bps
    p0_df, lo_df, hi_df, p15_df = precompute_exec_frames(idx, list(SYMS))
    offsets = {}
    for d_bps in OFFSETS_BPS:
        net, turn, maker, dW, cost = run_offset(Wt, o, carry_s, s_hv, p0_df, lo_df, hi_df, p15_df, d_bps)
        summ = summarize_offset(pd.Series(net, index=idx), pd.Series(turn, index=idx), maker, dW)
        offsets[str(d_bps)] = summ
        print(f"d={d_bps}bps monthly={summ['monthly_pct']} fullDD={summ['full_path_dd']} "
              f"maker={summ['maker_fill_rate']} mean_first4={summ['mean_net_first4']} "
              f"hidden_net={summ['hidden_year']['net_pct']}", flush=True)

    means = {k: v["mean_net_first4"] for k, v in offsets.items()}
    chosen = max(means, key=lambda k: means[k])
    out = {
        "version": "v135_audit_replication",
        "anchors": list(ANCHORS),
        "offsets_bps": list(OFFSETS_BPS),
        "offsets": offsets,
        "chosen_d_bps": int(chosen),
        "chosen": offsets[chosen],
        "anchors_v114_pvol": a114,
        "anchors_v103_pvol": a103,
        "n_replaced": {"v114_lo": int(n_lo), "v114_ls": int(n_ls), "v103": int(n_103)},
        "union_bars": int(len(idx)),
        "oos_span": [str(idx[0]), str(idx[-1])],
        "meta": {
            "base": "audited v132_v133 replication: v133 weights Wt = 0.8*s*books (tranched mean/6, own 0.20-cap-2 scales, books 0.25/0.25/0.5, s target 0.15 sequential), carry 0.6*s*carry - |diff(0.6*s)|*2*0.0004/1.2, v104 cost path generalized to limit offsets",
            "exec": "1m per major dedup open_time; T = t + 4h; p0 = 1m open minute 0; lo/hi = min low / max high offsets 2..14; p15 = 1m open minute 15; buy limit p0*(1-d) sell p0*(1+d); maker if lo<limit/ hi>limit and p0 exists (fee 0.0002 rel -d/+d) else taker fee 0.0005 rel p15/p0-1 +/-0.0002 (p15:=p0 if missing; missing p0 taker +/-0.0002); cost=|dW|*fee+dW*rel; net=sum(Wt*(open[t+2]/open[t+1]-1))-cost-0.00005*long+0.6*s*carry-carrycost",
            "selection": "choose d with highest mean net_pct over first four anchor years; report its hidden year (2025-09-24 anchor)",
            "full_path": "[2021-09-24, +1825 days); maker rate over live orders t>=2021-09-24",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"chosen_d_bps": int(chosen), "chosen": offsets[chosen]["hidden_year"],
                      "means_first4": means}, indent=2))


if __name__ == "__main__":
    main()
