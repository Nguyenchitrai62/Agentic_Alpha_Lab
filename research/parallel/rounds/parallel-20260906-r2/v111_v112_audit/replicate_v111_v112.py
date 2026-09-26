"""Blind v111+v112 audit reproduction from OPENCODE_V111_V112_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/* (not needed here),
and audited replications v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv
for the v96 leg. Does NOT read research/.../v111/* or v112/* (blind until replication.json saved).

Base = audited v103_v105 replication (v103 panel/features/targets/embargo/HGB,
v94 weights_ls, vol targets, v92 book).

A1 (v111): for P in BTC, ETH: Binance spot 4h = concat(spot_4h_2017, spot_4h)
  on open_time, dedup, sorted. Coinbase = {P}-USD_1h. For each Binance 4h bar T
  (open_time): coinbase close of 1h candle with open_time <= T+3h (asof backward,
  tolerance 2h, else NaN); cbp = 1e4*log(cb_close/binance_close).
  p6 = rolling-6 mean (min 4), p42 = rolling-42 mean (min 30),
  m540/s540 = rolling-540 mean/std of cbp (min 270).
  Joined on t to every asset: cb_btc_dev = p6-m540 (BTC), cb_btc_z = (p6-m540)/s540,
  cb_btc_chg = p6-p42, cb_eth_z, cb_eth_chg (ETH).
  Primary: v103 + these 5 features (LS book). Secondary: v92 + these 5
  (v92 7d model, long-only book, v92 vol target). Report ICs + yearly normal/fee/exec net/DD.
A2 (v112): v103 setup but per-horizon HistGradientBoostingClassifier
  (max_depth 4, lr 0.03, max_iter 400, min_samples_leaf 300, l2 1.0, random_state 0)
  on target (y_h > 0); pred = 2*mean_h P(up) - 1; v94 weights_ls LS with own 20% vol
  target; secondary 0.5*v96 books + 0.5*(LS*scale), scale 1. Report ICs + yearly net/DD.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit"
V9394_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H_V92 = 42
EMBARGO_V103 = 78
EMBARGO_V92 = 102
HS_V103 = (6, 18)
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)
FLOW_FEATS = ["tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z",
              "tsize_z", "ntr_z", "rng6", "clv6"]
CB_FEATS = ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}


def load_asset(s):
    if s == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{s}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{s}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():
        s4 = b.iloc[:0].copy(); s1 = d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{s}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{s}_spot_1d_2017.parquet")
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


def features_flow(b, d, f):
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


def build_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x = features_flow(b, d, f)
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


def build_cb_features_one(P, coin):
    """Spot 4h concat + coinbase asof per spec. Returns DataFrame indexed by spot open_time."""
    sym = f"{P}USDT"
    s17 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_4h_2017.parquet")
    s4 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_4h.parquet")
    spot = pd.concat([s17, s4], ignore_index=True)
    spot["open_time"] = pd.to_datetime(spot["open_time"], utc=True)
    spot["close"] = spot["close"].astype(float)
    spot = spot.sort_values("open_time").drop_duplicates(subset="open_time", keep="last").reset_index(drop=True)
    cb = pd.read_parquet(CB_DIR / f"{coin}-USD_1h.parquet")
    cb["open_time"] = pd.to_datetime(cb["open_time"], utc=True)
    cb["close"] = cb["close"].astype(float)
    cb = cb.sort_values("open_time").reset_index(drop=True)
    left = pd.DataFrame({"T": spot["open_time"], "key": spot["open_time"] + pd.Timedelta(hours=3),
                         "bin_close": spot["close"].to_numpy()})
    left = left.sort_values("key")
    right = pd.DataFrame({"key": cb["open_time"], "cb_close": cb["close"].to_numpy()}).sort_values("key")
    m = pd.merge_asof(left, right, on="key", direction="backward", tolerance=pd.Timedelta(hours=2))
    m = m.sort_values("T").reset_index(drop=True)
    cbp = 1e4 * np.log(m["cb_close"] / m["bin_close"])
    p6 = cbp.rolling(6, min_periods=4).mean()
    p42 = cbp.rolling(42, min_periods=30).mean()
    m540 = cbp.rolling(540, min_periods=270).mean()
    s540 = cbp.rolling(540, min_periods=270).std()
    return pd.DataFrame({"t": m["T"], "p6": p6, "p42": p42, "m540": m540, "s540": s540, "cbp": cbp})


def add_cb_features(panel):
    btc = build_cb_features_one("BTC", "BTC")
    eth = build_cb_features_one("ETH", "ETH")
    b = btc.set_index("t")
    e = eth.set_index("t")
    cb = pd.DataFrame(index=b.index.union(e.index))
    cb["cb_btc_dev"] = (b["p6"] - b["m540"]).reindex(cb.index)
    cb["cb_btc_z"] = ((b["p6"] - b["m540"]) / b["s540"]).reindex(cb.index)
    cb["cb_btc_chg"] = (b["p6"] - b["p42"]).reindex(cb.index)
    cb["cb_eth_z"] = ((e["p6"] - e["m540"]) / e["s540"]).reindex(cb.index)
    cb["cb_eth_chg"] = (e["p6"] - e["p42"]).reindex(cb.index)
    panel = panel.join(cb, on="t")
    return panel


def train_predict_v103(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB_PARAMS)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS_V103):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def train_predict_7d(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V92)
    tr = panel[(panel.t < cutoff) & panel["y42"].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB_PARAMS)
    m.fit(tr[feats], tr["y42"])
    te["pred"] = m.predict(te[feats])
    return te, int(len(tr))


def train_predict_clf(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    probs = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingClassifier(**HGB_PARAMS)
        m.fit(tr[feats], (tr[yh] > 0).astype(int))
        probs[:, j] = m.predict_proba(te[feats])[:, 1]
    te["pred"] = 2 * probs.mean(axis=1) - 1
    for j, h in enumerate(HS_V103):
        te[f"pup_h{h}"] = probs[:, j]
    return te, ntrs


def weights_ls(oos, shorts):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = (((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)) if shorts else 0.0 * long_
        raw = (long_ - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_target_scale(o, W, target=0.20, cap=2.0):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    sc = (target / vol).clip(upper=cap).fillna(1.0)
    sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    return sc


def simulate(o, W, scale, fee, slip=0.0):
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0) if isinstance(scale, pd.Series) else W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def yearly_slices(net, turn):
    out = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = anchor
        out.append(st)
    return out


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def build_v96_books():
    pred92 = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred92["t"] = pd.to_datetime(pred92["t"], utc=True)
    oos92 = pred92.sort_values(["t", "sym"]).reset_index(drop=True)
    pred94 = pd.read_csv(V9394_DIR / "predictions_v94.csv", parse_dates=["t"])
    pred94["t"] = pd.to_datetime(pred94["t"], utc=True)
    oos94 = pred94.sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = weights_ls(oos92.assign(pred=oos92["pred"]), False)
    W94 = weights_ls(oos94, True)
    o = oos92.pivot_table(index="t", columns="sym", values="open").reindex(W92.index).sort_index()
    o = o[list(SYMS)]
    s92 = vol_target_scale(o, W92.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s94 = vol_target_scale(o, W94.reindex(o.index).fillna(0.0), 0.20, 2.0)
    idx = W92.index.union(W94.index).union(o.index)
    W92a = W92.reindex(idx).fillna(0.0)
    W94a = W94.reindex(idx).fillna(0.0)
    s92a = s92.reindex(idx).fillna(1.0)
    s94a = s94.reindex(idx).fillna(1.0)
    books = 0.5 * W92a.mul(s92a, axis=0) + 0.5 * W94a.mul(s94a, axis=0)
    o = o.reindex(idx).sort_index()
    return dict(books=books, o=o)


def run_book_scenarios(o, W, scale):
    out = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = simulate(o, W, scale, fee, slip)
        out[sc] = dict(net=net, turn=turn, yearly=yearly_slices(net, turn))
    return out


def main():
    global FEATS_ALL, FEATS_V92, FEATS_V111P, FEATS_V111S
    panel = build_panel()
    FEATS_ALL = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                       "pred", "pred_h6", "pred_h18", "pup_h6", "pup_h18")]
    FEATS_V92 = [c for c in FEATS_ALL if c not in FLOW_FEATS]
    assert len(FEATS_V92) == 26, len(FEATS_V92)
    assert len(FEATS_ALL) == 36, len(FEATS_ALL)
    panel = add_cb_features(panel)
    assert all(c in panel.columns for c in CB_FEATS)
    FEATS_V111P = FEATS_ALL + CB_FEATS
    FEATS_V111S = FEATS_V92 + CB_FEATS
    assert len(FEATS_V111P) == 41 and len(FEATS_V111S) == 31
    # --- A1 primary: v103 + 5cb, LS ---
    v111p_anchors, v111p_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v103(panel, anchor, FEATS_V111P)
        v111p_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                                  n_pred_rows=int(len(te)),
                                  n_pred_rows_with_y6=int(te["y6"].notna().sum()),
                                  n_pred_rows_with_y18=int(te["y18"].notna().sum()),
                                  n_pred_rows_with_y42=int(te["y42"].notna().sum()),
                                  ic_vs_y6=round(spearman(te["pred"], te["y6"]), 4),
                                  ic_vs_y18=round(spearman(te["pred"], te["y18"]), 4),
                                  ic_vs_y42=round(spearman(te["pred"], te["y42"]), 4)))
        v111p_parts.append(te)
        print("v111p", anchor, ntrs, v111p_anchors[-1]["ic_vs_y6"], v111p_anchors[-1]["ic_vs_y18"], flush=True)
    oos111p = pd.concat(v111p_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o111p = oos111p.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W111p = weights_ls(oos111p, True)
    s111p = vol_target_scale(o111p, W111p, 0.20, 2.0)
    scen111p = run_book_scenarios(o111p, W111p, s111p)
    # --- A1 secondary: v92 + 5cb, 7d long-only ---
    v111s_anchors, v111s_parts = [], []
    for anchor in ANCHORS:
        te, ntr = train_predict_7d(panel, anchor, FEATS_V111S)
        v111s_anchors.append(dict(anchor=anchor, train_rows=int(ntr), n_pred_rows=int(len(te)),
                                  ic_vs_y42=round(spearman(te["pred"], te["y42"]), 4),
                                  ic_vs_y6=round(spearman(te["pred"], te["y6"]), 4),
                                  ic_vs_y18=round(spearman(te["pred"], te["y18"]), 4)))
        v111s_parts.append(te)
        print("v111s", anchor, ntr, v111s_anchors[-1]["ic_vs_y42"], flush=True)
    oos111s = pd.concat(v111s_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o111s = oos111s.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W111s = weights_ls(oos111s, False)
    s111s = vol_target_scale(o111s, W111s, 0.20, 2.0)
    scen111s = run_book_scenarios(o111s, W111s, s111s)
    # --- A2 primary: v103 feats, per-horizon classifier, LS ---
    v112p_anchors, v112p_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_clf(panel, anchor, FEATS_ALL)
        v112p_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                                  n_pred_rows=int(len(te)),
                                  n_pred_rows_with_y6=int(te["y6"].notna().sum()),
                                  n_pred_rows_with_y18=int(te["y18"].notna().sum()),
                                  n_pred_rows_with_y42=int(te["y42"].notna().sum()),
                                  ic_vs_y6=round(spearman(te["pred"], te["y6"]), 4),
                                  ic_vs_y18=round(spearman(te["pred"], te["y18"]), 4),
                                  ic_vs_y42=round(spearman(te["pred"], te["y42"]), 4)))
        v112p_parts.append(te)
        print("v112p", anchor, ntrs, v112p_anchors[-1]["ic_vs_y6"], v112p_anchors[-1]["ic_vs_y18"], flush=True)
    oos112p = pd.concat(v112p_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o112p = oos112p.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W112p = weights_ls(oos112p, True)
    s112p = vol_target_scale(o112p, W112p, 0.20, 2.0)
    scen112p = run_book_scenarios(o112p, W112p, s112p)
    # --- A2 secondary: 0.5*v96 + 0.5*(LS*scale), scale 1 ---
    v96 = build_v96_books()
    idx = v96["books"].index.union(W112p.index).union(o112p.index)
    books96 = v96["books"].reindex(idx).fillna(0.0)
    o_all = v96["o"].reindex(idx).ffill()
    o112pa = o112p.reindex(idx)
    o_blend = o_all.combine_first(o112pa).sort_index()
    W112pa = W112p.reindex(idx).fillna(0.0)
    s112pa = s112p.reindex(idx).fillna(1.0)
    v112_scaled = W112pa.mul(s112pa, axis=0)
    blend = 0.5 * books96 + 0.5 * v112_scaled
    scen112b = run_book_scenarios(o_blend, blend, 1.0)
    result = {
        "anchors": list(ANCHORS),
        "cutoff_rule_v103": "cutoff = anchor - 78*4h = anchor - 312h; per-horizon train t<cutoff and t+(h+1)*4h<cutoff and y_h not NaN",
        "cutoff_rule_v92": "cutoff = anchor - 102*4h = anchor - 408h; train t<cutoff and t+43*4h<cutoff and y42 not NaN",
        "model_reg": HGB_PARAMS,
        "model_clf": HGB_PARAMS,
        "features_v92": FEATS_V92,
        "features_flow": FLOW_FEATS,
        "features_all": FEATS_ALL,
        "features_cb": CB_FEATS,
        "features_v111_primary": FEATS_V111P,
        "features_v111_secondary": FEATS_V111S,
        "assets": list(SYMS),
        "cb_spec": "spot=concat(spot_4h_2017,spot_4h) dedup open_time sorted; cb=1h open_time<=T+3h asof backward tol 2h else NaN; cbp=1e4*log(cb_close/bin_close); p6=roll6min4; p42=roll42min30; m540/s540=roll540min270; cb_btc_dev=p6-m540; cb_btc_z=(p6-m540)/s540; cb_btc_chg=p6-p42; cb_eth_z/chg likewise",
        "v111_primary": {"anchors": v111p_anchors,
                         "yearly": {sc: v["yearly"] for sc, v in scen111p.items()}},
        "v111_secondary": {"anchors": v111s_anchors,
                           "yearly": {sc: v["yearly"] for sc, v in scen111s.items()}},
        "v112_primary": {"anchors": v112p_anchors,
                         "yearly": {sc: v["yearly"] for sc, v in scen112p.items()}},
        "v112_secondary": {"yearly": {sc: v["yearly"] for sc, v in scen112b.items()}},
        "data": {"usdm_btc": "data/raw/ma_ribbon_20260924", "usdm_others": "data/raw/xs_universe_20260924",
                 "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar",
                 "spot_cb": "data/raw/spot_majors_20260925/{BTC,ETH}USDT_spot_4h_2017.parquet + {BTC,ETH}USDT_spot_4h.parquet",
                 "coinbase": "data/raw/coinbase_20260925/{BTC,ETH}-USD_1h.parquet",
                 "v96_books_source": "v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv, leader vol_target_scale (no fillna, NaN->1)"},
        "execution": {"fee_per_unit_turnover": 0.0002, "long_funding_per_4h_bar": 5e-05,
                      "weight": "v94.weights_ls; long=min(max(p,0)/0.5,1) rib!=-1; short=min(max(-p,0)/0.5,1) rib!=+1; raw=(l-s)/(vol42*sqrt(2190)); /sum|raw| *min(1,count/5); every 6th bar ffill",
                      "vol": "v94.vol_target_scale target 0.20 cap 2 (realized=W.shift(2)*ret1 no fillna, rolling360 min120, NaN->1)",
                      "v112_pred": "pred=2*mean_h P(y_h>0)-1 per-horizon HGBClassifier",
                      "v112_blend": "blend_books=0.5*v96books+0.5*(W112LS*s112); simulate with scale 1.0"},
        "assumptions": ["cb features causal rolling on spot series; coinbase 1h bar [T+3h,T+4h) available at 4h close",
                        "v111 ICs spearman(mean pred, y_h) on OOS rows with y_h not NaN",
                        "v112 ICs spearman(2*mean P(up)-1, y_h) on OOS rows with y_h not NaN",
                        "v96 books recomputed from audited CSVs (no retrain) with leader scales",
                        "scenarios use v92.SCEN fees/slips; fills = turnover bars"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    oos111p[["t", "sym", "open", "pred", "pred_h6", "pred_h18", "y6", "y18", "y42", "vol42", "rib"] + CB_FEATS].to_csv(
        OUT_DIR / "predictions_v111_primary.csv", index=False)
    oos111s[["t", "sym", "open", "pred", "y6", "y18", "y42", "vol42", "rib"] + CB_FEATS].to_csv(
        OUT_DIR / "predictions_v111_secondary.csv", index=False)
    oos112p[["t", "sym", "open", "pred", "pup_h6", "pup_h18", "y6", "y18", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v112_primary.csv", index=False)
    for sc, v in scen111p.items():
        suffix = "" if sc == "normal" else f"_{sc}"
        pd.DataFrame({"t": v["net"].index, "net": v["net"].values,
                      "turnover": v["turn"].values}).to_csv(OUT_DIR / f"equity_v111_primary{suffix}.csv", index=False)
    for sc, v in scen111s.items():
        suffix = "" if sc == "normal" else f"_{sc}"
        pd.DataFrame({"t": v["net"].index, "net": v["net"].values,
                      "turnover": v["turn"].values}).to_csv(OUT_DIR / f"equity_v111_secondary{suffix}.csv", index=False)
    for sc, v in scen112p.items():
        suffix = "" if sc == "normal" else f"_{sc}"
        pd.DataFrame({"t": v["net"].index, "net": v["net"].values,
                      "turnover": v["turn"].values}).to_csv(OUT_DIR / f"equity_v112_primary{suffix}.csv", index=False)
    for sc, v in scen112b.items():
        suffix = "" if sc == "normal" else f"_{sc}"
        pd.DataFrame({"t": v["net"].index, "net": v["net"].values,
                      "turnover": v["turn"].values}).to_csv(OUT_DIR / f"equity_v112_blend{suffix}.csv", index=False)
    print(json.dumps({"v111p": scen111p["normal"]["yearly"], "v111s": scen111s["normal"]["yearly"],
                      "v112p": scen112p["normal"]["yearly"], "v112b": scen112b["normal"]["yearly"]}, indent=2))


if __name__ == "__main__":
    main()
