# Book-model refresh plan (oc_bookmodel_plan, 2026-10-06, DESIGN ONLY — no outcomes)

Scope: walk-forward refresh of the BOT/MANUAL **book leg** (the dip sleeve,
agents, and execution are held fixed). The BOT book earns about one third of
the return at trade win rate ~0.52; MANUAL is book-heavy and short of the
5 %/month floor (G2 books dev4 2.50, 2021 losing, win ~0.50–0.52;
research/diagnostics/book_vs_bot). Goal: move the book frontier (return up at
DD <= 20, worst-year up) under the AGENTS.md gate and user cost model
(maker 0.02 % / taker 0.055 %, adverse funding longs 0.01 %/8h, shorts zero).

No training, no Kaggle, no commits, no long runs were done for this plan.
Nothing below was fitted or scored; selection happens only after the
pre-registered runs.

## (a) Inventory of the current book members

Deployed book formula (scripts/forward_v205.py `research_books_d2`):
`D2 = 0.8 × O1 + 0.2 × (D + Dq)/2`, same units throughout.

- **O1 leg** (`research_books_o1`): `0.5×(A+B)/2 + 0.5×(Aq+Bq)/2` where
  A=`member_A_O1_orders.parquet`, Aq=`member_Aq_O1_orders.parquet`
  (A-members = 4h TradingView 17 + **order-level** whale flow, v240 rebuild of
  v236 formulas on `data/raw/aggflow_20260928_orders`; an aggTrade row ≠ an
  order — consecutive same-timestamp/side rows are one taker order),
  B=`member_B_tv.parquet`, Bq=`member_Bq_tv.parquet` (B-members = TV only).
  O1 = v240; its predecessor W2 used fill-level flow in A (v236), T3 used TV
  in all four members (v233).
- **D leg** (Coinbase-premium satellite, the only accepted satellite):
  D=`members_v154.parquet` key `D` (annual) +
  Dq=`members_quarterly_D.parquet` (quarterly), averaged. D = v144 builder +
  v111 Coinbase-premium market features (cb_btc_dev, cb_btc_z, cb_btc_chg,
  cb_eth_z, cb_eth_chg; Coinbase 1h close vs Binance spot 4h close, known at
  the bar close). Live member `v285_CB` logged by scripts/v285_cb_advisor.py.
- **Base builders** (audited, in
  research/parallel/rounds/parallel-20260906-r2/): v92 pooled 5-majors HGB
  long-only (7d vol-normalised target H=42 bars, `y=clip(fwd/(vol42·√H),±4)`,
  2017 spot prefix as training rows only); v94 horizons 18/42/84 long/short
  ensemble; v103 1d/3d short-horizon + taker-flow features; extended panel
  v113/v114 (Bitstamp BTC 2013+, Coinbase BTC 2015/ETH 2016, Binance);
  vol sizing v129, governor v110, quarterly retrain v202 (Aq/Bq/Dq).
  Path-label variant PA (v287: first-touch ±vol42·√h, stop-first, else clipped
  return; corr 0.87 with A) exists as `member_PA_path.parquet` but is NOT in
  the deployed mix.
- **Targets**: v92 7d vol-norm regression; v103 y1d/y3d; D same v144 targets on
  premium-augmented panels.
- **Training windows / embargo (status quo)**: expanding annual (earliest
  available → anchor − embargo; per-asset perp start, 2017 spot prefix for
  majors); quarterly members per v202 schedule. Embargo v92:
  EMBARGO_BARS = H+10·PD = 102 4h bars (~17 d); v103: max(HS)+10·PD; labels
  additionally required realised before the cutoff
  (`t + (H+1) bars < cutoff`). Tournament/GAs use a flat 7-day embargo
  (`t_exit < anchor − 7 d`).
