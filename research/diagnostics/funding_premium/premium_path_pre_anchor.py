"""Premium-index path and price moves around funding settlements - HYPOTHESIS FORMATION ON PRE-ANCHOR DATA ONLY (descriptive).

Question (user 2026-09-28): funding hunters move the funding in the last minutes before a settlement; is that visible, and is there
a causal (known-in-advance) price effect around the settlement? Data: Binance 1m premium-index klines and 1m trade klines strictly
before 2021-09-24 (first walk-forward anchor), so the 2021-2026 test years stay unseen.
For each settlement S of each major (interval from the funding file):
  pred60 = predicted funding known at S-60 (reconstruction from 1m premium samples before S-60, premium_features.reconstruct);
  final  = settled rate; last-hour shift = final - pred60 (bps);
  premium path: mean premium per minute S-60..S+15 minus the mean premium of S-120..S-60 (bps), by pred60 bucket;
  returns: pre15 = close(S-1)/open(S-15) - 1, post15 = close(S+14)/open(S) - 1, post60 = close(S+59)/open(S) - 1 (bps), by pred60 bucket,
  with t-stats; placebo = the same windows at the non-settlement 4h opens (04/12/20 UTC).
Buckets on pred60: < -1 bp, [-1, 1), [1, 3), >= 3 bp (per 8h).

  python research/diagnostics/funding_premium/premium_path_pre_anchor.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CUT = pd.Timestamp("2021-09-24", tz="UTC")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BUCKETS = [(-1e9, -1, "neg<-1bp"), (-1, 1, "~0"), (1, 3, "1-3bp"), (3, 1e9, ">=3bp")]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pfm = _load("premium_features", ROOT / "research/parallel/rounds/parallel-20260906-r2/v231/premium_features.py")
es = _load("es", ROOT / "research/diagnostics/funding_settlement/event_study_pre_anchor.py")


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return (round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2), len(x)) if len(x) > 2 else None


def main():
    rows, paths, placebo = [], [], []
    for s in SYMS:
        p, f = pfm.load(s)
        p, f = p[p.index < CUT], f[(f.index < CUT) & (f.index >= p.index[0] + pd.Timedelta(hours=9))]
        px = es.load_1m(s)
        px = px[px.index < CUT] if isinstance(px.index, pd.DatetimeIndex) else px
        o, c = px["open"].astype(float), px["close"].astype(float)
        pred60 = pfm.reconstruct(p, f, f.index - pd.Timedelta(minutes=60))
        for S in f.index:
            pr = pred60.get(S - pd.Timedelta(minutes=60))
            if pr is None or not np.isfinite(pr):
                continue
            base = p[S - pd.Timedelta(minutes=120):S - pd.Timedelta(minutes=61)].mean()
            seg = p[S - pd.Timedelta(minutes=60):S + pd.Timedelta(minutes=15)]
            if len(seg) < 70 or not np.isfinite(base):
                continue
            rel = ((seg - base) * 1e4).to_numpy()[:75]

            def r(a, b):
                try:
                    return 1e4 * (c.loc[S + pd.Timedelta(minutes=b)] / o.loc[S + pd.Timedelta(minutes=a)] - 1)
                except KeyError:
                    return np.nan
            rows.append(dict(sym=s, S=S, pred60=pr * 1e4, final=f.loc[S, "last_funding_rate"] * 1e4, pre15=r(-15, -1), post15=r(0, 14),
                             post60=r(0, 59)))
            paths.append((pr * 1e4, rel))
        for S in pd.date_range(f.index[0].floor("D") + pd.Timedelta(hours=4), CUT, freq="8h"):
            try:
                placebo.append(dict(pre15=1e4 * (c.loc[S - pd.Timedelta(minutes=1)] / o.loc[S - pd.Timedelta(minutes=15)] - 1),
                                    post15=1e4 * (c.loc[S + pd.Timedelta(minutes=14)] / o.loc[S] - 1)))
            except KeyError:
                pass
        print(s, "settlements", sum(1 for x in rows if x["sym"] == s), flush=True)
    d = pd.DataFrame(rows)
    d["shift"] = d["final"] - d["pred60"]
    out = {"range": f"premium start .. {CUT.date()} (pre-anchor)", "n": len(d),
           "last_hour_shift_bps": {"mean": round(float(d["shift"].mean()), 3), "mean_abs": round(float(d["shift"].abs().mean()), 3),
                                   "p95_abs": round(float(d["shift"].abs().quantile(0.95)), 3),
                                   "corr_pred60_final": round(float(d[["pred60", "final"]].corr().iloc[0, 1]), 4)},
           "buckets": {}, "placebo": {k: tstat([x[k] for x in placebo]) for k in ("pre15", "post15")}}
    for lo, hi, name in BUCKETS:
        g = d[(d.pred60 >= lo) & (d.pred60 < hi)]
        pp = np.array([rel for pr, rel in paths if lo <= pr < hi and len(rel) == 75])
        out["buckets"][name] = {"n": len(g), "shift_mean_bps": round(float(g["shift"].mean()), 3),
                                "pre15": tstat(g.pre15), "post15": tstat(g.post15), "post60": tstat(g.post60),
                                "premium_path_bps_at_min": {m: round(float(pp[:, m + 60].mean()), 3) for m in (-60, -30, -15, -5, -1, 0, 5, 14)} if len(pp) else {}}
    print(json.dumps(out, indent=1))
    (Path(__file__).parent / "premium_path_pre_anchor.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
