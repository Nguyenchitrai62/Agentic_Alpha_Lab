"""EXT COPY of research/tournament/context/build_market_features.py (only input/output paths changed).

Input : research/tournament/ext/hourly_ext.parquet (35 coins, hour-start t, OHLC, < 2026-09-24; only rows < 2026-09-24 are used).
Output: research/tournament/ext/market_features_ext.parquet, aligned with harness5.load() rows (columns T, sym + features).

CAUSALITY: the hourly bar starting at t ends at t + 1h. A feature at bar open T uses ONLY hourly rows with t <= T - 1h (all windows are
backward-looking and are sampled at the row t = T - 1h; the hour starting at T is never read). `causality_check` truncates the hourly data to
t < T for 20 random rows (each at its own T) plus one global random cut and asserts identical features.

  .venv/Scripts/python.exe research/tournament/ext/build_market_features_ext.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness5 as H  # noqa: E402

HOURLY = HERE / "hourly_ext.parquet"
OUT = HERE / "market_features_ext.parquet"
MINC = 8            # minimum coins for a cross-sectional statistic
ONE_H = pd.Timedelta(hours=1)
MKT_COLS = ["m_r4", "m_r24", "m_r72", "m_dd7", "m_tr7", "m_vts", "m_vlvl", "x_disp4", "x_disp24", "x_br2", "x_dn24", "x_corr72", "btc_rel24"]
COIN_COLS = ["c_beta7", "c_idio24", "c_idio4", "c_corr72"]
FEATS = MKT_COLS + COIN_COLS


def load_hourly():
    h = pd.read_parquet(HOURLY)
    return h[h.t < H.DEV_END].reset_index(drop=True)


def _xs_share(mask, valid):
    n = valid.sum(1)
    return (mask & valid).sum(1).where(n >= MINC) / n.where(n >= MINC)


def build(hourly: pd.DataFrame, req: pd.DataFrame) -> pd.DataFrame:
    """req: DataFrame with columns T (bar open, UTC) and sym. Returns features (same index as req) using hourly rows t <= T - 1h only."""
    LC = np.log(hourly.pivot(index="t", columns="sym", values="close"))
    LH = np.log(hourly.pivot(index="t", columns="sym", values="high"))
    grid = pd.date_range(LC.index.min(), LC.index.max(), freq="1h")
    LC, LH = LC.reindex(grid), LH.reindex(grid)
    syms = list(LC.columns)
    R = LC.diff()                                        # hourly log return of hour t (needs hour t-1 present)
    cnt = R.notna().sum(1)
    M = R.mean(1).where(cnt >= MINC)                     # equal-weight market index hourly return
    alt = R.drop(columns=["BTCUSDT"])
    MA = alt.mean(1).where(alt.notna().sum(1) >= MINC)   # ex-BTC alt index
    I = M.fillna(0.0).cumsum()
    v24, v168, v720 = (M.rolling(w, min_periods=int(0.85 * w)).std() for w in (24, 168, 720))
    s = {h: M.rolling(h, min_periods=int(0.85 * h)).sum() for h in (4, 24, 72, 168)}
    mk = pd.DataFrame(index=grid)
    mk["m_r4"] = s[4] / (v168 * 2.0)
    mk["m_r24"] = s[24] / (v168 * np.sqrt(24))
    mk["m_r72"] = s[72] / (v168 * np.sqrt(72))
    mk["m_dd7"] = (I - I.rolling(168, min_periods=144).max()) / (v168 * np.sqrt(24))
    mk["m_tr7"] = s[168] / (v168 * np.sqrt(168))
    mk["m_vts"] = np.log(v24 / v168)
    mk["m_vlvl"] = np.log(v168 / v720)
    sig = R.rolling(168, min_periods=120).std()          # coin hourly sigma
    R4, R24 = LC - LC.shift(4), LC - LC.shift(24)
    ok4, ok24 = R4.notna() & sig.notna(), R24.notna() & sig.notna()
    mk["x_disp4"] = R4.where(ok4).std(1).where(ok4.sum(1) >= MINC) / (sig.where(ok4) * 2.0).median(1)
    mk["x_disp24"] = R24.where(ok24).std(1).where(ok24.sum(1) >= MINC) / (sig.where(ok24) * np.sqrt(24)).median(1)
    H24 = LH.rolling(24, min_periods=20).max()
    dist = (LC - H24) / (sig * 2.0)
    mk["x_br2"] = _xs_share(dist < -2.0, dist.notna())
    mk["x_dn24"] = _xs_share(R24 < 0, R24.notna())
    mk["btc_rel24"] = (R24["BTCUSDT"] - MA.rolling(24, min_periods=20).sum()) / (v168 * np.sqrt(24))

    # sample at the last completed hour e = T - 1h
    Te = pd.DatetimeIndex(req["T"]) - ONE_H
    out = pd.DataFrame(index=req.index)
    mk_at = mk.reindex(Te)
    for c in mk.columns:
        out[c] = mk_at[c].to_numpy()

    # average pairwise correlation of hourly returns over the last 72 h (coins with a full window), per unique T
    pos = pd.Series(np.arange(len(grid)), index=grid)
    Rv = R.to_numpy()
    cache = {}
    for t in pd.unique(Te):
        p = pos.get(t)
        val = np.nan
        if p is not None and p >= 71:
            W = Rv[p - 71: p + 1]
            W = W[:, np.isfinite(W).all(0)]
            W = W[:, W.std(0) > 0]
            if W.shape[1] >= MINC:
                C = np.corrcoef(W.T)
                n = C.shape[0]
                val = (C.sum() - n) / (n * (n - 1))
        cache[t] = val
    out["x_corr72"] = [cache[t] for t in Te]

    # coin vs market
    vM168 = M.rolling(168, min_periods=120).var()
    coin = {}
    for sy in syms:
        r = R[sy]
        cov = r.rolling(168, min_periods=120).cov(M)
        beta = cov / vM168
        rv = r.rolling(168, min_periods=120).var()
        res_sd = np.sqrt((rv - beta ** 2 * vM168).clip(lower=1e-12))
        coin[sy] = pd.DataFrame({
            "c_beta7": beta,
            "c_idio24": (R24[sy] - beta * s[24]) / (res_sd * np.sqrt(24)),
            "c_idio4": (R4[sy] - beta * s[4]) / (res_sd * 2.0),
            "c_corr72": r.rolling(72, min_periods=60).corr(M),
        })
    cc = {c: np.full(len(req), np.nan) for c in COIN_COLS}
    syv = req["sym"].to_numpy()
    for sy in np.unique(syv):
        m = syv == sy
        if sy not in coin:
            continue
        at = coin[sy].reindex(Te[m])
        for c in COIN_COLS:
            cc[c][m] = at[c].to_numpy()
    for c in COIN_COLS:
        out[c] = cc[c]
    return out[FEATS].replace([np.inf, -np.inf], np.nan)


def causality_check(hourly, req, full, n=20, seed=7):
    rng = np.random.default_rng(seed)
    worst = 0.0
    picks = rng.choice(len(req), n, replace=False)
    for i in picks:
        T = req["T"].iloc[i]
        tr = hourly[hourly.t < T]                        # the hour starting at T (and everything after) removed
        f = build(tr, req.iloc[[i]])
        a, b = f.to_numpy(float)[0], full.iloc[i].to_numpy(float)
        same = (np.isnan(a) == np.isnan(b)).all()
        diff = np.nanmax(np.abs(a - b)) if np.isfinite(a).any() else 0.0
        assert same and diff < 1e-9, (i, T, a, b)
        worst = max(worst, diff)
    # one global cut: every row with T <= cut must be unchanged
    cut = req["T"].iloc[rng.integers(len(req))]
    sub = req[req["T"] <= cut].sample(min(500, int((req["T"] <= cut).sum())), random_state=seed)
    f = build(hourly[hourly.t < cut], sub)
    a, b = f.to_numpy(float), full.loc[sub.index].to_numpy(float)
    assert (np.isnan(a) == np.isnan(b)).all() and np.nanmax(np.abs(a - b)) < 1e-9
    worst = max(worst, float(np.nanmax(np.abs(a - b))))
    print(f"causality check passed: {n} per-row truncations + global cut at {cut} ({len(sub)} rows); max |diff| {worst:.2e}", flush=True)
    return worst


def main():
    hourly = load_hourly()
    d = H.load()
    req = d[["T", "sym"]].copy()
    full = build(hourly, req)
    worst = causality_check(hourly, req, full)
    res = pd.concat([req, full], axis=1)
    res.to_parquet(OUT)
    print("saved", res.shape, "coverage:", full.notna().mean().round(3).to_dict(), "max_diff", worst)
    print(full.describe().T.round(3))


if __name__ == "__main__":
    main()
