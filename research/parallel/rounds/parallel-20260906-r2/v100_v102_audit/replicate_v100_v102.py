"""Blind v100+v101+v102 audit reproduction from OPENCODE_V100_V102_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/*, and audited
replications v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv.
Does NOT read research/.../v100/*, v101/* or v102/* (blind until
replication.json is saved).

Base (all three): v92 5-asset features/target/anchors/embargo
  cutoff = anchor - 102*4h = anchor - 408h;
  train rows need t < cutoff and t + 43*4h < cutoff and y not NaN;
  long-only book weights_from(...,"model"), causal 20% vol target, costs
  fee 0.0002, funding 0.00005 long gross, unless stated.

A1 (v100, extra training rows only): phase-shifted 4h bars phases 1,2,3 from
  perp 1h klines (BTC data/raw/ma_ribbon_20260924/klines_1h.parquet, others
  data/raw/majors_intraday_20260924/{SYM}_1h.parquet). Group = 4 consecutive
  1h bars whose first open_time hour % 4 == phase; open first, high max,
  low min, close last, close_time last, quote_volume sum; keep only complete
  groups of 4. Unchanged v92 features(b,d,f) with same daily/funding files;
  asset id as v92; BTC context joined from BTC same-phase grid by open_time.
  Training pool = v92 panel (phase 0 incl spot prefix) + phases 1-3;
  test rows = v92 panel only. HGB as v92 except min_samples_leaf 1200
  (primary) and 300 (sensitivity).

A2 (v101, extra assets training only): ADA DOGE LINK LTC BCH DOT AVAX TRX ETC
  XLM UNI AAVE FIL from data/raw/xs_universe_20260924 (no spot prefix), v92
  features, asset ids 5..17 in that order, BTC context from v92 BTC rows.
  Training pool = majors + extras; sample_weight 1 majors / w extras,
  w=1 primary, w=0.5 sensitivity; test/trading majors only.

A3 (v102, market-neutral): y_xs = y - mean y over majors with label at same
  bar (NaN if <2 labelled). xs_c = c - same-bar mean over majors for
  c in snr42 snr180 ret42 ret180 d50 d200 f7 vol_ratio volz.
  HGB (v92 params) on v92 feats + xs feats, target y_xs.
  Weights: raw=(pred-bar mean pred)/(vol42*sqrt(2190)); W=raw-bar mean(raw)
  over assets with prediction, NaN->0, zero if <2 predictions, /sum|W|;
  daily rebalance every 6th row as v92. Scale v92 vol_target_scale target
  0.10 cap 2. Simulate with v92.simulate. Blend=0.75*v99+0.25*neutral per bar
  using v99 normal with leader convention carry_exp[t]*carry[t].
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit"
V9394_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ASSET_ID = {s: i for i, s in enumerate(SYMS)}
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H = 42
EMBARGO_BARS = 102  # 42 + 10*6
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
MAJORS_1H_DIR = ROOT / "data/raw/majors_intraday_20260924"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
HGB_BASE = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                min_samples_leaf=300, l2_regularization=1.0, random_state=0)
EXTRAS = ("ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "DOTUSDT",
          "AVAXUSDT", "TRXUSDT", "ETCUSDT", "XLMUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT")
XS_COLS = ["snr42", "snr180", "ret42", "ret180", "d50", "d200", "f7", "vol_ratio", "volz"]


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
        s4 = b.iloc[:0].copy()
        s1 = d.iloc[:0].copy()
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


def load_asset_nospot(s):
    # for v101 extras: USD-M only, no spot prefix
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
    return b, d, f


def features(b, d, f):
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
    fwd = np.full(n, np.nan)
    if n > 1 + H:
        fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    y = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H)), -4, 4)
    return x, y


def build_v92_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x, y = features(b, d, f)
        x["asset"] = i
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


FEATS_V92 = None


def load_1h(s):
    if s == "BTCUSDT":
        df = pd.read_parquet(BTC_DIR / "klines_1h.parquet")
    else:
        df = pd.read_parquet(MAJORS_1H_DIR / f"{s}_1h.parquet")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def build_phase_bars(h1, phase):
    h1 = h1.sort_values("open_time").reset_index(drop=True)
    ot = h1["open_time"]
    hours = ot.dt.hour + ot.dt.minute / 60.0  # should be exact hours
    # candidate starts where hour % 4 == phase and minute == 0
    o = h1["open"].to_numpy(float)
    hi = h1["high"].to_numpy(float)
    lo = h1["low"].to_numpy(float)
    cl = h1["close"].to_numpy(float)
    qv = h1["quote_volume"].to_numpy(float)
    ots = ot.to_numpy()
    cts = h1["close_time"].to_numpy()
    out = []
    n = len(h1)
    for i in range(n):
        h = int(pd.Timestamp(ots[i]).hour) % 4
        if h != phase:
            continue
        if i + 3 >= n:
            continue
        # check 4 consecutive 1h bars exactly 1h apart
        ok = True
        for j in range(1, 4):
            dt = (pd.Timestamp(ots[i + j]) - pd.Timestamp(ots[i + j - 1])).total_seconds()
            if dt != 3600:
                ok = False
                break
        if not ok:
            continue
        out.append({
            "open_time": pd.Timestamp(ots[i]),
            "open": float(o[i]),
            "high": float(np.max(hi[i:i + 4])),
            "low": float(np.min(lo[i:i + 4])),
            "close": float(cl[i + 3]),
            "close_time": pd.Timestamp(cts[i + 3]),
            "quote_volume": float(np.sum(qv[i:i + 4])),
        })
    df = pd.DataFrame(out)
    if len(df):
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
        df = df.sort_values("open_time").reset_index(drop=True)
    return df


def build_phase_panels(v92_panel, daily_funding):
    # daily_funding: dict sym -> (d, f)
    phase_panels = {}
    btc_phase_feats = {}
    for phase in (1, 2, 3):
        rows = []
        for i, s in enumerate(SYMS):
            h1 = load_1h(s)
            bph = build_phase_bars(h1, phase)
            d, f = daily_funding[s]
            x, y = features(bph, d, f)
            x["asset"] = i
            x["y"] = y
            x["t"] = bph["open_time"]
            x["open"] = bph["open"].astype(float).to_numpy()
            x["sym"] = s
            x["bar"] = np.arange(len(bph))
            x["phase"] = phase
            rows.append(x)
            if s == "BTCUSDT":
                btc_phase_feats[phase] = x.set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
        panel = pd.concat(rows, ignore_index=True)
        # replace btc_ with same-phase BTC join by open_time
        panel = panel.drop(columns=["btc_ret42", "btc_ret180", "btc_rib", "btc_snr42"], errors="ignore")
        panel = panel.join(btc_phase_feats[phase], on="t")
        phase_panels[phase] = panel
    return phase_panels


def train_predict(pool, test_panel, anchor, hgb_params, sample_weight_col=None):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    tr = pool[(pool.t < cutoff) & pool.y.notna()].copy()
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
    te = test_panel[(test_panel.t >= a) & (test_panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**hgb_params)
    if sample_weight_col is not None:
        m.fit(tr[FEATS_V92], tr["y"], sample_weight=tr[sample_weight_col].to_numpy(float))
    else:
        m.fit(tr[FEATS_V92], tr["y"])
    te["pred"] = m.predict(te[FEATS_V92])
    return te, len(tr)


def compute_weights_longonly(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    W = W.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def backtest(oos_opens, W, vol_target=0.20):
    o = oos_opens
    ret1 = o / o.shift(1) - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (vol_target / vol).clip(upper=2.0).fillna(1.0)
    scale = scale.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r_fwd).sum(axis=1) - turn * 0.0002 - funding
    return net, turn, scale, book, vol


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


def run_v100(v92_panel, phase_panels):
    pool = pd.concat([v92_panel] + [phase_panels[p] for p in (1, 2, 3)], ignore_index=True)
    out = {}
    for leaf, key in ((1200, "primary1200"), (300, "sens300")):
        params = dict(HGB_BASE)
        params["min_samples_leaf"] = leaf
        anchors_rec, oos_parts = [], []
        for anchor in ANCHORS:
            te, ntr = train_predict(pool, v92_panel, anchor, params)
            ev = te.dropna(subset=["y"])
            rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
            anchors_rec.append(dict(anchor=anchor, train_rows=int(ntr),
                                    n_pred_rows=int(len(te)),
                                    n_pred_rows_with_y=int(len(ev)),
                                    ic=round(rho, 4)))
            oos_parts.append(te)
            print(f"v100 {key} {anchor} train {ntr} IC {round(rho,4)}", flush=True)
        oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
        W = compute_weights_longonly(oos)
        o = oos.pivot_table(index="t", columns="sym", values="open")
        o = o[list(SYMS)]
        net, turn, scale, book, vol = backtest(o, W, vol_target=0.20)
        yearly = yearly_slices(net, turn)
        out[key] = dict(anchors=anchors_rec, oos=oos, W=W, o=o, net=net, turn=turn, scale=scale, yearly=yearly)
        print(f"v100 {key} yearly:", json.dumps(yearly), flush=True)
    return out, pool


def build_extras_panel(v92_btc):
    rows = []
    for j, s in enumerate(EXTRAS):
        b, d, f = load_asset_nospot(s)
        x, y = features(b, d, f)
        x["asset"] = 5 + j
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    panel = panel.join(v92_btc, on="t")
    return panel


def run_v101(v92_panel, extras_panel):
    out = {}
    for w_extra, key in ((1.0, "primary_w1"), (0.5, "sens_w05")):
        pool = pd.concat([v92_panel.assign(_w=1.0),
                          extras_panel.assign(_w=float(w_extra))], ignore_index=True)
        anchors_rec, oos_parts = [], []
        for anchor in ANCHORS:
            a = pd.Timestamp(anchor, tz="UTC")
            end = a + pd.Timedelta(days=365)
            cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
            tr = pool[(pool.t < cutoff) & pool.y.notna()].copy()
            tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
            te = v92_panel[(v92_panel.t >= a) & (v92_panel.t < end)].copy()
            m = HistGradientBoostingRegressor(**HGB_BASE)
            m.fit(tr[FEATS_V92], tr["y"], sample_weight=tr["_w"].to_numpy(float))
            te["pred"] = m.predict(te[FEATS_V92])
            ev = te.dropna(subset=["y"])
            rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
            anchors_rec.append(dict(anchor=anchor, train_rows=int(len(tr)),
                                    train_rows_majors=int((tr.sym.isin(SYMS)).sum()),
                                    train_rows_extras=int((~tr.sym.isin(SYMS)).sum()),
                                    n_pred_rows=int(len(te)),
                                    n_pred_rows_with_y=int(len(ev)),
                                    ic=round(rho, 4)))
            oos_parts.append(te)
            print(f"v101 {key} {anchor} train {len(tr)} IC {round(rho,4)}", flush=True)
        oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
        W = compute_weights_longonly(oos)
        o = oos.pivot_table(index="t", columns="sym", values="open")
        o = o[list(SYMS)]
        net, turn, scale, book, vol = backtest(o, W, vol_target=0.20)
        yearly = yearly_slices(net, turn)
        out[key] = dict(anchors=anchors_rec, oos=oos, W=W, o=o, net=net, turn=turn, scale=scale, yearly=yearly)
        print(f"v101 {key} yearly:", json.dumps(yearly), flush=True)
    return out


def add_xs_targets(panel):
    # y_xs and xs_ features, contemporaneous only
    df = panel.copy()
    # y mean per bar over majors with label
    ycnt = df.dropna(subset=["y"]).groupby("t")["y"].agg(["mean", "count"])
    ymean = ycnt["mean"]
    ycount = ycnt["count"]
    df["y_mean_bar"] = df["t"].map(ymean)
    df["y_count_bar"] = df["t"].map(ycount).fillna(0)
    df["y_xs"] = df["y"] - df["y_mean_bar"]
    df.loc[df["y_count_bar"] < 2, "y_xs"] = np.nan
    for c in XS_COLS:
        m = df.dropna(subset=[c]).groupby("t")[c].mean()
        df[f"xs_{c}"] = df[c] - df["t"].map(m)
    return df


def compute_weights_neutral(oos):
    # oos has pred, vol42 per row; index by t
    piv_pred = oos.pivot_table(index="t", columns="sym", values="pred")
    piv_vol = oos.pivot_table(index="t", columns="sym", values="vol42")
    piv_pred = piv_pred[list(SYMS)]
    piv_vol = piv_vol[list(SYMS)]
    bar_mean_pred = piv_pred.mean(axis=1, skipna=True)
    cnt = piv_pred.notna().sum(axis=1)
    raw = piv_pred.sub(bar_mean_pred, axis=0).div(piv_vol * np.sqrt(PD * 365))
    raw = raw.replace([np.inf, -np.inf], np.nan)
    # second demean over assets with prediction
    raw_mean = raw.mean(axis=1, skipna=True)
    W = raw.sub(raw_mean, axis=0)
    W = W.fillna(0.0)
    # zero if fewer than 2 predictions
    W = W.mul(cnt.ge(2), axis=0)
    row_sum = W.abs().sum(axis=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W, piv_pred, cnt


def run_v102(v92_panel):
    panel = add_xs_targets(v92_panel)
    feats_xs = FEATS_V92 + [f"xs_{c}" for c in XS_COLS]
    anchors_rec, oos_parts = [], []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
        tr = panel[(panel.t < cutoff) & panel.y_xs.notna()].copy()
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB_BASE)
        m.fit(tr[feats_xs], tr["y_xs"])
        te["pred"] = m.predict(te[feats_xs])
        ev = te.dropna(subset=["y_xs"])
        rho_pool = float(spearmanr(ev["pred"], ev["y_xs"]).statistic) if len(ev) > 2 else float("nan")
        # mean per-bar IC
        perbar = []
        for t, g in ev.groupby("t"):
            g2 = g.dropna(subset=["pred", "y_xs"])
            if len(g2) >= 2:
                try:
                    r = float(spearmanr(g2["pred"], g2["y_xs"]).statistic)
                    if np.isfinite(r):
                        perbar.append(r)
                except Exception:
                    pass
        rho_bar = float(np.mean(perbar)) if perbar else float("nan")
        anchors_rec.append(dict(anchor=anchor, train_rows=int(len(tr)),
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_yxs=int(len(ev)),
                                ic_pooled_xs=round(rho_pool, 4) if np.isfinite(rho_pool) else None,
                                ic_mean_perbar_xs=round(rho_bar, 4) if np.isfinite(rho_bar) else None))
        oos_parts.append(te)
        print(f"v102 {anchor} train {len(tr)} ICpool {round(rho_pool,4)} ICbar {round(rho_bar,4)}", flush=True)
    oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W, piv_pred, cnt = compute_weights_neutral(oos)
    o = oos.pivot_table(index="t", columns="sym", values="open")
    o = o[list(SYMS)]
    net, turn, scale, book, vol = backtest(o, W, vol_target=0.10)
    yearly = yearly_slices(net, turn)
    # pooled + mean per-bar over full OOS
    ev_all = oos.dropna(subset=["y_xs"])
    ic_pooled = float(spearmanr(ev_all["pred"], ev_all["y_xs"]).statistic)
    perbar_all = []
    for t, g in ev_all.groupby("t"):
        g2 = g.dropna(subset=["pred", "y_xs"])
        if len(g2) >= 2:
            r = float(spearmanr(g2["pred"], g2["y_xs"]).statistic)
            if np.isfinite(r):
                perbar_all.append(r)
    ic_bar = float(np.mean(perbar_all)) if perbar_all else float("nan")
    return dict(anchors=anchors_rec, oos=oos, W=W, o=o, net=net, turn=turn,
                scale=scale, yearly=yearly, ic_pooled=ic_pooled, ic_bar=ic_bar,
                feats=feats_xs)


def compute_weights_longshort(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
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


def run_v99_leader_convention():
    """v99 normal with leader convention exposure[t]*carry[t] (for v102 blend)."""
    pred92 = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred92["t"] = pd.to_datetime(pred92["t"], utc=True)
    oos92 = pred92.sort_values(["t", "sym"]).reset_index(drop=True)
    pred94 = pd.read_csv(V9394_DIR / "predictions_v94.csv", parse_dates=["t"])
    pred94["t"] = pd.to_datetime(pred94["t"], utc=True)
    oos94 = pred94.sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = compute_weights_longonly(oos92)
    W94 = compute_weights_longshort(oos94)
    o = oos92.pivot_table(index="t", columns="sym", values="open").reindex(W92.index).sort_index()
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1  # keep NaN (leader)

    def _scale_leader(W):
        Wx = W.reindex(o.index).fillna(0.0)
        book = (Wx.shift(2) * ret1).sum(axis=1)  # no fillna (leader)
        vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
        sc = (0.20 / vol).clip(upper=2.0).fillna(1.0)
        sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
        return sc, book, vol, Wx

    s92, _, _, W92a = _scale_leader(W92)
    s94, _, _, W94a = _scale_leader(W94)
    books = 0.5 * W92a.mul(s92, axis=0) + 0.5 * W94a.mul(s94, axis=0)
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    c = carry.reindex(o.index)["carry"].astype(float).fillna(0.0)
    realized = 0.8 * (books.shift(2) * ret1).sum(axis=1) + 0.6 * c.shift(1)
    vol = realized.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    s = (0.15 / vol).clip(upper=2.0).fillna(1.0)
    s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wt = books.mul(0.8 * s, axis=0)
    model_gross = (Wt * r_fwd).sum(axis=1)
    model_turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
    model_funding = Wt.clip(lower=0).sum(axis=1) * 0.00005
    model_net = model_gross - model_turn * 0.0002 - model_funding
    pos_c = 0.6 * s
    carry_gross = pos_c * c  # leader contemporaneous
    carry_turn = pos_c.diff().fillna(0.0).abs()  # leader first diff 0
    carry_cost = carry_turn * 2 * 0.0004 / 1.2
    carry_net = carry_gross - carry_cost
    net = model_net + carry_net
    return dict(net=net, model_turn=model_turn, Wt=Wt, o=o, scale=s, model_net=model_net,
                carry_net=carry_net, carry=c)


def main():
    global FEATS_V92
    v92_panel = build_v92_panel()
    FEATS_V92 = [c for c in v92_panel.columns if c not in ("y", "t", "open", "sym", "bar", "phase", "_w",
                                                            "y_mean_bar", "y_count_bar", "y_xs") and not c.startswith("xs_")]
    # daily/funding for phase grids (same files as v92 incl spot prefix in d)
    daily_funding = {}
    for s in SYMS:
        _, d, f = load_asset(s)
        daily_funding[s] = (d, f)
    phase_panels = build_phase_panels(v92_panel, daily_funding)
    v100, pool100 = run_v100(v92_panel, phase_panels)
    v92_btc = v92_panel[v92_panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    extras_panel = build_extras_panel(v92_btc)
    v101 = run_v101(v92_panel, extras_panel)
    v102 = run_v102(v92_panel)
    v99 = run_v99_leader_convention()
    # blend 0.75 v99 + 0.25 neutral (aligned)
    neutral_net = v102["net"].reindex(v99["net"].index).fillna(0.0)
    v99_net = v99["net"].fillna(0.0)
    blend_net = 0.75 * v99_net + 0.25 * neutral_net
    # blend turnover for fills: use weighted? use neutral+model turn proxy: use 0.75*model_turn+0.25*neutral turn
    blend_turn = 0.75 * v99["model_turn"].reindex(blend_net.index).fillna(0.0) + 0.25 * v102["turn"].reindex(blend_net.index).fillna(0.0)
    yearly_neutral = v102["yearly"]
    yearly_blend = yearly_slices(blend_net, blend_turn)
    yearly_v99 = yearly_slices(v99["net"], v99["model_turn"])
    # daily correlation neutral vs v99 from 2021-09-24 onward
    start = pd.Timestamp("2021-09-24", tz="UTC")
    n_al = neutral_net[neutral_net.index >= start].fillna(0.0)
    v_al = v99_net[v99_net.index >= start].fillna(0.0)
    # daily aggregate every 6 bars
    def to_daily(sr):
        arr = sr.to_numpy()
        n = len(arr) // 6 * 6
        return pd.Series(((1 + pd.Series(arr[:n]).fillna(0.0).to_numpy().reshape(-1, 6)).prod(axis=1) - 1))
    d_n = to_daily(n_al)
    d_v = to_daily(v_al)
    corr_daily = float(d_n.corr(d_v)) if len(d_n) > 2 else float("nan")
    corr_4h = float(n_al.corr(v_al)) if len(n_al) > 2 else float("nan")

    result = {
        "anchors": list(ANCHORS),
        "cutoff_rule": "cutoff = anchor - 102*4h = anchor - 408h; train t<cutoff and t+43*4h<cutoff and label not NaN",
        "model_base": HGB_BASE,
        "features_v92": FEATS_V92,
        "assets_majors": list(SYMS),
        "v100": {
            "primary1200": {"anchors": v100["primary1200"]["anchors"], "yearly_normal": v100["primary1200"]["yearly"]},
            "sens300": {"anchors": v100["sens300"]["anchors"], "yearly_normal": v100["sens300"]["yearly"]},
            "train_pool": "v92 phase0 (incl spot prefix) + phases 1-3 from 1h; test v92 phase0 only",
        },
        "v101": {
            "primary_w1": {"anchors": v101["primary_w1"]["anchors"], "yearly_normal": v101["primary_w1"]["yearly"]},
            "sens_w05": {"anchors": v101["sens_w05"]["anchors"], "yearly_normal": v101["sens_w05"]["yearly"]},
            "extras": list(EXTRAS),
            "train_pool": "majors + 13 extras (no spot prefix); sample_weight 1 majors / w extras",
        },
        "v102": {
            "anchors": v102["anchors"],
            "ic_pooled_xs": round(float(v102["ic_pooled"]), 4),
            "ic_mean_perbar_xs": round(float(v102["ic_bar"]), 4),
            "yearly_neutral_normal": v102["yearly"],
            "yearly_blend_normal": yearly_blend,
            "yearly_v99_leader_convention_normal": yearly_v99,
            "corr_daily_neutral_vs_v99": round(float(corr_daily), 4),
            "corr_4h_neutral_vs_v99": round(float(corr_4h), 4),
            "features": v102["feats"],
            "weight": "raw=(pred-barmean pred)/(vol42*sqrt(2190)); W=raw-barmean(raw) over assets with pred, NaN->0, zero if <2 preds, /sum|W|; every 6th bar ffill",
            "vol_target": "v92 vol_target_scale target 0.10 cap 2",
        },
        "execution": {
            "fee_per_unit_turnover": 0.0002,
            "long_funding_per_4h_bar": 0.00005,
            "weight_longonly": "s=min(max(pred,0)/0.5,1) zeroed when rib==-1; raw=s/(vol42*sqrt(2190)); normalise to 1 then *min(1,count/5); every 6th bar ffill",
            "vol_target_longonly": "book=sum W_{t-2}*ret1; vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "realisation": "W_t*scale_t earns open[t+2]/open[t+1]-1",
            "v99_blend_convention": "v99 leader convention exposure[t]*carry[t], first carry diff 0, vol NaN->1 default (as audited v93/v99)",
        },
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_1h_btc": "data/raw/ma_ribbon_20260924/klines_1h.parquet",
            "usdm_1h_others": "data/raw/majors_intraday_20260924/{SYM}_1h.parquet",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL none)",
            "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
        },
        "assumptions": [
            "Phase groups require 4 consecutive 1h bars exactly 1h apart with first hour%4==phase; incomplete/gapped groups dropped.",
            "Phase features use same daily (incl spot prefix) + funding files as v92 via merge_asof backward; BTC context from same-phase BTC grid.",
            "v101 extras no spot prefix; BTC context from v92 BTC phase0 rows by open_time; HGB NaN-native.",
            "v102 y_xs NaN if <2 labelled majors at bar; xs_c mean over majors with non-NaN c; IC pooled + mean per-bar vs y_xs.",
            "Blend uses v99 leader-convention net (exposure[t]*carry[t]) recomputed from audited CSVs; blend=0.75*v99+0.25*neutral per bar.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    # CSVs
    for key in ("primary1200", "sens300"):
        d = v100[key]
        d["oos"][["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / f"predictions_v100_{key}.csv", index=False)
        pd.DataFrame({"t": d["net"].index, "net": d["net"].values, "turnover": d["turn"].values,
                      "scale": d["scale"].values}).to_csv(OUT_DIR / f"equity_v100_{key}.csv", index=False)
    for key in ("primary_w1", "sens_w05"):
        d = v101[key]
        d["oos"][["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / f"predictions_v101_{key}.csv", index=False)
        pd.DataFrame({"t": d["net"].index, "net": d["net"].values, "turnover": d["turn"].values,
                      "scale": d["scale"].values}).to_csv(OUT_DIR / f"equity_v101_{key}.csv", index=False)
    v102["oos"][["t", "sym", "open", "pred", "y", "y_xs", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v102.csv", index=False)
    pd.DataFrame({"t": v102["net"].index, "net": v102["net"].values, "turnover": v102["turn"].values,
                  "scale": v102["scale"].values}).to_csv(OUT_DIR / "equity_v102_neutral.csv", index=False)
    pd.DataFrame({"t": blend_net.index, "net_blend": blend_net.values, "net_v99": v99_net.reindex(blend_net.index).values,
                  "net_neutral": neutral_net.reindex(blend_net.index).values}).to_csv(OUT_DIR / "equity_v102_blend.csv", index=False)
    pd.DataFrame({"t": v99["net"].index, "net": v99["net"].values, "model_turn": v99["model_turn"].values,
                  "scale": v99["scale"].values}).to_csv(OUT_DIR / "equity_v99_leader_convention.csv", index=False)
    print(json.dumps({k: result[k] for k in ("v100", "v101", "v102")}, indent=2)[:4000])


if __name__ == "__main__":
    main()
