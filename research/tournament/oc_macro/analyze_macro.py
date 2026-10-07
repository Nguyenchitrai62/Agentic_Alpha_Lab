"""oc_macro analysis: macro-window overlap vs dip-fill y1.0 (LIGHT: fills + calendar only).

Reads research/tournament/ext/fills_U_ext.parquet and
research/tournament/oc_macro/macro_calendar.csv. No 1m/hourly data.
Writes results.json. Single run per PLAN.md (no iteration on outcomes).

  .venv/Scripts/python.exe research/tournament/oc_macro/analyze_macro.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_macro"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
BAR = pd.Timedelta(hours=4)
MIN_N = 10  # fixed in PLAN.md


def overlap_flags(T: pd.Series, t_fill: pd.Series, cal: pd.DataFrame):
    """SKIP (holding-bar overlap, causal) + per-series + FILL_IN (descriptive)."""
    Tn = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    Fn = pd.to_datetime(t_fill, utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ws = pd.to_datetime(cal["window_start_utc"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    we = pd.to_datetime(cal["window_end_utc"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ser = cal["series"].to_numpy()
    Tn4 = Tn + 4 * 3_600_000_000_000
    # (n_rows, n_win) bool chunks per series to stay LIGHT
    skip = np.zeros(len(Tn), bool)
    per = {}
    for s in ("FOMC", "CPI", "NFP"):
        m = ser == s
        o = (Tn[:, None] < we[None, m]) & (ws[None, m] < Tn4[:, None])
        f = o.any(axis=1)
        per[s] = f
        skip |= f
    fall = (Fn[:, None] >= ws[None, :]) & (Fn[:, None] < we[None, :])
    fill_in = fall.any(axis=1)
    return skip, per, fill_in


def year_stats(y: np.ndarray, mask: np.ndarray):
    n = int(mask.sum())
    yy = y[mask]
    if n == 0:
        return {"n": 0, "mean_bps": None, "win": None, "min_bps": None}
    return {"n": n, "mean_bps": round(float(yy.mean()) * 1e4, 2),
            "win": round(float((yy > 0).mean()), 4),
            "min_bps": round(float(yy.min()) * 1e4, 2)}


def main() -> None:
    f = pd.read_parquet(FILLS)
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d = d[d["T"] < pd.Timestamp("2026-09-24", tz="UTC")].reset_index(drop=True)
    cal = pd.read_csv(OC / "macro_calendar.csv")
    skip, per, fill_in = overlap_flags(d["T"], d["t_fill"], cal)
    d["SKIP"] = skip
    for s in ("FOMC", "CPI", "NFP"):
        d[f"SKIP_{s}"] = per[s]
    d["FILL_IN"] = fill_in

    y = d["y1.0"].to_numpy(dtype=float)
    ymasks = [((d["T"] >= a) & (d["T"] < a + YEAR)).to_numpy() for a in ANCHORS]
    sk = d["SKIP"].to_numpy(bool)

    years = []
    spreads = []
    for k, a in enumerate(ANCHORS):
        m = ymasks[k]
        mi, mo = m & sk, m & ~sk
        si, so = year_stats(y, mi), year_stats(y, mo)
        if mi.sum() >= MIN_N and mo.sum() >= MIN_N:
            spread = round(float(y[mi].mean() - y[mo].mean()) * 1e4, 2)
        else:
            spread = None
        spreads.append(spread)
        # skip simulation: daily sums by T date
        day = d["T"][m].dt.floor("D").to_numpy()
        s_full = pd.Series(y[m]).groupby(day).sum()
        keep = ~sk[m]
        s_skip = pd.Series(y[m][keep]).groupby(day[keep]).sum() if keep.sum() else pd.Series(dtype=float)
        S_full = round(float(y[m].sum()), 6)
        S_skip = round(float(y[m & ~sk].sum()), 6)
        if S_full > 0:
            cut = round((S_full - S_skip) / S_full, 4)
        else:
            cut = None
        wd_full = round(float(s_full.min()), 6) if len(s_full) else None
        wd_skip = round(float(s_skip.min()), 6) if len(s_skip) else None
        tail = bool(wd_skip is not None and wd_full is not None and wd_skip > wd_full)
        useful = bool(tail and cut is not None and 0 <= cut <= 0.05)
        # per-series descriptive spreads
        desc = {}
        for s in ("FOMC", "CPI", "NFP"):
            ms = m & d[f"SKIP_{s}"].to_numpy(bool)
            ns = int(ms.sum())
            if ns >= MIN_N and mo.sum() >= MIN_N:
                desc[s] = {"n": ns, "spread_bps": round(float(y[ms].mean() - y[mo].mean()) * 1e4, 2)}
            else:
                desc[s] = {"n": ns, "spread_bps": None}
        fi = m & fill_in
        years.append({"year": str(a.date()), "n": int(m.sum()),
                      "n_in": int(mi.sum()), "n_out": int(mo.sum()),
                      "inside": si, "outside": so, "spread_bps": spread,
                      "S_full": S_full, "S_skip": S_skip, "cut_frac": cut,
                      "worst_day_full": wd_full, "worst_day_skip": wd_skip,
                      "tail_improves": tail, "useful_skip": useful,
                      "per_series": desc,
                      "n_fill_in": int(fi.sum())})
    # LOYO agreement
    loyo = []
    for h in range(5):
        trm = np.zeros(len(d), bool)
        for k in range(5):
            if k != h:
                trm |= ymasks[k]
        tri, tro = trm & sk, trm & ~sk
        held = ymasks[h]
        hi, ho = held & sk, held & ~sk
        if tri.sum() >= MIN_N and tro.sum() >= MIN_N and hi.sum() >= MIN_N and ho.sum() >= MIN_N:
            pooled = round(float(y[tri].mean() - y[tro].mean()) * 1e4, 2)
            hs = spreads[h]
            agree = bool(hs is not None and pooled != 0 and hs != 0
                         and np.sign(hs) == np.sign(pooled))
        else:
            pooled, agree = None, False
        loyo.append({"heldout": str(ANCHORS[h].date()), "held_spread_bps": spreads[h],
                     "pooled_other4_bps": pooled, "sign_agrees": agree})
    sgn = [1 if (s is not None and s > 0) else (-1 if (s is not None and s < 0) else 0)
           for s in spreads]
    pos, neg = sum(1 for z in sgn if z > 0), sum(1 for z in sgn if z < 0)
    dom = max(pos, neg)
    agr = sum(1 for L in loyo if L["sign_agrees"])
    # overall inside-vs-outside pooled + fill_in descriptive
    mi_all = sk & np.isfinite(y)
    mo_all = ~sk & np.isfinite(y)
    fi_all = fill_in & np.isfinite(y)
    out = {
        "meta": {"fills": str(FILLS), "n_majors_r2": int(len(d)),
                 "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
                 "outcome": "y1.0", "unit": "bps in tables (x1e4)",
                 "window": "[R, R+5h) half-open; SKIP = holding bar [T,T+4h) overlaps",
                 "min_n": MIN_N,
                 "rule": "PROMISING iff sign(spread) identical in >=4/5 years AND agree in >=4/5 LOYO"},
        "years": years, "loyo": loyo,
        "decision": {"pos_spread_count": f"{pos}/5", "neg_spread_count": f"{neg}/5",
                     "dominant_sign_count": f"{dom}/5", "loyo_agree_count": f"{agr}/5",
                     "promising": bool(dom >= 4 and agr >= 4)},
        "overall": {
            "n_in": int(mi_all.sum()), "n_out": int(mo_all.sum()),
            "mean_in_bps": round(float(y[mi_all].mean()) * 1e4, 2),
            "mean_out_bps": round(float(y[mo_all].mean()) * 1e4, 2),
            "spread_bps": round(float(y[mi_all].mean() - y[mo_all].mean()) * 1e4, 2),
            "n_fill_in": int(fi_all.sum()),
            "mean_fill_in_bps": round(float(y[fi_all].mean()) * 1e4, 2) if fi_all.sum() else None},
    }
    (OC / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["decision"], indent=1))
    for w in years:
        print(w["year"], "n_in", w["n_in"], "spread", w["spread_bps"],
              "cut", w["cut_frac"], "tail", w["tail_improves"])


if __name__ == "__main__":
    main()
