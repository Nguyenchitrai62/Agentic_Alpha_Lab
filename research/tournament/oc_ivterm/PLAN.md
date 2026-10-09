# oc_ivterm PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

Question: does the option-implied TERM STRUCTURE TS = 7-day ATM IV / 30-day DVOL
state dip-ladder outcomes and next-24h book returns? Descriptive first; ONE
conditional tilt only if the descriptive candidate rule fires.

## Feature TS(h) (frozen, hourly, known at the end of each hour)

- Per coin BTC / ETH, per UTC hour h (hour = bar START, label h; known at end of h):
  - Candidate strike rows: from `data/raw/deribit_strike_20261007/{BTC,ETH}/` plus
    `data/raw/deribit_strike_20261007_b/{BTC,ETH}/` (hourly per-instrument
    aggregates; files on disk are complete months; overlapping months are
    identical -> concat then dedupe on (hour, instrument_name), B wins ties).
    Columns: hour, instrument_name, expiry (date 08:00 UTC), strike, cp,
    n, sum_amount, vwap_price_usd, vwap_iv, vwap_index, taker_buy_amount,
    taker_sell_amount, block_amount.
  - Keep rows with 3..10 days to expiry: 3d <= (expiry - hour_end) <= 10d, where
    hour_end = h + 1h (expiry is 08:00 UTC date). Moneyness on vwap_index:
    |strike / vwap_index - 1| <= 0.02, calls and puts, sum_amount > 0,
    finite vwap_iv and vwap_index > 0.
  - IV_7d_ATM(h) = sum(vwap_iv * sum_amount) / sum(sum_amount) over the last
    6 hours of candidate rows with row.hour in (h-5h .. h] (6 hourly buckets
    ending at h). Denominator coin traded C(h) = sum(sum_amount) in that window.
    If C(h) < 0.5 coin -> NaN at h. Else value-weighted average (vol points,
    same units as DVOL).
  - DVOL(h) = close of the last closed hourly DVOL candle with candle_end <=
    hour_end, from `data/raw/deribit_dvol_20261005/{BTC,ETH}_YYYY-MM.json`
    (candles [ms, O,H,L,C], hourly, candle [t, t+1h), known at t+1h).
  - TS(h) = IV_7d_ATM(h) / DVOL(h) (both finite, DVOL > 0) else NaN.
  - Carry: forward-fill TS up to 24h across NaN gaps, then NaN (gap > 24h
    stays NaN; leading NaNs stay NaN). No other imputation.
- SOL / BNB / XRP use BTC's TS (market-wide; disclosed everywhere).
- Signal join (causal): for a 4h bar with open T, TS_used = last hourly TS(h)
  with hour_end <= T, i.e. the last FULL hour before the bar open
  (h <= T - 1h). Never the straddling hour.
- Dev window for selection/descriptives: bar open in [2021-09-24, 2025-09-23)
  (4 dev years Y0..Y3, anchors 2021/22/23/24-09-24, [A, A+365d)). The most
  recent year 2025-09-24..2026-09-23 is NEVER used for the candidate decision
  or thresholds; it is scored at most once for the single conditional tilt as
  a labelled 5-year-calibration row (see below).

## Dip ledger (replica; reproduce base 7.718 first)

- Base = exact oc_dipexit D0 + oc_b1deeper B1 replica on all four clock phases
  (4h grid from 2020-08-01 00:00 UTC + 0/1/2/3h), majors x R2 depths
  {2.5,3,3.5,4,5}, live offsets 16..238 strict trade-through, maker 0.0002 /
  taker 0.00055, v293 settle funding. Source: read-only
  `research/tournament/oc_depthtilt/fills.parquet` (identical replica;
  n_candidates 22312, checksum ae59061350564158). ASSERT before any join:
  uncapped 4-phase-mean sums per year == [0.9113, 0.8326, 2.0998, 3.1974,
  0.6772] (=> base_sum5y 7.7182) to 1e-3; else STOP and report.
- Per kept fill: w_base = 1/(1+n_fill), ret = D0 net (fraction of lv, net of
  fees + settle funding), y = w_base * ret; stop flag = (how == 'stop' or
  'backstop') from outcome legs. Recompute `how` from fills.parquet `how`
  column (values 'tp'/'stop'/'backstop'/'time'); stop rate = share with
  how in {stop, backstop}.
- Join TS_used per fill by (coin -> BTC TS for SOL/BNB/XRP; ETH for ETH) at
  last full hour before t_bar. Fills with NaN TS are EXCLUDED from tercile /
  inversion splits but KEPT in the base totals (reported share NaN per year).

## Descriptive tables (dev years Y0..Y3 only; no selection beyond the fixed rule)

- D1 distribution: per dev year, hourly TS(h) rows (BTC, ETH separately):
  n, mean, median, p10, p90, share TS > 1 (inversion), share NaN after carry.
