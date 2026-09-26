# v173 blind audit — COMPARISON (Part B)

Blind Part A (`replication.json`) was saved before opening `v173/`.
Independent implementation from `OPENCODE_V173_AUDIT.md` only
(+ `engine_real`/v144/v135/v110/v92 for books/context/W60 execution, as in the v172 base).

## Numbers: worker vs blind replication

Sleeve alone per anchor (worker `sleeve_alone` vs audit `per_anchor`):

| anchor | train (w/a) | test (w/a) | taken (w/a) | IC (w/a) | sleeve net% (w/a) | sleeve dd% (w/a) |
|---|---|---|---|---|---|---|
| 2021-09-24 | 1568 / 1581 | 927 / 927 | 306 / 339 | 0.0790 / 0.0817 | -8.97 / -6.68 | 16.39 / 16.42 |
| 2022-09-24 | 2489 / 2502 | 836 / 836 | 272 / 284 | 0.1074 / 0.1088 | 3.38 / 2.47 | 15.17 / 16.84 |
| 2023-09-24 | 3331 / 3344 | 1073 / 1073 | 351 / 350 | 0.1749 / 0.1762 | 29.77 / 36.40 | 11.08 / 11.01 |
| 2024-09-24 | 4404 / 4417 | 933 / 933 | 288 / 280 | 0.1104 / 0.1032 | 5.04 / 3.07 | 13.99 / 15.76 |
| 2025-09-24 | 5334 / 5347 | 1062 / 1062 | 327 / 318 | 0.1383 / 0.1439 | 7.91 / 3.15 | 9.38 / 10.17 |

Combined books+sleeve, engine_real W60, target 0.25, governor:

| | monthly% | full-path DD% |
|---|---|---|
| worker `primary_books_plus_model_sleeve` | 3.98 | 25.12 |
| blind replication `combined` | 3.918 | 25.43 |
| books alone W60 (both agree) | 3.802 | 18.93 |
| worker reference v172 rule sleeve | 4.597 | 22.42 |

Yearly nets agree in ranking (2023 best: worker 151.59 vs audit 165.16;
2021 worst: 9.2 vs 13.91). All sleeve signs match per anchor.

## Why the small deltas (all pre-registered edge choices, see replicate docstring A1–A18)

1. Exit base: worker uses 4h `open(T+4h)`; audit uses 1m open at minute 0 of
   `T+4h` with 4h fallback (usually identical; differ on missing/divergent minutes).
2. NaN features: worker passes NaNs to HGB (native support); audit imputes
   neutral fallbacks (r5/r15/rng 0.0, vspike 1.0, taker15 0.5, btc_depth 0.0).
3. Asset code: worker single ordinal int; audit 5 one-hot cols (spec column order).
4. 1m dedup: worker keep-first; audit keep-last (as v172 audit).
5. Zero-volume guards: worker `v5/max(vbase,1e-9)` can spike; audit falls back neutral.
6. Train count +13/anchor in audit: sigma warmup on full 4h history vs worker's
   grid-truncated rolling (test points match exactly, so no window error).

None of these change the economic conclusion.

## Look-ahead check (worker `v173_rebound_model.py`)

- depth/c/m: minute-m close — at or before m. OK.
- r5/r15/vspike/taker15/rng: minutes <= m. OK.
- breadth/btc_depth: same wall-clock minute m across assets. OK.
- trend/r1d/sigma/open(T): 4h opens <= T (bar open, m >= 16). OK.
- funding feature: ffill of settled rates at or before t. OK.
- label y: entry m+1, exit/funding at T+4h — strictly after m. OK.
- cutoff: train `T+4h < anchor-1d`, test `t in [anchor, anchor+365d)`;
  embargo (1d) > horizon (4h); no train/test overlap. OK.
- Normalizers (sigma/trend rolling, funding ffill) are causal.
- No future-bar data in any feature; `book_w` built but dropped before fitting.

**No look-ahead found.**

## Verdict

Replication confirms the worker's result within edge-case tolerance:
IC positive every anchor (0.08–0.18, ranking works), pred>0 takes ~300
marginal events/yr, sleeve alone mixed (2021 negative), combined
~3.9–4.0%/mo at ~25% DD — below books-alone DD (18.93) and below the v172
rule sleeve (4.597/22.42). The worker's own conclusion ("rejected; ranking
works, the entry threshold is too lax") is supported by the independent
replication. Manifest already `rejected`, `live_approved: false` — no change requested.
