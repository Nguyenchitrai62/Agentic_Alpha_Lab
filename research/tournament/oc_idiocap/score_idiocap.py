"""oc_idiocap: idiosyncratic caps on n=0 dip rungs (LIGHT, no 1m, one process).

Join fills_U_ext (x0/x4/y1.0) to oc_b1shape fills_n (n25) on (sym, t_fill, x1=k),
score B0=1/(1+n) vs C1/C3 caps (ONLY when n==0, x4>-1 & x0<-4), equal exposure
per year. See PLAN.md (pre-registered BEFORE outcomes).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
EXT = ROOT / "research/tournament/ext/fills_U_ext.parquet"
FILLS_N = ROOT / "research/tournament/oc_b1shape/fills_n.parquet"
OUT = HERE / "results.json"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)


def year_of(t: pd.Series) -> np.ndarray:
    y = np.full(len(t), -1, dtype=np.int8)
    tv = pd.DatetimeIndex(t)
    for i, a in enumerate(ANCHORS):
        y[(tv >= a) & (tv < a + YEAR_LEN)] = i
    return y


def max_dd(daily: pd.Series) -> float:
    c = daily.sort_index().cumsum().to_numpy(dtype="float64")
    if len(c) == 0:
        return float("nan")
    return float(np.minimum.accumulate(c - np.maximum.accumulate(c)).min())


def main() -> None:
    fills = pd.read_parquet(EXT)
    n = pd.read_parquet(FILLS_N)
    sub = fills[fills.sym.isin(MAJORS) & fills.x1.isin(R2)].copy()
    m = sub.merge(
        n[["sym", "t_fill", "k", "n25"]],
        left_on=["sym", "t_fill", "x1"],
        right_on=["sym", "t_fill", "k"],
        how="inner",
    )
    assert len(m) == len(sub) == len(n), f"join loss: {len(sub)} vs {len(n)} vs {len(m)}"
    m["T"] = m["t_fill"] - pd.to_timedelta(m["f"], unit="min")
    m["yi"] = year_of(m["T"])
    m = m[m.yi >= 0].copy().reset_index(drop=True)
    assert m["yi"].value_counts().shape[0] == 5

    # trigger: ONLY n==0, coin crashing fast alone (NaN -> False, conservative)
    trig = (
        (m["n25"].to_numpy() == 0)
        & np.isfinite(m["x0"].to_numpy(float))
        & np.isfinite(m["x4"].to_numpy(float))
        & (m["x4"].to_numpy(float) > -1.0)
        & (m["x0"].to_numpy(float) < -4.0)
    )
    m["trig"] = trig
    base = 1.0 / (1.0 + m["n25"].to_numpy(dtype="float64"))
    variants = {
        "B0_plain": np.ones(len(m)),
        "C1_idio05": np.where(trig, 0.5, 1.0),
        "C3_idio07": np.where(trig, 0.7, 1.0),
    }
    raw = {k: base * v for k, v in variants.items()}

    labels = [a.strftime("%Y-%m-%d") for a in ANCHORS]
    out: dict = {
        "anchors": labels,
        "n_rows_5y": int(len(m)),
        "trigger_overall_share_of_n0": float(trig[m["n25"] == 0].mean()),
        "trigger_share_of_all": float(trig.mean()),
        "variants": {},
    }
    # per-variant per-year scoring with equal exposure (mean w'=1 per year)
    per_v: dict[str, dict] = {}
    for name, w in raw.items():
        ms = m.assign(w=w)
        yearly_S, wd, dd, nfill, ntrig = [], [], [], [], []
        for i in range(5):
            d = ms[ms.yi == i].copy()
            wprime = d["w"].to_numpy(float) / d["w"].mean()
            d["v"] = wprime * d["y1.0"].to_numpy(float)
            S = float(d["v"].sum())
            daily = d.groupby(d["T"].dt.floor("D"))["v"].sum()
            yearly_S.append(S)
            wd.append(float(daily.min()))
            dd.append(max_dd(daily))
            nfill.append(int(len(d)))
            ntrig.append(int(d["trig"].sum()))
        daily_all = (
            ms.assign(wprime=ms["w"] / ms.groupby("yi")["w"].transform("mean"))
            .assign(v=lambda t: t["wprime"] * t["y1.0"])
            .groupby(ms["T"].dt.floor("D"))["v"]
            .sum()
        )
        per_v[name] = {
            "yearly_S": yearly_S,
            "worst_day_per_year": wd,
            "maxDD_per_year": dd,
            "worst_day_overall": float(min(wd)),
            "maxDD_fullpath": max_dd(daily_all),
            "n_fills_per_year": nfill,
            "n_trig_per_year": ntrig,
        }
    out["variants"] = per_v
    b = per_v["B0_plain"]

    def decide(v: dict) -> dict:
        wd_im = [a > c for a, c in zip(v["worst_day_per_year"], b["worst_day_per_year"])]
        dd_im = [a > c for a, c in zip(v["maxDD_per_year"], b["maxDD_per_year"])]
        keep = [
            (a >= 0.95 * c) if c > 0 else (a >= c)
            for a, c in zip(v["yearly_S"], b["yearly_S"])
        ]
        return {
            "wd_improve_years": int(sum(wd_im)),
            "dd_improve_years": int(sum(dd_im)),
            "keep95_years": int(sum(keep)),
            "promising": bool(sum(wd_im) >= 4 and sum(dd_im) >= 4 and sum(keep) >= 4),
            "wd_improve": wd_im,
            "dd_improve": dd_im,
            "keep95": keep,
        }

    out["baseline_yearly_S"] = b["yearly_S"]
    out["decisions"] = {k: decide(v) for k, v in per_v.items() if k != "B0_plain"}
    # LOYO side row: leave each year out, re-check triple bar on remaining 4 (>=3/4)
    loyo = {}
    for k in out["decisions"]:
        v, passes = per_v[k], 0
        for L in range(5):
            idx = [i for i in range(5) if i != L]
            wd = sum(v["worst_day_per_year"][i] > b["worst_day_per_year"][i] for i in idx)
            dd = sum(v["maxDD_per_year"][i] > b["maxDD_per_year"][i] for i in idx)
            kp = sum(
                (v["yearly_S"][i] >= 0.95 * b["yearly_S"][i])
                if b["yearly_S"][i] > 0
                else (v["yearly_S"][i] >= b["yearly_S"][i])
                for i in idx
            )
            passes += int(wd >= 3 and dd >= 3 and kp >= 3)
        loyo[k] = {"loyo_passes_of_5": passes}
    out["loyo"] = loyo
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out["decisions"][k] for k in out["decisions"]}, indent=1))
    print(json.dumps(out["loyo"], indent=1))
    for k, v in per_v.items():
        print(k, [round(s, 4) for s in v["yearly_S"]], [round(s, 4) for s in v["worst_day_per_year"]], [round(s, 4) for s in v["maxDD_per_year"]])


if __name__ == "__main__":
    main()
