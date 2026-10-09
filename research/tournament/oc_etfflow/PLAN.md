# oc_etfflow PLAN (pre-registered BEFORE any outcome is computed — 2026-10-07)

Idea B2 of docs/opencode/IDEAS_20261007c.md: ETF-outflow book-long throttle.
SHORT-SPAN study: US spot BTC+ETH ETF flows exist only 2024-01-11 .. 2026-09-23.
NO dev4 (2021-2024) selection is possible. Everything below is descriptive /
overlap-only. No deployment from this span.

## Pre-registered variants (ONLY these; no additions after outcomes)

- G2 = deployed reference `R2B1D17BFG2` (v421 RUNS: rule inv, k 1.0, kd 1.7,
  bear True, G 2.0). Must reproduce v421_result.json G2 exactly first
  (5.41 %/mo 5y reset mean, W 2.588, DD 16.91, full-path DD 16.82).
- T1 = G2 + halve BOOK long weights (x0.5) while S5 < trailing p5.
- T2 = G2 + halve BOOK long weights (x0.5) while S5 < trailing p10.
- C0 = G2 + constant BOOK long weights x0.95 on every bar (exposure-matched
  constant control; ~matches T2's ~10% gated x0.5 ≈ 5% mean cut; T1's mean
  cut ~2.5% is reported alongside for interpretation).

No variant picking on any year. Both T1/T2 (+C0) are reported descriptively
on overlap years only. The most-recent-year rule still applies: 2025-09-24 ..
2026-09-23 is scored once, together with the rest, no re-pick.

## Data (fixed)

- Source: https://farside.co.uk/btc/ and https://farside.co.uk/eth/ , one GET
  per page only (single small fetch, respect robots/terms, no heavy scraping).
  If either page is not machine-readable or blocked, try ONE alternative free
  source (CoinGlass public ETF page or Stooq/Yahoo proxy) and stop if none
  works (report failure, no engine run).
- Saved: `data/raw/etf_flows_20261007/btc_etf_flows_daily.csv`,
  `eth_etf_flows_daily.csv` with columns `date,total_net_flow_usd_m`
  (date = US trading day D, YYYY-MM-DD; total = summed per-ETF US$m that day),
  plus `manifest.json` (source URLs, fetch UTC time, sha256 of each CSV,
  row counts, date span, robots note).
- Availability (conservative, fixed): flows for US trading day D are known
  from D+1 08:00 UTC. No bar with close < D+1 08:00 UTC may use D's value.

## Signal (fixed, causal)

- Trading-day index: sorted unique dates present in EITHER csv (US ETF trading
  days; weekends/holidays absent = no publication). Combined daily flow
  F(D) = BTC(D) + ETH(D), missing side on a listed day treated as 0.0 only if
  that side's csv has no row for D but the other side does (both missing = no
  trading day, excluded from index).
- Published-as-of: value F(D) usable for 4h bars with close_time >= D+1 08:00 UTC.
- S5(B) at 4h bar B (close time t): let D*(B) = max trading day D with
  D+1 08:00 UTC <= t. S5(B) = sum of F over the last 5 trading days <= D*(B).
  If fewer than 5 published days exist as of B, S5 = NaN (gate OFF).
- Trailing distribution: H(B) = {S5(b) : b is a 4h bar with close < t, and
  S5(b) finite}, restricted to distinct trading-day D*(b) values, last 250
  values (min 120). Quantiles p5(B), p10(B) = linear-interpolated percentiles
  of H(B). If |H(B)| < 120, gate OFF (fail-safe, early span).
- Gates (global, all 5 book syms): T1_ON(B) = finite S5 and |H|>=120 and
  S5(B) < p5(B); T2_ON(B) = S5(B) < p10(B). Shorts untouched.
- z-score (diagnostic only, not a gate): z(B) = (S5 - median(H)) / (p90-p10
  spread of H, floored at 1e-9); reported in panel, never used for weights.

## Engine judgement (fixed, exactly like v426_book_brake.py)

- Base: G2 config on standard book rows: v426 worker steps — research_books_d2
  (forward_v205), BTC 1200-bar bear filter (longs x0.5 where bear), THEN the
  ETF gate (longs x0.5 where gate ON), BEFORE the shifted-clock forward fill.
  Per (T,sym) long-weight multiplier on STANDARD rows only; shorts/flats
  bit-identical. Rows before 2021-09-24 never gated. C0 applies x0.95 to
  every standard-row long weight instead of the gate.
- 4-phase engine (shifts 0..3), gate costs: maker 0.0002 (limit entries/TP),
  taker 0.00055 (stops/market exits); longs pay 0.0001 per 8h settlement held
  (00/08/16 UTC), shorts zero; limit fills only on 1m trade-through, no fill
  in first 5 min after a 4h close; stop-first if SL+TP same 1m bar.
- Runs via shared semaphore:
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_etfflow
  --min-free-gb 2.0 -- <cmd>`; never --leader. Reproduce G2 first (f=0 style
  check vs v421_result.json to the digit); if G2 does not reproduce, stop.
- Metrics: reset_metric.year_reset per anchor year (fresh 1.0) R (%/mo
  geometric) / DD, plus v421 continuous full-path DD. Report per overlapping
  anchor year ONLY: 2023-09-24 year (partial overlap from 2024-01-11, labelled
  PARTIAL), 2024-09-24 (full), 2025-09-24 (full, labelled scored-once). Also
  report number of gated 4h bars and gated weeks (distinct Mon-Sun UTC weeks
  with >=1 gated bar) per year, and realized mean long multiplier per variant.
- 2021/2022 anchor years: no ETF data → gate OFF everywhere → T1/T2/C0-vs-G2
  deltas are zero by construction there (still run through engine for
  completeness, reported as NO-DATA). No dev4 mean/W/DD selection is computed
  or used.

## Leakage checks (stated in REPORT.md)

- Feature timing: S5(B) uses only F(D) with D+1 08:00 UTC <= close(B);
  H(B)/p5/p10 use only S5(b) with close(b) < close(B); no row >= B.
- Fit windows: no pooled fit; trailing-only quantiles (250, min 120).
- Label windows: engine forward returns start at next 4h open after close.
- Fill timing: engine_user 5-min ban + 1m trade-through (inherited from engine).

## Deliverables

- `research/tournament/oc_etfflow/`: PLAN.md (this file), fetch script,
  signal/engine scripts, `panel.parquet` (per-4h-bar S5/p5/p10/gates),
  `results.json`, `REPORT.md` (per-year overlap table + gated-week counts +
  exposure control + 3-line Vietnamese verdict: at best "log prospectively").
- `data/raw/etf_flows_20261007/`: two CSVs + manifest.json.
- `tests/test_oc_etfflow.py`: >=1 causality/truncation test + >=1 hand-checked
  synthetic case; run with `.venv/Scripts/python.exe -m pytest <file> -q`.

## Post-hoc log

- (none yet; any change after outcomes adds a disclosed extra row, original kept)
