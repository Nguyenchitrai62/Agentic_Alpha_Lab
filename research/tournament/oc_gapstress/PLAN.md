# oc_gapstress PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

STRESS / reporting task (no selection rule, no PROMISING verdict).
Question: R2B1D17BF's open exposure (oc_kpi: dip rungs up to ~6.4x equity
notional in calm markets; book up to 1.3x) — what does an instantaneous GAP
do (exchange outage or flash move that skips through stops and the 8-sigma
backstop)?

## Inputs (fixed here, read-only)
- research/tournament/oc_kpi/events_s{0..3}.parquet — engine_user events for
  the exact v411 R2B1D17BF s=0..3 replicas (book_fill/add/reduce/partial/
  close/stop/tp with signed `weight`, rung_fill/tp/sl/timeout with `weight`).
- research/tournament/oc_kpi/barsum_s{0..3}.parquet — per 4h bar end: t,
  n_book, gross_book, equity (phase sub-account equity).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; findings need
  prospective validation). No refit, no selection, no tuning.

## Exact causal position definitions (fixed)
- Engine semantics (verified in engine_user/engine_user.py before writing this
  plan): book quantities q = w/o1 with w = weight fraction of equity at bar
  start; every book_* event `weight` is a SIGNED delta of that fraction
  (book_fill = dw, book_add = +dq*px/prev_eq, book_reduce/partial/close/stop/tp
  = -dq*px/prev_eq). Dip rung_fill `weight` = rn (fraction of start equity,
  always long); rung exit `weight` = same rn.
- Open book fraction per coin at minute T: engine q-units cumulated per coin
  (book_fill qk = weight/limit-price; book_add/reduce/partial qk =
  weight*prev_eq/price; book_stop/tp/close zero the coin's qty), times the
  hourly mark, times bar-start equity / indexed end equity (see corrections
  C1-C3 below). Open dip fraction per coin: FIFO fill quantities
  (qk = weight/limit-price, exits pop oldest) marked the same way.
  Post-event state at each sample minute; fill-minute-stop rungs net to zero.
- Equity at T = barsum indexed equity (end of the containing bar).
- Check: reconstructed |book| gross vs barsum gross_book at bar ends
  (median/max abs diff reported; C2/C3 document the conventions found).

## Sampling (fixed)
- Per phase: distinct event-minute timestamps (any book/dip delta) UNION 4h
  bar ends, restricted to minutes where book or dip gross > 0 (open minutes).
  The open set is constant between samples except equity drift, which the bar-
  end samples capture. No 1m price data is used (LIGHT job).
- 4-phase mix: union of the four phases' sample times; at each, phase states
  and equities are ffill'd; mix equity = mean of phase equities (1/4 capital
  each); mix loss fraction = equity-weighted mean of phase loss fractions.

## Gap math (fixed)
- Gaps g in {-0.05, -0.10, -0.20} (down gaps; shorts profit). All-coin: every
  open position gaps. Single-coin c: only coin c gaps (fee only on c).
- Signed gapped exposure S (fractions of equity), gapped gross G;
  DOWN gap of magnitude g: pnl_frac = -(S*g) - TAKER*G*(1-g), TAKER = 0.00055
  (close at gapped price, no stop protection, no backstop).
  loss_pct = -100*pnl_frac = 100*(S*g + TAKER*G*(1-g)) (positive = loss,
  negative = gain).
- Caps: dip gross D(T) = sum of open dip fractions (all long). If D > cap
  (3.0, 2.0), scale every open dip fraction by cap/D at that minute (book
  untouched); mix caps are applied per phase before mixing. Uncapped + cap3 +
  cap2 are all reported from the same samples.

## Outputs (fixed)
- Script compute_gapstress.py (one process, no 1m data, peak RAM < 1 GB):
  per phase s=0..3 and mix, per gap config (all-coin -5/-10/-20, single-coin
  -10% x5 majors; single-coin -5/-20 in JSON only): n samples, median/p99/max
  loss%, worst-10 timestamps (loss%, gross, dip/book split, equity), share of
  open minutes with all-coin -10% loss > 20% / > 50% (+ extrapolated share of
  all live minutes via open-minute coverage).
- results.json (all numbers + checks + config), REPORT.md (tables, plain
  language for the deployment doc, one-line descriptive summary; no verdict).
- Test tests/test_tournament_oc_gapstress.py (presence, plan-predates-results,
  no data >= 2026-09-24, reconstruction check vs barsum, loss-math spot
  checks, JSON/REPORT consistency). No commits; no edits outside
  research/tournament/oc_gapstress/ + the test file.

## Post-hoc corrections (logged 2026-10-06, BEFORE writing REPORT.md; no
outcome was selected on — this is a reporting task with no selection rule)
- C1: first reconstruction (cumsum of raw signed weights) drifted: engine
  weights mix bases across bars. Rebuilt in engine q-units (fill qk =
  weight/limit-price; book flats zeroed on stop/tp/close; dip FIFO fill qty),
  fractions = Q x hourly mark x bar-start equity / indexed end equity.
  Verified in engine_user/engine_user.py: `dq = ps*T["w"]/px`,
  `eq[i] = prev_eq*(1+pnl)` (multiplicative), bars `qty/end,`open`=o1,`equity`=eq[i]`.
- C2: barsum `t` is the HOLDING-bar start (end-state qty/open=o1/equity);
  recon compares barsum row k with our state at bt[k+1]. Also found
  barsum gross omits the x bar-start-equity factor (documented in REPORT).
- C3: book_add/reduce/partial event weights carry a /prev_eq factor
  (`dq*apx/prev_eq`), fills do not — qk = weight*prev_eq/price for those.
  After C3, recon vs barsum: median abs diff 0.0006-0.0012, max 0.07-0.16
  (residual = hourly-close vs minute-0 mark timing + minute-0 edge fills).
- C4: loss-sign fix — gaps are DOWN gaps: loss% = (S*g + 0.00055*G*(1-g))*100
  with g the magnitude (first run had the sign inverted).
