# oc_optflow — PLAN (pre-registered BEFORE any outcome is computed)

## Question
Does INFORMED option flow (strike-level, short-dated, large/block, taker-initiated)
predict the majors? Descriptive first. NO trading rule is scored in this task.

## Inputs (read-only)
- `data/raw/deribit_strike_20261007/{BTC,ETH}/` + `data/raw/deribit_strike_20261007_b/{BTC,ETH}/`
  hourly per-instrument aggregates 2021-01..2026-09. Columns include hour, instrument_name,
  expiry, strike, cp (C/P), n, sum_amount, vwap_price_usd, vwap_index,
  taker_buy_amount, taker_sell_amount, block_amount (ETH files also carry dte_hour,
  ignored; DTE is recomputed uniformly). Overlapping months are identical → dedupe on
  (hour, instrument_name) after concat of both folders per coin.
- 4h opens: `artifacts/research/engine_real/opens_v154.parquet` (standard 4h grid,
  freq 4h). Grid = intersection of opens index with option-feature availability.
- Dip replica: `research/tournament/oc_placebo_dip/compute_placebo_dip.py`
  (`build_base`, `outcome_mu`, costs maker 0.0002/taker 0.00055, FUND 0.0001).

## Feature definitions (fixed now; per coin BTC/ETH; hourly, known at END of hour)
Per (hour h, instrument row): index = vwap_index (per-row; must be finite and > 0).
DTE_days = (expiry − hour).total_seconds()/86400, require 1 <= DTE_days <= 9
(expiry timestamps are 00:00 UTC in the files; this excludes the final 24h before expiry).
Moneyness m = strike/index − 1. Keep OTM only: puts P with K < index and m in [−0.15,−0.03];
calls C with K > index and m in [+0.03,+0.15]. |m| bounds inclusive.
Notional USD = amount × vwap_index.
Per hour h, coin c in {BTC,ETH}:
- NPB(h) = Σ_OTMputs (taker_buy_amount − taker_sell_amount) × vwap_index
- NCB(h) = Σ_OTMcalls (taker_buy_amount − taker_sell_amount) × vwap_index
- BLKp(h) = Σ_OTMputs block_amount × vwap_index; BLKc(h) = Σ_OTMcalls block_amount × vwap_index;
  BLK(h) = BLKp(h) − BLKc(h).
Missing hour (no qualifying rows) → 0.0 for all three (no flow observed).
Hourly frame is reindexed to the full hourly range 2021-01-01..2026-09-24 00:00 UTC (hour starts);
missing hours filled with 0.0.
Denominator D(T) at 4h bar open T = trailing-30-day (720 hourly buckets) mean of
(|NCB(h)| + |NPB(h)|) over hours h in [T−720h, T−1h] (the 720 full hours ending at T),
min_periods 360; if fewer than 360 non-missing hours exist (only at the very start of
history, never inside dev years) F = NaN and the bar is dropped. One shared D per coin
for all three signals (disclosed choice; F2 is NOT normalised by |BLK|).
At each 4h bar open T (standard grid = opens_v154 index):
- F1(T) = Σ_{h in last 24 full hours before T} (NCB(h) − NPB(h)) / D(T)
- F2(T) = Σ_{h in last 24 full hours before T} BLK(h) / D(T)
- F3(T) = Σ_{h in last 4 full hours before T} (NCB(h) − NPB(h)) / D(T)
"Last N full hours before T" = hourly buckets with hour start in [T−N·1h, T−1h].
Since T is on an hour boundary, the bucket [T−1h,T) is the last full hour and is known
at T (hour closed). No hour starting at/after T is used. F2 shares D(T) (same normaliser).
SOL/BNB/XRP use BTC's F1/F2/F3 (market-wide; disclosed everywhere).
ETH coin uses ETH features; BTC coin uses BTC features.

## Descriptive study window (fixed)
Dev years ONLY: bars with open in [2021-09-24, 2025-09-24), partitioned as
[A_k, A_{k+1}) with A = 2021-09-24..2025-09-24 (matches oc_placebo_dip year_of).
Labels/years: Y0=[2021-09-24,2022-09-24), Y1, Y2 (2023-09-24..2024-09-24, 366d incl. Feb-29),
Y3=[2024-09-24,2025-09-24). Never compute or look at forward returns for opens >= 2025-09-24
(most recent year untouched; no G2 overlay in this task).

