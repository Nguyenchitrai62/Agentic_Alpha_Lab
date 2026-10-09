"""audit_k2 fits: per-anchor direction + q20/q80 of risk=-low1 (blind, no oc_kronoshidden outputs)."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FEATS = ROOT / "research/tournament/oc_kronoshidden/kronos_features_4shift.parquet"

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
EMBARGO = pd.Timedelta(days=7)
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def load_harness():
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    return harness.load()


def compute_fits():
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    d = load_harness()
    f = pd.read_parquet(FEATS)
    f0 = f[f["shift"] == 0][["sym", "T", "low1"]].copy()
    f0["T"] = pd.to_datetime(f0["T"], utc=True)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    fits = {}
    for a in ANCHORS:
        cut = a - EMBARGO
        tr = d[d.sym.isin(MAJORS) & (d.t_exit < cut)].copy()
        m = tr.merge(f0, on=["sym", "T"], how="inner")
        m["risk"] = -m["low1"]
        rho = float(m["risk"].corr(m["y_dep"], method="spearman")) if len(m) else float("nan")
        direction = int(1 if rho > 0 else (-1 if rho < 0 else 0))
        q20 = float(m["risk"].quantile(0.20)) if len(m) else float("nan")
        q80 = float(m["risk"].quantile(0.80)) if len(m) else float("nan")
        fits[str(a.date())] = dict(anchor=str(a.date()), cut=str((cut).date()),
                                   n_train=int(len(tr)), n_joined=int(len(m)),
                                   spearman_rho=rho, direction=direction,
                                   q20=q20, q80=q80)
        print(str(a.date()), "n_train", len(tr), "n_joined", len(m),
              "rho", round(rho, 4), "dir", direction,
              "q20", round(q20, 6), "q80", round(q80, 6), flush=True)
    return fits


if __name__ == "__main__":
    fits = compute_fits()
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    (HERE / "tmp" / "fits_preview.json").write_text(json.dumps(fits, indent=1))
    print(json.dumps(fits, indent=1))
