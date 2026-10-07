# oc_agentens — PLAN (pre-registered BEFORE any outcome is computed)

Hypothesis (#52): the deployed R2 dip tables come from ONE seed chosen among
several (v321 seed choice) — a selection risk. A majority-vote ensemble over
5 seeds (the deployed seed + 4 new fixed seeds) averages out seed noise in
the size (S1) + TP (X4) rules and is therefore more ROBUST walk-forward:
it beats or matches the deployed single seed in most years and has a better
worst year, without any new feature or rule. Null (stated upfront): rung
outcomes y are seed-invariant enough that the 5 tables agree almost
everywhere, so the ensemble ~ equals the deployed seed (no gain, no harm);
a robustness gain requires seed dispersion to be material AND the majority
vote to pick the better side on average.

## Exact causal definitions (frozen)

- Anchors A_k = 2021-09-24 + k*365 d, k=0..4. Test year Y(A_k) =
  [A_k, A_k+365 d). Market data used is strictly < 2026-09-24 00:00 UTC.
- Fills: rows of research/tournament/ext/fills_U_ext.parquet (72,130 rows,
  verbatim v293.fills_of replica, rungs U=2.0..5.0, 35-coin universe).
  Columns j (standard-grid 4h bar index, START=2020-08-01 00:00 UTC), r, f,
  t_fill, t_exit, y0.5/y1.0/y1.5 (exact net returns, engine_user
  close5+backstop, maker 0.0002 / taker 0.00055 / adverse long funding),
  x0..x6 (sp30, k, volreg, trend, btc sp30, dd24, hour), sym. Training uses
  the FULL fills_U_ext universe (majors + alts), exactly as R2.
- Features/windows/embargo/fits/rules IDENTICAL to
  research/tournament/oc_rlbear/build_v0_v2.py V0 (itself a verbatim copy
  of phase_agents/build_tables.py + v296 HGB hyperparams): X = x0..x6
  (7 floats); Y clipped to [-0.10, 0.08]; y1 = Y[:,1.0]; half = j%2;
  keep_k = (t_exit < A_k - 7 days) (v293.EMBARGO, >= horizon);
  mu_k = mean of y1[keep_k]; size models fit on y1, TP models fit on
  Y[:,c] c in {0,1,2}; HGB max_depth=3, lr=0.05, max_iter=200,
  min_samples_leaf=200, l2=1.0; size rule 1.5 if pa,pb > 2*mu, 0.5 if
  pa,pb < 0 (and not up), else 1.0 (NaN pa -> 1.0); TP 0.5/1.5 iff both
  halves agree on the same non-base action with gain > 0.001, else 1.0.
- Seeds (frozen, v303 convention): seed set S = {0, 101, 202, 303, 404}.
  S=0 is the DEPLOYED seed: random_state = 10*jj+h (size) and
  10*jj+h+3*c (TP), exactly build_v0_v2.py V0 (must reproduce
  v376/tables_hidden/r2_table_s0.parquet). For S>0: random_state =
  1000*S + 10*jj+h (size) and 1000*S + 10*jj+h+3*c (TP). 5 anchors x
  8 fits = 40 HGB fits per seed, 200 total, single process. Per-bar
  model k(T) = max{q : T >= A_q}. No other change between seeds.
- Table rows (phase s=0 ONLY, bar-open form EXACTLY as build_v0_v2.py):
  for each major sym and each standard-grid holding bar T with
  A_0=2021-09-24 <= T <= 2026-09-23 12:00 and finite sig[j]:
  kk=j*240; base=[A.sp30(kk), k, A.volreg[j], A.trend[j], btc.sp30(kk),
  log(C[kk]/hmax24[kk])/sig[j], T.hour]; one row per k in U, filtered to
  traded R2=(2.5,3.0,3.5,4.0,5.0) with rung=0..4. Majors 1m loaded ONE
  coin at a time. Output schema (T, sym, rung, size, tp) per seed.
- ENSEMBLE table (ens_table_s0.parquet, same schema): per (T, sym, rung),
  majority vote over the 5 single-seed tables, voted SEPARATELY for size
  and for tp. Values are in {0.5, 1.0, 1.5}. Count votes per value; pick
  the unique mode; on any tie for top (e.g. 2-2-1, 1-1-3 is not a tie,
  but 2-2-1 or 1-1-1 splits among the leaders) choose the deployed
  default 1.0. Deterministic, no outcome data used.
- S=0 reproduction gate: S=0 table must match oc_rlbear/v0_table_s0.parquet
  (hence the v376 hidden ref) on the inner join on (T,sym,rung) at
  size_match >= 99.9% and tp_match >= 99.9%. If not, STOP, no verdict.

## Screening (rung level, phase 0; frozen before computing)

- Universe: fills_U_ext rows with sym in majors, x1 (=k) in R2 traded
  rungs 2.5..5.0, and holding-bar open T(j)=START+4h*j inside Y(A_k).
- Realised outcome per fill under table V: look up (T,sym,rung) in V;
  outcome = size_V * y_{tp_V} (y0.5/y1.0/y1.5 per the TABLE's tp). Fills
  with no table row are dropped and counted. V ranges over {S0(deployed),
  S101, S202, S303, S404, ENS}.
- Daily sums by exit date: group outcomes by t_exit date (UTC). Per year
  and per V: sum, fill win rate = mean(outcome>0), day win rate over
  non-zero days, worst day = min(daily_sum), maxDD = max drawdown of the
  cumulative daily-sum path starting at 0 (same convention as
  oc_rlbear/screen_rung.py max_dd, reported identically for all V).
- Dispersion: per year, the 5 single-seed sums (min/max/range/std, best
  seed id, rank of deployed S0, deployed minus mean/sum of singles);
  plus pairwise table-agreement rates (size agree / tp agree) of each
  single seed vs S0 and of ENS vs S0.
- Decision rule (assignment default, frozen): PROMISING only if
  (i) sum(ENS) >= sum(S0) in >= 3 of 5 anchor years AND (ii) worst year
  of ENS is better: min_k sum_k(ENS) > min_k sum_k(S0) (robustness, not
  mean). Otherwise NOT PROMISING. One-line verdict in REPORT.md. No
  leave-one-year-out beyond the >=4/5-style check in the assignment text
  (the assignment's "holds leave-one-year-out in >= 4 of 5" is the generic
  template; this idea's concrete frozen rule is (i)+(ii) above per the
  task paragraph). No engine replay in this task.

## Leakage checklist (to be confirmed in REPORT)

1. Table state at bar open uses minutes <= 240*j only (same as build).
2. Fits/mu/thresholds use t_exit < A-7d only; no test-year row in any fit.
3. Seeds/clip/rules fixed from build_tables.py/v303 convention; the 4 new
   seeds (101/202/303/404) fixed here before any outcome.
4. Ensemble vote uses only the 5 tables (no y, no test-year statistic).
5. No statistic from any test year feeds any choice; S0/V0 shared mu.

## Deliverables in this folder

- PLAN.md (this file, written before any outcome).
- build_ensemble.py (5-seed tables + majority-vote ENS, one coin at a time).
- screen_ensemble.py (screening exactly as above).
- ens_table_s0.parquet (ENS, s0, schema T/sym/rung/size/tp) + per-seed
  tables seed_table_s{S}_s0.parquet (kept for audit; S0 doubles as V0 check).
- build_info.json, results.json (per-year S0/singles/ENS stats + dispersion).
- REPORT.md (tables + one-line verdict).
- RAM < 3 GB, one process, no commits, no edits outside this folder
  (+ tests/test_tournament_oc_agentens.py).
