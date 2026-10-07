"""oc_eventblk analysis: scheduled FOMC/CPI event-bar blackout vs dip-fill y_dep.

Frozen PLAN.md definitions. LIGHT: fills + calendar only, one process.
EVENTBAR(T) = 1 iff the 4h holding bar [T, T+4h) contains a scheduled
FOMC-statement or CPI release instant R (T <= R < T+4h). Calendar known
in advance -> causal at bid time T. Outcome = y_dep via harness5.load
(exactly as oc_idea7 loads it).

  .venv/Scripts/python.exe research/tournament/oc_eventblk/analyze_eventblk.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OC = ROOT / "research/tournament/oc_eventblk"
MAJORS = H5.MAJORS
R2 = H5.R2
ANCHORS = H5.ANCHORS
YEAR = pd.Timedelta(days=365)
BAR = pd.Timedelta(hours=4)
MIN_IN = 5   # PLAN.md
MIN_OUT = 30  # PLAN.md


def eventbar_flags(T: pd.Series, cal: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Instant-in-bar flags (causal: T + calendar only)."""
    Tn = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    R = pd.to_datetime(cal["release_utc"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ser = cal["series"].to_numpy()
    Tn4 = Tn + 4 * 3_600_000_000_000
    out = {}
    for s in ("FOMC", "CPI"):
        m = ser == s
        o = (Tn[:, None] <= R[None, m]) & (R[None, m] < Tn4[:, None])
        out[s] = o.any(axis=1)
    both = out["FOMC"] | out["CPI"]
    return both, out


def grp(y: np.ndarray, mask: np.ndarray) -> dict:
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "mean_bps": None, "win": None, "min_bps": None}
    yy = y[mask]
    return {"n": n, "mean_bps": round(float(yy.mean()) * 1e4, 2),
            "win": round(float((yy > 0).mean()), 4),
            "min_bps": round(float(yy.min()) * 1e4, 2)}


def maxdd(cumsum: np.ndarray) -> float:
    peak = np.maximum.accumulate(cumsum)
    return round(float((peak - cumsum).max()), 6) if len(cumsum) else 0.0


def main() -> None:
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    m = (d["sym"].isin(MAJORS) & d["x1"].isin(R2)).to_numpy()
    d = d[m].reset_index(drop=True)
    assert len(d) == 6876, len(d)  # PLAN counts (no outcomes inspected)
    folds = H5.folds(d)
    assert [int(te.sum()) for _, _, _, te in folds] == [990, 1045, 1330, 989, 1144]
    ymasks = [te for _, _, _, te in folds]

    cal = pd.read_csv(OC / "event_calendar.csv")
    assert (pd.to_datetime(cal["release_utc"], utc=True) < H5.DEV_END).all()
    ev, per = eventbar_flags(d["T"], cal)
    d["EVENTBAR"] = ev
    for s in ("FOMC", "CPI"):
        d[f"EVENTBAR_{s}"] = per[s]

    y = d["y_dep"].to_numpy(dtype=float)

    # blackout sizes -> harness5 equal-exposure renorm per year
    size_new = np.where(ev, 0.0, d["size_dep"].to_numpy())
    res_score = H5.score(d, size_new, name="eventblk")

    years = []
    spreads: list[float | None] = []
    for k, a in enumerate(ANCHORS):
        ym = ymasks[k]
        mi, mo = ym & ev, ym & ~ev
        si, so = grp(y, mi), grp(y, mo)
        spread = (round(float(y[mi].mean() - y[mo].mean()) * 1e4, 2)
                  if mi.sum() >= MIN_IN and mo.sum() >= MIN_OUT else None)
        spreads.append(spread)
        sy = res_score["years"][k]
        # raw (no-renorm) retention, size-weighted
        sd = d["size_dep"].to_numpy()[ym]
        S_full = round(float((sd * y[ym]).sum()), 6)
        S_skip = round(float((sd[~ev[ym]] * y[ym][~ev[ym]]).sum()), 6)
        ret = round(S_skip / S_full, 4) if S_full > 0 else None
        # maxDD of renormed daily-sum cumsum path (same renorm as harness5)
        sn = np.where(ev[ym], 0.0, sd)
        sn = sn * sd.mean() / max(sn.mean(), 1e-12)
        day = d["T"][ym].dt.floor("D").to_numpy()
        dep_path = pd.Series(sd * y[ym]).groupby(day).sum().sort_index().cumsum().to_numpy()
        new_path = pd.Series(sn * y[ym]).groupby(day).sum().sort_index().cumsum().to_numpy()
        desc = {}
        for s in ("FOMC", "CPI"):
            ms = ym & d[f"EVENTBAR_{s}"].to_numpy(bool)
            ns = int(ms.sum())
            desc[s] = {"n": ns,
                       "spread_bps": (round(float(y[ms].mean() - y[mo].mean()) * 1e4, 2)
                                      if ns >= MIN_IN and mo.sum() >= MIN_OUT else None)}
        years.append({"year": str(a.date()), "n": int(ym.sum()),
                      "n_in": int(mi.sum()), "n_out": int(mo.sum()),
                      "inside": si, "outside": so, "spread_bps": spread,
                      "S_dep": sy["S_dep"], "S_new": sy["S_new"], "gain": sy["gain"],
                      "gain_pass": bool(sy["gain"] > 0),
                      "worst_day_dep": sy["worst_day_dep"], "worst_day_new": sy["worst_day_new"],
                      "tail_pass": bool(sy["worst_day_new"] >= sy["worst_day_dep"]),
                      "maxDD_dep": maxdd(dep_path), "maxDD_new": maxdd(new_path),
                      "S_raw_full": S_full, "S_raw_skip": S_skip, "retention_raw": ret,
                      "per_series": desc})

    loyo = []
    for h in range(5):
        trm = np.zeros(len(d), bool)
        for k in range(5):
            if k != h:
                trm |= ymasks[k]
        tri, tro = trm & ev, trm & ~ev
        hi, ho = ymasks[h] & ev, ymasks[h] & ~ev
        if tri.sum() >= MIN_IN and tro.sum() >= MIN_OUT and hi.sum() >= MIN_IN and ho.sum() >= MIN_OUT:
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
    dom, dom_sign = (pos, "+") if pos >= neg else (neg, "-")
    agr = sum(1 for L in loyo if L["sign_agrees"])
    ntail = sum(1 for w in years if w["tail_pass"])
    ngain = sum(1 for w in years if w["gain_pass"])
    promising = bool(dom >= 4 and agr >= 4 and ntail >= 4)

    mi_all = ev & np.isfinite(y)
    mo_all = ~ev & np.isfinite(y)
    out = {
        "meta": {"fills": str(H5.FILLS), "table": str(H5.TABLE),
                 "calendar": "research/tournament/oc_eventblk/event_calendar.csv",
                 "n_majors_r2": int(len(d)),
                 "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
                 "outcome": "y_dep (deployed TP, exact net)",
                 "unit": "means in bps (x1e4); sums native size*y_dep",
                 "flag": "EVENTBAR(T)=1 iff [T,T+4h) contains an FOMC/CPI release instant",
                 "min_n": {"in": MIN_IN, "out": MIN_OUT},
                 "rule": "PROMISING iff spread sign identical >=4/5 AND loyo agree >=4/5 AND tail not-worse >=4/5"},
        "years": years, "loyo": loyo,
        "decision": {"pos_spread_count": f"{pos}/5", "neg_spread_count": f"{neg}/5",
                      "dominant_sign": dom_sign, "dominant_sign_count": f"{dom}/5",
                      "loyo_agree_count": f"{agr}/5",
                      "tail_not_worse_count": f"{ntail}/5",
                      "gain_pos_count": f"{ngain}/5",
                      "promising": promising},
        "overall": {"n_in": int(mi_all.sum()), "n_out": int(mo_all.sum()),
                    "mean_in_bps": round(float(y[mi_all].mean()) * 1e4, 2),
                    "mean_out_bps": round(float(y[mo_all].mean()) * 1e4, 2),
                    "spread_bps": round(float(y[mi_all].mean() - y[mo_all].mean()) * 1e4, 2)},
    }
    (OC / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["decision"], indent=1))
    for w in years:
        print(w["year"], "n_in", w["n_in"], "spread", w["spread_bps"],
              "gain", w["gain"], "tail", w["tail_pass"],
              "maxDD", w["maxDD_dep"], "->", w["maxDD_new"])


if __name__ == "__main__":
    main()
