"""Blind v123+v124+v125 audit replication (Part A).
Does NOT read research/.../v123/*, v124/* nor v125/*.

Base (per OPENCODE_V123_V125_AUDIT.md):
  audited v115 (books, v110 sequential engine, v104 hidden path),
  v118 (band logic) and v113_v114 (v114 extended panel, v92/v94 training) replications.

Blind specs implemented:
A1 (v123): on v114 panel add per asset:
  r4_50/r4_200 = log(close/SMA50|SMA200) on 4h closes (rolling mean, min_periods=window);
  rib4 = +1 if close>SMA50>SMA200, -1 if close<SMA50<SMA200, else 0 (NaN while SMA200 NaN);
  from daily closes: w50=log(close/SMA350), w50_slope=diff(log SMA350,5),
  ribw=+1/-1/0 with SMA350/SMA1400 (0 while SMA1400 NaN, NaN while SMA350 NaN),
  joined to 4h bars asof backward on close_time;
  rib_agree=rib4+rib+ribw (NaN-propagating sum).
  Retrain v92 LO (HGB h=42, cutoff anchor-408h) and v94 LS (3x HGB h=18/42/84,
  cutoff anchor-576h) with all non-target columns as features.
  Portfolio as v115 primary (books=0.25*b_lo+0.25*b94+0.5*b103, target 0.15
  ungoverned sequential v110 engine); secondary v96 blend (0.5*b_lo+0.5*b94, scale 1).
A2 (v124): v115 books (from audited OOS CSVs), target 0.15, held weights with
  band 0.05 applied from first index row (held=target where |target-held|>0.05
  per asset; outside live targets 0 taken immediately, same as v118 blind choice);
  orders=diff of held; hidden-year v104 strict 1m fill rule + v104 cost path
  (carry, long funding on held weights). Report hidden-year net/DD/maker/orders.
A3 (v125): for each book's un-subsampled weight frame (audited LO/LS formulas
  without the keep/ffill step) take mean over phase=0..5 of (keep rows with
  position%6==phase, ffill, fillna 0); own vol scales (0.20 cap2, W.shift(2),
  trailing 360/min-120) on tranched weights; v115 primary portfolio (target 0.15
  sequential). Reference phase 0 only (=v115).

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
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
H_V92 = 42
HS = (18, 42, 84)
EMB_V92 = H_V92 + 10 * PD  # 102 bars
EMB_V94 = 84 + 60  # 144 bars
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"


# ---------- v114 panel rebuild (audited formulas) ----------
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


def features_v123(b, d, f):
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
    # --- v123 extras: 4h ribbon ---
    sma50_4 = c.rolling(50).mean()
    sma200_4 = c.rolling(200).mean()
    x["r4_50"] = np.log(c / sma50_4)
    x["r4_200"] = np.log(c / sma200_4)
    rib4_vals = np.where((c.to_numpy() > sma50_4.to_numpy()) & (sma50_4.to_numpy() > sma200_4.to_numpy()), 1.0,
                         np.where((c.to_numpy() < sma50_4.to_numpy()) & (sma50_4.to_numpy() < sma200_4.to_numpy()), -1.0, 0.0))
    rib4_vals = np.where(sma200_4.isna().to_numpy(), np.nan, rib4_vals)
    x["rib4"] = rib4_vals
    # --- v123 extras: weekly (daily SMA350/1400) ---
    sma350 = dc.rolling(350).mean()
    sma1400 = dc.rolling(1400).mean()
    log_sma350 = np.log(sma350)
    wfe = pd.DataFrame({
        "t": d["close_time"],
        "w50": np.log(dc / sma350),
        "w50_slope": log_sma350.diff(5),
        "ribw": np.where(sma350.isna().to_numpy(), np.nan,
                         np.where(sma1400.isna().to_numpy(), 0.0,
                                  np.where((dc.to_numpy() > sma350.to_numpy()) & (sma350.to_numpy() > sma1400.to_numpy()), 1.0,
                                           np.where((dc.to_numpy() < sma350.to_numpy()) & (sma350.to_numpy() < sma1400.to_numpy()), -1.0, 0.0)))),
    })
    jw = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), wfe.sort_values("t"), on="t", direction="backward")
    x[["w50", "w50_slope", "ribw"]] = jw[["w50", "w50_slope", "ribw"]].to_numpy()
    x["rib_agree"] = x["rib4"].to_numpy(dtype=float) + x["rib"].to_numpy(dtype=float) + x["ribw"].to_numpy(dtype=float)
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    for h in HS:
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(h)), -4, 4)
    x["y"] = x["y42"]
    return x


def build_panel_v123(ext_bars):
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = ext_bars[s]
        x = features_v123(b, d, f)
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


# ---------- shared weight/scale/sim ----------
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


def apply_daily_keep(W):
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


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


def simulate_simple(o, W, scale, fee, slip):
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    if np.isscalar(scale):
        Wk = W * scale
    else:
        Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


def load_1m(sym):
    d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_202[56].parquet" if sym == "BTCUSDT" else f"{sym}_1m_202[56].parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time").sort_index()


def fill_strict_v104(W):
    rel = pd.DataFrame(0.0, index=W.index, columns=W.columns)
    maker = pd.DataFrame(True, index=W.index, columns=W.columns)
    dW = W.diff().fillna(W)
    for s in W.columns:
        m = load_1m(s)
        for t in dW.index[(dW[s].abs() > 1e-9) & (dW.index >= HIDDEN)]:
            T = t + pd.Timedelta(hours=4)
            buy = dW.at[t, s] > 0
            if T not in m.index:
                maker.at[t, s] = False
                rel.at[t, s] = 0.0002 if buy else -0.0002
                continue
            p0 = m.at[T, "open"]
            w = m.loc[T + pd.Timedelta(minutes=2): T + pd.Timedelta(minutes=14)]
            through = (w["low"] < p0).any() if buy else (w["high"] > p0).any()
            if not through:
                T15 = T + pd.Timedelta(minutes=15)
                px = m.at[T15, "open"] if T15 in m.index else p0
                rel.at[t, s] = px / p0 - 1 + (0.0002 if buy else -0.0002)
                maker.at[t, s] = False
    return rel, maker


def part_a1_v123():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    ext = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
    panel = build_panel_v123(ext)
    feats = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y", "y18", "y42", "y84")]
    o_panel = panel.pivot_table(index="t", columns="sym", values="open").sort_index()[list(SYMS)]
    # v92 LO retrain
    anchors92, parts92 = [], []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_V92)
        tr = panel[(panel.t < cutoff) & panel.y.notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr["y"])
        te["pred"] = m.predict(te[feats])
        ev = te.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        anchors92.append(dict(anchor=anchor, train_rows=int(len(tr)), n_pred_rows=int(len(te)),
                              n_pred_rows_with_y=int(len(ev)), ic=round(rho, 4)))
        parts92.append(te)
        print("v123 v92", anchor, len(tr), round(rho, 4), flush=True)
    oos92 = pd.concat(parts92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    # v94 LS retrain
    anchors94, parts94 = [], []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_V94)
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        preds = np.zeros((len(te), len(HS)))
        ntrs = []
        for j, h in enumerate(HS):
            yh = f"y{h}"
            tr = panel[(panel.t < cutoff) & panel[yh].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            ntrs.append(int(len(tr)))
            m = HistGradientBoostingRegressor(**HGB)
            m.fit(tr[feats], tr[yh])
            preds[:, j] = m.predict(te[feats])
        te["pred"] = preds.mean(axis=1)
        for j, h in enumerate(HS):
            te[f"pred_h{h}"] = preds[:, j]
        ev = te.dropna(subset=["y42"])
        rho = float(spearmanr(ev["pred"], ev["y42"]).statistic) if len(ev) > 2 else float("nan")
        anchors94.append(dict(anchor=anchor, train_rows_h18=ntrs[0], train_rows_h42=ntrs[1],
                              train_rows_h84=ntrs[2], n_pred_rows=int(len(te)),
                              n_pred_rows_with_y=int(len(ev)), ic_mean_vs_h42=round(rho, 4)))
        parts94.append(te)
        print("v123 v94", anchor, ntrs, round(rho, 4), flush=True)
    oos94 = pd.concat(parts94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W92_raw = weights_lo_from_oos(oos92)
    W94_raw = weights_ls_from_oos(oos94)
    W92 = apply_daily_keep(W92_raw)
    W94 = apply_daily_keep(W94_raw)
    assert (W92.index == W94.index).all()
    o_oos = o_panel.loc[W92.index].copy()
    s92 = vol_scale(o_oos, W92)
    s94 = vol_scale(o_oos, W94)
    # v103 book from audited CSV
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    o103_df["t"] = pd.to_datetime(o103_df["t"], utc=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)
    W103_raw = weights_ls_from_oos(o103_df)
    W103 = apply_daily_keep(W103_raw)
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))
    idx = W92.index.union(W103.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo = W92.reindex(idx).fillna(0.0).mul(s92.reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    o = o_v103.reindex(idx).sort_index()
    books = books[o.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15 = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s15.to_numpy(dtype=float)
    primary = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        primary[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
        print("v123 primary", sc, primary[sc]["monthly_pct"], flush=True)
    # secondary v96 blend scale 1
    Wb = 0.5 * W92.mul(s92, axis=0).reindex(idx).fillna(0.0) + 0.5 * W94.mul(s94, axis=0).reindex(idx).fillna(0.0)
    o_b = o_oos.reindex(idx).sort_index() if set(idx) <= set(o_oos.index) else o.reindex(idx)
    blend = {}
    for sc, (fee, slip) in SCEN.items():
        r = (o_b.shift(-2) / o_b.shift(-1) - 1).fillna(0.0)
        turn = Wb.diff().abs().sum(axis=1).fillna(Wb.abs().sum(axis=1))
        funding = Wb.clip(lower=0).sum(axis=1) * 0.00005
        net = (Wb * r).sum(axis=1) - turn * (fee + slip) - funding
        blend[sc] = dict(yearly=yearly(net, turn))
        print("v123 blend", sc, [y["net_pct"] for y in blend[sc]["yearly"]], flush=True)
    oos92[["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v123_v92.csv", index=False)
    oos94[["t", "sym", "open", "pred", "pred_h18", "pred_h42", "pred_h84", "y42", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v123_v94.csv", index=False)
    return dict(anchors_v92=anchors92, anchors_v94=anchors94, primary=primary, blend=blend,
                features=feats, idx_span=[str(idx[0]), str(idx[-1])], n_oos=int(len(idx)),
                first_v103_t=str(first_v103)), (idx, books, o, carry_s, s15, W92, s92, W94, s94, W103, s103, o_v103, oos92, oos94)


def build_v115_books():
    """Audited v115 books from OOS CSVs (NOT v123 retrain)."""
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    W_lo_raw = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94_raw = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    W103_raw = weights_ls_from_oos(o103_df.sort_values(["t", "sym"]).reset_index(drop=True))
    W_lo = apply_daily_keep(W_lo_raw)
    W94 = apply_daily_keep(W94_raw)
    W103 = apply_daily_keep(W103_raw)
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    s_lo = vol_scale(o_v114, W_lo.reindex(o_v114.index).fillna(0.0))
    s94 = vol_scale(o_v114, W94.reindex(o_v114.index).fillna(0.0))
    s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))
    idx = W_lo.index.union(W94.index).union(W103.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    o = o_v103.reindex(idx).sort_index()
    books = books[o.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15 = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    return idx, books, o, carry_s, s15


def part_a2_v124(idx115=None, books115=None, o115=None, carry115=None, s115=None):
    # v124 uses v115 books (audited), band 0.05 continuously over whole index
    # (per leader script: held from first index row, no live gating).
    idx, books, o, carry_s, s = build_v115_books()
    band = 0.05
    # portfolio vol scale recomputed vectorised over whole index (v104/v115 hidden convention)
    ret1 = o / o.shift(1) - 1
    realized_h = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s_hv = (0.15 / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    Wt_target = books.mul(W_BOOKS * s_hv, axis=0)
    # banded held continuously from first index row (leader v124 semantics)
    Wt = Wt_target.to_numpy(dtype=float)
    held2 = np.zeros(Wt.shape[1])
    held2_mat = np.zeros_like(Wt)
    for i in range(Wt.shape[0]):
        w = Wt[i]
        held2 = np.where(np.abs(w - held2) > band, w, held2)
        held2_mat[i] = held2
    Held = pd.DataFrame(held2_mat, index=idx, columns=books.columns)
    dW = Held.diff().fillna(Held)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s_hv
    rel, maker = fill_strict_v104(Held)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net_h = (Held * r_next).sum(axis=1) - cost - Held.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry_s - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
    turn_h = dW.abs().sum(axis=1)
    mk = (idx >= HIDDEN) & (idx < HIDDEN + pd.Timedelta(days=365))
    orders_h = (dW.abs() > 1e-9) & (idx >= HIDDEN)[:, None]
    maker_rate = round(float(maker[orders_h].stack().mean()) if orders_h.values.any() else float("nan"), 3)
    n_orders = int((dW.abs() > 1e-9).loc[mk].sum().sum())
    hid = stats(net_h[mk], turn_h[mk])
    hid.update(maker_fill_rate=maker_rate, orders_hidden_year=n_orders,
               fills_hidden_year=int((turn_h[mk] > 1e-6).sum()))
    print("v124 hidden", hid, flush=True)
    Held.to_csv(OUT_DIR / "held_v124.csv")
    return dict(hidden_year_1m_execution_strict=hid, band=band,
                union_bars=int(len(idx)),
                oos_span=[str(idx[0]), str(idx[-1])])


def part_a3_v125():
    # rebuild un-subsampled frames from audited OOS CSVs (v114 LO/LS + v103 LS)
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    Wlo_raw = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94_raw = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    W103_raw = weights_ls_from_oos(o103_df.sort_values(["t", "sym"]).reset_index(drop=True))
    # tranche means
    Wlo_t, phases_lo = tranche_mean(Wlo_raw)
    W94_t, phases_94 = tranche_mean(W94_raw)
    W103_t, phases_103 = tranche_mean(W103_raw.reindex(o_v103.index).fillna(0.0) if not W103_raw.index.equals(o_v103.index) else W103_raw)
    # own vol scales on tranched
    s_lo_t = vol_scale(o_v114.reindex(Wlo_t.index).fillna(method="ffill"), Wlo_t)
    s94_t = vol_scale(o_v114.reindex(W94_t.index).fillna(method="ffill"), W94_t)
    # W103 tranched index may equal o_v103 index
    idx103 = W103_t.index
    s103_t = vol_scale(o_v103.reindex(idx103), W103_t)
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
    tranched = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        tranched[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
        print("v125 tranched", sc, tranched[sc]["monthly_pct"], flush=True)
    # reference phase 0 only (=v115): recompute with phase-0 frames
    Wlo_0 = phases_lo[0]
    W94_0 = phases_94[0]
    W103_0 = phases_103[0]
    s_lo_0 = vol_scale(o_v114.reindex(Wlo_0.index).fillna(method="ffill"), Wlo_0)
    s94_0 = vol_scale(o_v114.reindex(W94_0.index).fillna(method="ffill"), W94_0)
    s103_0 = vol_scale(o_v103.reindex(W103_0.index), W103_0)
    b_lo_0 = Wlo_0.reindex(idx).fillna(0.0).mul(s_lo_0.reindex(idx).fillna(1.0), axis=0)
    b94_0 = W94_0.reindex(idx).fillna(0.0).mul(s94_0.reindex(idx).fillna(1.0), axis=0)
    b103_0 = W103_0.reindex(idx).fillna(0.0).mul(s103_0.reindex(idx).fillna(1.0), axis=0)
    books_0 = 0.25 * b_lo_0 + 0.25 * b94_0 + 0.5 * b103_0
    books_0 = books_0[o.columns]
    realized0 = W_BOOKS * (books_0.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol0 = realized0.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15_0 = (0.15 / vol0).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    ref = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_0.to_numpy(dtype=float), carry_vals, s15_0.to_numpy(dtype=float), live_mask, fee, slip)
        ref[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
    return dict(tranched=tranched, reference_phase0=ref, union_bars=int(len(idx)),
                oos_span=[str(idx[0]), str(idx[-1])])


def main():
    v123, aux = part_a1_v123()
    idx, books, o, carry_s, s15, W92, s92, W94, s94, W103, s103, o_v103, oos92, oos94 = aux
    v124 = part_a2_v124(idx, books, o, carry_s, s15)
    # A3 uses audited v115 books path (independent of v123 retrain) per spec
    v125 = part_a3_v125()
    out = {
        "version": "v123_v125_audit_replication",
        "v123": v123,
        "v124": v124,
        "v125": v125,
        "meta": {
            "anchors": list(ANCHORS),
            "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
            "v123_spec": "v114 panel + r4_50/r4_200 log(close/SMA50|200 4h), rib4 +1/-1/0 NaN while SMA200 NaN; daily w50=log(close/SMA350), w50_slope=diff(log SMA350,5), ribw +1/-1/0 SMA350/1400 (0 while SMA1400 NaN, NaN while SMA350 NaN) asof-backward on close_time; rib_agree=rib4+rib+ribw (NaN-propagating); HGB v92 h42 cutoff-408h / v94 h18/42/84 cutoff-576h, all non-target cols; books=0.25*b_lo+0.25*b94+0.5*b103 audited v103; s target 0.15 sequential v110; secondary 0.5*b_lo+0.5*b94 scale1 v92 costs",
            "v124_spec": "v115 books (audited OOS CSVs) target 0.15; held band 0.05 continuously from first index row per-asset (|tgt-held|>0.05 -> tgt else hold), no live gating (leader v124 semantics); orders=diff held; hidden v104 fill_strict [T+2m,T+14m] T+15m fallback missing-T taker + v104 cost path (carry 0.6*s, long funding 0.00005 on held)",
            "v125_spec": "un-subsampled LO/LS frames (no keep step) -> per phase keep pos%6==phase ffill fillna0, mean over 6 phases; own 0.20-cap-2 scales (W.shift(2) trailing 360/min-120) on tranched; books 0.25/0.25/0.5; s 0.15 sequential v110; ref phase0 only (=v115)",
            "data": {"v103": "v103_v105_audit/predictions_v103.csv", "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                      "panel": "v114 extended Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot+USD-M, UTC floor agg 4h>=3/1d>=20"},
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"v123_monthly_primary_normal": v123["primary"]["normal"]["monthly_pct"],
                      "v124_hidden": v124["hidden_year_1m_execution_strict"],
                      "v125_monthly_normal": v125["tranched"]["normal"]["monthly_pct"]}, indent=2))


if __name__ == "__main__":
    main()
