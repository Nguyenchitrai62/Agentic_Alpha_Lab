# oc_oldidea2 REPORT — was the fixed per-coin dip stop ever judged in the full 4-phase engine?

## Question (assignment OPENCODE_W_oc_oldidea2)

`oc_idea2` (fixed XRP 5.5sg / rest 4.0sg, PROMISING screen) and `oc_idea2wf`
(walk-forward per-coin stops, NOT PROMISING screen): had either variant already
been judged in the full 4-phase engine (v421/v422 harness: 4 clock phases,
reset metric per anchor year, full-path DD)? If yes, report that verdict with
sources and stop (no engine run).

## Answer: YES — judged as v417 row R2B1D17BFX (REJECTED)

The exact fixed variant from `oc_idea2` (V leg: XRP 5.5sg, BTC/ETH/SOL/BNB
4.0sg, 8sg backstop unchanged) was run in the full 4-phase engine as
`R2B1D17BFX` in `research/parallel/rounds/parallel-20260906-r2/v417/`
on the `R2B1D17BF` (D17BF) base. Same harness family as v421/v422: 4 clock
phases (`Pool(2)` over shifts 0..3), per-year reset metric
(`research/diagnostics/r2_decompose5/reset_metric.py::year_reset`), full-path DD
via `v388.mix`, blind audit PASS.

Engine verdict (sources below): **REJECTED — D17BF stays.**
X adds +0.15pp/mo vs base but DD is 0.04pp worse and no fold transfers (0/3).

| row (v417) | 5y R (%/mo, reset) | worst year W | max yearly DD | full-path DD | losing yrs |
|---|---|---|---|---|---|
| R2B1D17BF (base = D17BF) | 5.425 | 2.831 | 18.33 | 16.90 | 0 |
| R2B1D17BFX (XRP 5.5 / rest 4.0) | 5.574 | 2.831 | 18.37 | 16.89 | 0 |
| R2B1D17BFC (cooldown only, context) | 5.416 | 3.438 | 18.45 | 17.42 | 0 |
| R2B1D17BFCX (cooldown + XRP 5.5) | 5.504 | 3.439 | 18.55 | 17.47 | 0 |

Folds (choice on years seen, tested on held-out year): FOLD 2/3/4 all pick CX
but `good=false` 0/3; `transfer=false`; `final=R2B1D17BFCX` by 5y rank only.
Manifest `status=rejected`, `audit.passed=true`.

## Sources (all in-repo, read-only)

1. `research/parallel/rounds/parallel-20260906-r2/v417/v417_cascade.py:1-16`
   — pre-registration: "X = per-coin close-stop: XRPUSDT 5.5 sigma, other majors
   4 sigma (engine hook sleeve_sl_coin…)", rows R2B1D17BF/C/X/CX, labelled
   POST-HOC INFORMED (motivated by same-5y anatomy, XRP singled out there).
2. `research/parallel/rounds/parallel-20260906-r2/v417/v417_cascade.py:118-121`
   — implementation: `kw["sleeve_sl_coin"] = lambda i,a: 5.5 if a==XRPUSDT else 4.0`.
3. `research/parallel/rounds/parallel-20260906-r2/v417/result_manifest.json:90-118,189`
   — X numbers (5.574/2.831/18.37/16.89) + note "…rejected, D17BF stays";
   `status=rejected`, `audit.passed=true`.
4. `research/parallel/rounds/parallel-20260906-r2/v417/v417_result.json:62-90`
   — identical X row (result sha matches manifest).
5. `docs/RESEARCH_INDEX.md:299` — "v417 … X (XRP close-stop 5.5, post-hoc
   informed) 5.57/2.83/18.37/16.89; …".
6. `docs/CLOSED_DIRECTIONS.md:75` — `oc_idea2` listed as "PROMISING screen"
   (screen only); the engine judgement lives in v417 above.
7. `docs/opencode/IDEAS_20261007.md:13` — "…(oc_idea2 screen 4/5+LOO 5/5,
   never engine-tested)" is STALE w.r.t. v417: the screen author missed that
   v417 had already engine-tested exactly XRP 5.5/rest 4.0 (see sources 1-4).
8. `research/tournament/oc_idea2/{PLAN.md,REPORT.md,results.json}` — screen
   definition of V (XRP 5.5/rest 4.0): D>0 4/5y, LOO 5/5, tails 4/5.
9. `research/tournament/oc_idea2wf/{PLAN.md,REPORT.md}` — walk-forward variant:
   NOT PROMISING (tails 1/5); screen only, never an engine row.

## What was NOT engine-tested (scope note)

- The walk-forward *choice rule* (`oc_idea2wf`/`oc_coinwf`) was never an engine
  row; only its fixed-distance legs relate to v417-X.
- Uniform-stop rows (v415: 5/6sg on R2B1D17BF, rejected) and the G2 gross-cap
  rows (v421/v422) are different ideas, not per-coin stops.
- Sibling worker `oc_idea2_dipstop` (see overlap below) re-tests fixed stops on
  the **G2** base (D17BF + gross cap 2.0) plus a new P2 (rest 4.5sg).

## Overlap with sibling worker oc_idea2_dipstop (read 2026-10-07, end of task)

- `research/tournament/oc_idea2_dipstop/REPORT.md` §0 pre-registers P1 =
  G2 + XRP 5.5/rest 4.0 and P2 = G2 + XRP 5.5/rest 4.5; §1 reproduces G2
  (5.410/W 2.588/DD 16.91/full 16.82) and G2+carry (5.634/16.75/16.66) from
  cache; §2 engine results TBD (runs not finished at read time).
- `research/tournament/oc_idea2_dipstop/run_dipstop.py:4-8,45-48` — same
  `sleeve_sl_coin` hook, P1 = v417-X distances on a different base (G2 vs
  D17BF), P2 (rest 4.5) is new and never engine-tested.
- Overlap: P1 duplicates the *distances* judged in v417-X, but NOT the verdict
  scope: v417 judged them on D17BF without the gross cap; the G2-base check
  (with cap 2.0 binding) is genuinely new. No conflicting result exists yet
  (their §2 TBD). This report claims no new engine result and stops per the
  assignment's first branch.

## Method (no engine run)

Read-only audit: compared `oc_idea2` V definition against v417 X definition
(distances, hook, backstop, base), transcribed the audited numbers verbatim
from `v417_result.json`/`result_manifest.json` into `results.json`. No
re-simulation, no heavy slot, no git writes, no data beyond 2026-09-24
consulted for outcomes. POST-HOC label inherited from v417 (choice informed by
the same five years).

## Verdict

JUDGED ALREADY: fixed XRP 5.5/rest 4.0 = v417 R2B1D17BFX — REJECTED in the full
4-phase engine (+0.15pp R, DD +0.04pp, 0/3 folds transfer). Do not re-run this
variant on D17BF; the only unjudged neighbour is the G2-base / rest-4.5 check
owned by oc_idea2_dipstop.

## Tom tat tieng Viet (3 dong)
Da co phan quyet engine day du: XRP 5.5/con lai 4.0 la v417-X, REJECTED (+0,15 R, DD +0,04, fold 0/3).
Khong chay lai bien the nay tren nen D17BF; chi nen G2-cap 2.0 / rest-4.5 do oc_idea2_dipstop lam.
Dong nay dong: giu D17BF/G2 hien tai, doi paper thuc chung, khong mo bien the stop moi.
