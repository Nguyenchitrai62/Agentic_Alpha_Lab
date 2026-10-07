"""oc_premfill analysis: perp-vs-spot dislocation at the fill -> dip-rung outcomes.

Causal rule: a premium 1m bar (open_time m, END = m + 1m) is usable for a fill
at t_fill iff its END <= t_fill, i.e. open_time <= t_fill - 1m. The f-1 bar
(open_time == t_fill - 1m, exact match) is the latest usable bar. Fill-time
features -> bot_only label (not available at the bar open T).

One process, one coin premium file at a time (LIGHT job).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_premfill"
PREM_DIR = ROOT / "data/raw/binance_premium_20260928"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MIN_NS = 60_000_000_000
WIN_7D = 10_080
MIN_WIN = 7_200
FEATURES = ["prem", "prem_chg30", "prem_z7d"]


def load_premium(sym: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-coin (opens_ns sorted int64, closes float64), bars starting at/after
    the 2026-09-24 00:00 UTC cutoff dropped."""
    p = pd.read_parquet(PREM_DIR / f"{sym}_premium_1m.parquet",
                        columns=["open_time", "close"])
    p["open_time"] = pd.to_datetime(p["open_time"], utc=True)
    p = p[p["open_time"] < CUTOFF].sort_values("open_time").reset_index(drop=True)
    opens = p["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    closes = p["close"].to_numpy(float)
    _, u = np.unique(opens, return_index=True)
    mask = np.zeros(len(opens), bool)
    mask[np.sort(u)] = True
    return opens[mask], closes[mask]


def compute_coin_features(tf: np.ndarray, opens: np.ndarray,
                          closes: np.ndarray) -> dict[str, np.ndarray]:
    """tf: fill minutes (ns int64) for one coin. Returns the 3 features."""
    n = len(tf)
    target = tf - MIN_NS  # open_time of the f-1 bar
    pos = np.searchsorted(opens, target)
    # exact-match check (guard the right edge)
    valid = np.zeros(n, bool)
    ok = pos < len(opens)
    valid[ok] = opens[pos[ok]] == target[ok]
    idx = np.where(valid, pos, -1)

    prem = np.full(n, np.nan)
    prem[valid] = closes[idx[valid]]

    chg = np.full(n, np.nan)
    has30 = valid & (idx >= 30)
    has30[has30] = (opens[idx[has30]] - opens[idx[has30] - 30] == 30 * MIN_NS)
    chg[has30] = closes[idx[has30]] - closes[idx[has30] - 30]

    # trailing contiguous run ending at idx (exact 1m steps), up to WIN_7D bars
    gaps = np.diff(opens) != MIN_NS
    gap_idx = np.where(gaps)[0]
    z = np.full(n, np.nan)
    vv = np.where(valid)[0]
    if len(vv):
        ii = idx[vv]
        if len(gap_idx):
            ss = np.searchsorted(gap_idx, ii, side="left")
            gi = np.clip(ss - 1, 0, len(gap_idx) - 1)
            runstart = np.where(ss > 0, gap_idx[gi] + 1, 0)
        else:
            runstart = np.zeros(len(vv), dtype=np.int64)
        for pos, t in enumerate(vv):
            i = int(ii[pos])
            j0 = int(max(runstart[pos], i - (WIN_7D - 1)))
            w = closes[j0:i + 1]
            w = w[np.isfinite(w)]
            if len(w) >= MIN_WIN:
                sd = float(np.std(w, ddof=1))
                if np.isfinite(sd) and sd > 0:
                    z[t] = (closes[i] - float(np.mean(w))) / sd
    return {"prem": prem, "prem_chg30": chg, "prem_z7d": z}


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int, float]:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 30:
        return np.nan, n, np.nan
    r, p = st.spearmanr(x[m], y[m])
    return float(r), n, float(p)


