"""oc_filltime analysis: per-year Spearman IC + terciles + LOYO + fixed LATE window.

Reads research/tournament/oc_filltime/features_filltime.parquet only (no 1m,
no outcome re-definition). Writes results.json.

  .venv/Scripts/python.exe research/tournament/oc_filltime/analyze_filltime.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_filltime"

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
FEATURES = ["f", "age24", "n_weak"]
LATE_CUT = 209  # f >= 209 = last 30 fillable minutes of the 16..238 window


def spearman_p(rho: float, n: int) -> float:
    if not np.isfinite(rho) or n < 4:
        return float("nan")
    t = rho * np.sqrt((n - 2) / max(1e-12, 1 - rho ** 2))
    return float(2 * st.t.sf(abs(t), n - 2))


def main() -> None:
    df = pd.read_parquet(OC / "features_filltime.parquet")
    df["TT"] = pd.to_datetime(df["TT"], utc=True)
    y = df["y1.0"].to_numpy(dtype=float)
    year_mask = [((df["TT"] >= a) & (df["TT"] < a + YEAR)).to_numpy() for a in ANCHORS]

    out: dict = {"meta": {
        "fills": str(ROOT / "research/tournament/ext/fills_U_ext.parquet"),
        "n_majors_r2": int(len(df)),
        "TT_min": str(df["TT"].min()), "TT_max": str(df["TT"].max()),
        "outcome": "y1.0", "unit": "bps in tables (x1e4)",
        "late_cut": LATE_CUT,
        "rule": ("PROMISING iff sign(rho)/sign(spread) identical in >=4/5 "
                 "years AND sign(spread_h) identical in >=4/5 LOYO folds")},
        "features": {}, "late_window": {}}

    for feat in FEATURES:
        x = df[feat].to_numpy(dtype=float)
        yearly, rhos = [], []
        for k, a in enumerate(ANCHORS):
            m = year_mask[k] & np.isfinite(x) & np.isfinite(y)
            n = int(m.sum())
            cov = float(m.sum() / max(1, int(year_mask[k].sum())))
            if n >= 30:
                rho = float(st.spearmanr(x[m], y[m]).statistic)
            else:
                rho = float("nan")
            rhos.append(rho)
            # terciles with cut-offs from strictly previous data
            tr = (df["TT"] < a).to_numpy() & np.isfinite(x)
            row: dict = {"year": str(a.date()), "n": int(year_mask[k].sum()),
                         "n_valid": n, "rho": rho,
                         "p": spearman_p(rho, n), "coverage": round(cov, 4)}
            if tr.sum() >= 100:
                q33, q67 = (float(v) for v in np.quantile(x[tr], [1 / 3, 2 / 3]))
                row["cutoffs"] = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
                terc = {}
                for name, sel in (("lo", x <= q33), ("mid", None), ("hi", x > q67)):
                    if name == "mid":
                        mm = year_mask[k] & np.isfinite(x) & (x > q33) & (x <= q67) & np.isfinite(y)
                    else:
                        mm = year_mask[k] & np.isfinite(x) & sel & np.isfinite(y)
                    terc[name] = {"mean_bps": round(float(1e4 * y[mm].mean()), 2) if mm.sum() else None,
                                  "n": int(mm.sum())}
                row["terciles"] = terc
            else:
                row["cutoffs"] = {"q33": None, "q67": None, "n_train": int(tr.sum())}
                row["terciles"] = None
            yearly.append(row)
        # LOYO spreads
        loyo = []
        for h in range(5):
            trm = np.zeros(len(df), bool)
            for k in range(5):
                if k != h:
                    trm |= year_mask[k]
            trm &= np.isfinite(x)
            held = year_mask[h] & np.isfinite(x) & np.isfinite(y)
            if trm.sum() >= 100:
                q33, q67 = (float(v) for v in np.quantile(x[trm], [1 / 3, 2 / 3]))
                lo = held & (x <= q33)
                hi = held & (x > q67)
                if lo.sum() >= 30 and hi.sum() >= 30:
                    spread = float(1e4 * (y[hi].mean() - y[lo].mean()))
                else:
                    spread = float("nan")
                loyo.append({"heldout": str(ANCHORS[h].date()), "spread_bps": spread,
                             "q33": q33, "q67": q67, "n_train": int(trm.sum()),
                             "n_lo": int(lo.sum()), "n_hi": int(hi.sum())})
            else:
                loyo.append({"heldout": str(ANCHORS[h].date()), "spread_bps": float("nan"),
                             "q33": None, "q67": None, "n_train": int(trm.sum()),
                             "n_lo": 0, "n_hi": 0})
        s_ic = [1 if (np.isfinite(r) and r > 0) else (-1 if (np.isfinite(r) and r < 0) else 0) for r in rhos]
        s_sp = [1 if (np.isfinite(L["spread_bps"]) and L["spread_bps"] > 0)
                else (-1 if (np.isfinite(L["spread_bps"]) and L["spread_bps"] < 0) else 0) for L in loyo]
        cnt = lambda s, v: sum(1 for z in s if z == v)
        ic_n = max(cnt(s_ic, 1), cnt(s_ic, -1))
        sp_n = max(cnt(s_sp, 1), cnt(s_sp, -1))
        match = (np.sign(rhos[0]) == np.sign([L["spread_bps"] for L in loyo][0])) if (
            np.isfinite(rhos[0]) and np.isfinite(loyo[0]["spread_bps"])) else False
        out["features"][feat] = {
            "yearly": yearly, "loyo": loyo,
            "decision": {"ic_sign_count": f"{ic_n}/5", "spread_sign_count": f"{sp_n}/5",
                         "spread_matches_ic_sign": bool(match),
                         "promising": bool(ic_n >= 4 and sp_n >= 4)}}

    # fixed LATE window: spread = mean_late - mean_early per year
    f = df["f"].to_numpy(dtype=float)
    late_rows, spreads = [], []
    for k, a in enumerate(ANCHORS):
        m = year_mask[k] & np.isfinite(f) & np.isfinite(y)
        la, ea = m & (f >= LATE_CUT), m & (f < LATE_CUT)
        ml = float(1e4 * y[la].mean()) if la.sum() else None
        me = float(1e4 * y[ea].mean()) if ea.sum() else None
        sp = (ml - me) if (ml is not None and me is not None) else None
        spreads.append(sp)
        late_rows.append({"year": str(a.date()), "n": int(m.sum()),
                          "n_late": int(la.sum()), "n_early": int(ea.sum()),
                          "mean_late_bps": ml,
                          "mean_early_bps": me,
                          "spread_bps": sp,
                          "win_late": round(float((y[la] > 0).mean()), 4) if la.sum() else None,
                          "win_early": round(float((y[ea] > 0).mean()), 4) if ea.sum() else None})
    # LOYO analogue for the fixed window: held-out spread vs pooled-other-4 spread
    loyo_late = []
    for h in range(5):
        trm = np.zeros(len(df), bool)
        for k in range(5):
            if k != h:
                trm |= year_mask[k]
        trm &= np.isfinite(f) & np.isfinite(y)
        la, ea = trm & (f >= LATE_CUT), trm & (f < LATE_CUT)
        pooled = float(1e4 * (y[la].mean() - y[ea].mean())) if (la.sum() and ea.sum()) else float("nan")
        hs = spreads[h]
        agree = (np.isfinite(pooled) and hs is not None and np.isfinite(hs)
                 and np.sign(hs) == np.sign(pooled) and pooled != 0 and hs != 0)
        loyo_late.append({"heldout": str(ANCHORS[h].date()), "held_spread_bps": hs,
                          "pooled_other4_bps": round(pooled, 2) if np.isfinite(pooled) else None,
                          "sign_agrees": bool(agree)})
    sgn = [1 if (s is not None and s > 0) else (-1 if (s is not None and s < 0) else 0) for s in spreads]
    neg = sum(1 for z in sgn if z < 0)
    agr = sum(1 for L in loyo_late if L["sign_agrees"])
    out["late_window"] = {"cut": f"f >= {LATE_CUT}", "yearly": late_rows, "loyo": loyo_late,
                          "decision": {"neg_spread_count": f"{neg}/5",
                                       "loyo_agree_count": f"{agr}/5",
                                       "promising_late_loses": bool(neg >= 4 and agr >= 4)}}
    (OC / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({f_: out["features"][f_]["decision"] for f_ in FEATURES}, indent=1))
    print(json.dumps(out["late_window"]["decision"], indent=1))


if __name__ == "__main__":
    main()
