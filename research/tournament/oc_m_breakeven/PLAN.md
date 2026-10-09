# oc_m_breakeven PLAN (pre-registered, frozen before any run, 2026-10-08)

IDEAS9 #2 (docs/opencode/IDEAS9_20261008.md): One-move break-even
(book/dip runner protection) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_breakeven.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: stops cluster in expansion bars; vetoes failed because they
delete entries. Protect after entry instead: lock the tail, keep exposure.
Prior 12 %. Effect pre-registered by the idea: +0.0-0.15 %/mo, DD -0-0.5 pp,
win +1-3 pp (BE = scratch).

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_k2manual / oc_c2manual / oc_m_btceth did
(same harness lines, this study changes ONLY the BE rule below):
- pipe v367 via pof.pipe_setup (book_mult 0.75, tighten on flat-signal
  losers, M3_R2_RUNG mapped agents ON with per-phase v376/tables_hidden R2
  tables; sleeve_risk_budget 0.26, m_sleeve_sl 8.0, size_mult 4.375,
  rungs (3.0, 4.0); no gross cap; book SL 5.0 / TP 10.0 sigma_d).
- human schedule on EVERY row: 15-min reaction (book orders from minute 15
  via win_start=15, dip limits from minute 16 via sleeve_start=16) + night
  bar skipped: on the holding bar starting at (20+s) UTC no new book order
  (flat -> wait, in position -> hold) and no new dip limit
  (sleeve_filter 0); resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h
  settlement, shorts nothing; limit fills only on 1m trade-through, no fill
  minutes 0..15 (stricter than the minute-5 user rule); stop-first if
  SL+TP touch the same 1m bar; dip exits: TP limit (maker) / touch stop
  8.0sg market (taker) / timeout at next 4h open (taker).