def main() -> None:
    f = pd.read_parquet(FILLS)
    f["t_fill"] = pd.to_datetime(f["t_fill"], utc=True)
    f["TT"] = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d["margin"] = d["y1.5"].to_numpy(float) - d["y1.0"].to_numpy(float)
    for feat in FEATURES:
        d[feat] = np.nan

    cov_info = {}
    for sym in MAJORS:
        m = (d["sym"] == sym).to_numpy()
        opens, closes = load_premium(sym)
        span = (str(pd.to_datetime(opens[0], utc=True, unit="ns")),
                str(pd.to_datetime(opens[-1], utc=True, unit="ns")))
        tf = d.loc[m, "t_fill"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        feats = compute_coin_features(tf, opens, closes)
        for feat in FEATURES:
            d.loc[m, feat] = feats[feat]
        cov_info[sym] = {"bars": int(len(opens)), "span": list(span),
                         "n_fills": int(m.sum()),
                         "n_fminus1": int(np.isfinite(feats["prem"]).sum())}
        del opens, closes  # keep RAM low: one coin at a time

    d[["TT", "t_fill", "sym", "x1", "y1.0", "y1.5",
       "margin"] + FEATURES].to_parquet(OC / "features_premfill.parquet")

    y = d["y1.0"].to_numpy(float)
    mg = d["margin"].to_numpy(float)
    years = [((d["TT"] >= a0) & (d["TT"] < a0 + pd.Timedelta(days=365))).to_numpy()
             for a0 in ANCHORS]

    res: dict = {"meta": {
        "fills": str(FILLS), "n_majors_r2": int(len(d)),
        "T_min": str(d["TT"].min()), "T_max": str(d["TT"].max()),
        "cutoff": "premium bars with open_time >= 2026-09-24 00:00 UTC dropped",
        "label": "bot_only (fill-time features, minute f-1)",
        "outcome_primary": "y1.0", "outcome_secondary": "margin = y1.5 - y1.0 (descriptive)",
        "unit": "bps in tables (x1e4); premium in decimal (1e-4 = 1 bp)",
        "coverage": cov_info,
    }, "features": {}}
    for feat in FEATURES:
        x = d[feat].to_numpy(float)
        fx = np.isfinite(x)
        fr: dict = {"yearly": [], "loyo": []}
        for k, a0 in enumerate(ANCHORS):
            te = years[k]
            rho, n, p = spearman(x[te], y[te])
            rhom, nm, pm = spearman(x[te], mg[te])
            cov = float(np.isfinite(x[te]).mean())
            tr = (d["TT"] < a0).to_numpy() & fx
            cut: dict = {}
            terc: dict = {}
            if int(tr.sum()) >= 100:
                q33, q67 = float(np.quantile(x[tr], 1 / 3)), float(np.quantile(x[tr], 2 / 3))
                cut = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
                lo = te & fx & (x <= q33)
                hi = te & fx & (x > q67)
                mid = te & fx & (x > q33) & (x <= q67)
                for nm_, mm in (("lo", lo), ("mid", mid), ("hi", hi)):
                    yy = y[mm]
                    terc[nm_] = {"mean_bps": round(float(np.mean(yy)) * 1e4, 2) if len(yy) else None,
                                 "n": int(len(yy))}
            fr["yearly"].append({"year": str(a0.date()), "n": int(te.sum()),
                                 "n_valid": n,
                                 "rho_y10": None if np.isnan(rho) else round(rho, 4),
                                 "p_y10": None if np.isnan(p) else round(float(p), 4),
                                 "rho_margin": None if np.isnan(rhom) else round(rhom, 4),
                                 "p_margin": None if np.isnan(pm) else round(float(pm), 4),
                                 "n_margin": nm,
                                 "coverage": round(cov, 4), "cutoffs": cut, "terciles": terc})
        for h in range(5):
            tr = np.zeros(len(d), bool)
            for k in range(5):
                if k != h:
                    tr |= years[k]
            te = years[h]
            trm = tr & np.isfinite(x)
            spread = None
            info: dict = {}
            if int(trm.sum()) >= 100:
                q33, q67 = float(np.quantile(x[trm], 1 / 3)), float(np.quantile(x[trm], 2 / 3))
                lo = te & (x <= q33)
                hi = te & (x > q67)
                if int(lo.sum()) >= 30 and int(hi.sum()) >= 30:
                    spread = float(np.mean(y[hi]) - np.mean(y[lo])) * 1e4
                info = {"q33": q33, "q67": q67, "n_train": int(trm.sum()),
                        "n_lo": int(lo.sum()), "n_hi": int(hi.sum())}
            fr["loyo"].append({"heldout": str(ANCHORS[h].date()),
                               "spread_bps": None if spread is None else round(spread, 2),
                               **info})
        rhos = [w["rho_y10"] for w in fr["yearly"]]
        signs_ic = [np.sign(r) for r in rhos if r is not None]
        spr = [w["spread_bps"] for w in fr["loyo"]]
        signs_sp = [np.sign(s) for s in spr if s is not None]
        n_ic = max(int((np.array(signs_ic) > 0).sum()), int((np.array(signs_ic) < 0).sum())) if signs_ic else 0
        n_sp = max(int((np.array(signs_sp) > 0).sum()), int((np.array(signs_sp) < 0).sum())) if signs_sp else 0
        fr["decision"] = {"ic_sign_count": f"{n_ic}/5", "spread_sign_count": f"{n_sp}/5",
                          "promising": bool(n_ic >= 4 and n_sp >= 4)}
        splits = {}
        for nm_, mm in (("BTC", d["sym"] == "BTCUSDT"), ("ETH", d["sym"] == "ETHUSDT"),
                        ("SOL", d["sym"] == "SOLUSDT"), ("BNB", d["sym"] == "BNBUSDT"),
                        ("XRP", d["sym"] == "XRPUSDT")):
            r = []
            for k in range(5):
                te = years[k] & mm.to_numpy()
                rho, n, _ = spearman(x[te], y[te])
                r.append(None if np.isnan(rho) else round(rho, 4))
            splits[nm_] = r
        fr["splits_ic_y10"] = splits
        res["features"][feat] = fr
    fc = d[FEATURES].corr(method="spearman")
    res["feature_crosscorr_spearman"] = {a: {b: round(float(fc.loc[a, b]), 4) for b in FEATURES} for a in FEATURES}
    (OC / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({ft: res["features"][ft]["decision"] for ft in FEATURES}, indent=1))


if __name__ == "__main__":
    main()
