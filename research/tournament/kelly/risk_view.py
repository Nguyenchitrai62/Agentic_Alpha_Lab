"""Post-hoc risk view (not a variant, written after the scores): compares sizes at EQUAL VOLATILITY EXPOSURE (mean(size * sig) matched to
the deployed sizes per year) and reports the per-year daily-PnL Sharpe at the harness's equal notional exposure. Writes risk_view.json."""
import json
import numpy as np
import pandas as pd
import kelly_sizing as K

d = K.build(); H = K.H
S = pd.read_parquet(K.HERE / "sizes.parquet"); M = pd.read_parquet(K.HERE / "sizes_meanonly.parquet")
cand = {c: S[c].to_numpy() for c in ("V1_quantile_kelly", "V2_meanvar", "V3_bucket_ev")}
cand["mean_only_continuous(post-hoc)"] = M.mean_only_continuous.to_numpy()
cand["flat_1"] = np.ones(len(d))
y = d.y_dep.to_numpy(); out = {}
for name, s in cand.items():
    rows = []
    for yi, a0, tr, te in H.folds(d):
        sd, sn, yy, sg = d.size_dep.to_numpy()[te], s[te], y[te], d.sig.to_numpy()[te]
        sg = np.where(np.isfinite(sg), sg, np.nanmedian(sg))
        day = d["T"][te].dt.floor("D").to_numpy()
        sn_n = sn * sd.mean() / sn.mean()                       # harness equal notional
        sn_v = sn * (sd * sg).mean() / (sn * sg).mean()         # equal volatility exposure
        pd_d = pd.Series(sd * yy).groupby(day).sum(); pd_n = pd.Series(sn_n * yy).groupby(day).sum()
        sh = lambda p: float(p.mean() / p.std() * np.sqrt(365))
        rows.append(dict(year=str(a0.date()), gain_equal_vol=round(float((sn_v * yy).sum() - (sd * yy).sum()), 4),
                         vol_ratio_at_equal_notional=round(float((sn_n * sg).mean() / (sd * sg).mean()), 3),
                         sharpe_dep=round(sh(pd_d), 3), sharpe_new=round(sh(pd_n), 3)))
    out[name] = dict(years=rows, total_gain_equal_vol=round(sum(r["gain_equal_vol"] for r in rows), 4))
    print(name, out[name]["total_gain_equal_vol"], [(r["gain_equal_vol"], r["vol_ratio_at_equal_notional"], r["sharpe_dep"], r["sharpe_new"]) for r in rows])
(K.HERE / "risk_view.json").write_text(json.dumps(out, indent=1))
