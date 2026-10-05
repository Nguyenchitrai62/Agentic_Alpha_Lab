# PLAN.md — oc_newinfo: two untried public information sources (pre-registered 2026-10-05, BEFORE any outcome statistic)

Scope note: this task's brief (`docs/opencode/OPENCODE_NEWINFO_WIKI_CME.md`) explicitly permits market data up to
2026-09-24 00:00 UTC (all five anchor years are research data; the clean test of anything found is prospective).
That overrides the default tournament hidden-year rule for THIS study only. No outcome statistic (IC, return,
correlation with any market label) has been computed at the time of writing; only source-availability checks
(Wikipedia title resolution + Jan-2025 view counts, API reachability) were done to fix definitions below.

## Hypotheses
- H1 (Wikipedia attention): abnormal retail attention to a coin's Wikipedia article predicts near-term
  continuation (FOMO/momentum) or reversal (exhaustion). Direction is NOT pre-registered; the sign test decides.
- H2 (CME weekend gap): the Friday-settle → Sunday-reopen gap (stale CME close vs 24/7 spot) predicts the
  Monday-week drift direction (gap-fill continuation/reversal). Direction is NOT pre-registered.

## Sources (raw → data/raw/newinfo_20261005/ + manifest.json with URLs + sha256)
- N1: Wikimedia REST per-article API, en.wikipedia, access=all-access, agent=user,
  `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{ART}/daily/{YYYYMMDD}/{YYYYMMDD}`,
  with `User-Agent: AgenticAlphaLab/1.0 (research contact local)`, 2016-01-01..2026-09-23, monthly chunks, ≥5 s
  between requests with retry/backoff. Title mapping (fixed from MediaWiki redirect resolution + Jan-2025 views):
  BTC→`Bitcoin`, ETH→`Ethereum`, SOL→`Solana_(blockchain_platform)` (82.5k/mo; `Solana` is a stub),
  BNB→`Binance` (exchange article; `Binance_Coin` redirects to `Binance#BNB`, `BNB` is a disambiguation page,
  no standalone coin article exists — EXCHANGE-CONFOUNDED, disclosed caveat),
  XRP→`XRP_Ledger` (34.8k/mo canonical; `XRP` and `Ripple_(payment_protocol)` redirect there; `Ripple_Labs`
  is the company, NOT used).
- N2: CME front-month continuous via Yahoo Finance chart API (`BTC=F`, `ETH=F` — ETH futures exist from
  2021-02-08, covering all five test years), daily interval, full history; document URL + payload in manifest.
  Friday settlement proxy = Friday daily-bar close (CME 16:00 CT settlement; Yahoo daily close is the proxy).
  Sunday reopen = Binance {BTC,ETH}USDT hourly bar open at 22:00 UTC (US daylight time) else 23:00 UTC
  (CME Globex Sunday 17:00 CT; DST rule: second Sunday of March → first Sunday of November = 22:00 UTC).

## Feature definitions (availability lags fixed)
- N1, day D usable from D+1 00:00 UTC only; all trailing windows end at D-1 (strictly before D):
  - `wiki_z90` = (ln(V_D+1) − mean90) / std90 over D−90..D−1 (std floored at 1e-6; first 90 days of history NaN).
  - `wiki_chg7` = ln(V_D+1) − ln(mean(V_{D−7..D−1})+1).
  - `wiki_share` = V_coin,D / Σ_5 V_D (level; cross-coin attention share).
- N2, per weekend w (Friday settle F, Sunday reopen R, trailing daily sigma s from Binance daily log returns
  over the 90 days ending Friday, strictly causal):
  - `gap_sigma` = ln(R/F) / s; `gap_abs` = |gap_sigma| (signed + magnitude = the 2 fixed N2 features).
  - `gap_fill_MF` (descriptive only): 1 if Mon–Fri hourly range touches F, else 0 → reported frequency/year.

## Labels (Binance, from research/tournament/ext/hourly_ext.parquet hourly opens)
- Daily 00:00 UTC opens per coin (hourly bar open at 00:00 UTC; 4h opens coincide at 00/04/…/20 UTC).
- N1: per (coin, D): y1d = ln(O_{D+2}/O_{D+1})/s30_D, y7d = ln(O_{D+8}/O_{D+1})/s30_D, s30 = trailing-30d std of
  daily log returns ending D (causal). Feature D (known D+1 00:00) → forward from D+1 open. No overlap handling
  needed for rank IC.
- N1-monthly (secondary): monthly mean `wiki_z90` per coin (pooled mean) vs dip-sleeve `edge` from
  research/tournament/oc_regime/monthly_main.csv; Spearman per anchor year (n≈12, low power, disclosed).
- N2: per weekend: y1d from Monday 00:00 UTC open, y7d Monday→next Monday, /s30 (causal). Pooled BTC+ETH.

## Tests (anchors A ∈ {2021,2022,2023,2024,2025}-09-24, window [A, A+365d))
- Per year per feature: Spearman IC over pooled observations (N1: coins×days; N2: BTC+ETH weekends).
- Leave-one-year-out sign test: sign(IC on other 4 years pooled) must equal sign(IC on held-out year).
- DECISION RULE (fixed): PROMISING iff (i) same IC sign in ≥4/5 years AND (ii) |mean IC| ≥ 0.03 AND
  (iii) LOYO sign holds in ≥4/5 held-out years. All 3 must hold. `gap_fill_MF` has no decision rule (reported).
- Per-coin IC tables reported for N1 (BNB caveat visible). Cost context: ~4–8 bps round-trip.

## Causality
- `features_wiki.py` / `features_cme.py` expose pure functions of (history → features_at_D); tests truncate
  input history at 20 random days and assert identical rows (assert-style, no market labels after D 00:00 UTC).
- Embargo: trailing windows only; labels start at D+1 open (N1) / Monday open (N2).

## Deliverables / resources
- `research/tournament/oc_newinfo/`: PLAN.md, `fetch_wiki.py`, `fetch_cme.py`, `features_wiki.py`,
  `features_cme.py`, `analyze.py`, `results.json`, `REPORT.md`. Raw → `data/raw/newinfo_20261005/` + manifest.
- `tests/test_oc_newinfo.py`. One process, RAM < 2.5 GB. No commits, no leader-file edits.
