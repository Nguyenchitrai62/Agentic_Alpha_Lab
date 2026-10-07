"""oc_optctx analysis: causal options-skew / put-call-flow / Coinbase-premium
features -> join to majors R2 rungs -> per-year IC + terciles + LOYO + DVOL-residual.

Strict as-of rule: a bar is usable at T iff its bar END is strictly before T
(implemented as end <= T - 1s via searchsorted side='left' on T-1s).
`bar` in the Deribit options files is the 4h bar START (fetch script floors
trade timestamps to 4h), so each row covers [bar, bar+4h).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_optctx"
OPT = ROOT / "data/raw/deribit_opt_20260926"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
DVOL_FEATS = ROOT / "research/tournament/oc_dvol/features_dvol.parquet"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
NS = 1_000_000_000
FEATURES = ["skew", "skew_z90", "putbuy_share6", "putbuy_share6_z90",
            "cbprem_last", "cbprem_mean24", "cbprem_z90"]


def load_options(cur: str) -> pd.DataFrame:
    """4h options grid for one coin, bars with START < CUTOFF. Ends = bar + 4h."""
    g = pd.read_parquet(OPT / f"{cur}_options_4h.parquet").copy()
    g["bar"] = pd.to_datetime(g["bar"], utc=True)
    g = g[g["bar"] < CUTOFF].sort_values("bar").reset_index(drop=True)
    g["end"] = g["bar"] + pd.Timedelta(hours=4)
    g["skew"] = g["iv_otm_put"] - g["iv_otm_call"]
    g["sum_put6"] = g["put_buy"].rolling(6, min_periods=6).sum()
    g["sum_call6"] = g["call_buy"].rolling(6, min_periods=6).sum()
    denom = g["sum_put6"] + g["sum_call6"]
    g["share6"] = np.where(denom > 0, g["sum_put6"] / denom, np.nan)
    for base, col in (("skew", "skew_z90"), ("share6", "putbuy_share6_z90")):
        r = g[base].rolling(540, min_periods=432)
        g[col] = (g[base] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    steps = g["bar"].diff().dropna()
    print(f"{cur} options: bars={len(g)} span={g['bar'].iloc[0]}..{g['bar'].iloc[-1]} "
          f"max_step={steps.max()} ivNaN_put={g['iv_otm_put'].isna().mean():.4f} "
          f"ivNaN_call={g['iv_otm_call'].isna().mean():.4f}", flush=True)
    return g


def load_premium() -> pd.DataFrame:
    """Hourly Coinbase/Binance premium grid, bar STARTs < CUTOFF. Ends = start + 1h."""
    cb = pd.read_parquet(CB).copy()
    cb["t"] = pd.to_datetime(cb["open_time"], utc=True)
    cb = cb[cb["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "cb"})
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "bin"})
    g = pd.merge(cb, h, on="t", how="inner").sort_values("t").reset_index(drop=True)
    g["prem"] = g["cb"] / g["bin"] - 1
    g["mean24"] = g["prem"].rolling(24, min_periods=20).mean()
    r = g["mean24"].rolling(2160, min_periods=1728)
    g["cbprem_z90"] = (g["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    g["end"] = g["t"] + pd.Timedelta(hours=1)
    steps = g["t"].diff().dropna()
    print(f"premium: rows={len(g)} span={g['t'].iloc[0]}..{g['t'].iloc[-1]} "
          f"max_step={steps.max()} median_prem_bps={g['prem'].median() * 1e4:.2f}", flush=True)
    return g


def asof_idx(ends_ns: np.ndarray, Tns: np.ndarray) -> np.ndarray:
    """Index of last bar with end < T (i.e. end <= T - 1s). -1 if none."""
    return np.searchsorted(ends_ns, Tns - NS, side="left") - 1


def lookup(grid: pd.DataFrame, Tns: np.ndarray, col: str) -> np.ndarray:
    ends = grid["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = grid[col].to_numpy(float)
    ii = asof_idx(ends, Tns)
    out = np.full(len(Tns), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
    return out


def compute_features(df: pd.DataFrame, opt_btc: pd.DataFrame,
                      opt_eth: pd.DataFrame, prem: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    Tns = df["TT"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    df["skew"] = lookup(opt_btc, Tns, "skew")
    df["skew_z90"] = lookup(opt_btc, Tns, "skew_z90")
    df["putbuy_share6"] = lookup(opt_btc, Tns, "share6")
    df["putbuy_share6_z90"] = lookup(opt_btc, Tns, "putbuy_share6_z90")
    df["eth_skew"] = lookup(opt_eth, Tns, "skew")
    df["eth_skew_z90"] = lookup(opt_eth, Tns, "skew_z90")
    df["eth_putbuy_share6"] = lookup(opt_eth, Tns, "share6")
    df["eth_putbuy_share6_z90"] = lookup(opt_eth, Tns, "putbuy_share6_z90")
    df["cbprem_last"] = lookup(prem, Tns, "prem")
    df["cbprem_mean24"] = lookup(prem, Tns, "mean24")
    df["cbprem_z90"] = lookup(prem, Tns, "cbprem_z90")
    return df


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int, float]:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 30:
        return np.nan, n, np.nan
    r, p = st.spearmanr(x[m], y[m])
    return float(r), n, float(p)


def residualize(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """OLS residual of x on z (pairwise-complete); NaN if <30 pairs or var(z)==0."""
    m = np.isfinite(x) & np.isfinite(z)
    if int(m.sum()) < 30 or float(np.var(z[m])) == 0:
        return np.full(len(x), np.nan)
    b = float(np.cov(x[m], z[m], ddof=1)[0, 1] / np.var(z[m], ddof=1))
    a = float(np.mean(x[m]) - b * np.mean(z[m]))
    out = np.full(len(x), np.nan)
    out[m] = x[m] - (a + b * z[m])
    return out


def tercile_split(x_te: np.ndarray, q33: float, q67: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fx = np.isfinite(x_te)
    return fx & (x_te <= q33), fx & (x_te > q33) & (x_te <= q67), fx & (x_te > q67)


def eval_feature(x: np.ndarray, y: np.ndarray, years: list[np.ndarray],
                 prev_pool: np.ndarray, TT: np.ndarray) -> dict:
    """Raw battery: per-year Spearman + prev-data terciles, LOYO spreads."""
    fr: dict = {"yearly": [], "loyo": []}
    for k, a0 in enumerate(ANCHORS):
        te = years[k]
        rho, n, p = spearman(x[te], y[te])
        cov = float(np.isfinite(x[te]).mean())
        tr = prev_pool & (TT < a0) & np.isfinite(x)
        cut: dict = {}
        terc: dict = {}
        if int(tr.sum()) >= 100:
            q33, q67 = float(np.quantile(x[tr], 1 / 3)), float(np.quantile(x[tr], 2 / 3))
            cut = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
            lo_f, mid_f, hi_f = tercile_split(x, q33, q67)
            for nm, mm in (("lo", lo_f), ("mid", mid_f), ("hi", hi_f)):
                mm = te & mm
                yy = y[mm]
                terc[nm] = {"mean_bps": round(float(np.mean(yy)) * 1e4, 2) if len(yy) else None,
                            "n": int(len(yy))}
        fr["yearly"].append({"year": str(a0.date()), "n": int(te.sum()),
                             "n_valid": n, "rho": None if np.isnan(rho) else round(rho, 4),
                             "p": None if np.isnan(p) else round(float(p), 4),
                             "coverage": round(cov, 4), "cutoffs": cut, "terciles": terc})
    for hh in range(5):
        tr = np.zeros(len(x), bool)
        for k in range(5):
            if k != hh:
                tr |= years[k]
        te = years[hh]
        trm = tr & np.isfinite(x)
        spread = None
        info: dict = {}
        if int(trm.sum()) >= 100:
            q33, q67 = float(np.quantile(x[trm], 1 / 3)), float(np.quantile(x[trm], 2 / 3))
            lo_f, _, hi_f = tercile_split(x, q33, q67)
            lo, hi = te & lo_f, te & hi_f
            if int(lo.sum()) >= 30 and int(hi.sum()) >= 30:
                spread = float(np.mean(y[hi]) - np.mean(y[lo])) * 1e4
            info = {"q33": q33, "q67": q67, "n_train": int(trm.sum()),
                    "n_lo": int(lo.sum()), "n_hi": int(hi.sum())}
        fr["loyo"].append({"heldout": str(ANCHORS[hh].date()),
                           "spread_bps": None if spread is None else round(spread, 2), **info})
    return fr


def sign_count(vals: list) -> tuple[int, int]:
    s = [np.sign(v) for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not s:
        return 0, 0
    return max(int((np.array(s) > 0).sum()), int((np.array(s) < 0).sum())), len(vals)


def main() -> None:
    opt_btc = load_options("BTC")
    opt_eth = load_options("ETH")
    prem = load_premium()

    f = pd.read_parquet(FILLS)
    f["TT"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d = compute_features(d, opt_btc, opt_eth, prem)

    dz = pd.read_parquet(DVOL_FEATS, columns=["TT", "sym", "x1", "dvol_z90"])
    dz["TT"] = pd.to_datetime(dz["TT"], utc=True)
    n0 = len(d)
    d = pd.merge(d, dz, on=["TT", "sym", "x1"], how="left", validate="one_to_one")
    assert len(d) == n0, "dvol_z90 merge must match every rung key"
    # dvol_z90 is NaN before the DVOL warm-up (~2021-06-30), i.e. outside the 5
    # anchor years; residual tests are pairwise-complete per year.
    in_years = np.zeros(len(d), bool)
    for a0 in ANCHORS:
        in_years |= ((d["TT"] >= a0) & (d["TT"] < a0 + pd.Timedelta(days=365))).to_numpy()
    assert d.loc[in_years, "dvol_z90"].notna().all(), "dvol_z90 must cover all anchor years"
    print(f"dvol NaN rows (all pre-2021-09-24): {int(d['dvol_z90'].isna().sum())}", flush=True)

    keep = ["TT", "sym", "x1", "y1.0", "dvol_z90"] + FEATURES + \
        ["eth_skew", "eth_skew_z90", "eth_putbuy_share6", "eth_putbuy_share6_z90"]
    d[keep].to_parquet(OC / "features_optctx.parquet")

    y = d["y1.0"].to_numpy(float)
    z = d["dvol_z90"].to_numpy(float)
    TT = d["TT"].to_numpy()
    years = [((d["TT"] >= a0) & (d["TT"] < a0 + pd.Timedelta(days=365))).to_numpy()
             for a0 in ANCHORS]
    prev_pool = np.ones(len(d), bool)  # training pool = all rows with T < anchor

    eth_mask = (d["sym"] == "ETHUSDT").to_numpy()
    eth_map = {"skew": "eth_skew", "skew_z90": "eth_skew_z90",
               "putbuy_share6": "eth_putbuy_share6", "putbuy_share6_z90": "eth_putbuy_share6_z90"}

    res: dict = {"meta": {
        "fills": str(FILLS), "n_majors_r2": int(len(d)),
        "T_min": str(d["TT"].min()), "T_max": str(d["TT"].max()),
        "opt_btc_span": [str(opt_btc["bar"].iloc[0]), str(opt_btc["bar"].iloc[-1])],
        "opt_eth_span": [str(opt_eth["bar"].iloc[0]), str(opt_eth["bar"].iloc[-1])],
        "premium_span": [str(prem["t"].iloc[0]), str(prem["t"].iloc[-1])],
        "outcome": "y1.0", "unit": "bps in tables (x1e4)",
        "dvol_source": str(DVOL_FEATS),
    }, "features": {}, "eth_only": {}}

    for feat in FEATURES:
        x = d[feat].to_numpy(float)
        fr = eval_feature(x, y, years, prev_pool, TT)
        # residual battery: within-year OLS residual on dvol_z90
        r = np.full(len(d), np.nan)
        for k in range(5):
            te = years[k]
            r[te] = residualize(x[te], z[te])
        rr = eval_feature(r, y, years, prev_pool, TT)
        fr["resid_yearly"] = rr["yearly"]
        fr["resid_loyo"] = rr["loyo"]
        n_ic, _ = sign_count([w["rho"] for w in fr["yearly"]])
        n_sp, _ = sign_count([w["spread_bps"] for w in fr["loyo"]])
        n_ri, _ = sign_count([w["rho"] for w in rr["yearly"]])
        n_rs, _ = sign_count([w["spread_bps"] for w in rr["loyo"]])
        fr["decision"] = {"ic_sign_count": f"{n_ic}/5", "spread_sign_count": f"{n_sp}/5",
                          "resid_ic_sign_count": f"{n_ri}/5",
                          "resid_spread_sign_count": f"{n_rs}/5 (descriptive)",
                          "promising": bool(n_ic >= 4 and n_sp >= 4 and n_ri >= 4)}
        res["features"][feat] = fr

    # SECONDARY: ETH-options features on ETH rungs (+ BTC-feature reference)
    ey = y[eth_mask]
    ez = z[eth_mask]
    estudy = [years[k][eth_mask] for k in range(5)]
    eTT = TT[eth_mask]
    eprev = np.ones(int(eth_mask.sum()), bool)
    for feat in FEATURES:
        col = eth_map.get(feat, feat)
        if feat.startswith("cbprem"):
            xx = d[feat].to_numpy(float)[eth_mask]  # premium is market-wide, same column
        else:
            xx = d[col].to_numpy(float)[eth_mask]
        er = eval_feature(xx, ey, estudy, eprev, eTT)
        r = np.full(int(eth_mask.sum()), np.nan)
        for k in range(5):
            te = estudy[k]
            r[te] = residualize(xx[te], ez[te])
        rr = eval_feature(r, ey, estudy, eprev, eTT)
        n_ic, _ = sign_count([w["rho"] for w in er["yearly"]])
        res["eth_only"][feat if feat.startswith("cbprem") else col] = {
            "yearly": er["yearly"], "loyo": er["loyo"],
            "resid_yearly": rr["yearly"], "resid_loyo": rr["loyo"],
            "ic_sign_count": f"{n_ic}/5",
            "n_eth": int(eth_mask.sum())}

    fc = d[FEATURES].corr(method="spearman")
    res["feature_crosscorr_spearman"] = {a: {b: round(float(fc.loc[a, b]), 4) for b in FEATURES}
                                        for a in FEATURES}
    (OC / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({f_: {"dec": res["features"][f_]["decision"],
                           "rho": [w["rho"] for w in res["features"][f_]["yearly"]],
                           "spr": [w["spread_bps"] for w in res["features"][f_]["loyo"]],
                           "rrho": [w["rho"] for w in res["features"][f_]["resid_yearly"]]}
                      for f_ in FEATURES}, indent=1))


if __name__ == "__main__":
    main()
