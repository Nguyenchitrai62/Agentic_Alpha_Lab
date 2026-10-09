# oc_altdipb1 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

Assignment: docs/opencode/OPENCODE_W_oc_altdipb1.md. The G2 dip ladder WITH
corr-aware sizing on three large alts (research only; trading them needs the
owner's OK). This PLAN is written before any fill/outcome is computed.

## Hypothesis (fixed here)

v398 X11 (11-coin dip sleeve) was rejected as "correlated weak alts", but it
ran BEFORE the corr-aware sizing (v399 B1: w = 1/(1+n)), which defuses
correlated flushes (DD 25 -> 14 on the majors). Hypothesis: the same B1 rule,
applied across an 8-coin universe (5 majors + DOGE/ADA/TRX), lets three large,
liquid alts add incremental dip P&L without breaking the majors book. Tested
as an exact replica with 8-coin n-counting. No fitted parameter.

## Variants (only these two; plus the MAJORS reference)

- MAJORS (reference): 5 majors only, n counts other majors (0..4). Must
  reproduce oc_placebo_dip base 5y 4-phase-mean sum 7.718 (Sbar per year
  0.911/0.833/2.100/3.197/0.677) before any alt outcome is used.
- ALT8: all 8 coins traded (5 majors + DOGE/ADA/TRX); n_fill counts flushing
  coins among ALL 8 (0..7, B1 rule w = 1/(1+n)); budget per coin as the
  majors (same rung set, same w formula, no alt down-weight).
- ALT3: the 3 alts only, with n counted on all 8 coins and sizes exactly as
  in ALT8 (subset of ALT8 fills). The incremental sleeve (ALT8 = majors-leg
  of ALT8 + ALT3 by construction).

No other variant will be added. If anything changes after seeing an outcome,
the original row is kept and the change is added as a disclosed extra row.

## Replica (frozen; oc_placebo_dip compute_placebo_dip.py verbatim + alts)

- Coins: MAJORS = BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT; ALTS =
  DOGEUSDT, ADAUSDT, TRXUSDT (Binance USD-M perps, 1m).
- 1m klines: BTC from data/raw/btc_intraday_20260924, majors from
  data/raw/majors_intraday_20260924, alts from
  data/raw/alts_intraday_20260926 (DOGE/ADA/TRX 1m 2020..2026 + manifest).
  Minutes used: t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill,
  never trigger an exit touch, never count as flushing; a fill whose timeout
  open o2 is NaN is dropped (paired y1.0-finite ledger, same rule all arms).
- Coverage check (pre-registered, before outcomes): manifest first/last per
  alt (DOGE first 2020-07-10, ADA/TRX first 2020-02-01, all last 2026-09-23
  23:59) all predate 2021-09-24, so all five anchor years are fully covered;
  per-year traded-bar counts per alt reported as the listing/coverage proof.
  No alt lists during the test window.
- Four clock phases p in {0,1,2,3}: 4h grid bars covering
  [START + p*1h + 4h*j, START + p*1h + 4h*j + 4h), START = 2020-08-01 00:00
  UTC. Phase 0 == oc_dipexit grid exactly. Bar has 240 offsets 0..239;
  next-bar open is offset 240. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 years Y0..Y4 =
  [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- sigma_4h per coin at bar open T (known at T): simple returns
  r_b = O_b/O_{b-1} - 1 of that phase's 4h bar opens; sigma(T) = std(r over
  360 bars ending at T-1, min_periods 120, ddof=1) (shift(1), bar excluded).
  Bars with non-finite O, sigma <= 0 or NaN are skipped (no rungs).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level lv = O(T)*(1-k*sg).
  Resting limit BUY at lv, live window offsets 16..238 inclusive. Fill at
  FIRST offset f with low(T+f) < lv (STRICT trade-through). Fill price = lv,
  maker 0.0002. At most one fill per (bar, k).
- B1 size (v399/oc_b1deeper-exact, causal: closes up to minute m-1 only):
  n(a,T,m) = number of OTHER coins b != a (among the 8 for ALT8/ALT3; among
  the 5 majors for the MAJORS reference) with finite O_b(T), finite
  C_b(T+m-1), finite sg_b(T) > 0 AND C_b(T+m-1) <= O_b(T)*(1-2.5*sg_b(T))
  (<= counts; NaN = not flushing; own coin never counted). At fill f,
  n_fill = n(a,T,f); w = 1/(1+n_fill).
- Post-fill exits (long), oc_dipexit D0 replica from lv: sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg), on t in f+1..239 then timeout at 240
  (o2 = 1m open at T+240): backstop (first t low(t) <= bl) exits at
  min(bl,open(t)) taker 0.00055; else TP (first t high(t) > tp, STRICT) exits
  at tp maker (2*maker total); else close5 stop (clock m with (m+1)%5==0,
  first m close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else
  timeout at o2 taker + funding 0.0001 iff (T+4h).hour in (0,8,16) (v293
  settle; no funding on intrabar exits). Priority stop-first: backstop wins
  ties (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
  else stop; else timeout. Stop+TP same minute -> stop wins. Nets are
  fractions of lv. Exit reason recorded per fill: tp / stop (close5) /
  backstop / time. Stop rate = (stop+backstop)/n strictly.
- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per settling
  timeout; limit fills only on strict 1m trade-through; no fill in the first
  5 min is implied (live window starts at offset 16).

## Scoring (fixed here)

- Daily sums per (arm, year, phase): group w*y by EXIT date (calendar UTC
  date of T+x, x = exit offset, 240 = next-bar open). S = sum of daily sums
  (= sum w*y); worst day W = min daily sum; cumulative path from 0 over exit
  dates sorted ascending: maxDD >= 0; trades n = kept fills; win = fraction
  with y > 0 strictly (equal-weight); stop rate as above.
- 4-phase means per year: Sbar(Y) = mean_p S(p,Y); DDbar(Y) = mean_p DD(p,Y);
  nbar(Y) = mean_p n(p,Y); win/stop pooled across phases within the year
  (placebo convention: win over all fills of the year).
- ALT3 standalone per year (4-phase mean): Sbar, DDbar, nbar, win, stop rate.
- ALT8 vs MAJORS per year (4-phase mean): S and DD side by side, plus the
  established dip-gate legs, labelled: (a) PASS_sum(Y) iff
  Sbar_ALT8(Y) >= Sbar_MAJORS(Y); (b) PASS_dd(Y) iff
  DDbar_ALT8(Y) <= DDbar_MAJORS(Y) + 0.01 (1 pp, placebo convention);
  (c, labelled stricter) 5y 4-phase-mean dSum = sum_Y Sbar_ALT8 - sum_Y
  Sbar_MAJORS vs +0.273 pooled placebo p95 (oc_placebo_dip).
- Correlation: Pearson correlation of ALT3 daily P&L vs the majors-sleeve
  daily P&L (majors-leg of ALT8, same w*y exit-date daily sums, pooled all
  phases, outer-joined on exit date, zeros filled on missing days; plus per
  year as context).
- DECISION (assignment rule): "show to owner" ONLY if ALT8 beats MAJORS on
  the sum leg in >= 4/5 years AND is within +1 pp on DD in >= 4/5 years.
  Otherwise research-only reject (no deployment; owner trades majors only).
  Selection-protocol note (common header): the dev4 years (anchors
  2021-2024) are the comparison set; the most recent year (2025-09-24 ..
  2026-09-23) is scored ONCE, only for the frozen ALT8/ALT3 and the MAJORS
  reference, and is labelled as such. No variant is picked on the last year.
- G2 baseline check (common header, read-only): load
  research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat
  R2B1D17BFG2 and assert f=0 reproduces v421_result.json G2 (5.41 %/mo,
  worst 2.588, max yearly DD 16.91, full-path DD 16.82) to the digit via the
  oc_carrycompound loader path. This study scores the dip sleeve in w*y
  units (established dip convention); no sleeve-to-%/month overlay or
  leverage is claimed, so no compounding overlay is run.

## Leakage statement (how it is checked)

- Features at decision time T use only data available at T: O(T) is the 1m
  open at minute T; sigma(T) excludes bar T (shift(1)); breadth-style fits:
  none (no fit, no threshold, no quantile); n(a,T,m) uses only closes at
  minutes <= T+m-1 with C at T+m-1 the last fully closed minute; fills use
  low(T+f) strictly (fill at f may use data up to f, exit race from f+1).
- No fit/quantile/threshold of any kind; rung set/depths/costs/phases are the
  frozen deployed values. All five anchor years are research data per the
  assignment (market data to 2026-09-24 read as ordered); a positive result
  is research-only and still needs prospective paper + owner OK.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation (this file). Then:
  compute_altdipb1.py (verbatim placebo core: outcome_mu/n_vector/size_mult/
  fill/cell_stats + alt 1m loaders + 8-coin grids + G2 f=0 check), results.json,
  REPORT.md (tables + 3-line Vietnamese verdict). Tests:
  tests/test_oc_altdipb1.py (synthetic hand checks + causality/truncation).
- One process, one coin H/L at a time; all-eight-coins 1m O/C float32 for the
  n detector; RAM < 3 GB. Heavy run through scripts/heavy_slot.py
  (never --leader). Write ONLY research/tournament/oc_altdipb1/ and
  tests/test_oc_altdipb1.py. No commits; git read-only.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
