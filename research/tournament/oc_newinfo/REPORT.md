# REPORT.md — oc_newinfo: Wikipedia attention (N1) + CME weekend gap (N2)

## Data (raw: `data/raw/newinfo_20261005/`, 79 files + `manifest.json` with URLs + sha256)
- N1: Wikimedia per-article API (en.wikipedia, all-access/user, `User-Agent` header), daily 2016-01-01..2026-09-23.
  Titles fixed from redirect resolution BEFORE any outcome stat: BTC→Bitcoin, ETH→Ethereum,
  SOL→Solana_(blockchain_platform) (created 2021-09-10; `Solana` is a stub), BNB→Binance (**caveat:** exchange
  article — `Binance_Coin` redirects to `Binance#BNB`, `BNB` is a disambiguation page, no standalone coin article),
  XRP→union of XRP_Ledger + Ripple_(payment_protocol) + XRP (article lived at the old title until Nov-2024 move).
- N2: Yahoo chart API daily `BTC=F` (from 2017-12-18) + `ETH=F` (from 2021-02-05; covers all test years).
  Friday bar close = settlement proxy; Sunday reopen = Binance hourly open 22:00 UTC (US DST) else 23:00 UTC.
- Labels: Binance hourly opens (`research/tournament/ext/hourly_ext.parquet`), 5 majors, to 2026-09-23.
  27,179 N1 panel rows; 504 N2 weekends (102/102/102/102/96 per anchor year).

## N1 daily (pooled coins×days; Spearman IC per anchor year [21,22,23,24,25], n≈1800/yr)
| feature→label | 21 | 22 | 23 | 24 | 25 | mean | sign≥4 | \|mean\|≥.03 | LOYO≥4 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| z90→1d | +.034 | −.016 | +.003 | +.028 | −.065 | −.003 | 3/5 | no | 0/5 | NOT_PROMISING |
| z90→7d | +.105 | −.057 | +.045 | +.006 | −.071 | +.006 | 3/5 | no | 1/5 | NOT_PROMISING |
| chg7→1d | −.005 | +.005 | −.000 | +.043 | −.050 | −.002 | 3/5 | no | 2/5 | NOT_PROMISING |
| chg7→7d | +.037 | −.057 | +.048 | +.020 | −.057 | −.002 | 3/5 | no | 0/5 | NOT_PROMISING |
| share→1d | −.006 | +.016 | +.007 | −.017 | +.009 | +.002 | 3/5 | no | 1/5 | NOT_PROMISING |
| share→7d | −.021 | +.046 | +.023 | −.028 | +.032 | +.010 | 3/5 | no | 3/5 | NOT_PROMISING |
Daily Wikipedia attention has no stable pooled edge; signs flip across years (esp. 2025 anchor).

## N1 monthly attention vs dip-sleeve edge (monthly mean z90 pooled vs `monthly_main.csv` edge, n=12/yr)
IC by year: +.154, −.378, +.371, +.462, +.343 → 4/5 same sign, mean +.190, LOYO 4/5 → **PROMISING by rule**.
**Fragility warning:** n=12/year (SE≈0.30), so the |mean IC|≥0.03 bar is trivially cleared by noise; hypothesis only.
Clean test = prospective monthly log.

## N2 gaps (BTC+ETH weekends; Spearman IC per anchor year, n≈100/yr)
| feature→label | 21 | 22 | 23 | 24 | 25 | mean | sign≥4 | \|mean\|≥.03 | LOYO≥4 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| gap_σ→1d | +.020 | +.074 | +.215 | −.140 | −.182 | −.003 | 2/5 | no | 0/5 | NOT_PROMISING |
| gap_σ→7d | +.053 | +.091 | +.180 | −.178 | +.040 | +.037 | 4/5 | yes (.007 margin) | 4/5 | PROMISING by rule, FRAGILE |
| \|gap\|→1d | −.116 | −.088 | +.019 | −.069 | +.214 | −.008 | 3/5 | no | 0/5 | NOT_PROMISING |
| \|gap\|→7d | +.119 | −.049 | +.079 | +.020 | −.057 | +.022 | 3/5 | no | 2/5 | NOT_PROMISING |
No Monday effect. gap_σ→7d passes the letter of the rule (positive drift after upward gaps) but rests on a
0.007 margin above threshold with one strongly dissenting year (2024: −.178, both coins) — needs prospective test.
Mon–Fri gap-fill frequency: 80/83/69/81/81% per year, 79% overall (504 weekends) — gaps usually fill, yet the
7d drift sign is continuation, not reversal (weak).

## Verdicts per feature
- PROMISING by fixed rule (both fragile, prospective test required): `N1 monthly z90 vs edge`, `gap_sigma→7d`.
- NOT_PROMISING: all 6 N1 daily, `gap_sigma→1d`, `gap_abs→1d/7d`. No tradability claim: ICs ≈ 0.01–0.04 on
  σ-normalised labels are far below a 4–8 bps round-trip edge; nothing here graduates to the pipeline.

## Post-hoc changes (all before outcome stats; definitions in PLAN.md untouched)
1. 404 yearly chunks (article not yet created) stored as explicit empty payloads.
2. XRP = 3-title union after finding the article lived at `Ripple_(payment_protocol)` until Nov 2024
   (source-completeness fix; without it XRP 2022–2024 would be near-empty).
3. Causality tests: 20 random truncation days (wiki, real data); DST unit cases + synthetic truncation (CME).
   `tests/test_oc_newinfo.py`: 6 passed.
