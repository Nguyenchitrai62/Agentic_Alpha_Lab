"""Per-anchor D1 / D2 fits (harness training rows only).

Training rows per anchor A: majors rows of harness.load() with t_exit < A - 7d
and shift-0 feature present (join on (sym, T)). risk = risk_D1 (resp. risk_D2);
direction = sign of Spearman(risk, y_dep); edges q20/q80 of risk.
Output: fits.json {D1: {...}, D2: {...}} (direction/q20/q80/rho/n).
CPU-only.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research/tournament"))
import harness  # noqa: E402
from tilt_rule import ANCH5  # noqa: E402

FEAT = HERE / "downshare_features_4shift.parquet"
VARIANTS = ("risk_D1", "risk_D2")


def sp(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman")) if m.sum() > 30 else float("nan")


def main():
    d = harness.load()
    print("harness rows", len(d), "T range", d["T"].min(), "..", d["T"].max(),
          "t_exit max", d["t_exit"].max(), flush=True)
    f = pd.read_parquet(FEAT, columns=["sym", "shift", "T", "risk_D1", "risk_D2"])
    f["T"] = pd.to_datetime(f["T"], utc=True)
    f0 = f[f["shift"] == 0][["sym", "T", "risk_D1", "risk_D2"]]
    n0 = len(d)
    d = d.merge(f0, on=["sym", "T"], how="left")
    assert len(d) == n0
    maj = d["sym"].isin(harness.MAJORS).to_numpy()
    for v in VARIANTS:
        print(f"majors rows with shift-0 {v}:",
              int((maj & d[v].notna()).sum()), "of", int(maj.sum()), flush=True)

    fits = {}
    for v in ("D1", "D2"):
        col = "risk_D1" if v == "D1" else "risk_D2"
        fits[v] = {}
        for a in ANCH5:
            A = pd.Timestamp(a, tz="UTC")
            trm = (d["t_exit"] < A - pd.Timedelta(days=7)).to_numpy() & maj
            risk = d[col].to_numpy(dtype=float)
            ok = trm & np.isfinite(risk)
            rho = sp(risk[ok], d["y_dep"].to_numpy()[ok])
            q20, q80 = [float(x) for x in np.quantile(risk[ok], [0.2, 0.8])]
            direction = 1 if rho > 0 else -1
            fits[v][a] = dict(direction=direction, q20=q20, q80=q80,
                              rho=round(rho, 4),
                              n_train_majors=int(trm.sum()),
                              n_train_vol=int(ok.sum()))
            print(f"fit {v} {a}: dir={direction} rho={rho:.4f} "
                  f"q20={q20:.4f} q80={q80:.4f} "
                  f"n_maj={trm.sum()} n_vol={ok.sum()}", flush=True)

    (HERE / "fits.json").write_text(json.dumps(fits, indent=1))
    print("FITS OK", flush=True)


if __name__ == "__main__":
    main()