- **Where things live**: frozen deployment models models/frozen/*.pkl
  (manifest.json: v104, v115, v133_vol, v144, v151_opt, v154_cb, v99);
  advisors scripts/v154_advisor.py, v151_advisor.py, v233_advisor.py,
  v236_advisor.py, v240_advisor.py, v285_cb_advisor.py, v287_path_advisor.py;
  member caches artifacts/research/engine_real/ (`members_v154.parquet`
  keys A/B/D 10950×15; `members_quarterly.parquet` keys A/B;
  `members_quarterly_D.parquet`; `member_*_tv*.parquet`,
  `member_*_whale.parquet`, `member_*_O1_orders.parquet`, plus rejected
  satellites `member_sat_*.parquet`, pooled `member_P*.parquet`,
  `member_PT*.parquet`, `member_CT*.parquet`, `member_G_gp.parquet`);
  dip-agent tables `v295_size_mult_m0.parquet`, `v301_g2_table_m0.parquet`,
  `v321_r2_table_m0.parquet`, `v306_gene_tables.parquet`.

## (b) Which feature families were tried, with what result

Source: research map §§v231–v424 + CONTINUOUS_RESEARCH.md v231–v242/v285/v382
entries. One line each; "rejected" = no transfer under the robust criterion.

- **TV indicators** (v231 tv_indicators.py, 17 causal, standard defaults:
  SuperTrend, Squeeze, WaveTrend, VIX-Fix, Ichimoku, anchored VWAP-W/M, POC-180,
  market-structure 3/3, Fisher): V1 in A dev4 5.46 / 5y 5.115 — first
  foundation gain in a long time; T3 (TV in all members) dev4 5.485 / 5y 5.156
  DD 18.41; daily/weekly TV (v234) rejected; premium+F&G with TV (V2/V3)
  dilutes and raises DD (23–25). KEPT (in O1/T3).
- **Whale/order flow**: v236 fill-level flow in A (W2 dev4 5.774, worst 2.491,
  DD 19.51, 5y 5.442, last 4.123) — dev mean + worst year + unseen year up
  together; flow in ALL members (W1) DD 27 rejected; v240 order-level rebuild
  O1 robust best (worst 2.759, DD 19.08, 5y 5.364, last 4.069) KEPT; spot-vs-perp
  (v237) DD 21–22, market-wide flow (v238) DD 22–24, Bybit cross-venue (v244)
  DD 22, spot order flow (v262) DD 22.4, intrabar flow (v252) below O1,
  monthly-retrained flow (v280) dev worse — all rejected; OKX (v253) deferred
  (incomplete history); more features on top of W2/O1 raise DD. Lesson: per-asset
  perp order flow in A only is the useful form.
- **Positioning (OI / long-short)** (v139/v153, um_metrics): IC up 2022–24 but
  hidden year down; satellite H rejected (DD breach); relative positioning
  DD 25. Closed as book members.
- **DVOL / options**: options-flow member helps in ensemble (v150/v151) but
  ETH-options add (v158) and DVOL member (v156, 2.98) dilute; E satellite 1.54 /
  DD 21.7 rejected; DVOL size tilt (v414) more return + more DD; short-leg-only
  screen (oc_dvolshort) pending, not a book member. Closed except via B.
- **Macro / COT / F&G / Korea / basis**: macro member (v157, 2.94), COT (v160,
  2.68), F&G (v159, dilutes), Korea premium K (v230 alone 3.69, dilutes;
  satellite K 2.13 rejected), quarterly basis (v351: dev4 6.55 but DD 22.85 —
  same one-way-exposure pattern as flow extensions) all rejected; event
  blackout, weekend, funding-surprise, premium-flip veto closed.
- **Premium / funding path**: exact 1m premium + predicted funding (MAE
  0.05–0.07 bp) inside A already tested in v231 V2/V3 — worse, do not repeat;
  settlement microstructure (+14–17 bp in the settlement minute) not tradable
  under the minute-5 rule — features only.
- **Accepted**: only D (Coinbase BTC/ETH premium): v285 D2 = 0.8×C4+0.2×D
  dev4 5.864, worst 3.005 (> C4 2.951 → robust pick), DD 18.39, 5y 5.725,
  last 5.167 — first deterministic gate pass (audit + robustness PASS,
  deployed CB). Upgrading D with TV/flow (v286) hurts (diversity > strength);
  per-coin Dc (v290, 2.75) rejected. Path labels: P1 weak edge (+0.05 worst
  year), Q1 no generalisation (v287/v288 closed). Pooled/stack/DL: NNLS
  stacking C≈0 (v283), pooled path/flow members worsen book (v316–v319),
  77-coin pool mean-up/weak-year-down with bigger HGB (v299), GRU/DL 5–6
  failures, spot-spliced history worse (v284). v382: book family CB/O1/T3
  equivalent on the honest harness — no free book gain left in current members.

## (c) Pre-registerable candidates (max 2; close the direction after)

Common rules for C1 and C2 (fixed here): symbols BTC/ETH/SOL/BNB/XRP USD-M
perps, 4h-bar decisions; features causal at the bar close; **embargo 7 days**
(`t_exit` and label-realisation `< anchor − 7 d`; ≥ all horizons used);
**walk-forward folds** anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24
(dev; model for year Y trains only on rows before anchor − 7 d) and
2025-09-24 scored **once** for the frozen finalist; selection ONLY on
2021–2024 per the user rule, with the v204+ robust criterion (DD ≤ 20 and no
losing year in 2021–2024; prefer mean ≥ 5 %/mo if any; among them highest
worst-year monthly; ties → higher mean). **Evaluation = the 4-phase
reset-metric harness** (v376 + research/diagnostics/r2_decompose5/reset_metric.py:
four clock-shifted 0/1/2/3 h sub-books, ¼ capital each, never rebalanced,
reset at each anchor; per-year R, worst year, max-yearly DD and full-path DD
as max(4h-close, 1m-marked incl. open positions); gate costs; report book-only
AND full-pipeline rows with the R2 dip sleeve + agents fixed; plus cost-stress
and latency-15 rows as robustness, not selection). No statistic from
2025-09-24+ feeds any choice.

- **C1 — pooled 77-coin training, fixed architecture, TV + order-flow, 4h/12h
  multi-horizon target.** O1 leg refit with training rows pooled over the 5
  majors + the 72 survivorship-free Dec-2020 perp markets
  (data/raw/alts2020_intraday_20260930, delisted included; alt rows only where
  the coin was listed before cutoff — universe fixed Dec-2020 so no
  survivorship pick-up; 2017 spot prefix for majors as today). Features per
  (t,sym): base v142 xs + TV(17) + v236 order-level flow(6) — NO new feature
  formulas, HGB depth-4 hyperparams unchanged (v299 overfit came from a larger
  HGB; this tests data scale, not capacity). Targets: v92 7d vol-norm panel +
  v103-style 12h (h=3 bars) and 3d short-horizon panel, same weights_ls blend
  structure. Members: annual A/B + quarterly Aq/Bq refit per anchor/quarter;
  books = 0.8×pooled-O1 + 0.2×D (D byte-identical to deployed). Windows:
  earliest available → anchor − 7 d, labels realised before cutoff. Why: v299
  pooled mean was up but weak years/unseen not with bigger HGB; v316/v317
  pooled-TV IC was + in 3/4 dev years — C1 isolates pooled estimation with
  capacity fixed, the one untested combination.
- **C2 — ranking/classification direction target with calibrated sizing, majors
  only.** Same O1 features/windows/embargo/folds/blend as C1 but trained on
  the 5 majors only (isolates the target effect): replace return regression
  with a pairwise listwise rank of the 5 majors' 7d vol-norm returns per bar
  (HGB ranker, same depth-4 budget) + probability calibration (Platt/isotonic
  fit on train folds only) → long/short weights via weights_ls on calibrated
  ranks, vol_target_scale unchanged. Why: book trades are structurally ~50 %
  winners and all profit comes from longs held > 4 days while shorts hedge
  bear years; v112 sign classifiers failed as raw signs but a calibrated
  rank→size mapping is untested and targets worst-year selection directly.
  (Path-label v287/v288 tested a different label; C2 does not reuse it.)

Register C1 and C2 (2 variants, at most); run dev folds; pick per the robust
criterion; score the finalist once on 2025-09-24; report gate + robustness +
book-win rows. If neither passes dev DD/worst-year filters, close the
book-refresh direction without touching the last year again.

## (d) Runtime estimate (measured sample, no long runs)

Measured on this PC (timing samples, each < 1 s, total < 10 min — no training):
member-cache parquet loads 0.06–0.09 s (`member_A_O1_orders.parquet`,
`members_v154.parquet` 10950×15, `members_quarterly_D.parquet`); D2-blend
pandas ops on the same frames < 0.1 s. Reference full-simulation cost from the
repo (kpack): **~4 s per engine_user year-simulation locally** (GA searches
run at this cost; v347 9-weight GA feasible). Expect per candidate: member
training = minutes (HGB on pooled panel; C1 ~10–40× rows of majors-only —
Kaggle CPU handles it; GPU NOT needed — the 5–6 GPU/DL attempts all failed
and HGB is CPU-bound) + evaluation ≈ folds(4) × phases(4) × sim(4 s) ≈
~1–2 min locally, ~2–4 min on Kaggle CPU (±2×), plus quarterly-member and
robustness rows. Plan: heavy refits on private Kaggle CPU (kpack bundle:
prep.npz + member caches + engine_standalone.py, asserts G2 6.504 / manual
2.502 reference rows so env drift stops the run); inference/replay stays on
this PC. No GPU budget requested for C1/C2.

## (e) Leakage checklist (must all PASS; blind audit re-checks)

1. Feature timing: every value at row t uses bars ≤ t close only (TV pivots
   confirmed after 3 right-hand bars; VWAP/POC rolling-only; flow from
   aggTrades with transact-time < close; D premium Coinbase-1h vs Binance-spot
   known at close; F&G-style lags if reused).
2. Label windows: v92 7d / 12h / 1d / 3d forwards realised before the cutoff
   (`t + (H+1) bars < cutoff`); path-style labels not used in C1/C2.
3. Fit windows: all fits (HGB, calibration, vol models, quarterly members, C1
   pool) end before anchor − 7 d embargo; alt rows only where listed before
   cutoff; universe fixed Dec-2020 (no survivorship additions).
4. No feedback: no statistic computed on any test year (incl. 2025-09-24+)
   enters features, labels, normalisation, calibration, thresholds, weights,
   or candidate choice; most-recent year scored once for the finalist.
5. Fill timing: signal at t fills ≥ t+1 (book limits minute-5+ trade-through,
   SL market / TP limit both attached, stop-first in same bar; no market
   fallback for entries).
6. Embargo ≥ horizon: 7 d embargo ≥ 7 d max horizon (plus the +1-bar and
   +10·PD margins inherited from v92/v103 formulas).
7. Replay parity: member caches bit-identical rebuild; live vs research
   feature code identical (corr 0.98–0.99 precedent); audit runs truncation +
   future-correlation + fit-window checks and the engine replay before any
   deployment claim.
