"""Blind v134 audit replication (Part A).
Does NOT read research/.../v134/*, v133/* nor v132/*.

Base (per OPENCODE_V134_AUDIT.md):
  v133 replication built from OPENCODE_V132_V133_AUDIT.md A2:
  v127 tranched books with vol42 replaced by v129 forecast pvol
  (v114-panel pvol for v92 LO / v94 LS, v103-panel pvol for v103 LS)
  before the weight formulas; three scenarios (v110 engine, target 0.15)
  and hidden year with v104 strict fill rule.

A (v134): identical to v133 except in the long/short weight formula used
for the v94 LS and v103 LS books the short leg is
((-pred).clip(0)/0.5).clip(upper=1) only where rib == -1 (0 elsewhere)
instead of where rib != 1; long legs unchanged.

Blind specs implemented:
  - v114 panel (v92 feats, no flow) + v103 panel (v103 feats + flow) rebuilt
    from raw (Bitstamp>=2013-01-01 + Coinbase BTC, Coinbase ETH,
    spot_2017 prefix, UTC floor agg 4h>=3/1d>=20).
  - fv = log(rolling-42 std of diff(log open)) shifted by -43 (std of
    returns t+2..t+43); HGB (v92 params) per anchor, cutoff = anchor-102*4h,
    rows need t+44*4h < cutoff and finite fv; pvol = exp(pred).
  - Replace vol42 by pvol (where available) in OOS frames of v92 LO / v94 LS
    (v114-panel pvol) and v103 LS (v103-panel pvol) before weight formulas.
  - LO weights unchanged; LS weights bear-only shorts (rib == -1).
  - Tranche mean over 6 phases, own 0.20-cap-2 vol scales, books
    0.25/0.25/0.5, target 0.15 sequential v110 ungoverned, three scenarios.
  - Hidden year with v104 strict fill rule + vectorised v104 cost path on
    the tranched weights, target 0.15, NO band.
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
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102  # bars of 4h
HS_V103 = (6, 18)  # panel targets (for feature completeness only)

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT17_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"


# ---------- weights (v134: bear-only shorts for LS) ----------
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


def weights_ls_bear_only_from_oos(oos):
    """v134: long unchanged (rib != -1 gate); short only where rib == -1."""
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib == -1, 0.0)
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


# ---------- panels (v129 method) ----------
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
    for h in (6, 18, 42):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (v42 * np.sqrt(h)), -4, 4)
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
    ext = {}
    bars = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
        bars[s] = b
    rows = []
    for i, s in enumerate(SYMS):
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


def build_panel(with_flow):
    # kept for compatibility; v114 uses extended history, v103 does not
    return build_v114_panel() if not with_flow else build_v103_panel()


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
        print(f"pvol {anchor} tr={len(tr)} rho_p={anchors[-1]['spearman_pvol_realized']} rho_v={anchors[-1]['spearman_vol42_realized']}", flush=True)
    oos = pd.concat(parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    return oos, anchors


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
    j114 = oos114[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)

    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have

    o114_lo_p, n_lo = replace_vol(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o114_ls_p, n_ls = replace_vol(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = replace_vol(o103_df.sort_values(["t", "sym"]).reset_index(drop=True), j103)

    # v134 bear-only LS weights on pvol-replaced frames
    Wlo_raw = weights_lo_from_oos(o114_lo_p)
    W94_raw = weights_ls_bear_only_from_oos(o114_ls_p)
    W103_raw = weights_ls_bear_only_from_oos(o103_p)

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
        print(f"v134 tranched+pvol+bear {sc} monthly={scenarios[sc]['monthly_pct']} fullDD={scenarios[sc]['full_path_dd']}", flush=True)

    realized_h = W_BOOKS * (books_t.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s_hv = (0.15 / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    Wt = books_t.mul(W_BOOKS * s_hv, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s_hv
    rel, maker = fill_strict_v104(Wt)
    dW = Wt.diff().fillna(Wt)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net_h = ((Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005
             + carry_exp * carry_s - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2)
    turn_h = dW.abs().sum(axis=1)
    mk = (idx >= HIDDEN) & (idx < HIDDEN + pd.Timedelta(days=365))
    orders_mask = (dW.abs() > 1e-9) & (idx >= HIDDEN)[:, None]
    maker_rate = round(float(maker[orders_mask].stack().mean()) if orders_mask.values.any() else float("nan"), 3)
    hid = stats(net_h[mk], turn_h[mk])
    hid.update(maker_fill_rate=maker_rate,
               orders_hidden_year=int((dW.abs() > 1e-9).loc[mk].sum().sum()),
               fills_hidden_year=int((turn_h[mk] > 1e-6).sum()))
    print("v134 hidden", hid, flush=True)

    # short-leg activity diagnostic: fraction of LS raw weight from shorts
    short_frac = {}
    for tag, df in (("v94", o114_ls_p), ("v103", o103_p)):
        p = df["pred"].astype(float).to_numpy()
        rib = df["rib"].astype(float).to_numpy()
        lng = np.clip(p, 0, None) / 0.5
        lng = np.minimum(lng, 1.0) * (rib != -1)
        sht = np.clip(-p, 0, None) / 0.5
        sht = np.minimum(sht, 1.0) * (rib == -1)
        denom = np.abs(lng - sht).sum()
        short_frac[tag] = round(float(np.abs(sht).sum() / denom), 4) if denom > 0 else 0.0

    out = {
        "version": "v134_audit_replication",
        "scenarios": scenarios,
        "hidden_year_1m_execution_strict": hid,
        "anchors_v114_pvol": a114,
        "anchors_v103_pvol": a103,
        "n_replaced": {"v114_lo": int(n_lo), "v114_ls": int(n_ls), "v103": int(n_103)},
        "short_fraction_of_ls_gross": short_frac,
        "union_bars": int(len(idx)),
        "oos_span": [str(idx[0]), str(idx[-1])],
        "meta": {
            "anchors": list(ANCHORS),
            "scenarios_params": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
            "v134_spec": "v133 (v127 tranched books + v129 pvol replacement, v110 engine target 0.15, v104 strict fill, no band) with v94/v103 LS short leg ((-pred).clip(0)/0.5).clip(upper=1) only where rib == -1 (0 elsewhere); long legs unchanged; books 0.25/0.25/0.5",
            "pvol_spec": "per panel (v114 no-flow 26 feats extended history; v103 flow 36 feats non-extended) fv=log(rolling-42 std of diff(log open)) shifted by -43; HGB v92 params per anchor cutoff=anchor-102*4h rows t+44*4h<cutoff & finite fv; pvol=exp(pred); vol42 replaced by pvol where available via left-join (t,sym)",
            "posthoc_fix": "initial draft extended v103 history like v114 (train_rows matched v114); fixed before opening v134/ to non-extended v103 panel per v129 method; reran full replication",
            "engine": "s 0.15 sequential v110 ungoverned; hidden v104 fill_strict [T+2m,T+14m] T+15m fallback missing-T taker + v104 cost path on tranched weights, no band",
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"monthly_normal": scenarios["normal"]["monthly_pct"],
                      "fullDD_normal": scenarios["normal"]["full_path_dd"],
                      "hidden": hid}, indent=2))


if __name__ == "__main__":
    main()
