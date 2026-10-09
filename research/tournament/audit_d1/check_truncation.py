"""audit_d1 truncation check: recompute 200 random risk_D1 rows from bars truncated at T.

For each sampled (sym, shift, T): keep ONLY bars of that (sym, shift) with
bar-open <= T (every bar after T deleted), rebuild log returns + 36-window
share exactly like build_d1.py, and compare to the stored risk_D1.
CPU-only, fast. Output tmp/truncation_check.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
FEATS = HERE / "downshare_D1_4shift.parquet"
N_SAMPLE = 200
SEED = 7
OUT = HERE / "tmp" / "truncation_check.json"


def share_of(rs: np.ndarray) -> float:
    a = np.asarray(rs, dtype=np.float64)
    if a.size == 0 or not np.all(np.isfinite(a)):
        return float("nan")
    tot = float(np.sum(a * a))
    if not np.isfinite(tot) or tot <= 0:
        return float("nan")
    return float(np.sum(np.minimum(a, 0.0) ** 2)) / tot


def main():
    f = pd.read_parquet(FEATS)
    f["T"] = pd.to_datetime(f["T"], utc=True)
    rng = np.random.default_rng(SEED)
    samp = f.iloc[rng.choice(len(f), size=N_SAMPLE, replace=False)].reset_index(drop=True)
    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    groups = {(s, sh): g.sort_values("T").reset_index(drop=True)
              for (s, sh), g in bars.groupby(["sym", "shift"], sort=True)}
    diffs = []
    n_nan_both = 0
    for _, r in samp.iterrows():
        sym, sh, T = r["sym"], int(r["shift"]), r["T"]
        stored = float(r["risk_D1"])
        g = groups[(sym, sh)]
        trunc = g[g["T"] <= T].reset_index(drop=True)
        pos = trunc.index[trunc["T"] == T]
        assert len(pos) == 1, (sym, sh, T)
        E = int(pos[0])
        closes = trunc["close"].to_numpy(dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            logc = np.log(closes)
        rr = np.empty(len(closes))
        rr[0] = np.nan
        rr[1:] = logc[1:] - logc[:-1]
        if E >= 37:
            recomp = share_of(rr[E - 36:E])
        else:
            recomp = float("nan")
        if np.isnan(stored) and np.isnan(recomp):
            n_nan_both += 1
            diffs.append(0.0)
        else:
            diffs.append(abs(recomp - stored))
    diffs = np.array(diffs)
    res = dict(n=N_SAMPLE, seed=SEED, max_abs_diff=float(np.nanmax(diffs)),
               mean_abs_diff=float(np.nanmean(diffs)),
               n_nan_both=int(n_nan_both),
               n_over_1e12=int((diffs > 1e-12).sum()),
               pass_1e9=bool((diffs <= 1e-9).all()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1), flush=True)
    assert res["pass_1e9"], res


if __name__ == "__main__":
    main()