- Bybit order types (idea #2): resting GTC limits + attached TP/SL
  (OCO-like pair), reduce-only SL; a human places them once per bar, no
  re-pegging; single reduce-only SL amend per position; checklist a few
  times/day.
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d,
  live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits
  via ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts, BE
  diagnostics (book be_moves via engine stats + sl_move why=break-even;
  dip BE-armed/exit counts via patched stats; BE stops labelled in events
  with be=True).
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no V1/V2 numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Pre-registered rows (ONLY these, no other variants)

Idea rule (frozen ex-ante): when mark reaches +BE_K sg toward TP, amend SL
to entry once via reduce-only update; TP unchanged; one amend per
position/checklist. Applies to ALL brackets (book positions AND dip rungs),
not a BOT-budget rule nor a second TP price (vs CLOSED oc_dipbe / oc_split).
Fractions frozen below; never tighten before entry fills.
- M5_human (reference, no BE; unpatched eu.simulate; identity filter line
  identical to oc_manualsplit / oc_k2manual / oc_c2manual / oc_m_btceth).
- V1_BE075: BE_K = 0.75, BE_OFF = 0.0 (SL to exactly entry).
- V2_BE050: BE_K = 0.50, BE_OFF = 0.0 (SL to exactly entry).

Book leg (engine-native be_k/be_off, no engine file edit):
- trade dict = pof.pipe_setup v367 trade + be_k=BE_K + be_off=0.0; every
  other trade key unchanged (n_valid 3, k_off 0.75 open, tighten on
  flat-signal losers, book_mult 0.75, GRID policy, max_adds etc.).
- trigger = entry * (1 + side * BE_K * sdv), sdv = sigma_d at entry
  (daily sigma = std of 4h opens over 360 bars * sqrt(6), known at the
  decision; book SL 5.0 / TP 10.0 sigma_d). Detection on 1m high/low touch
  (long: high >= trig; short: low <= trig), causal, only while in position
  (T[be] reset at each fill; trigger checked from the minute after the
  fill; never before entry fills).
- amend: SL -> entry * (1 + side * 0.0) = exactly entry once; TP unchanged;
  one amend per position (engine T[be] flag; never loosened on adds).
  Priority inside a 1m bar: stop, then TP, then scale order, then partial,
  then BE (engine order; stop-first on any tie; a same-minute SL+TP touch
  resolves stop-first; a same-minute TP+BE touch resolves TP, i.e. BE arms
  only if strictly before TP/SL).
- Bybit: attached OCO TP/SL at placement + single reduce-only SL amend.

Dip leg (patched simulate, audited inspect.getsource pattern cf.
oc_manualsplit make_split_simulate; M5_human uses the unpatched path):
- per taken rung (long only): lv = fill limit, sg = sigma_4h at the bar
  open (known at decision), tp = lv * (1 + m0 * sg) with m0 = deployed
  agent TP mult from sleeve_tp bar-open lookup (unchanged), sl =
  lv * (1 - 8.0 * sg) touch (unchanged), be_trig = lv * (1 + BE_K * sg),
  be_stop = lv * (1 + 0.0) = exactly lv.
- tb = FIRST t in f+1..end_m-1 with high[t] >= be_trig (inclusive touch,
  causal, 1m marks <= amend time only; NaN never triggers; trigger minute
  itself still uses sl). ks = FIRST t with low[t] <= sl (touch, inclusive).
  kt = FIRST t with high[t] > tp (strict, as the engine with ft=0).
- BE arms IFF tb exists AND tb < ks (or ks None) AND tb < kt (or kt None);
  a same-minute tie (tb==ks or tb==kt) goes to the base exit; BE never
  arms. If never armed, the rung == base exactly.
- If armed, for t in tb+1..end_m-1: BE-stop = low[t] <= be_stop (touch,
  fills at min(be_stop, open) taker with the same slip/fee convention as
  the engine stop: ret = min(be_stop, open)/lv - 1 - MAKER - TAKER);
  TP = high[t] > tp (strict, maker, ret = tp/lv - 1 - 2*MAKER); stop-first
  on a same-minute tie; else timeout at the next 4h open (taker + funding
  if settle, as the engine). One amend per rung. TP level unchanged.
  Risk budget 0.26 counted once at the initial stop (unchanged); night dip
  skip and sleeve_start=16 apply before any BE logic.
- events: rung_fill unchanged; BE-stop exits emit kind rung_sl with
  ret as above plus be=True (labelled; counted in rung wins by ret>0 like
  any stop); TP/timeout unchanged (be=False). stats: be_armed += 1 when a
  rung arms; be_exits += 1 when a rung exits via its BE stop.

Everything not named above stays exactly M5_human (same books, opens,
prep, R2 tables, sizes, TP table, governor, costs, settlement, win_start,
sleeve_start, night rule, scoring).

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare V1 vs V2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. If neither is eligible, PICK = none-eligible.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the
chosen variant (and M5_human), labelled POST-RELEASE, never used to choose.
If anything changes after seeing an outcome, the original row stays and the
change is added as a disclosed extra row (not planned). 5-year R5/W/maxDD/
fullDD are context only. Verdict question: how much of the MANUAL gap to
5 %/month (M5_human R5 3.728, gap 1.272 pp) does the pick close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: BE trigger levels use only entry + sigma known at the
  bar open/decision (book sigma_d, dip sigma_4h, R2 size/TP tables keyed by
  holding-bar time T bar-open lookup only); the trigger mark uses only 1m
  high/low/close <= the amend minute (causality test bans fill-minute and
  future markers; synthetic tests check strict-before arming and the
  trigger-minute-uses-sl rule); no 1m data enters any placement decision.
- label windows: no new labels; no outcome enters any sizing or amend rule.
- fit windows: no fits/thresholds/quantiles of any kind; BE_K/BE_OFF frozen
  ex-ante (0.75/0.50/0.0); coin set, sigma/TP distances, schedule frozen
  (M5_human); no statistic from any test year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open; BE never arms before its fill and never re-arms.

## Outputs

research/tournament/oc_m_breakeven/{PLAN.md,compute_m_breakeven.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_breakeven.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills/BE counts,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, BE_K/BE_OFF. REPORT.md ends with a 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) + one-line MANUAL-gap verdict
with gap in pp. MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND pooled
book win >= 55 %. Heavy run in ONE heavy_slot process (tag oc_m_breakeven),
heartbeat progress at least every 10 minutes.