## (a) BOOK IC (fixed)
Per coin opens o_c[t] on the standard grid. Trailing vol
sigma_c[t] = std of 4h log returns log(o[t]/o[t−1]) over trailing 360 bars ending at t
(min_periods 120, ddof=1); requires o>0 and finite. Forward returns
r1_c[t] = o_c[t+1]/o_c[t] − 1; r6_c[t] = o_c[t+6]/o_c[t] − 1 (open-to-open).
Vol-normalised: z1 = r1/sigma, z6 = r6/sigma (rows with non-finite z or non-finite F dropped
pairwise per (feature, horizon) correlation).
Per dev year × (pooled-5-coins and per coin BTC/ETH/SOL/BNB/XRP) × feature (F1/F2/F3) ×
horizon (z1, z6): Spearman rank correlation + n. Pooled stacks (F, z) pairs across the 5
coins (each coin's own z, F mapped per coin rule above).
Bootstrap CI: moving-block bootstrap over the year's time-ordered pairs, block length
42 bars, n_boot=1000, seed 20261007, statistic = Spearman; report 2.5/97.5 percentiles.
Blocks sampled with replacement to cover the year length (last partial block truncated).
Round-trip cost context: ~4–8 bps; |IC|>=0.02 discussed against that (no P&L claimed).

## (b) DIPS join (fixed)
Reproduce the dip base FIRST: import build_base/score helpers from
research/tournament/oc_placebo_dip/compute_placebo_dip.py (read-only import, no copy) and
run the exact D0+B1 4-phase replica; require base 5y 4-phase-mean sum == 7.718304 ±0.01
(phase-0 raw sums [2.388,0.183,3.810,2.579,0.712] ±0.01, n_fills 22312, checksum
902c5bbfe8fed3c0). If not reproduced, stop and report (no (b) join).
Extension for stop flag: the ledger stores y09/y10/y11 but not exit type; recompute how10
per fill with the same imported outcome_mu on the same 1m windows is NOT re-run here
(to avoid a second 1m pass): instead define stop proxy STOP10 = 1 iff the TP1.0-leg
return satisfies a stop-like loss AND the fill did not take profit — NOT used. DECISION:
run the replica once with an added how10 capture by calling the imported outcome_mu
inside a thin wrapper that reuses build_base source logic? NO — simpler and exact:
(b) uses only y10 (continuous rung outcome, net of maker/taker + settle funding as in
replica) plus a stop indicator derived from the replica's exit-day vs timeout? REJECTED.
FINAL fixed choice: patch-free — re-run build_base-equivalent loop is forbidden duplication;
so (b) computes per-fill how10 by re-invoking imported outcome_mu is impossible without
1m windows. THEREFORE (b) is defined WITHOUT a model-based stop flag:
- Primary: per dev year, pooled over all fills (all 4 phases × 5 coins × 5 rungs),
  Spearman(F1_asof_bar, y10) and Spearman(F3_asof_bar, y10), n fills.
  F_asof_bar = F1/F3 of the traded coin's mapped option coin (SOL/BNB/XRP→BTC) at the
  bar open of that fill (phase-specific open; last full hour before that open).
  Year of fill = ledger year (same anchors; dev years Y0..Y3 only).
- Secondary (tercile table, descriptive only): within each dev year, split fills into
  terciles of F1 (and separately F3) using that year's pooled cutpoints (disclosed
  in-sample cutpoints, descriptive only, never a trading threshold); report per tercile
  mean y10 and loss rate P(y10<0) (labelled LOSS rate, not stop rate, since exit type
  is unavailable without a second 1m pass) + n. Explicitly state the deviation:
  assignment says "stop rate"; exit-type how is not stored by the replica, so loss
  rate P(y10<0) is reported instead with the reason.
No bootstrap for (b) (Spearman + n only).

## Consistency / candidate rule (verbatim from assignment, fixed)
A feature is a CANDIDATE only if its IC has the same sign in >= 4 of 4 dev years for
(a) or >= 4 of 4 for (b), with pooled |IC| >= 0.02. Report all; mark candidates.
NO trading rule is scored in this task (a candidate goes to a separate pre-registered test).

## Leakage statement (how checked)
- Option hourly buckets use only trades within that hour; F(T) uses hours ending ≤ T−1s.
- Denominator D(T) uses hours ending ≤ T−1s only.
- Labels r1/r6/y10 use opens/prices strictly after T.
- No fit: no normalisation fitted on future; tercile cutpoints are within-year
  descriptive summaries (disclosed, not thresholds).
- Dev-only: any row with open ≥ 2025-09-24 is excluded before every correlation.
- Fill timing N/A (no fills in (a); (b) reuses replica fills whose timing was audited upstream).

## G2 note
Common header asks to reproduce G2 baseline before any overlay. This task has no overlay
and scores no trading rule, so G2 reproduction is vacuous; the audited reproduction gate
here is the dip base 7.718304 (phase-0 sums + checksum above).

## Outputs
- `research/tournament/oc_optflow/compute_optflow.py` (features + study),
  `results.json`, `ic_book.csv`, `dips_terciles.csv`, `REPORT.md` (tables + 3-line
  Vietnamese verdict), `SUMMARY.md` (<=15 lines).
- `tests/test_oc_optflow.py`: ≥1 causality/truncation test + ≥1 hand-checked synthetic case.
- Run tests with `.venv/Scripts/python.exe -m pytest tests/test_oc_optflow.py -q`.
- Heavy 1m replica via `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_optflow
  --min-free-gb 2.0 -- ...`. Print progress (watchdog).

## Post-hoc log
(none yet; any change after seeing an outcome is appended here with reason).
