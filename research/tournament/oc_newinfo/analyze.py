"""Outcome analysis for oc_newinfo (run AFTER PLAN.md fixed; single execution).

Labels from Binance hourly (research/tournament/ext/hourly_ext.parquet):
- N1: per (coin, D): y1d = ln(O[D+2]/O[D+1]) / s30[D], y7d = ln(O[D+8]/O[D+1]) / s30[D],
  O[d] = 00:00 UTC hourly open, s30 = trailing-30d std of daily log returns ending D.
- N2: per weekend (Friday in window): y1d/y7d from Monday 00:00 UTC open, / s30 ending Sunday.
- N1-monthly: monthly pooled mean wiki_z90 vs dip-sleeve edge (oc_regime/monthly_main.csv).
Windows: anchors 2021..2025-09-24, each [A, A+365d). Spearman IC per year (pooled), LOYO sign test,
fixed decision rule from PLAN.md. Writes results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from features_cme import SYMS, load_cme_daily, weekend_gaps
from features_wiki import COINS, compute_features, load_views

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "newinfo_20261005"
HERE = Path(__file__).resolve().parent
EXT = ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet"
MAJORS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT"}
INV = {v: k for k, v in MAJORS.items()}
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC").tz_localize(None) for y in (2021, 2022, 2023, 2024, 2025)]
WINDOW = pd.Timedelta(days=365)


def daily_opens(hourly: pd.DataFrame) -> pd.DataFrame:
    h = hourly[hourly["sym"].isin(set(MAJORS.values()))].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True).dt.tz_localize(None)
    h = h.sort_values("t")
    recs = {}
    for sym, coin in INV.items():
        s = h[h["sym"] == sym].set_index("t")["open"]
        recs[coin] = s[s.index.time == pd.Timestamp("00:00").time()]
    out = pd.DataFrame(recs)
    out.index.name = "day"
    return out


def trailing_sigma(daily: pd.DataFrame, win: int) -> pd.DataFrame:
    lr = np.log(daily / daily.shift(1))
    return lr.rolling(win, min_periods=max(20, win // 2)).std(ddof=1)


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    m = x.notna() & y.notna()
    if m.sum() < 10:
        return float("nan"), int(m.sum())
    r, _ = stats.spearmanr(x[m].to_numpy(float), y[m].to_numpy(float))
    return float(r), int(m.sum())


def loyo(ic_by_year: list[float]) -> dict:
    """Leave-one-year-out sign test on pooled (non-averaged) yearly ICs."""
    n = len(ic_by_year)
    holds = []
    for i in range(n):
        others = [v for j, v in enumerate(ic_by_year) if j != i]
        rest = float(np.nanmean(others))
        holds.append(bool(np.isfinite(ic_by_year[i]) and np.isfinite(rest)
                          and np.sign(ic_by_year[i]) == np.sign(rest) and rest != 0))
    return {"holds": holds, "n_hold": int(sum(holds))}


def decide(ic_by_year: list[float], loyo_holds: list[bool]) -> dict:
    ic = np.array(ic_by_year, float)
    same_sign = bool(np.all(np.sign(ic) == np.sign(ic[0])) and ic[0] != 0) if np.all(np.isfinite(ic)) else False
    n_sign = int((np.sign(ic) == np.sign(np.nanmean(ic))).sum()) if np.all(np.isfinite(ic)) else 0
    mean_ic = float(np.nanmean(ic))
    verdict = bool(n_sign >= 4 and abs(mean_ic) >= 0.03 and sum(loyo_holds) >= 4)
    return {"n_same_sign": n_sign, "mean_ic": mean_ic,
            "loyo_hold": int(sum(loyo_holds)), "verdict": "PROMISING" if verdict else "NOT_PROMISING"}


def year_of(day: pd.Timestamp) -> int | None:
    for i, a in enumerate(ANCHORS):
        if a <= day < a + WINDOW:
            return i
    return None


def main() -> None:
    views = load_views(RAW)
    feats = compute_features(views)  # (day, (coin, feature))
    hourly = pd.read_parquet(EXT)
    daily = daily_opens(hourly)
    sig30 = trailing_sigma(daily, 30)

    # ---- N1 daily panel ----
    recs = []
    for coin in COINS:
        for feat in ("wiki_z90", "wiki_chg7", "wiki_share"):
            f = feats[(coin, feat)]
            for day, val in f.items():
                if pd.isna(val):
                    continue
                o1 = daily[coin].get(day + pd.Timedelta(days=1), np.nan)
                o2 = daily[coin].get(day + pd.Timedelta(days=2), np.nan)
                o8 = daily[coin].get(day + pd.Timedelta(days=8), np.nan)
                s = sig30[coin].get(day, np.nan)
                if not (np.isfinite(o1) and np.isfinite(o2) and np.isfinite(o8) and np.isfinite(s) and s > 0):
                    continue
                recs.append((coin, feat, day, float(val),
                             float(np.log(o2 / o1) / s), float(np.log(o8 / o1) / s)))
    panel = pd.DataFrame(recs, columns=["coin", "feat", "day", "x", "y1d", "y7d"])
    panel["yr"] = panel["day"].map(year_of)
    panel = panel[panel["yr"].notna()]

    n1 = {}
    for feat in ("wiki_z90", "wiki_chg7", "wiki_share"):
        for label in ("y1d", "y7d"):
            sub = panel[panel["feat"] == feat]
            ic = [spearman(sub[sub["yr"] == i]["x"], sub[sub["yr"] == i][label])[0] for i in range(5)]
            ns = [spearman(sub[sub["yr"] == i]["x"], sub[sub["yr"] == i][label])[1] for i in range(5)]
            ly = loyo(ic)
            per_coin = {c: [spearman(sub[(sub["yr"] == i) & (sub["coin"] == c)]["x"],
                                      sub[(sub["yr"] == i) & (sub["coin"] == c)][label])[0] for i in range(5)]
                        for c in COINS}
            n1[f"{feat}__{label}"] = {"ic_by_year": ic, "n_by_year": ns,
                                      "loyo": ly, "per_coin_ic": per_coin,
                                      "decision": decide(ic, ly["holds"])}

    # ---- N1 monthly vs dip-sleeve edge ----
    monthly = pd.read_csv(ROOT / "research" / "tournament" / "oc_regime" / "monthly_main.csv",
                          parse_dates=["month"])
    z90 = feats.xs("wiki_z90", level="feature", axis=1)
    mon_z = z90.resample("MS").mean().mean(axis=1)  # pooled monthly mean attention
    mrec = []
    for _, r in monthly.iterrows():
        m = pd.Timestamp(r["month"]).tz_localize(None).normalize().replace(day=1)
        if m in mon_z.index and np.isfinite(r["edge"]) and np.isfinite(mon_z[m]):
            mrec.append((m, float(mon_z[m]), float(r["edge"]), year_of(m + pd.Timedelta(days=1))))
    mdf = pd.DataFrame(mrec, columns=["month", "z", "edge", "yr"]).dropna(subset=["yr"])
    mon_out = {}
    for i in range(5):
        s = mdf[mdf["yr"] == i]
        r, n = spearman(s["z"], s["edge"])
        mon_out[f"anchor_{2021 + i}"] = {"ic": r, "n_months": n}
    ic5 = [mon_out[f"anchor_{2021 + i}"]["ic"] for i in range(5)]
    mon_out["loyo"] = loyo(ic5)
    mon_out["decision"] = decide(ic5, mon_out["loyo"]["holds"])

    # ---- N2 CME gaps ----
    cme = load_cme_daily(RAW)
    gaps = weekend_gaps(cme, hourly)
    grec = []
    for _, g in gaps.iterrows():
        if not np.isfinite(g["gap_sigma"]):
            continue
        fri = pd.Timestamp(g["friday"]).tz_localize(None)
        yi = year_of(fri)
        if yi is None:
            continue
        mon = fri + pd.Timedelta(days=3)
        s = sig30[g["coin"]].get(fri + pd.Timedelta(days=2), np.nan)  # sigma ending Sunday
        o0 = daily[g["coin"]].get(mon, np.nan)
        o1 = daily[g["coin"]].get(mon + pd.Timedelta(days=1), np.nan)
        o7 = daily[g["coin"]].get(mon + pd.Timedelta(days=7), np.nan)
        if not (np.isfinite(s) and s > 0 and np.isfinite(o0) and np.isfinite(o1) and np.isfinite(o7)):
            continue
        grec.append((g["coin"], fri, float(g["gap_sigma"]), float(g["gap_abs"]),
                     float(np.log(o1 / o0) / s), float(np.log(o7 / o0) / s), yi,
                     None if pd.isna(g["gap_fill_MF"]) else bool(g["gap_fill_MF"])))
    gdf = pd.DataFrame(grec, columns=["coin", "friday", "gap_sigma", "gap_abs", "y1d", "y7d", "yr", "filled"])
    n2 = {}
    for feat in ("gap_sigma", "gap_abs"):
        for label in ("y1d", "y7d"):
            ic = [spearman(gdf[gdf["yr"] == i][feat], gdf[gdf["yr"] == i][label])[0] for i in range(5)]
            ns = [spearman(gdf[gdf["yr"] == i][feat], gdf[gdf["yr"] == i][label])[1] for i in range(5)]
            ly = loyo(ic)
            per_coin = {c: [spearman(gdf[(gdf["yr"] == i) & (gdf["coin"] == c)][feat],
                                      gdf[(gdf["yr"] == i) & (gdf["coin"] == c)][label])[0] for i in range(5)]
                        for c in ("BTC", "ETH")}
            n2[f"{feat}__{label}"] = {"ic_by_year": ic, "n_by_year": ns,
                                      "loyo": ly, "per_coin_ic": per_coin,
                                      "decision": decide(ic, ly["holds"])}
    fill = {}
    for i in range(5):
        s = gdf[gdf["yr"] == i]
        fill[f"anchor_{2021 + i}"] = {"freq": float(s["filled"].mean()),
                                      "n": int(s["filled"].notna().sum())}
    sall = gdf["filled"].dropna()
    fill["overall"] = {"freq": float(sall.mean()), "n": int(sall.notna().sum())}

    results = {
        "meta": {
            "anchors": [f"{2021 + i}-09-24+365d" for i in range(5)],
            "n1_panel_rows": int(len(panel)),
            "n2_weekends": int(len(gdf)),
            "coverage": {
                "views_days": [str(views.index.min().date()), str(views.index.max().date())],
                "daily_days": [str(daily.index.min().date()), str(daily.index.max().date())],
            },
        },
        "N1_daily": n1,
        "N1_monthly_vs_edge": mon_out,
        "N2_gaps": n2,
        "N2_gapfill_MF": fill,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({k: {kk: vv.get("decision", vv) for kk, vv in v.items()} if isinstance(v, dict) else v
                      for k, v in results.items() if k != "meta"}, indent=2)[:3000])
    print("meta:", json.dumps(results["meta"], indent=2))


if __name__ == "__main__":
    main()
