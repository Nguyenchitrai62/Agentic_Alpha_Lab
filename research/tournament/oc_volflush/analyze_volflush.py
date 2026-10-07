"""oc_volflush evaluation: per-year IC + terciles (previous-data cut-offs) + LOYO.

Reads research/tournament/oc_volflush/features_volflush.parquet, writes
results.json. All cut-offs are fit strictly on data before each anchor
(yearly) or on the other four years (LOYO). See PLAN.md.
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "research" / "tournament" / "oc_volflush"
FEAT = ["vol_ratio", "sell_share"]
ANCHORS = [pd.Timestamp(f"{a}-09-24", tz="UTC") for a in (2021, 2022, 2023, 2024, 2025)]
DAY = pd.Timedelta(days=365)


def spearman(x: np.ndarray, y: np.ndarray):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return np.nan, int(m.sum())
    r = stats.spearmanr(x[m], y[m]).statistic
    return float(r), int(m.sum())


def pearson(x: np.ndarray, y: np.ndarray):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return np.nan
    x0, y0 = x[m], y[m]
    if x0.std() == 0 or y0.std() == 0:
        return np.nan
    return float(np.corrcoef(x0, y0)[0, 1])


def tercile_split(v: pd.Series, q33: float, q67: float) -> pd.Series:
    g = pd.Series(index=v.index, dtype="object")
    g[v <= q33] = "Lo"
    g[(v > q33) & (v <= q67)] = "Mid"
    g[v > q67] = "Hi"
    return g


def main() -> None:
    f = pd.read_parquet(D / "features_volflush.parquet")
    f["year"] = -1
    for k, a in enumerate(ANCHORS):
        f.loc[(f["T"] >= a) & (f["T"] < a + DAY), "year"] = k
    in5 = f.loc[f["year"] >= 0].reset_index(drop=True)
    y = in5["y1.0"].to_numpy(dtype=float)
    # Training pools use the FULL frame (incl. pre-window rows with T < A_k):
    # strictly previous data only, as pre-registered.
    fT = f["T"].to_numpy()
    res = {"n_total": int(len(f)), "n_in5y": int(len(in5)),
           "anchors": [str(a.date()) for a in ANCHORS],
           "features": {}}
    for feat in FEAT:
        v = in5[feat].to_numpy(dtype=float)
        years = []
        for k, a in enumerate(ANCHORS):
            my = in5["year"].to_numpy() == k
            rho, nvp = spearman(v[my], y[my])
            r_p = pearson(v[my], y[my])
            cov = float(np.isfinite(v[my]).mean())
            fv = f[feat].to_numpy(dtype=float)
            train = (fT < a) & np.isfinite(fv)
            tq = {}
            if int(train.sum()) >= 100:
                qq = np.nanquantile(fv[train], [1 / 3, 2 / 3])
                q33, q67 = float(qq[0]), float(qq[1])
                g = tercile_split(in5.loc[my, feat], q33, q67)
                tm = {}
                sub = in5.loc[my].reset_index(drop=True)
                gg = g.to_numpy()
                for lab in ("Lo", "Mid", "Hi"):
                    yy = sub.loc[gg == lab, "y1.0"].to_numpy(dtype=float)
                    tm[lab] = {"mean_y10": float(yy.mean()) if len(yy) else float("nan"),
                               "n": int(len(yy))}
                tq = {"q33": q33, "q67": q67, "n_train": int(train.sum()), "terciles": tm}
            else:
                tq = {"q33": float("nan"), "q67": float("nan"),
                      "n_train": int(train.sum()), "terciles": {}}
            years.append({"year": str(a.date()), "n": int(my.sum()),
                          "n_valid": nvp, "coverage": cov,
                          "spearman": rho, "pearson": r_p, "terciles": tq})
        # LOYO spreads
        loyo = []
        for h in range(5):
            tr = (in5["year"].to_numpy() != h) & np.isfinite(v)
            ho = in5["year"].to_numpy() == h
            if int(tr.sum()) < 100:
                loyo.append({"held_out": str(ANCHORS[h].date()), "spread": float("nan"),
                             "n_hi": 0, "n_lo": 0})
                continue
            q33 = float(np.nanquantile(v[tr], 1 / 3))
            q67 = float(np.nanquantile(v[tr], 2 / 3))
            g = tercile_split(in5.loc[ho, feat], q33, q67).to_numpy()
            suby = y[ho]
            yhi = suby[g == "Hi"]
            ylo = suby[g == "Lo"]
            if len(yhi) >= 30 and len(ylo) >= 30:
                sp = float(yhi.mean() - ylo.mean())
            else:
                sp = float("nan")
            loyo.append({"held_out": str(ANCHORS[h].date()), "spread": sp,
                         "n_hi": int(len(yhi)), "n_lo": int(len(ylo)),
                         "q33": q33, "q67": q67})
        # per-coin IC splits (descriptive)
        coins = {}
        for c in sorted(in5["sym"].unique()):
            mc = in5["sym"].to_numpy() == c
            rho, nvp = spearman(v[mc], y[mc])
            coins[c] = {"spearman pooled5y": rho, "n_valid": nvp}
        # decision
        rhos = np.array([w["spearman"] for w in years])
        sps = np.array([w["spread"] for w in loyo])
        s_rho = np.sign(rhos)
        s_sp = np.sign(sps)
        ok_rho = (~np.isnan(rhos)) & (s_rho != 0)
        ok_sp = (~np.isnan(sps)) & (s_sp != 0)
        # majority non-zero sign among valid, count matches
        def majority_count(s, ok):
            if ok.sum() == 0:
                return 0, 0.0
            maj = np.sign(s[ok].sum())
            if maj == 0:
                return 0, 0.0
            return int(((s == maj) & ok).sum()), float(maj)
        c_rho, maj_rho = majority_count(s_rho, ok_rho)
        c_sp, maj_sp = majority_count(s_sp, ok_sp)
        promising = (c_rho >= 4) and (c_sp >= 4)
        res["features"][feat] = {
            "per_year": years, "loyo": loyo, "per_coin": coins,
            "sign_rho_count": c_rho, "sign_rho_majority": maj_rho,
            "sign_spread_count": c_sp, "sign_spread_majority": maj_sp,
            "verdict": "PROMISING" if promising else "NOT PROMISING"}
    # sell_share range audit (unclipped by design)
    ss = f["sell_share"].to_numpy(dtype=float)
    ss = ss[np.isfinite(ss)]
    res["sell_share_range"] = {"min": float(ss.min()) if len(ss) else float("nan"),
                               "max": float(ss.max()) if len(ss) else float("nan")}
    vr = f["vol_ratio"].to_numpy(dtype=float)
    vr = vr[np.isfinite(vr)]
    res["vol_ratio_quantiles"] = {q: float(np.nanquantile(vr, float(q)))
                                  for q in ("0.01", "0.1", "0.5", "0.9", "0.99")} if len(vr) else {}
    with open(D / "results.json", "w") as fh:
        json.dump(res, fh, indent=1)
    for feat in FEAT:
        d = res["features"][feat]
        print(feat, [round(w["spearman"], 4) if w["spearman"] == w["spearman"] else None
                     for w in d["per_year"]],
              [round(w["spread"], 6) if w["spread"] == w["spread"] else None
               for w in d["loyo"]], d["verdict"], flush=True)


if __name__ == "__main__":
    main()
