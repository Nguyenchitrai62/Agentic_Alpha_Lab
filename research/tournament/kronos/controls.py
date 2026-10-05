"""DISCLOSED POST-HOC CONTROLS (added after V1-V3 were scored; not candidates, never used for selection).
Question: is V1's gain specific to Kronos, or does the identical rule (direction + q20/q80 from fold-training majors rows, size_dep * 1.5/0.5)
on a naive bar-open volatility / drawdown proxy do the same?
  C1: risk = sigma42 / sigma360 (trailing realised 4h vol ratio, bars closed <= T)
  C2: risk = bar_open rng24 (24h high-low range / sigma, known at T + 1 min)
  C3: risk = -(Kronos low1) residualised on [sigma42/sigma, last 4h return/sigma] by OLS fitted on fold-training rows (Kronos beyond naive)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import harness  # noqa: E402
from evaluate import sp, md  # noqa: E402


def main():
    bars = pd.read_parquet(HERE / "bars_4h.parquet")
    nv = []
    for sym, b in bars.groupby("sym"):
        b = b.sort_values("T").reset_index(drop=True)
        ret = pd.Series(np.r_[np.nan, np.diff(np.log(b.open.to_numpy()))])
        nv.append(pd.DataFrame(dict(sym=sym, T=b["T"], s42=ret.rolling(42).std(), s360=ret.rolling(360).std(), last1=ret)))
    nv = pd.concat(nv)
    nv["vr"] = nv.s42 / nv.s360
    nv["last1s"] = nv.last1 / nv.s360
    k = pd.read_parquet(HERE / "kronos_4h_features.parquet")
    d = harness.load()
    n0 = len(d)
    bo = pd.read_parquet(ROOT / "research/tournament/data/bar_open.parquet")
    d = d.merge(bo[["j", "sym", "r", "rng24"]], on=["j", "sym", "r"], how="left")
    d = d.merge(nv[["sym", "T", "vr", "last1s"]], on=["sym", "T"], how="left").merge(k[["sym", "T", "low1"]], on=["sym", "T"], how="left")
    assert len(d) == n0
    maj = d.sym.isin(harness.MAJORS).to_numpy()
    y = d.y_dep.to_numpy()
    out, lines = {}, ["# Disclosed post-hoc controls (V1 rule on naive proxies)\n"]
    for name in ("C1_vol_ratio", "C2_rng24", "C3_kronos_low1_resid"):
        arr = np.full(len(d), np.nan)
        info = []
        for yi, a0, tr, te in harness.folds(d):
            trm = tr & maj
            if name == "C1_vol_ratio":
                risk = d.vr.to_numpy()
            elif name == "C2_rng24":
                risk = d.rng24.to_numpy()
            else:
                Z = np.c_[np.ones(len(d)), d.vr.to_numpy(), d.last1s.to_numpy()]
                ok0 = trm & np.isfinite(Z).all(1) & np.isfinite(d.low1.to_numpy())
                beta = np.linalg.lstsq(Z[ok0], -d.low1.to_numpy()[ok0], rcond=None)[0]
                risk = -d.low1.to_numpy() - Z @ beta
            ok = trm & np.isfinite(risk)
            rho = sp(risk[ok], y[ok])
            q20, q80 = np.quantile(risk[ok], [0.2, 0.8])
            hi, lo_ = (1.5, 0.5) if rho > 0 else (0.5, 1.5)
            m = np.where(risk >= q80, hi, np.where(risk <= q20, lo_, 1.0))
            m = np.where(np.isfinite(risk), m, 1.0)
            arr[te] = d.size_dep.to_numpy()[te] * m[te]
            info.append(dict(year=str(a0.date()), rho_train=round(rho, 4)))
        r = harness.score(d, arr, name)
        r["fold_info"] = info
        (HERE / f"score_{name}.json").write_text(json.dumps(r, indent=1))
        out[name] = r
        lines.append(f"\n## {name}: total gain {r['total_gain']}, graduates {r['graduates']}, train rho {[i['rho_train'] for i in info]}\n\n"
                     + md(pd.DataFrame(r["years"]), index=False) + "\n")
    # correlation of the V1 risk with the naive proxies on majors test rows (descriptive)
    lines.append(f"\nSpearman(-low1, vol ratio) on majors rows: {sp(-d.low1.to_numpy()[maj], d.vr.to_numpy()[maj]):.3f}; "
                 f"Spearman(-low1, rng24): {sp(-d.low1.to_numpy()[maj], d.rng24.to_numpy()[maj]):.3f}\n")
    (HERE / "controls_tables.md").write_text("".join(lines), encoding="utf-8")
    print("".join(lines))


if __name__ == "__main__":
    main()
