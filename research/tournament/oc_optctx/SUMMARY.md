# oc_optctx SUMMARY (<= 15 lines)

Q: do Deribit skew/put-flow and Coinbase premium predict dip-fill y1.0 beyond DVOL?
A: No feature passes the pre-registered triple bar (IC>=4/5, LOYO>=4/5, resid IC>=4/5).
Skew family: IC 4/5 but spreads flip yearly (3/5); z90 redundant (corr 0.90).
Put-buy share: IC 3/5, spreads 3/5 (z: 4/5 spread but 3/5 IC) — fail.
Coinbase premium level: 5/5 negative IC, DVOL-independent, BUT spreads 3/5 and
oppose the IC (+149/-66 bps swings, non-monotonic terciles) — unusable as a rule.
Premium z: weak everywhere (4/5, 3/5, 3/5). Coverage 100%, strict end<T causality.
ETH-only put-share: 5/5 IC on 1417 rungs, spreads fail — hypothesis only.
Verdict: NOTHING PROMISING; premium stays a watchlist item for prospective data.
Files: PLAN.md, analyze_optctx.py, features_optctx.parquet, results.json, REPORT.md.
