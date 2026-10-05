"""crashrisk: hourly panel of market-state features at every whole hour T + forward 24h crash labels of the 5-majors index (dev-only).

Features at T use ONLY hourly bars with start t <= T - 1h (ported from research/tournament/context/build_market_features.py, market-wide
columns, plus 4 columns on the 5-majors index). Labels use the closes of the bar starting T - 1h (reference) and the 24 bars starting
T .. T + 23h. Nothing at or after 2025-09-24 is read. See PLAN.md for exact definitions.

  .venv/Scripts/python.exe research/tournament/crashrisk/build_panel.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
HOURLY = HERE.parent / "data/hourly.parquet"
OUT = HERE / "panel.parquet"
CUT = pd.Timestamp("2025-09-24", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
MINC = 8
ONE_H = pd.Timedelta(hours=1)
MKT_COLS = ["m_r4", "m_r24", "m_r72", "m_dd7", "m_tr7", "m_vts", "m_vlvl", "x_disp4", "x_disp24", "x_br2", "x_dn24", "x_corr72", "btc_rel24"]
J_COLS = ["j_r24", "j_dd7", "j_vts", "j_vlvl"]
FEATS = MKT_COLS + J_COLS
K_SIG = 2.5


def load_hourly():
    h = pd.read_parquet(HOURLY, filters=[("t", "<", CUT)])
    h = h[h.t < CUT].reset_index(drop=True)
    assert h.t.max() < CUT
    return h


def _xs_share(mask, valid):
    n = valid.sum(1)
    return (mask & valid).sum(1).where(n >= MINC) / n.where(n >= MINC)


def _jindex(R):
    J = R[MAJORS]
    return J.mean(1).where(J.notna().sum(1) >= 4)


def features(hourly: pd.DataFrame, Ts: pd.DatetimeIndex) -> pd.DataFrame:
    """Features at each T in Ts from hourly rows t <= T - 1h (all rolling windows end at row T - 1h)."""
    LC = np.log(hourly.pivot(index="t", columns="sym", values="close"))
    LH = np.log(hourly.pivot(index="t", columns="sym", values="high"))
    grid = pd.date_range(LC.index.min(), LC.index.max(), freq="1h")
    LC, LH = LC.reindex(grid), LH.reindex(grid)
    R = LC.diff()
    cnt = R.notna().sum(1)
    M = R.mean(1).where(cnt >= MINC)
    alt = R.drop(columns=["BTCUSDT"])
    MA = alt.mean(1).where(alt.notna().sum(1) >= MINC)
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
    sig = R.rolling(168, min_periods=120).std()
    R4, R24 = LC - LC.shift(4), LC - LC.shift(24)
    ok4, ok24 = R4.notna() & sig.notna(), R24.notna() & sig.notna()
    mk["x_disp4"] = R4.where(ok4).std(1).where(ok4.sum(1) >= MINC) / (sig.where(ok4) * 2.0).median(1)
    mk["x_disp24"] = R24.where(ok24).std(1).where(ok24.sum(1) >= MINC) / (sig.where(ok24) * np.sqrt(24)).median(1)
    H24 = LH.rolling(24, min_periods=20).max()
    dist = (LC - H24) / (sig * 2.0)
    mk["x_br2"] = _xs_share(dist < -2.0, dist.notna())
    mk["x_dn24"] = _xs_share(R24 < 0, R24.notna())
    mk["btc_rel24"] = (R24["BTCUSDT"] - MA.rolling(24, min_periods=20).sum()) / (v168 * np.sqrt(24))
    # 5-majors index J
    J = _jindex(R)
    IJ = J.fillna(0.0).cumsum()
    j24, j168, j720 = (J.rolling(w, min_periods=int(0.85 * w)).std() for w in (24, 168, 720))
    mk["j_r24"] = J.rolling(24, min_periods=20).sum() / (j168 * np.sqrt(24))
    mk["j_dd7"] = (IJ - IJ.rolling(168, min_periods=144).max()) / (j168 * np.sqrt(24))
    mk["j_vts"] = np.log(j24 / j168)
    mk["j_vlvl"] = np.log(j168 / j720)

    Te = pd.DatetimeIndex(Ts) - ONE_H
    out = mk.reindex(Te)
    out.index = pd.DatetimeIndex(Ts)
    pos = pd.Series(np.arange(len(grid)), index=grid)
    Rv = R.to_numpy()
    vals = np.full(len(Te), np.nan)
    for i, t in enumerate(Te):
        p = pos.get(t)
        if p is not None and p >= 71:
            W = Rv[p - 71: p + 1]
            W = W[:, np.isfinite(W).all(0)]
            W = W[:, W.std(0) > 0]
            if W.shape[1] >= MINC:
                C = np.corrcoef(W.T)
                n = C.shape[0]
                vals[i] = (C.sum() - n) / (n * (n - 1))
    out["x_corr72"] = vals
    return out[FEATS].replace([np.inf, -np.inf], np.nan)


def labels(hourly: pd.DataFrame, Ts: pd.DatetimeIndex) -> pd.DataFrame:
    """crash24, mdd24, sigma24 at each T: sigma from J returns of bars [T-168h, T-1h]; path from bars T .. T+23h vs close of bar T-1h."""
    hm = hourly[hourly.sym.isin(MAJORS)]
    grid = pd.date_range(hm.t.min(), hm.t.max(), freq="1h")
    LC = np.log(hm.pivot(index="t", columns="sym", values="close")).reindex(grid)[MAJORS]
    LL = np.log(hm.pivot(index="t", columns="sym", values="low")).reindex(grid)[MAJORS]
    J = _jindex(LC.diff())
    sd = J.rolling(168, min_periods=144).std() * np.sqrt(24)        # at row t: bars t-167..t
    pos = pd.Series(np.arange(len(grid)), index=grid)
    lc, ll, sdv = LC.to_numpy(), LL.to_numpy(), sd.to_numpy()
    n = len(Ts)
    crash, mdd, sig, minl = (np.full(n, np.nan) for _ in range(4))
    for i, T in enumerate(pd.DatetimeIndex(Ts)):
        p = pos.get(T - ONE_H)
        if p is None or p + 24 >= len(grid):
            continue
        s24 = sdv[p]
        if not np.isfinite(s24) or s24 <= 0:
            continue
        ref = lc[p]
        C, L = lc[p + 1: p + 25] - ref, ll[p + 1: p + 25] - ref
        ok = np.isfinite(ref) & np.isfinite(C).all(0) & np.isfinite(L).all(0)
        if ok.sum() < 4:
            continue
        c, l = C[:, ok].mean(1), L[:, ok].mean(1)
        peak = np.maximum.accumulate(np.concatenate([[0.0], c[:-1]]))
        sig[i], minl[i] = s24, l.min()
        crash[i] = float(l.min() <= -K_SIG * s24)
        mdd[i] = float(np.max(peak - l)) / s24
    return pd.DataFrame({"crash24": crash, "mdd24": mdd, "sigma24": sig, "minlow": minl}, index=pd.DatetimeIndex(Ts))


def causality_check(hourly, Ts, full, n=20, seed=11):
    rng = np.random.default_rng(seed)
    worst = 0.0
    valid = np.where(full.notna().sum(1).to_numpy() > 10)[0]
    for i in rng.choice(valid, n, replace=False):
        T = Ts[i]
        f = features(hourly[hourly.t < T], pd.DatetimeIndex([T]))
        a, b = f.to_numpy(float)[0], full.iloc[i].to_numpy(float)
        assert (np.isnan(a) == np.isnan(b)).all(), (T, a, b)
        d = float(np.nanmax(np.abs(a - b))) if np.isfinite(a).any() else 0.0
        assert d < 1e-9, (T, d)
        worst = max(worst, d)
    cut = Ts[rng.choice(valid)]
    sub = pd.DatetimeIndex(sorted(rng.choice(Ts[Ts <= cut], 500, replace=False)))
    f = features(hourly[hourly.t < cut], sub)
    a, b = f.to_numpy(float), full.loc[sub].to_numpy(float)
    assert (np.isnan(a) == np.isnan(b)).all() and np.nanmax(np.abs(a - b)) < 1e-9
    worst = max(worst, float(np.nanmax(np.abs(a - b))))
    print(f"feature causality OK: {n} truncations at t < T + global cut {cut} (500 T); max|diff| {worst:.1e}", flush=True)


def label_check(hourly, Ts, lab, n=20, seed=12):
    """Labels at T must depend only on bars t <= T + 23h and must CHANGE nothing when later bars are removed."""
    rng = np.random.default_rng(seed)
    idx = np.where(lab.crash24.notna().to_numpy())[0]
    for i in rng.choice(idx, n, replace=False):
        T = Ts[i]
        l2 = labels(hourly[(hourly.t <= T + pd.Timedelta(hours=23)) & (hourly.t >= T - pd.Timedelta(hours=200))], pd.DatetimeIndex([T]))
        a, b = l2.to_numpy(float)[0], lab.iloc[i].to_numpy(float)
        assert np.allclose(a, b, equal_nan=True), (T, a, b)
        l3 = labels(hourly[hourly.t <= T + pd.Timedelta(hours=22)], pd.DatetimeIndex([T]))
        assert np.isnan(l3.crash24.iloc[0])                       # one bar short -> no label (window is exactly 24 bars)
    print(f"label window OK: {n} random T recomputed from bars [T-200h, T+23h] only", flush=True)


def main():
    hourly = load_hourly()
    Ts = pd.date_range(pd.Timestamp("2020-08-01", tz="UTC"), hourly.t.max() + ONE_H, freq="1h")
    Ts = Ts[Ts <= CUT]
    feat = features(hourly, Ts)
    causality_check(hourly, Ts, feat)
    lab = labels(hourly, Ts)
    label_check(hourly, Ts, lab)
    panel = pd.concat([feat, lab], axis=1)
    panel.index.name = "T"
    panel.reset_index().to_parquet(OUT)
    ok = panel.crash24.notna()
    print("saved", panel.shape, "labelled", int(ok.sum()), "range", panel.index[ok].min(), panel.index[ok].max())
    print("crash24 base rate overall", round(panel.crash24.mean(), 4))
    yr = pd.Series(panel.index.year, index=panel.index)
    print(panel.groupby(yr)[["crash24", "mdd24"]].agg(["mean", "count"]).round(4))
    print(feat.notna().mean().round(3).to_dict())


if __name__ == "__main__":
    main()
