# v181 blind-audit comparison

Verdict: REPLICATED. Independent implementation matches
research/parallel/rounds/parallel-20260906-r2/v181/v181_result.json on every
reported field to rounding (fills exact; means/sleeve/DD within 0.05).

## Part A (blind, before opening v181)

- Re-implemented from the assignment text only into
  research/parallel/rounds/parallel-20260906-r2/v181_audit/replicate_v181.py.
- Saved research/parallel/rounds/parallel-20260906-r2/v181_audit/replication.json
  before reading anything under v181/.
- Conventions fixed blind and documented in replication.json spec block:
  sigma = sample std (ddof=1) of 360 4h open pct-changes ending at t, min 120;
  fill window = 1m open_times in [T+16min, T+238min], strict low < L, missing
  minutes never fill; funding = fundingRate summed by fundingTime floored to 4h
  at bucket T+4h; s_out from 1m minute 0 of T+4h with 0.0002 fallback;
  anchor membership by T in [anchor, anchor+365d); sleeve w = 0.0625 per filled
  (asset, rung), equity compounded per-T from 1.0, DD peak-to-trough %.

## Numeric comparison (mine vs v181, normal costs)

- 2021-09-24: fills 1032 = 1032; mean 49.9 = 49.9; sleeve 35.04 = 35.04; DD 10.22 = 10.22
- 2022-09-24: fills 1129 = 1129; mean 14.4 = 14.4; sleeve 8.68 = 8.68; DD 17.52 = 17.52
- 2023-09-24: fills 1438 = 1438; mean 53.1 = 53.1; sleeve 54.89 = 54.89; DD 14.25 = 14.25
- 2024-09-24: fills 1019 = 1019; mean 43.6 = 43.6; sleeve 30.27 = 30.27; DD 13.07 = 13.07
- 2025-09-24: fills 1109 = 1109; mean 16.6 = 16.6; sleeve 9.17 = 9.17; DD 20.28 = 20.28
- Pooled normal 36.11 vs 36.1 bps over 5727 fills; pooled stress 27.09 vs 27.1 bps.
- Per-asset means match to 0.1 bps in all 5 years x 6 assets x 2 scenarios.
- Criterion passes both ways: 5/5 normal years > 0, stress pooled > 0.

## Implementation differences found (all immaterial here)

- v181 masks anchor years on t (= T-4h); mine masks on T. Fill counts are
  identical, so no fill falls on any boundary bar; means agree to <0.05 bps.
- v181 builds a 4h x 240 1m cube and uses nan->inf / nan->0 guards; mine uses
  searchsorted + explicit missing-minute and missing-exit-minute-0 handling.
  Same economics; only 6 exit minute-0 fallbacks total (1 per symbol).
- v181 pooled window is t >= 2021-09-24; mine is T in the 5 anchor windows.
  Same 5727 fills; edge bars empty as above.

## Adversarial data checks

- Duplicates/bad rows: 0 duplicated 1m open_times, 0 duplicated 4h bars, 0
  bars with high < low or non-positive open/close, for all six symbols.
- Manifest missing minutes (DOGE 156, AVAX 220) are pre-listing archive gaps;
  every evaluated fill window had all 223 minutes present.
- 1m/4h alignment: 4h open equals the same-timestamp 1m open at median 0 bps
  for all symbols (p99 0 bps; at most 2 bars per symbol above 5 bps, max
  13.9 bps on one 2020 ADA bar). No systematic misalignment.
- Funding floors to 00/08/16 UTC as expected; summed at T+4h per spec.

## Ten largest rung returns (are they real moves?)

- Global top-10 are all OUTSIDE the anchor windows and do not inflate reported
  means: 2021-01-28/29 DOGE meme squeeze (+3329 to +3893 bps), 2021-05-19 crash
  (+2388 to +3908 bps), 2020-03-13 COVID crash (TRX +2522 bps), 2021-01-02.
- In-anchor top-10 (normal): 2024-03-05 DOGE (+1599 to +1964 bps, 4 rungs),
  2022-06-14 LINK (+1322 to +1640 bps, 3 rungs), 2024-04-13 DOGE (+1300/+1501
  bps), 2024-08-05 ADA (+1267 bps). Forensics: each dip spans several minutes
  (2-6 minutes within 0.2% of the window low, neighboring minutes also
  depressed), exits match the 1m minute-0 opens, and each maps to a known
  stress event (Mar-2024 meme flush, Jun-2022 bear-market flush, Apr-2024
  weekend selloff, Aug-2024 yen-carry unwind). Real dislocations, not bad ticks.
- Concentration note: the same 4h bucket fills up to 4 rungs x 6 assets at once
  (max 24 x 0.0625 = 1.5x sleeve notional), and in-anchor leaders cluster in a
  few buckets; the mean is broad (5/5 years positive) but DOGE-heavy while TRX
  is negative in 3/5 normal years.

## Tuning-risk assessment

- Parameters (k grid 2.5/3/3.5/4, sigma 360, offsets 16..238, s_out, funding,
  anchors, sleeve, criterion) were frozen on the majors (v171-v180) per the
  v181 header, not re-chosen on these six assets: no within-asset tuning
  surface was exercised here.
- Residual risks, not disproven by this audit: (a) out-of-universe but NOT
  out-of-time (same 2021-2026 regime, shared crash buckets); (b) asset
  selection (six liquid perps with a full 1m archive) is itself a selection;
  (c) per-asset heterogeneity (TRX negative, LTC ~0 in two years) argues
  against a uniform mechanism; (d) the header criterion text says pooled mean
  in 4/5 years while the assignment says mean > 0 in 4/5 years + stress pooled
  > 0 -- results pass both wordings, but the wording should be fixed.
- Audit tests: tests/test_v181_audit.py (8 tests) pass.

No leader files edited. No v181 files edited.
