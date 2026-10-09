"""oc_d1c2 overlap: Spearman correlation + agreement table of the D1 and C2 multipliers.

CPU-only. Read-only inputs (frozen parquets + frozen fits). No returns, no engine.
Universe: inner-joined feature rows (sym, shift, T) present in BOTH parquets;
year by T date into [A_y, A_y+365d) (last year capped at 2026-09-23).
Per-leg mults via tilt_rule.assign_mult with the frozen anchor-y fits.
Output: tmp/overlap.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DS = ROOT / "research/tournament/oc_downshare"
CH = ROOT / "research/tournament/oc_chronos"

sys.path.insert(0, str(HERE))
from tilt_rule import ANCH5, assign_mult  # noqa: E402

ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
CAP = pd.Timestamp("2026-09-23", tz="UTC")


def year_of(t) -> int:
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    for y, a in enumerate(ANCH):
        hi = min(a + pd.Timedelta(days=365), CAP + pd.Timedelta(seconds=1))
        if a <= tt < hi:
            return y
    return 4


def main() -> None:
    d = pd.read_parquet(DS / "downshare_features_4shift.parquet",
                        columns=["sym", "shift", "T", "risk_D1"])
    c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    d["T"] = pd.to_datetime(d["T"], utc=True)
    c["T"] = pd.to_datetime(c["T"], utc=True)
    n_d, n_c = len(d), len(c)
    j = d.merge(c, on=["sym", "shift", "T"], how="inner")
    n_join = len(j)
    print(f"downshare rows={n_d} chronos rows={n_c} joined={n_join}", flush=True)

    fits_d1 = json.loads((DS / "fits.json").read_text())["D1"]
    fits_c2 = json.loads((CH / "fits.json").read_text())

    j["year"] = j["T"].map(year_of)
    m1, m2 = [], []
    for _, r in j.iterrows():
        y = int(r["year"])
        f1 = fits_d1[ANCH5[y]]
        f2 = fits_c2[ANCH5[y]]
        rd = float(r["risk_D1"])
        q = float(r["ch_q10"])
        rc = -q if np.isfinite(q) else float("nan")
        m1.append(assign_mult(rd, f1["direction"], f1["q20"], f1["q80"], 1.25, 0.75))
        m2.append(assign_mult(rc, f2["direction"], f2["q20"], f2["q80"], 1.25, 0.75))
    j["m_D1"] = np.array(m1)
    j["m_C2"] = np.array(m2)

    per_year = []
    for y in range(5):
        g = j[j["year"] == y]
        rho = float(g["m_D1"].corr(g["m_C2"], method="spearman")) if len(g) > 2 else None
        tab = {}
        for a in (0.75, 1.0, 1.25):
            for b in (0.75, 1.0, 1.25):
                tab[f"{a}x{b}"] = int(((g["m_D1"] == a) & (g["m_C2"] == b)).sum())
        agree = tab["1.25x1.25"] + tab["0.75x0.75"] + tab["1.0x1.0"]
        per_year.append({"year": ANCH5[y], "n": int(len(g)),
                         "spearman": None if rho is None or not np.isfinite(rho) else round(rho, 4),
                         "agree_same": agree, "agree_rate": round(agree / len(g), 4) if len(g) else None,
                         "table": tab})
        print(f"y={y} {ANCH5[y]} n={len(g)} spearman={rho} agree={agree}/{len(g)}", flush=True)
        print(f"   table={tab}", flush=True)

    pooled_rho = float(j["m_D1"].corr(j["m_C2"], method="spearman"))
    out = {"config": {"universe": "inner-joined (sym,shift,T) of both frozen parquets; year by T date",
                       "fits": "frozen anchor-y fits; hi/lo 1.25/0.75; NaN->1.0"},
           "rows": {"downshare": n_d, "chronos": n_c, "joined": n_join},
           "per_year": per_year,
           "pooled_spearman": round(pooled_rho, 4) if np.isfinite(pooled_rho) else None}
    (HERE / "tmp/overlap.json").write_text(json.dumps(out, indent=1))
    print(f"pooled spearman={pooled_rho:.4f} wrote tmp/overlap.json", flush=True)


if __name__ == "__main__":
    main()
