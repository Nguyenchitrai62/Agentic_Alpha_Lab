# oc_cashcarry PLAN (pre-registered BEFORE any outcome is computed)

Question: can idle equity earn a locked cash-and-carry basis (long spot +
short quarterly delivery future, held to delivery) without hurting the BOT?
Gate cost context (AGENTS.md 2026-09-27): entries/TPs maker 0.02%, stop/market
taker 0.055%; funding rule makes the PERP carry sleeve earn nothing. That
funding rule is IRRELEVANT here: quarterly DELIVERY futures pay NO funding;
the basis is locked at entry and realised at delivery. Fees below are the
assignment's own cash-carry fees, not the gate maker/taker pair.

## Data (fixed here, read-only, 4h only, RAM < 2 GB)

- Quarterly delivery 4h closes: `data/raw/qbasis_20261003/um_BTCUSDT_*_1h.parquet`
  and `um_ETHUSDT_*_1h.parquet` (Binance USDT-margined QUARTERLY delivery
  contracts from data.binance.vision, see `manifest.json`). These are the
  delivery futures (no funding). `cm_*` coin-margined files are NOT used.
  Resample to 4h by taking, for each spot 4h bar, the last 1h close with
  1h open_time < spot bar close_time (strictly causal; 4h closes only).
- Spot majors 4h: `data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet` and
  `ETHUSDT_spot_4h.parquet` (Binance SPOT 4h; open_time-indexed bars).
  BTC and ETH ONLY: the only majors with quarterly delivery data in
  `data/raw/qbasis_20261003` (SOL quarterlies start 2024-09, BNB/XRP are
  cm_ coin-margined; assignment says BTC and ETH only — state: BTC + ETH).
- No 1m data is loaded. No re-download. Market data up to 2026-09-23 may be
  read (all five anchor years are research data; findings need prospective
  validation like everything else).
- Margin context (read-only): `docs/DEPLOYMENT_PLAN_VI.md` §5 (Bybit unified
  cross margin, Hedge Mode, 5x on all coins; G2 `--dip-gross-cap 2.0`),
  `research/tournament/oc_margin/{PLAN,REPORT,results}.json`,
  `research/tournament/oc_kpi_g2/barsum_s{0..3}.parquet` (phase 4h book_gross
  + equity) and `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl`
  (phase 4h BOT equities, G2 arm) if present, else an analytic bound
  (results.json states which path was used).

## Delivery / settlement (fixed)

- Contract code `um_<COIN>_<YYMMDD>` delivers at 08:00 UTC on 20YY-MM-DD
  (matches every manifest `last_open_time`; all codes fall on quarter-end
  Fridays). Delivery timestamp D is exact and known from the code at entry.
- Settlement = delivery index, modelled as the SPOT 4h CLOSE of the spot bar
  containing D (first spot bar with open_time <= D < close_time; its close).
  If D is beyond the last spot bar, the trade is INCOMPLETE and excluded
  (counted separately, no P&L imputed). No other settlement model.

## Roll / entry rule (fixed, causal)

