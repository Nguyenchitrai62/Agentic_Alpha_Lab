# OpenCode task oc_horizonfix - check and fix a suspected contemporaneous-return leak in the IC yardstick of two diagnostics
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_horizonfix/` and `tests/test_oc_horizonfix.py`.
Print progress every 10 minutes. Light job.

## Suspicion (leader)
research/tournament/oc_presampleshort and research/tournament/oc_bookichorizon scored predictions against y = (open[t+h] / open[t] - 1) /
sigma[t]. If the prediction / book row indexed t was computed from features that include bar t's CLOSE (the features of a bar are known at
its close), then open[t] -> open[t+1] is bar t's own move, already known to the features: a contemporaneous leak in the YARDSTICK (not in
any strategy - the engine's fills are audited). Symptom: oc_presampleshort's TV-only member shows IC +0.13..+0.18 at h = 1 in all 7 years,
decaying to ~0 at h = 42. The rebuilt members' own label was v92's fwd = log(o[t+43] / o[t+1]) (starts at the NEXT bar's open).

## Tasks
1. Determine, from the code, the exact time meaning of the row index t in: (a) the preds_*.csv files of research/tournament/oc_presamplebook
   and oc_presampleflow (are features from bars closing <= t, i.e. including bar t? what is t: bar open or bar close timestamp?); (b) the
   member caches / blended book rows used by research/tournament/oc_bookichorizon (research_books_d2 / scripts/forward_v205.py: is the row at
   T the decision available at T's open, built from bars closing <= T, or the decision made at the close of the bar opening at T?).
2. Re-score both studies with the strictly forward target: y = (open[t_trade + h] / open[t_trade] - 1) / sigma, where t_trade is the FIRST
   bar open at or after the moment the prediction becomes available (features' last bar close). Report old vs corrected tables side by side
   (pooled IC per year and h, TS / XS means), per family / member.
3. Also prove with a test on synthetic data that the old yardstick inflates IC for a feature equal to the current bar's return, and the new
   one does not.
Vietnamese 3-line verdict: which conclusions of oc_bookichorizon / oc_presampleshort survive.
