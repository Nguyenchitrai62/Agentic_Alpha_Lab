"""Blind v92 audit reproduction from OPENCODE_V92_AUDIT.md spec.

Reads only raw data under data/raw/*, writes only under v92_audit/.
Does NOT read research/.../v92/* (blind until replication_5asset.json is saved).

Leader NaN conventions (from v89 audit): ribbon=0 when SMA unavailable;
funding rolling(21,min_periods=3)/rolling(90,min_periods=9).
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
ASSET_ID = {s: i for i, s in enumerate(SYMS)}
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H = 42
EMBARGO_BARS = H + 10 * PD  # 102 bars = 408h, as in v89
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"


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
    # Prefix Binance SPOT bars for open_time before first USD-M bar (funding NaN there).
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():  # leader edit: SOL has no spot prefix
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
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()  # ddof=1, min_periods=42
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


def build():
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


FEATS = None


def train_predict(panel, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400,
                                      min_samples_leaf=300, l2_regularization=1.0,
                                      random_state=0)
    m.fit(tr[FEATS], tr["y"])
    te["pred"] = m.predict(te[FEATS])
    return te, len(tr)


def compute_weights(oos):
    """Step (3): risk-parity-ish daily weights from predictions."""
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    # normalise to sum 1 when any > 0, then partial-exposure factor count/5
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def backtest(panel, oos, W):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index).sort_index()
    for s in SYMS:
        if s not in o.columns:
            o[s] = np.nan
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1  # open_t/open_{t-1} - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (0.20 / vol).clip(upper=2.0).fillna(1.0)
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


def main():
    global FEATS
    panel = build()
    FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    anchors_rec = []
    oos_parts = []
    for anchor in ANCHORS:
        te, ntr = train_predict(panel, anchor)
        ev = te.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        anchors_rec.append(dict(anchor=anchor, train_rows=int(ntr),
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)),
                                ic=round(rho, 4)))
        oos_parts.append(te)
        print(anchor, "train", ntr, "pred", len(te), "with_y", len(ev), "IC", round(rho, 4), flush=True)
    oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W = compute_weights(oos)
    net, turn, scale, book, vol = backtest(panel, oos, W)
    A_last = pd.Timestamp("2025-09-24", tz="UTC")
    hidden_mask = (net.index >= A_last) & (net.index < A_last + pd.Timedelta(days=365))
    hidden_net, hidden_turn = net[hidden_mask], turn[hidden_mask]
    hidden_stats = stats(hidden_net, hidden_turn)
    full_stats = stats(net, turn)
    result = {
        "anchors": anchors_rec,
        "hidden_year_2025_2026_normal": hidden_stats,
        "five_year_continuous_oos_normal": full_stats,
        "model": {"max_depth": 4, "learning_rate": 0.03, "max_iter": 400,
                  "min_samples_leaf": 300, "l2_regularization": 1.0, "random_state": 0},
        "features": FEATS,
        "assets": list(SYMS),
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar",
        },
        "execution": {
            "fee_per_unit_turnover": 0.0002,
            "long_funding_per_4h_bar": 0.00005,
            "weight": "s=min(max(pred,0)/0.5,1) zeroed when rib==-1; raw=s/(vol42*sqrt(2190)); normalise to 1 then *min(1,count/5); every 6th bar ffill",
            "vol_target": "book_t=sum W_{t-2}*(open_t/open_{t-1}-1); vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "realisation": "W_t*scale_t earns open_{t+2}/open_{t+1}-1",
        },
        "assumptions": [
            "anchors 2021-09-24..2025-09-24; cutoff=A-408h; train t<cutoff and t+172h<cutoff and y not NaN; predict [A,A+365d); 5 forward sets concatenated.",
            "leader NaN: ribbon 0 when SMA unavailable (np.where); funding rolling21/min3 and rolling90/min9 x1e4 via merge_asof backward.",
            "spot 4h/1d prefix for open_time < first USD-M bar per asset; funding from USD-M only (NaN in spot region).",
            "HGB NaN-native, no row drop on NaN features; asset ids BTC=0,ETH=1,BNB=2,XRP=3.",
        ],
    }
    with open(OUT_DIR / "replication_5asset.json", "w") as f:
        json.dump(result, f, indent=2)
    oos[["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_5asset.csv", index=False)
    pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values, "scale": scale.values}).to_csv(
        OUT_DIR / "equity_5asset.csv", index=False)
    print(json.dumps({"anchors": anchors_rec, "hidden": hidden_stats, "five_year": full_stats}, indent=2))


if __name__ == "__main__":
    main()
