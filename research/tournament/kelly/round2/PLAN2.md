# kelly round 2 - pre-registered 2026-10-05 (before any W score)

Context: V2 meanvar (round 1) passed the harness (+4.72) and the honest R2-4P engine (dev4 5.85 vs 5.24 %/month, every year higher, DD 25.2
vs 23.1). DISCLOSURE: the mean-only rule (W2 below) was already seen post-hoc in round 1 (`decompose.json`: +8.33 total, per-year
+3.49 / +1.81 / +1.50 / +1.54, worst days -0.33 / -1.41 / -0.87 / -0.63); it is scored here as its own variant at the leader's request,
with exactly the round-1 post-hoc definition, so its result is known in advance and is not independent evidence.

## Fixed settings (identical to V2)
Rows / label / folds: harness.load, y_dep, harness.folds (train t_exit < anchor - 7 d, any coin; test = majors R2 rungs).
Base feature set F = V2's 20 features (17 bar-open + k + tp + lsig, kelly_sizing.FEATS, built by kelly_sizing.build()).
Market features M = the 17 columns of research/tournament/context/market_features.parquet (build_market_features.FEATS: m_r4, m_r24, m_r72,
m_dd7, m_tr7, m_vts, m_vlvl, x_disp4, x_disp24, x_br2, x_dn24, x_corr72, btc_rel24, c_beta7, c_idio24, c_idio4, c_corr72), joined by row
position exactly as context/run_variants.py does (the parquet is aligned with harness.load rows); asserted: same length, same T and sym
per row, and kelly_sizing.build() keeps harness.load's row order (j, sym, r identical).
Model: HGB depth 3, lr 0.05, 300 iter, min leaf 200, no early stopping, random_state 0; cross-fit on j % 2 halves (OOF on training rows,
mean of the two halves on test rows). Scale c from training OOF only (bisection, training mean size = 1). Size in [0, 2].

## Variants (each scored once with harness.score)
- W1 meanvar_mkt: V2 rule on F + M (mean HGB, |OOF residual| HGB, size = clip(c max(mu,0) / sd^2, 0, 2), sd = sqrt(pi/2) |e|_hat).
- W2 meanonly: size = clip(c max(mu, 0), 0, 2), mu = cross-fitted mean HGB on F.
- W3 meanonly_mkt: W2 on F + M.

## Reporting and the table-building trigger (fixed now)
Per year: gain vs deployed (harness), gain vs V2 (S_W - S_V2, both at the harness equal exposure), worst day, IC, raw filled-rung mean
size (before harness normalisation) vs deployed and V2, graduation flag.
Trigger for engine tables: a W beats V2 on harness gain in >= 3 of 4 years AND its worst day (min over the 4 years) is not worse than
V2's (-0.6889). Qualifying W -> tables/kelly_<W>_s{s}.parquet with the same checks as kelly_v2 (phase-0 match, per-phase stats, causality).

## Addendum (2026-10-05, written AFTER W1-W3 were scored, BEFORE W4 is computed) - disclosed extra variant W4
Leader request after the engine showed V2's extra DD does not shrink with a global scale (x0.9 / x0.8): suspicion that return-unit targets
plus lsig push size into high-volatility periods. W4 is therefore an extra, disclosed round-2 variant (the W1-W3 results were known when
it was added; W1-W3 did not influence its definition, which the leader specified).
- W4 meanvar_sigunits: target z = y_dep / sig4, sig4 = the coin's sigma_4h at the bar open with the engine definition (v293.Asset.sig:
  std of the 4h-open pct changes over 360 bars, min 120, shifted one bar), computed from the 4h opens of data/hourly.parquet (hour-start
  open at T on the standard grid, missing bars NaN, then pct_change / rolling / shift exactly as Asset); spot-checked against
  v293.Asset("BTCUSDT").sig on the harness rows. Features = V2's minus lsig (17 bar-open + k + tp). Mean HGB on z, |OOF residual| HGB,
  size = clip(c max(mu_n, 0) / sd_n^2, 0, 2) with sd_n = sqrt(pi/2) |e_n|_hat; c from training OOF (training mean size 1). Rows with
  NaN sig4 are excluded from training; a test row with NaN sig4 keeps the model prediction from the remaining features (z-model needs no sig).
- Extra tail report for V2, W1-W4 and the deployed sizes (equal exposure as harness.score): per year the worst day and the max drawdown of
  the cumulative daily sum(size * y_dep).
- The table-building trigger above applies to W4 too.
