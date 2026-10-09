"""oc_voltilt overlap analysis (no selection input): is the simple-vol tilt the same trade as the FM tilts?

Per year y (all 4 shifts pooled, decision bars in year y on each shift's grid):
  Spearman(risk_RV6, risk_FM) and Spearman(risk_GARCH, risk_FM) for
  FM in {C2: risk=-ch_q10, K2: risk=-low1, T3: risk=-f_q10}, on the
  intersection of rows with both features present;
  plus the share of (sym, shift, T) decision rows in year y where V_RV6's
  multiplier (anchor-y V_RV6 fits) equals C2's multiplier (anchor-y C2 fits,
  missing -> 1 on both legs).
CPU-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from tilt_rule import ANCH5, assign_mult  # noqa: E402

C2F = ROOT / "research/tournament/oc_chronos/chronos_features_4shift.parquet"
K2F = ROOT / "research/tournament/oc_kronoshidden/kronos_features_4shift.parquet"
T3F = ROOT / "research/tournament/oc_toto/toto_features_4shift.parquet"


def sp(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman")) if m.sum() > 30 else float("nan")


def main():
    v = pd.read_parquet(HERE / "vol_features_4shift.parquet")
    v["T"] = pd.to_datetime(v["T"], utc=True)
    c = pd.read_parquet(C2F, columns=["sym", "shift", "T", "ch_q10"])
    c["T"] = pd.to_datetime(c["T"], utc=True)
    k = pd.read_parquet(K2F, columns=["sym", "shift", "T", "low1"])
    k["T"] = pd.to_datetime(k["T"], utc=True)
    t = pd.read_parquet(T3F, columns=["sym", "shift", "T", "f_q10"])
    t["T"] = pd.to_datetime(t["T"], utc=True)
    print(f"rows vol={len(v)} c2={len(c)} k2={len(k)} t3={len(t)}", flush=True)

    m = v.merge(c, on=["sym", "shift", "T"], how="inner")
    m = m.merge(k, on=["sym", "shift", "T"], how="inner")
    m = m.merge(t, on=["sym", "shift", "T"], how="inner")
    m["fm_C2"] = -m["ch_q10"].to_numpy(dtype=float)
    m["fm_K2"] = -m["low1"].to_numpy(dtype=float)
    m["fm_T3"] = -m["f_q10"].to_numpy(dtype=float)
    print(f"intersection rows={len(m)} range={m['T'].min()}..{m['T'].max()}", flush=True)

    fits_v = json.loads((HERE / "fits.json").read_text())
    fits_c2 = json.loads((ROOT / "research/tournament/oc_chronos/fits.json").read_text())

    out = []
    for y, a in enumerate(ANCH5):
        A = pd.Timestamp(a, tz="UTC")
        A1 = pd.Timestamp(ANCH5[y + 1], tz="UTC") if y < 4 else pd.Timestamp("2026-09-24", tz="UTC")
        # decision rows of year y: per-shift grid [A+sh, min(A+sh+365d, live1))
        yy = m[(m["T"] >= A) & (m["T"] < A1)].copy()
        # drop rows before the shift's year start (shift grids start at A+sh)
        keep = np.zeros(len(yy), dtype=bool)
        for sh in (0, 1, 2, 3):
            sh_td = pd.Timedelta(hours=sh)
            lo = A + sh_td
            hi = min(A + sh_td + pd.Timedelta(days=365),
                     pd.Timestamp("2026-09-23", tz="UTC") + sh_td)
            sub = (yy["shift"] == sh) & (yy["T"] >= lo) & (yy["T"] < hi)
            keep |= sub.to_numpy()
        yy = yy[keep]
        row = {"year": a, "n": int(len(yy))}
        r6 = yy["risk_RV6"].to_numpy(dtype=float)
        rg = yy["risk_GARCH"].to_numpy(dtype=float)
        for fm in ("fm_C2", "fm_K2", "fm_T3"):
            f = yy[fm].to_numpy(dtype=float)
            row[f"spear_RV6_{fm}"] = round(sp(r6, f), 4)
            row[f"spear_GARCH_{fm}"] = round(sp(rg, f), 4)
        # multiplier agreement V_RV6 vs C2 (anchor-y fits, missing -> 1)
        fv = fits_v["V_RV6"][a]
        fc = fits_c2[a]
        mv = np.array([assign_mult(x, fv["direction"], fv["q20"], fv["q80"], 1.25, 0.75) for x in r6])
        mc = np.array([assign_mult(x, fc["direction"], fc["q20"], fc["q80"], 1.25, 0.75)
                       for x in yy["fm_C2"].to_numpy(dtype=float)])
        row["agree_VRV6_C2"] = round(float((mv == mc).mean()), 4)
        out.append(row)
        print(row, flush=True)
    # pooled (all years)
    prow = {"year": "pooled", "n": int(len(m))}
    r6 = m["risk_RV6"].to_numpy(dtype=float)
    rg = m["risk_GARCH"].to_numpy(dtype=float)
    for fm in ("fm_C2", "fm_K2", "fm_T3"):
        f = m[fm].to_numpy(dtype=float)
        prow[f"spear_RV6_{fm}"] = round(sp(r6, f), 4)
        prow[f"spear_GARCH_{fm}"] = round(sp(rg, f), 4)
    print(prow, flush=True)
    (HERE / "tmp/overlap.json").write_text(json.dumps({"per_year": out, "pooled": prow}, indent=1))
    print("wrote tmp/overlap.json", flush=True)


if __name__ == "__main__":
    main()