- Per coin, sort expiries ascending: C_0..C_{N-1} with deliveries D_0..D_{N-1}.
- For contract k >= 1: candidate entry E_k = round_UP(delivery(k-1) - 7 days)
  to the next spot 4h open_time ("enter the next-quarter contract when the
  current one has <= 7 days left"). For k = 0: E_k = first availability.
- Actual entry bar T_k = max(E_k, first spot 4h bar with BOTH a spot close
  AND a resampled quarterly-4h close for contract k available at its close).
  Exactly one entry opportunity per contract. All information used
  (F_entry, S_entry) comes from 4h closes with close_time <= T_k close.
- Annualised basis at entry:
  ann_basis = ln(F_entry / S_entry) * 365 / DTE_days,
  DTE_days = (D_k - close_time(T_k)) / 86400s.
- ENTER the pair iff ann_basis >= 0.04 (4 %/yr, fixed threshold, no tuning).
  Else SKIP that contract (no position that quarter). The threshold, the
  7-day roll and the hold-to-delivery are frozen here; no variant is tested.

## Position / hold / fees (fixed)

- Per ENTERED coin-contract: buy SPOT and SHORT the quarterly in EQUAL
  notional, each leg = f x Eq_entry, with Eq_entry = 1.0 indexed unit
  (returns scale linearly; rows f = 0.25 and f = 0.5 are the SAME trades,
  P&L multiplied by f). f is PER COIN pair: if BTC and ETH are both open,
  total carry spot notional = up to 2f, total short notional = up to 2f
  (total carry gross up to 4f). Stated explicitly.
- Hold to delivery D_k. No early exit, no stop (the hedge is delivery-locked;
  MtM is tracked for information only). Positions for different contracts of
  the same coin never overlap by construction (entries are >= ~84 days apart).
- Fees (assignment-fixed): spot 0.001 per side (buy at entry, sell at
  delivery), futures 0.00055 entry short, 0.0002 delivery settlement.
  Fee drag per pair = f*Eq_entry*(0.001+0.001+0.00055+0.0002)
  = f*Eq_entry*0.00275. No funding leg (delivery futures pay none).
- Per-trade net P&L (USDT per Eq_entry=1):
  P&L = f * [ (S_del - S_entry)/S_entry + (F_entry - S_del)/F_entry - 0.00275 ],
  where S_del = settlement spot close. Return on ALLOCATED capital
  ret_alloc = P&L / f (independent of f). Locked gross = (F_entry-S_entry)
  terms above; net = gross - 0.00275.

## Per anchor year reporting (fixed)

- Anchors A_k = 2021..2025-09-24, year Y_k = [A_k, A_k + 365d), grouped by
  ENTRY bar open_time. Incomplete (undelivered by last spot bar) trades are
  listed but excluded from year stats.
- Per coin per year and per year total: n_entered, n_skipped, mean ann_basis
  at entry, mean DTE, mean ret_alloc, total ret_alloc sum.
- Contribution to the ACCOUNT at allocation f:
  contribacct(f) = f * (sum of ret_alloc over trades entered in Y_k),
  reported as total % over the year and as %/month = total/12. (Indexed
  equity, ignores intra-year compounding; exact for small returns; linear
  in f so both rows are shown.)
- Worst mark-to-market of the pair (basis widening): at each 4h close t in
  (T_k, D_k]: mtm_alloc(t) = (S(t)/S_entry - 1) + ((F_entry - F(t))/F_entry)
  - 0.00155 (entry fees paid: 0.001 + 0.00055; exit fees not yet paid).
  Per-trade worst = min_t mtm_alloc; year worst = min over trades; account
  units = f * worst. This is the incremental DD the carry sleeve could add
  if the BOT equity were flat.
- 5-year summary: same stats pooled + geometric-mean %/month equivalent of
  the carry sleeve alone at each f (compounded from contribacct yearly
  totals), for the verdict only.

## Margin interaction (fixed)

- Bybit unified cross margin, Hedge Mode, leverage 5x on all coins (runbook
  `docs/DEPLOYMENT_PLAN_VI.md` §5: 5x is the minimum setting that never
  blocks; IM = notional / 5; blocked iff IM > 95% of equity).
- Haircut assumption (ASSUMPTION — no Bybit spot-haircut table was found in
  this repo; marked as such in REPORT.md): spot BTC counts as collateral at
  95% of mark (5% haircut), spot ETH at 90% (10% haircut). The short quarterly
  needs initial margin at 5x on its current mark
  (IM_short(t) = short_mark(t)/5). Spot longs need no IM (they ARE collateral).
- Check at EVERY spot 4h close t in 2021-09-24..2026-09-23, per phase
  (barsum_s0..s3 equities + book_gross) and mix (mean equity):
  G_bot(t) <= book_gross(t) + 2.0 (barsum book leg + G2 dip cap 2.0 enforced;
  oc_margin measured mix max 3.41 / per-phase max 3.78 — the bound is the
  conservative time-varying envelope, cited in REPORT.md).
  G_carry_short(t) = sum over open carry pairs of
  f * (F(t)/F_entry) * (Eq_entry_indexed / Eq_bot(t)) (f rows separately;
  BTC-only, ETH-only, both-active cases).
  IM_frac(t) = (G_bot(t) + G_carry_short(t)) / 5, in units of current BOT
  equity; account equity_total(t) = Eq_bot(t) + carry_unreal(t), with
  carry_unreal(t) = sum_open f*mtm_alloc(t)*Eq_entry_indexed >= f*worst bound.
  BLOCKED(t) iff IM_frac(t) > 0.95 * (equity_total(t)/Eq_bot(t)).
  Report max_t IM_frac / equity ratio per phase and mix for f = 0.25 / 0.5
  (both-active worst case), plus the analytic note: the carry pair is
  delta-hedged (spot long + futures short, net delta ~= 0 ex-basis), so a
  uniform gap moves both legs together and the incremental gap loss is only
  the basis widening (bounded by worst MtM above); the extra maintenance is
  0.5% x carry gross (oc_margin tier assumption MMR=0.005). If the v421/barsum
  files are missing, state the pure analytic bound instead (no silent fallback).
- No liquidation simulation beyond this bound + the d_liq note
  (d_liq = (1-0.005*G)/(G*0.995), oc_margin formula) with carry gross added.

## Verdict rule (fixed)

- Plain verdict USEFUL ADD-ON: YES iff (a) pooled 5-year carry contribution
  at f = 0.25 is >= +0.10 %/month to the account with year-worst account MtM
  >= -1.0% (i.e. adds return without a material new DD source), AND (b) the
  margin check shows zero blocked 4h closes at f = 0.25 AND f = 0.5
  (both-active) on all phases and the mix; else NO. Report the expected
  %/month added (at each f) and any DD impact regardless.

## Deliverables (fixed)

- `research/tournament/oc_cashcarry/`: THIS PLAN.md (written first),
  `analyze_cashcarry.py` (one process, 4h data only, peak RAM < 2 GB),
  `results.json`, `REPORT.md` (per-year table + margin table + one-line
  verdict). `tests/test_oc_cashcarry.py`. No commits. No edits outside these
  two paths.
- Causality tests: entry uses only 4h closes <= entry close; settlement uses
  the delivery-bar spot close; truncate-before-entry leaves F_entry/S_entry
  unchanged; fee math spot-checked by hand; results.json <-> REPORT.md
  consistency; script never references 1m/intraday paths.

(End of PLAN — frozen before outcomes.)
