"""Blind v89 audit reproduction from OPENCODE_V89_AUDIT.md spec.

Reads only raw data under data/raw/*, writes only under v89_audit/.
Does NOT read research/.../v89/* (blind until replication.json is saved).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]  # repo root
OUT_DIR = Path(__file__).resolve().parent
KS = [6, 42, 90, 180, 540]
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ASSET_ID = {s: i for i, s in enumerate(ASSETS)}

BTC_4H = ROOT / "data/raw/ma_ribbon_20260924/klines_4h.parquet"
BTC_1D = ROOT / "data/raw/ma_ribbon_20260924/klines_1d.parquet"
BTC_FUND = ROOT / "data/raw/ma_ribbon_20260924/funding.parquet"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"


def asset_paths(sym):
    if sym == "BTCUSDT":
        return BTC_4H, BTC_1D, BTC_FUND
    return XS_DIR / f"{sym}_4h.parquet", XS_DIR / f"{sym}_1d.parquet", XS_DIR / f"{sym}_funding.parquet"


def funding_means(close_times, fund_times, fund_rates):
    """Mean of last 21 / 90 funding prints with fundingTime <= bar close_time.

    Requires full window (NaN otherwise). Returns means scaled x1e4.
    """
    ft = np.asarray(pd.to_datetime(fund_times, utc=True))
    fr = np.asarray(fund_rates, dtype=float)
    order = np.argsort(ft)
    ft = ft[order]
    fr = fr[order]
    cs = np.concatenate([[0.0], np.cumsum(fr)])
    ct = np.asarray(pd.to_datetime(pd.Series(close_times), utc=True))
    pos = np.searchsorted(ft, ct, side="right") - 1
    m21 = np.full(len(ct), np.nan)
    m90 = np.full(len(ct), np.nan)
    ok21 = pos >= 20
    ok90 = pos >= 89
    # vectorized via cumsum
    p = pos[ok21]
    m21[ok21] = (cs[p + 1] - cs[p - 20]) / 21.0 * 1e4
    p = pos[ok90]
    m90[ok90] = (cs[p + 1] - cs[p - 89]) / 90.0 * 1e4
    return m21, m90


def build_asset(sym):
    p4, p1, pf = asset_paths(sym)
    bars = pd.read_parquet(p4).sort_values("open_time").reset_index(drop=True)
    daily = pd.read_parquet(p1).sort_values("open_time").reset_index(drop=True)
    fund = pd.read_parquet(pf).sort_values("fundingTime").reset_index(drop=True)

    close = bars["close"].astype(float)
    logc = np.log(close)
    r1 = logc.diff()  # 1-bar log return ending at t

    out = pd.DataFrame({"open_time": bars["open_time"], "close_time": bars["close_time"],
                        "open": bars["open"].astype(float), "close": close,
                        "symbol": sym, "asset_id": ASSET_ID[sym]})
    std42 = r1.rolling(42, min_periods=42).std(ddof=1)
    std180 = r1.rolling(180, min_periods=180).std(ddof=1)
    out["std42"] = std42
    out["std180"] = std180
    out["std_ratio"] = std42 / std180
    for k in KS:
        retk = logc - logc.shift(k)
        out[f"ret{k}"] = retk
        out[f"snr{k}"] = retk / (std42 * np.sqrt(k))
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    out["log_close_ema20"] = np.log(close / ema20)
    out["log_close_ema200"] = np.log(close / ema200)

    # Daily SMA features from last CLOSED daily bar (daily close_time <= 4h close_time)
    dclose = daily["close"].astype(float)
    sma50 = dclose.rolling(50, min_periods=50).mean()
    sma200 = dclose.rolling(200, min_periods=200).mean()
    dfeat = pd.DataFrame({"close_time": daily["close_time"],
                          "d_close": dclose, "d_sma50": sma50, "d_sma200": sma200})
    dfeat = dfeat.sort_values("close_time")
    left = out[["close_time"]].sort_values("close_time")
    m = pd.merge_asof(left, dfeat, on="close_time", direction="backward")
    m = m.reindex(out.sort_values("close_time").index).sort_index()
    # align back to out order (out already sorted by open_time == close_time order)
    out = out.sort_values("close_time").reset_index(drop=True)
    m = m.reset_index(drop=True)
    out["d_log_sma50"] = np.log(m["d_close"] / m["d_sma50"])
    out["d_log_sma200"] = np.log(m["d_close"] / m["d_sma200"])
    out["ribbon"] = 0
    out.loc[(m["d_close"] > m["d_sma50"]) & (m["d_sma50"] > m["d_sma200"]), "ribbon"] = 1
    out.loc[(m["d_close"] < m["d_sma50"]) & (m["d_sma50"] < m["d_sma200"]), "ribbon"] = -1
    out.loc[m["d_sma50"].isna() | m["d_sma200"].isna() | m["d_close"].isna(), "ribbon"] = np.nan

    # Funding means known at bar close
    m21, m90 = funding_means(out["close_time"], fund["fundingTime"], fund["fundingRate"])
    out["fund_m21"] = m21
    out["fund_m90"] = m90

    # Log quote-volume z-score over 180 bars
    lv = np.log(bars["quote_volume"].astype(float))
    lmean = lv.rolling(180, min_periods=180).mean()
    lstd = lv.rolling(180, min_periods=180).std(ddof=1)
    out["vol_z180"] = (lv - lmean) / lstd

    # Target y = clip(log(open[t+43]/open[t+1]) / (std42_t*sqrt(42)), -4, 4)
    op = out["open"].astype(float)
    num = np.log(op.shift(-43) / op.shift(-1))
    den = out["std42"] * np.sqrt(42)
    y = num / den
    y = y.clip(-4, 4)
    y[out["std42"].isna() | (out["std42"] == 0)] = np.nan
    out["y"] = y
    return out


FEATURE_COLS = ([f"ret{k}" for k in KS] + [f"snr{k}" for k in KS]
                + ["std42", "std180", "std_ratio", "log_close_ema20", "log_close_ema200",
                   "d_log_sma50", "d_log_sma200", "ribbon", "fund_m21", "fund_m90",
                   "vol_z180", "asset_id",
                   "btc_ret42", "btc_ret180", "btc_ribbon", "btc_snr42"])


def main():
    frames = [build_asset(s) for s in ASSETS]
    btc = frames[0][["open_time", "ret42", "ret180", "ribbon", "snr42"]].rename(
        columns={"ret42": "btc_ret42", "ret180": "btc_ret180",
                 "ribbon": "btc_ribbon", "snr42": "btc_snr42"})
    pooled = []
    for f in frames:
        g = f.merge(btc, on="open_time", how="left")
        pooled.append(g)
    df = pd.concat(pooled, ignore_index=True).sort_values(["open_time", "asset_id"]).reset_index(drop=True)

    A = pd.Timestamp("2025-09-24", tz="UTC")
    cutoff = A - pd.Timedelta(hours=4 * (42 + 60))
    train_mask = (df["open_time"] < cutoff) & (df["open_time"] + pd.Timedelta(hours=4 * 43) < cutoff) & df["y"].notna()
    pred_mask = (df["open_time"] >= A) & (df["open_time"] < A + pd.Timedelta(days=365))
    train = df[train_mask]
    pred = df[pred_mask].copy()

    X_train = train[FEATURE_COLS]
    y_train = train["y"].astype(float)
    model = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400,
                                          min_samples_leaf=300, l2_regularization=1.0,
                                          random_state=0)
    model.fit(X_train, y_train)
    pred["pred"] = model.predict(pred[FEATURE_COLS])
    ev = pred.dropna(subset=["y"])
    rho, _ = spearmanr(ev["pred"], ev["y"])

    result = {
        "anchor": "2025-09-24",
        "cutoff": cutoff.isoformat(),
        "n_train_rows": int(train_mask.sum()),
        "n_pred_rows": int(pred_mask.sum()),
        "n_pred_rows_with_y": int(len(ev)),
        "spearman_pred_vs_y": float(rho),
        "model": {"max_depth": 4, "learning_rate": 0.03, "max_iter": 400,
                  "min_samples_leaf": 300, "l2_regularization": 1.0, "random_state": 0},
        "features": FEATURE_COLS,
        "assumptions": [
            "A=2025-09-24T00:00Z; cutoff=A-408h; train open_time<cutoff and open_time+172h<cutoff and y not NaN; predict [A,A+365d).",
            "rolling std ddof=1, min_periods=full window; EMA pandas ewm adjust=False min_periods=span; SMA min_periods=full.",
            "daily features use daily-bar close vs its SMA50/200 from last daily bar with close_time<=4h close_time.",
            "funding means require full 21/90 prints with fundingTime<=bar close_time, x1e4; vol z uses log(quote_volume) 180-bar mean/std ddof=1.",
            "asset_id BTC=0,ETH=1,SOL=2,BNB=3,XRP=4; BTC cross features joined on open_time; HGB NaN-native (no row drop on NaN features).",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    pred[["open_time", "symbol", "pred", "y"]].to_csv(OUT_DIR / "predictions.csv", index=False)
    print(json.dumps({k: result[k] for k in ["n_train_rows", "n_pred_rows", "n_pred_rows_with_y", "spearman_pred_vs_y"]}, indent=2))


if __name__ == "__main__":
    main()