- D2 DIPS: per dev year Y, over fills with finite TS_used: rung visuals:
  (a) TS tercile split: tercile cut points computed IN-YEAR (descriptive only)
  on that year's finite TS_used values; per tercile (Lo/Mid/Hi): n fills,
  mean(y) per rung (= mean w*ret, in w*y units), mean(ret) in bps,
  stop rate. Tercile spread = mean(y)_Hi - mean(y)_Lo in bps-per-rung units
  (mean w*ret x 1e4; w~0.2-1 so this is per-rung economics, comparable to the
  ~4-8 bps round-trip cost scale after dividing by mean w -- both stated).
  (b) inversion split: TS > 1 vs <= 1: same stats. Sign s(Y) = sign(Hi - Lo)
  (per-rung mean y; Hi minus Lo). Record s(Y) per dev year.
- D3 BOOK: per dev year Y, per coin (5 coins; TS from BTC except ETH):
  signal = TS_used at each phase-0 standard-grid 4h bar open T in year Y
  (bars with finite open and sigma>0, same sigma definition as the dip
  replica: std of 4h-open returns over 360 bars ending j-1, min 120, ddof=1);
  label = next-6-bar (24h) open-to-open return / sigma (vol-normalised);
  Spearman IC(signal, label) over bars with finite both. Report pooled (all
  coins) + per coin per year. No trading rule from BOOK in this task.
- Candidate rule (FIXED here): a tilt is scored IFF the DIPS tercile sign
  s(Y) is the SAME in 4/4 dev years AND |tercile spread| > 5 bps per rung
  (on mean(ret) x 1e4, i.e. unweighted rung economics) in the majority (>=3)
  of dev years. Direction: if Hi worse (s<0, high TS = worse dips) the tilt
  is DAMP (x0.6 above p80); if Hi better (s>0) the tilt is BOOST (x1.3 above
  p80). BOOK IC does NOT enter the candidate rule (reported only).
  If the rule does NOT fire, NO tilt is scored and the verdict is descriptive.

## Conditional ONE tilt (scored at most once, only if candidate fires)

- TILT-A (damp, if high TS = worse): per fill with finite TS_used,
  w_rule = w_base * 0.6 if TS_used > p80 else w_base * 1.0.
- TILT-B (boost, if high TS = better): w_rule = w_base * 1.3 if
  TS_used > p80 else w_base * 1.0.
- Only the direction matching the descriptive sign is scored (ONE variant).
  Fills with NaN TS keep w_base in every arm (identical membership).
- Walk-forward p80: for anchor A_k (k=0..4), p80_k per signal (BTC-TS and
  ETH-TS separately) = 80th percentile of the carried hourly TS(h) values with
  hour_end < A_k - 7d (all history since 2021-04, 7-day embargo; non-empty even
  for k=0 where no dip fills exist yet). A fill in year k uses the p80 of its
  own signal (ETH fills -> ETH-TS p80; all other coins -> BTC-TS p80).
- Exposure-matched control (in-year diagnostic, not tradable): per year Y
  (pooled phases, uncapped): R(Y) = realised_rule(Y)/realised_base(Y)
  (sum w over kept fills; R=1 if base 0); S_ctrl_bar(Y) = R(Y)*S_base_bar(Y).
- Scoring (established dip gate, uncapped 4-phase means, same as placebo):
  per (phase, year, arm) S = sum(w*y), DD/W from exit-date daily sums;
  4-phase means S_bar/DD_bar per year; dSum5y = sum_Y(S_rule_bar-S_base_bar).
  PASS_sum(Y): S_rule_bar>=S_base_bar; PASS_dd(Y): DD_rule_bar<=DD_base_bar+0.01;
  PASS_ctrl(Y): S_rule_bar>S_ctrl_bar. PROMISING iff sum>=4/5 AND dd>=4/5 AND
  ctrl>=4/5 AND dSum5y>=+0.273. PRIMARY = 5-year calibration (labelled; the
  recent year is scored exactly once for this single tilt + base reference).
  Dev4-only legs (Y0..Y3) reported as context. No other variant, no tuning.

## Leakage / causality checks (stated in REPORT)

- Strike rows: row.hour is the aggregation hour (trades in [h,h+1h));
  IV window (h-5h..h] uses only hours ending <= signal hour_end; TS(h) joined
  to bars with hour_end <= T (last full hour) -- checked by truncation test.
- DVOL: candle close known at candle_end; latest candle_end <= hour_end only.
- Sigma for BOOK labels excludes the bar itself (shift-1); labels use
  post-open returns only; thresholds (terciles/p80) from training rows with
  t_bar < anchor - 7d (fills) -- no in-year fit for sizing.
  used for sizing); sizing uses ONLY the walk-forward hourly p80.
- No statistic from 2025-09-24+ enters any descriptive cut, sign, or p80.

## Outputs (only these paths)

- research/tournament/oc_ivterm/{PLAN.md, compute_ivterm.py, results.json,
  REPORT.md, SUMMARY.md, tmp/} + tests/test_oc_ivterm.py (>=1
  causality/truncation test + >=1 hand-checked synthetic IV/TS case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_ivterm.py -q`).
- results.json: D1/D2/D3 tables + fidelity assert + (if fired) tilt legs +
  methods note. REPORT.md: tables + plain paragraph + 3-line Vietnamese
  verdict (adopt / reject / needs prospective evidence). SUMMARY.md <= 15 lines.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
