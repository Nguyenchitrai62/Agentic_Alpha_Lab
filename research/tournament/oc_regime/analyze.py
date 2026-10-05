"""oc_regime Part B: monthly dip edge vs month-start slow regimes + LOYO gate test."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from regime import (
    compute_regimes,
    daily_closes_from_1m,
    daily_closes_from_hourly,
    load_hourly,
    splice_daily,
)

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
FILLS_DEV = ROOT / "research/diagnostics/phase_agents/fills_U.parquet"
FILLS_EXT = ROOT / "research/tournament/ext/fills_U_ext.parquet"
CUT = pd.Timestamp("2025-09-24", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
VARS = ["trend30", "trend90", "volratio", "corr30", "stress30", "breadth50", "dd90", "vollevel"]


def load_fills() -> pd.DataFrame:
    dev = pd.read_parquet(FILLS_DEV)
    ext = pd.read_parquet(FILLS_EXT)
    assert list(ext.columns) == list(dev.columns), "ext schema mismatch"
    dev = dev.copy()
    ext = ext.copy()
    dev["T"] = pd.to_datetime(dev["t_fill"], utc=True) - pd.to_timedelta(dev["f"], unit="min")
    ext["T"] = pd.to_datetime(ext["t_fill"], utc=True) - pd.to_timedelta(ext["f"], unit="min")
    use = pd.concat([dev[dev["T"] < CUT], ext[ext["T"] >= CUT]], ignore_index=True)
    use = use.sort_values("T").reset_index(drop=True)
    return use


def build_daily() -> pd.DataFrame:
    h = load_hourly()
    hd = daily_closes_from_hourly(h)
    syms = sorted(h["sym"].unique().tolist())
    od = daily_closes_from_1m(syms)
    # overlap agreement check (log-diff on common days/syms)
    common_days = hd.index.intersection(od.index)
    common_days = common_days[(common_days >= pd.Timestamp("2024-09-01", tz="UTC")) &
                              (common_days <= pd.Timestamp("2025-09-23", tz="UTC"))]
    ldiff = (np.log(hd.loc[common_days, syms] / od.loc[common_days, syms])).abs()
    med = float(np.nanmedian(ldiff.to_numpy()))
    print(f"daily-close overlap: days={len(common_days)} median|logdiff|={med:.2e}", flush=True)
    assert med < 5e-4, f"hourly vs 1m daily closes disagree: {med}"
    return splice_daily(hd, od)


def monthly_edge(fills: pd.DataFrame, mask: np.ndarray) -> pd.DataFrame:
    d = fills.loc[mask, ["T", "y1.0"]].copy()
    d["month"] = pd.to_datetime(d["T"].dt.strftime("%Y-%m-01"), utc=True)
    g = d.groupby("month")["y1.0"].agg(["mean", "count"])
    g.columns = ["edge", "n"]
    return g


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    z = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(z) < 3:
        return np.nan, int(len(z))
    return float(z["x"].corr(z["y"], method="spearman")), int(len(z))


def run() -> dict:
    fills = load_fills()
    daily = build_daily()
    reg = compute_regimes(daily)
    reg = reg[(reg.index >= pd.Timestamp("2021-01-01", tz="UTC")) &
              (reg.index <= pd.Timestamp("2026-09-01", tz="UTC"))]
    reg.to_parquet(HERE / "regimes_daily.parquet")

    masks = {
        "main": (fills["sym"].isin(MAJORS) & fills["x1"].isin(R2)).to_numpy(),
        "pooled": (fills["x1"].isin(R2)).to_numpy(),
    }
    out: dict = {
        "meta": {
            "fills_dev": str(FILLS_DEV.relative_to(ROOT)),
            "fills_ext": str(FILLS_EXT.relative_to(ROOT)),
            "cut": "2025-09-24",
            "T_min": str(fills['T'].min()),
            "T_max": str(fills['T'].max()),
            "rows": int(len(fills)),
            "rows_main": int(masks["main"].sum()),
            "rows_pooled": int(masks["pooled"].sum()),
            "outcome": "y1.0 fill-level mean",
            "regime_note": "hourly.parquet to 2025-09-23, 1m-derived daily closes after (overlap median|logdiff| checked)",
            "vars": VARS,
        },
        "universes": {},
    }
    for uni, m in masks.items():
        me = monthly_edge(fills, m)
        me["reg_day"] = me.index
        me = me.join(reg, on="reg_day")
        me.to_csv(HERE / f"monthly_{uni}.csv")
        years = {}
        for a in ANCHORS:
            a1 = a + pd.Timedelta(days=365)
            years[str(a.date())] = me[(me.index >= a.floor("D")) & (me.index < a1)].copy()
        sp = {}
        for v in VARS:
            sp[v] = {}
            for y, tab in years.items():
                rho, n = spearman(tab[v], tab["edge"])
                sp[v][y] = {"rho": None if np.isnan(rho) else round(rho, 4), "n": n,
                            "months": [str(i.date()) for i in tab.index]}
        loyo = {}
        for v in VARS:
            loyo[v] = {}
            for y, _ in years.items():
                tr = pd.concat([t for yy, t in years.items() if yy != y])
                tr = tr[[v, "edge"]].dropna()
                thr = float(tr[v].median()) if len(tr) else np.nan
                if len(tr) == 0 or np.isnan(thr):
                    loyo[v][y] = {"thr": None, "good_side": None, "without": None,
                                  "with": None, "helps": False, "kept_months": 0,
                                  "kept_fills": 0, "total_fills": 0}
                    continue
                hi = tr.loc[tr[v] >= thr, "edge"].mean()
                lo = tr.loc[tr[v] < thr, "edge"].mean()
                good = "above" if hi >= lo else "below"
                te_months = years[y]
                te_fills = fills.loc[m & (fills["T"] >= pd.Timestamp(y, tz="UTC")) &
                                     (fills["T"] < pd.Timestamp(y, tz="UTC") + pd.Timedelta(days=365))].copy()
                te_fills["month"] = pd.to_datetime(te_fills["T"].dt.strftime("%Y-%m-01"), utc=True)
                mreg = te_months[v].to_dict()
                te_fills["rv"] = te_fills["month"].map(mreg)
                if good == "above":
                    kept = te_fills[te_fills["rv"] >= thr]
                else:
                    kept = te_fills[te_fills["rv"] < thr]
                kept_months = int(te_months[(te_months[v] >= thr if good == "above"
                                             else te_months[v] < thr) & te_months[v].notna()].shape[0])
                without = float(te_fills["y1.0"].mean()) if len(te_fills) else np.nan
                withm = float(kept["y1.0"].mean()) if (len(kept) and kept_months >= 2) else np.nan
                loyo[v][y] = {"thr": round(thr, 6), "good_side": good,
                              "without": None if np.isnan(without) else round(without, 6),
                              "with": None if np.isnan(withm) else round(withm, 6),
                              "helps": bool(np.isfinite(withm) and np.isfinite(without) and withm > without),
                              "kept_months": kept_months,
                              "kept_fills": int(len(kept)), "total_fills": int(len(te_fills))}
        verdict = {}
        for v in VARS:
            signs = [np.sign(sp[v][y]["rho"]) for y in years
                     if sp[v][y]["rho"] is not None and np.isfinite(sp[v][y]["rho"])]
            helps = sum(1 for y in years if loyo[v][y]["helps"])
            nsign = max(sum(1 for s in signs if s > 0), sum(1 for s in signs if s < 0)) if signs else 0
            verdict[v] = {"sign_count": int(nsign), "help_count": int(helps),
                          "consistent": bool(nsign >= 4 and helps >= 4)}
        out["universes"][uni] = {"spearman": sp, "loyo": loyo, "verdict": verdict,
                                 "n_months": int(me["edge"].notna().sum())}
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({u: v["verdict"] for u, v in out["universes"].items()}, indent=1))
    return out


if __name__ == "__main__":
    run()
