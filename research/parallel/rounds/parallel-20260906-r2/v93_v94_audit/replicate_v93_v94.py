"""Blind v93+v94 audit reproduction from OPENCODE_V93_V94_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/*, and the
audited v92 replication (v92_audit/replicate_5asset_leader_run.py logic +
v92_audit/predictions_5asset.csv). Does NOT read research/.../v93/* or
research/.../v94/* (blind until replication.json is saved).

A1 (v94): 3x HGB (v92 hyperparams) on h=18/42/84 targets
  y_h = clip(log(open[t+1+h]/open[t+1])/(vol42*sqrt(h)), -4, 4);
  cutoff = anchor - 4h*(84+60) = anchor - 576h;
  per-horizon train filter: t < cutoff and t+(h+1)*4h < cutoff and y_h not NaN;
  pred = mean of 3 models. Long-short weights per spec, vol-target/execution as v92.
A2 (v93): v92 long-only W at 70% + carry sleeve 30%x3 (0.9 weight), vol target 0.15.
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
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ASSET_ID = {s: i for i, s in enumerate(SYMS)}
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H_V92 = 42
HS = (18, 42, 84)
EMBARGO_V94_BARS = 84 + 60  # 144 bars = 576h
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)


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
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():  # SOL has no spot prefix
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


def features(b, d, f):
    """Same features as v92 replication; labels for h in HS (plus v92 H=42 as y42)."""
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
    for h in HS:
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(h)), -4, 4)
    return x


def build():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x = features(b, d, f)
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


FEATS = None


def train_predict_v94(panel, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V94_BARS)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS)))
    ntrs = []
    for j, h in enumerate(HS):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB_PARAMS)
        m.fit(tr[FEATS], tr[yh])
        preds[:, j] = m.predict(te[FEATS])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def compute_weights_v94(oos):
    Wdict, Ldict, Sdict = {}, {}, {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
        Ldict[s] = long.fillna(0.0)
        Sdict[s] = short.fillna(0.0)
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def backtest_v92_style(panel, oos, W, vol_target=0.20):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index).sort_index()
    for s in SYMS:
        if s not in o.columns:
            o[s] = np.nan
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (vol_target / vol).clip(upper=2.0).fillna(1.0)
    scale = scale.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005  # long gross only
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


def compute_weights_v92_longonly(oos):
    """v92 long-only weights from OOS preds (same as v92 replication)."""
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def run_v93_from_v92_csv():
    """A2 blind: v92 W (from saved v92 replication CSV) + carry sleeve.

    Timing (blind assumption, documented): forward convention as v92 —
    position decided at t earns open[t+2]/open[t+1]-1; carry position at t
    earns carry[t+1] (book uses 1-bar lag carry[t-1] realised at t).
    """
    pred = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred["t"] = pd.to_datetime(pred["t"], utc=True)
    oos = pred.sort_values(["t", "sym"]).reset_index(drop=True)
    W = compute_weights_v92_longonly(oos)
    o = oos.pivot_table(index="t", columns="sym", values="open").reindex(W.index).sort_index()
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    c = carry.reindex(W.index)["carry"].astype(float)
    c = c.fillna(0.0)
    # unscaled realised book at t (for vol only)
    book = 0.7 * (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1) + 0.9 * c.shift(1).fillna(0.0)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    s = (0.15 / vol).clip(upper=2.0).fillna(1.0)
    s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_fwd = c.shift(-1).fillna(0.0)
    Wm = W.mul(0.7 * s, axis=0)
    model_gross = (Wm * r_fwd).sum(axis=1)
    model_turn = Wm.diff().abs().sum(axis=1).fillna(Wm.abs().sum(axis=1))
    model_funding = Wm.clip(lower=0).sum(axis=1) * 0.00005
    model_net = model_gross - model_turn * 0.0002 - model_funding
    pos_c = 0.9 * s
    carry_gross = pos_c * carry_fwd
    carry_turn = pos_c.diff().abs().fillna(pos_c.abs())
    carry_cost = carry_turn * 2 * 0.0004 / 1.2
    carry_net = carry_gross - carry_cost
    net = model_net + carry_net
    turn = model_turn + carry_turn
    return dict(W=W, net=net, turn=turn, scale=s, book=book, vol=vol,
                model_net=model_net, carry_net=carry_net, carry=c)


def yearly_slices(net, turn):
    out = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = anchor
        out.append(st)
    return out


def main():
    global FEATS
    panel = build()
    FEATS = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y18", "y42", "y84")]
    # --- A1 v94 ---
    anchors_rec, oos_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v94(panel, anchor)
        ev = te.dropna(subset=["y42"])
        rho = float(spearmanr(ev["pred"], ev["y42"]).statistic) if len(ev) > 2 else float("nan")
        anchors_rec.append(dict(anchor=anchor, train_rows_h18=ntrs[0], train_rows_h42=ntrs[1],
                                train_rows_h84=ntrs[2], n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)), ic_mean_vs_h42=round(rho, 4)))
        oos_parts.append(te)
        print(anchor, ntrs, "IC42", round(rho, 4), flush=True)
    oos94 = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W94 = compute_weights_v94(oos94)
    net94, turn94, scale94, book94, vol94 = backtest_v92_style(panel, oos94, W94, vol_target=0.20)
    yearly94 = yearly_slices(net94, turn94)
    # --- A2 v93 ---
    v93 = run_v93_from_v92_csv()
    yearly93 = yearly_slices(v93["net"], v93["turn"])
    result = {
        "anchors_v94": anchors_rec,
        "yearly_v94_normal": yearly94,
        "yearly_v93_normal": yearly93,
        "hidden_v94_2025_2026_normal": next(y for y in yearly94 if y["anchor"] == "2025-09-24"),
        "hidden_v93_2025_2026_normal": next(y for y in yearly93 if y["anchor"] == "2025-09-24"),
        "model": HGB_PARAMS,
        "features": FEATS,
        "assets": list(SYMS),
        "cutoffs": {a: str(pd.Timestamp(a, tz="UTC") - pd.Timedelta(hours=4 * EMBARGO_V94_BARS)) for a in ANCHORS},
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL none)",
            "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet (column carry, reindexed to W index, NaN->0)",
            "v92_weights_source": "research/parallel/rounds/parallel-20260906-r2/v92_audit/predictions_5asset.csv recomputed with v92 long-only formula",
        },
        "execution_v94": {
            "labels": "y_h=clip(log(open[t+1+h]/open[t+1])/(vol42*sqrt(h)),-4,4) h=18,42,84; pred=mean of 3 HGB",
            "train_filter": "t<cutoff and t+(h+1)*4h<cutoff and y_h not NaN; cutoff=anchor-576h",
            "weight": "long=min(max(p,0)/0.5,1) zeroed if rib==-1; short=min(max(-p,0)/0.5,1) zeroed if rib==+1; raw=(long-short)/(vol42*sqrt(2190)); /sum|raw| then *min(1,count_nonzero/5); every 6th bar ffill",
            "vol_target": "as v92: book=sum W_{t-2}*(open_t/open_{t-1}-1); vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "realisation": "W_t*scale_t earns open[t+2]/open[t+1]-1; fee 0.0002 on turnover; funding 0.00005 on long gross only",
        },
        "execution_v93_blind_assumption": {
            "book_for_vol": "book_t=0.7*sum W_{t-2}*(open_t/open_{t-1}-1)+0.9*carry_{t-1}; vol=rolling360(min120)std*sqrt(2190); s=min(0.15/vol,2) NaN->1",
            "model_net_forward": "Wm_t=0.7*s_t*W_t earns o[t+2]/o[t+1]-1; cost turnover(Wm)*0.0002 + 0.00005*long gross",
            "carry_net_forward": "pos_t=0.9*s_t earns carry[t+1]; cost |diff(pos)|*2*0.0004/1.2; first-bar diff filled with |pos|",
            "note": "forward convention chosen blind; Part B reconciles with leader script timing if different",
        },
        "assumptions": [
            "features identical to v92 5-asset replication (26 feats incl asset id + btc_ prefix); HGB NaN-native.",
            "v94 cutoff anchor-576h (4h*(84+60)); per-horizon realised-label filter t+(h+1)*4h<cutoff.",
            "v94 IC is spearman(mean pred, y42) on rows with y42 not NaN.",
            "v94 raw NaN/inf->0 before normalisation; empty rows stay 0; daily rebalance every 6th bar ffill.",
            "v93 carry aligned to W timestamps (10950 bars 2021-09-24..2026-09-23), NaN->0; yearly slices [A,A+365d).",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    oos94[["t", "sym", "open", "pred", "pred_h18", "pred_h42", "pred_h84", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v94.csv", index=False)
    pd.DataFrame({"t": net94.index, "net": net94.values, "turnover": turn94.values,
                  "scale": scale94.values}).to_csv(OUT_DIR / "equity_v94.csv", index=False)
    pd.DataFrame({"t": v93["net"].index, "net": v93["net"].values, "turnover": v93["turn"].values,
                  "scale": v93["scale"].values, "model_net": v93["model_net"].values,
                  "carry_net": v93["carry_net"].values}).to_csv(OUT_DIR / "equity_v93.csv", index=False)
    print(json.dumps({"v94_yearly": yearly94, "v93_yearly": yearly93}, indent=2))


if __name__ == "__main__":
    main()
