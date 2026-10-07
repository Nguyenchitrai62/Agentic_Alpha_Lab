"""oc_corrbudget: rolling 30d majors hourly-return correlation as dip budget scaler.

Frozen PLAN.md definitions. LIGHT: hourly only, one process, < 1 GB.
Causality: bar END = t+1h strictly before the labelled time.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "research" / "tournament" / "ext"
OUT = ROOT / "research" / "tournament" / "oc_corrbudget"
FILLS = EXT / "fills_U_ext.parquet"
HOURLY = EXT / "hourly_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")
WIN_D = 30
MIN_OVERLAP = 600
MIN_PAIRS = 8
MIN_TRAIN = 100
MIN_BUCKET_DAYS = 10


def daily_corr(hm: pd.DataFrame) -> pd.DataFrame:
    """c(D) per calendar day D: mean pairwise Pearson over hourly log returns
    with bar END in [D-30d, D). Strictly before D 00:00 by construction."""
    piv = hm.pivot(index="t", columns="sym", values="close").sort_index()
    piv = piv[[c for c in MAJORS if c in piv.columns]]
    ret = np.log(piv / piv.shift(1))
    days = pd.date_range("2020-10-15", "2026-09-23", tz="UTC", freq="D")
    pairs = [(MAJORS[i], MAJORS[j]) for i in range(5) for j in range(i + 1, 5)]
    rows = []
    ridx = ret.index
    for D in days:
        lo = D - pd.Timedelta(days=WIN_D) - pd.Timedelta(hours=1)
        hi = D - pd.Timedelta(hours=1)
        w = ret[(ridx >= lo) & (ridx < hi)]
        corrs = []
        for a, b in pairs:
            if a not in w.columns or b not in w.columns:
                corrs.append(np.nan)
                continue
            x = w[a].to_numpy()
            y = w[b].to_numpy()
            m = np.isfinite(x) & np.isfinite(y)
            if int(m.sum()) < MIN_OVERLAP:
                corrs.append(np.nan)
                continue
            xa = x[m] - x[m].mean()
            yb = y[m] - y[m].mean()
            den = np.sqrt((xa @ xa) * (yb @ yb))
            corrs.append(float((xa @ yb) / den) if den > 0 else np.nan)
        corrs = np.array(corrs, float)
        ok = np.isfinite(corrs)
        c = float(corrs[ok].mean()) if int(ok.sum()) >= MIN_PAIRS else np.nan
        rows.append({"D": D, "c": c, "n_pairs": int(ok.sum()),
                     "n_hours": int(len(w))})
    return pd.DataFrame(rows)


def assign_buckets(cvals: pd.Series, q33: float, q67: float) -> pd.Series:
    out = pd.Series(index=cvals.index, dtype=object)
    out[cvals <= q33] = "lo"
    out[(cvals > q33) & (cvals <= q67)] = "mid"
    out[cvals > q67] = "hi"
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"].isin(MAJORS) & (h["t"] < DEV_END)].copy()
    corr = daily_corr(h)

    f = pd.read_parquet(FILLS)
    f["T"] = f["t_fill"] - pd.to_timedelta(f["f"], unit="min")
    f = f[f["T"] < DEV_END].copy()
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy()
    d["day"] = d["T"].dt.floor("D")
    daily = d.groupby("day")["y1.0"].sum().rename("s").reset_index()
    daily["D"] = daily["day"]
    daily = daily.merge(corr, on="D", how="left")
    daily["w"] = np.where(np.isfinite(daily["c"].to_numpy())
                          & (daily["c"].to_numpy() > -0.9),
                          1.0 / (1.0 + daily["c"].to_numpy()), 1.0)
    daily["s_scaled"] = daily["s"] * daily["w"]

    years = []
    for a0 in ANCHORS:
        a1 = a0 + pd.Timedelta(days=365)
        yd = daily[(daily["D"] >= a0) & (daily["D"] < a1)].copy()
        yd = yd[np.isfinite(yd["c"].to_numpy())].copy()
        n_days = int(len(yd))
        n_fills = int(((d["T"] >= a0) & (d["T"] < a1)).sum())
        S_base = float(yd["s"].sum()) if n_days else float("nan")
        S_scaled = float(yd["s_scaled"].sum()) if n_days else float("nan")
        W_base = float(yd["s"].min()) if n_days else float("nan")
        W_scaled = float(yd["s_scaled"].min()) if n_days else float("nan")
        worst_date = str(yd.loc[yd["s"].idxmin(), "D"].date()) if n_days else None
        worst_scaled_date = str(yd.loc[yd["s_scaled"].idxmin(), "D"].date()) if n_days else None
        retention = (S_scaled / S_base) if (n_days and S_base > 0) else float("nan")
        scaler_pass = bool(np.isfinite(retention) and W_scaled > W_base
                           and retention >= 0.90)
        rho = float(yd["c"].corr(yd["s"], method="spearman")) if n_days >= 3 else float("nan")

        train = daily[(daily["D"] < a0) & np.isfinite(daily["c"].to_numpy())]
        terc = {"q33": None, "q67": None, "n_train": int(len(train)), "buckets": {},
                "e1": None}
        if len(train) >= MIN_TRAIN:
            q33, q67 = float(train["c"].quantile(1 / 3)), float(train["c"].quantile(2 / 3))
            terc["q33"], terc["q67"] = q33, q67
            yd["bucket"] = assign_buckets(yd["c"], q33, q67).values
            for b in ("lo", "mid", "hi"):
                sub = yd[yd["bucket"] == b]
                terc["buckets"][b] = {
                    "n_days": int(len(sub)),
                    "mean_bps": float(sub["s"].mean() * 1e4) if len(sub) else float("nan"),
                    "worst_bps": float(sub["s"].min() * 1e4) if len(sub) else float("nan"),
                }
            lo_n = terc["buckets"]["lo"]["n_days"]
            hi_n = terc["buckets"]["hi"]["n_days"]
            if lo_n >= MIN_BUCKET_DAYS and hi_n >= MIN_BUCKET_DAYS:
                terc["e1"] = bool(terc["buckets"]["hi"]["worst_bps"]
                                  < terc["buckets"]["lo"]["worst_bps"])
        years.append({
            "anchor": str(a0.date()), "n_fills": n_fills, "n_days": n_days,
            "S_base": S_base, "S_scaled": S_scaled,
            "S_base_bps": S_base * 1e4 if np.isfinite(S_base) else float("nan"),
            "S_scaled_bps": S_scaled * 1e4 if np.isfinite(S_scaled) else float("nan"),
            "retention": retention,
            "W_base_bps": W_base * 1e4 if np.isfinite(W_base) else float("nan"),
            "W_scaled_bps": W_scaled * 1e4 if np.isfinite(W_scaled) else float("nan"),
            "worst_date": worst_date, "worst_scaled_date": worst_scaled_date,
            "spearman_c_vs_s": rho, "scaler_pass": scaler_pass, "terc": terc,
        })

    loyo = []
    for i, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        held = daily[(daily["D"] >= a0) & (daily["D"] < a1)
                     & np.isfinite(daily["c"].to_numpy())].copy()
        tr = daily[np.isfinite(daily["c"].to_numpy())].copy()
        # restrict training to anchor-year fill-days of the other 4 years
        keep = np.zeros(len(tr), bool)
        for j, b0 in enumerate(ANCHORS):
            if j == i:
                continue
            b1 = b0 + pd.Timedelta(days=365)
            keep |= ((tr["D"] >= b0) & (tr["D"] < b1)).to_numpy()
        tr = tr[keep]
        rec = {"heldout": str(a0.date()), "n_train": int(len(tr)),
               "q33": None, "q67": None, "buckets": {}, "e1": None}
        if len(tr) >= MIN_TRAIN and len(held):
            q33, q67 = float(tr["c"].quantile(1 / 3)), float(tr["c"].quantile(2 / 3))
            rec["q33"], rec["q67"] = q33, q67
            held["bucket"] = assign_buckets(held["c"], q33, q67).values
            for b in ("lo", "mid", "hi"):
                sub = held[held["bucket"] == b]
                rec["buckets"][b] = {
                    "n_days": int(len(sub)),
                    "worst_bps": float(sub["s"].min() * 1e4) if len(sub) else float("nan"),
                }
            if (rec["buckets"]["lo"]["n_days"] >= MIN_BUCKET_DAYS
                    and rec["buckets"]["hi"]["n_days"] >= MIN_BUCKET_DAYS):
                rec["e1"] = bool(rec["buckets"]["hi"]["worst_bps"]
                                 < rec["buckets"]["lo"]["worst_bps"])
        loyo.append(rec)

    e1_seq = sum(1 for y in years if y["terc"]["e1"] is True)
    e1_loyo = sum(1 for r in loyo if r["e1"] is True)
    n_scale = sum(1 for y in years if y["scaler_pass"])
    promising = bool(e1_seq >= 4 and e1_loyo >= 4 and n_scale >= 4)
    res = {
        "meta": {
            "fills": str(FILLS), "hourly": str(HOURLY),
            "universe": "majors x R2(2.5,3,3.5,4,5)", "outcome": "y1.0",
            "corr": "30d mean pairwise Pearson of majors hourly log returns, "
                    "bar END in [D-30d, D), >=600 overlap/pair, >=8/10 pairs",
            "daily_rows": int(len(daily)),
            "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
            "c_span": [str(corr['D'].min()), str(corr['D'].max())],
            "unit": "bps = 1e-4 per unit rung notional",
        },
        "years": years,
        "loyo": loyo,
        "decision": {
            "e1_sequential": f"{e1_seq}/5",
            "e1_loyo": f"{e1_loyo}/5",
            "scaler_pass": f"{n_scale}/5",
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        t = y["terc"]
        print(y["anchor"], "fills", y["n_fills"], "days", y["n_days"],
              "S_bps", round(y["S_base_bps"], 1), "->", round(y["S_scaled_bps"], 1),
              "ret", round(y["retention"], 3) if np.isfinite(y["retention"]) else None,
              "W_bps", round(y["W_base_bps"], 1), "->", round(y["W_scaled_bps"], 1),
              "e1", t["e1"], "scale_pass", y["scaler_pass"])


if __name__ == "__main__":
    main()
