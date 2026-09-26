# v180 blind audit — Part B comparison

Blind: `research/parallel/rounds/parallel-20260906-r2/v180_audit/replication.json`
was saved before opening `v180/` (see Part A script header assumptions A1–A11).
Base: v179 spec in OPENCODE_V178_V179_AUDIT.md (implemented independently; no
`v178_v179_audit/` replication existed).

## Primary rows (model-gated ladder + v179 budget, target 0.25, governor on)

| row | monthly % | 4h full-path DD % | 1m-marked DD % | gate DD | taken / cancelled |
| --- | --- | --- | --- | --- | --- |
| v180 reported normal | 4.088 | 19.00 | 21.03 | 21.03 | 1771 / 2462 |
| audit replication normal | 4.177 | 18.09 | 19.57 | 19.57 | 1839 / 2449 |
| diff (audit − reported) | +0.089pp | −0.91pp | −1.46pp | −1.46pp | +68 / −13 |
| v180 reported stress | 3.672 | 19.40 | 21.30 | 21.30 | 1787 / 2446 |
| audit replication stress | 3.783 | 18.27 | 19.92 | 19.92 | 1851 / 2437 |
| diff | +0.111pp | −1.13pp | −1.38pp | −1.38pp | +64 / −9 |

Yearly nets (normal, reported vs audit):
2021 23.86 vs 26.90 (+3.04), 2022 43.09 vs 44.74 (+1.65),
2023 114.75 vs 119.38 (+4.63), 2024 70.69 vs 70.83 (+0.14),
2025 70.32 vs 69.21 (−1.11).
Worst minute cluster matches: `2022-11-09 12:00 UTC` (FTX window) in both rows.

IC / kept per anchor (reported vs audit):

| anchor | train | test | reported IC / kept | audit IC / kept |
| --- | --- | --- | --- | --- |
| 2021-09-24 | 1754 | 932 | 0.0160 / 765 | 0.0123 / 767 (+2) |
| 2022-09-24 | 2679 | 973 | 0.0374 / 718 | 0.0266 / 728 (+10) |
| 2023-09-24 | 3659 | 1250 | 0.0681 / 1019 | 0.1085 / 1030 (+11) |
| 2024-09-24 | 4909 | 946 | 0.2501 / 848 | 0.2295 / 862 (+14) |
| 2025-09-24 | 5853 | 1092 | 0.2024 / 891 | 0.1938 / 910 (+19) |

Train/test counts match exactly (rung fills reproduced).
Live total: reported 4241 kept vs audit 4297 (+56).

## Why the gaps are small and explained

1. **Rung fills match.** Train/test fill counts are identical per anchor, so the
   ladder (`L=open(T)*(1-k*sigma)`, first `low<L` in 16..238, exit
   `open(T+4h)*(1-s_out)`, funding at `T+4h`) is reproduced. Fill-minute and
   return math are not the source of the gap.
2. **Feature/model deltas (kept +56, IC ±0.01–0.04).**
   Reported uses integer `asset` code (0..4) as a single HGB feature;
   audit uses 5 one-hot columns in BNB,BTC,ETH,SOL,XRP order (v173 style).
   Reported `funding` = `funding_at_bar_open` ffilled (0→NaN→ffill);
   audit = last non-zero raw `fundingRate` at or before `t`.
   Reported `vspike` denominator `mean(V[0:q-5])`; audit `mean(V[0:q-4])`
   (one-minute window shift). Reported leaves NaN features to HGB-native
   missing handling; audit falls back (r5/r15/rng/trend/r1d 0, vspike 1,
   taker15 0.5, btc_depth 0; depth-invalid candidates skipped).
   Together these move a few dozen borderline `pred>0` calls, hence
   +68 taken and +0.09pp monthly.
3. **Vol leg (documented assumption delta).**
   Audit A8 froze “vol uses UNCAPPED (no gate, no budget) unit shifted by 2”.
   Reported (`v180_model_gated_ladder.py:18,110-117`) uses KEPT (gated) but
   still budget-uncapped unit shifted by 2 (`gate` applied to `fk/rk` before
   `v179.run`, whose `unit` then sums the gated `rk`). Audit vol is thus
   slightly more conservative (larger sleeve in vol, smaller `s`), which
   explains part of the DD gap (−0.9pp 4h, −1.4pp 1m) alongside the kept-count
   effect. Payoff timing, `N_MAX=0.05/0.30=1/6`, sort `(f, rung, col)`, and
   `rn=s*g*0.25/4/1.657` are otherwise identical.
4. **1m mark matches in shape.** Same worst bar, same formula
   (`prev*(1+min(0,min path)-exec+min(funding,0))`, taken rungs only from
   fill minute at `close/L-1`). Level gap follows from (2)–(3).

## Look-ahead check (every feature ≤ minute f-1)

Reviewed `v180_model_gated_ladder.py:53-83` (`features`) and `v179` rung/budget:

- `depth/r5/r15/rng/breadth/btc_depth`: 1m `close/high/low` at `p=f-1`
  (and `p-5/p-15` for r5/r15; breadth over other assets at same `p`). All
  indices `≤ f-1` of holding bar `T`. ✓
- `vspike`: `volume(f-5..f-1)` / `5*mean(volume(0..f-6))`. ✓
- `taker15`: `taker_buy(f-15..f-1)/volume(f-15..f-1)`. ✓
- `trend`: `open(T)/mean(last 42 4h opens incl open(T))-1` (`shift(-1)`).
  `open(T)` is the holding-bar open (known at decision, before minute 16). ✓
- `r1d`: `open(T)/open(T-24h)-1` over sigma (shifts `-1`/`5`). ✓
- `funding`: `funding_at_bar_open` ffilled at `G` (`t`), i.e. last non-zero
  settlement at or before `t`. ✓
- `k`, `asset`: rung constant and column index. ✓
- Training: `T+4h < anchor-1d` and `T ≥ 2020-03-02`; test `t ∈
  [anchor, anchor+365d)`. One-day embargo between train exit and test start. ✓
- Gate `pred>0` uses only `f-1` state, applied at fill `f`; budget order
  `(fill minute, shallower rung, BNB,BTC,ETH,SOL,XRP)` uses only fills known
  at their minute; same mask for normal and stress payoff legs. ✓
- `s_out` minute-0 range and funding at `T+4h` are in the label/costs only,
  not in features; vol uses `shift(2)` (v176-audit fix). ✓

No forward use found. The `open(T)`-in-`L`/features convention is the same
close→open continuity already accepted in engine_real execution base `p0`.

## Verdict

- Engineering: **reproduced**. Fills/train/test counts exact, budget/1m-mark
  loop and worst-bar location match, monthly within +0.09–0.11pp, DD within
  ~1–1.5pp, fully explained by the documented one-hot-vs-integer,
  funding/vspike-window, NaN-fallback, and vol-gated-vs-ungated deltas.
- Look-ahead: **pass**. Every feature uses data `≤ minute f-1` (plus
  decision-known `open(T)/sigma/funding`); training cutoff and budget order
  are causal.
- Gate: both reported rows fail `DD ≤ 20%` on gate DD (21.03 normal, 21.30
  stress; audit 19.57/19.92 also passes 4h but the reported gate is the
  binding one). Monthly passes. Do not promote without mark-price/queue/
  slippage robustness and calibrated sizing. Manifest must stay
  non-`live_approved`.
