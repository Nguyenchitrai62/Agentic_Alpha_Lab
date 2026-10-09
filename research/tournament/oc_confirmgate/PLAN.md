# oc_confirmgate — PLAN (frozen 2026-10-08, BEFORE computing any meta-table)

Assignment: `docs/opencode/OPENCODE_W_oc_confirmgate.md` (+ `OPENCODE_W_COMMON_20261007.md`,
AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_confirmgate/`
+ `tests/test_oc_confirmgate.py` (+ `docs/opencode/CONFIRM_GATE.md` <=30 lines ONLY if
the 2-leg gate separates — conditional, see §5).

## Nature of this task (retrospective meta-study, no new fits)

All candidate outcomes PRE-EXIST in stored REPORTs/results.json (CLOSED_DIRECTIONS rows
dated 2026-10-07/2026-10-08). We create NO new strategy fits, NO new engine rows, NO new
thresholds. We run ZERO heavy engines (0 of the allowed at-most-6 Bybit S5 reruns):
leg1 uses stored S5 rows where they exist, else UNKNOWN; leg2 uses stored pre-sample
replica rows where they exist, else N/A. Post-release numbers are QUOTED from the
original direction (scored once there), never re-scored here. Exposure log: candidate
names come from the assignment + CLOSED_DIRECTIONS (read before freezing this PLAN);
numbers below are collected AFTER freezing leg definitions.

## Candidates (frozen — assignment e.g. list + 2 stored-S5 illustrators)

C2 (oc_chronos), K2 (oc_kronoshidden/oc_k2bybit), D1 (oc_downshare), W2 (oc_fundclock),
L2 (oc_lsratio best-mean; REF keeps robust — mean-winner control), V1 (oc_vpinveto),
V2 (oc_decayexit), AS18 (oc_shortmember), B7 (oc_cascadeboost, contaminated idea),
A1 (oc_lit_xs, stored S5), M1 (oc_lit_position H8 MVRV, stored frictions).
REF everywhere = G2 R2B1D17BFG2 (5.601/2.588/16.91 dev4; Y4 4.648/12.90; 5y 5.410/16.82).

## Confirm legs (frozen definitions, IDEAS10 #1)

- Leg1 Bybit-confirm: CAND vs REF on Bybit-S5 dev4 under the robust rule
  (DD<=20, no losing dev year, then highest WORST, ties->mean) AND full-path DD<=20.
  PASS = wins/ties-robust on S5 dev4 with DD<=20 both; FAIL = loses or DD>20;
  UNKNOWN = no stored S5 row (no new run per §above).
- Leg2 pre-sample: frozen dip-tilt replica on never-used 2017-2020 spot
  (oc_presample harness family). PASS = gain>0 in >=3/4 pre-sample years;
  PARTIAL = 3/4 with crash-leg (COVID Y2020p) fail; FAIL = <=2/4; N/A = mechanism
  cannot run on the dip replica (book gates, member retrains — by construction).
- Transfer: CAND Y4 R > REF Y4 R on Binance base (quoted, labelled; contamination
  labels inherited, e.g. B7). Absolute >=5 noted separately (none reaches it here).

## Costs / leakage (inherited, asserted not recomputed)

Gate costs inside every quoted engine (maker 0.0002/taker 0.00055/stop-taker,
longs 0.0001 per 8h, shorts 0; S5 Bybit prices from 2021-11-15, y2021 short window).
No new feature/label/fit/fill timing created here; checklist quotes each direction's
own audit + blind audits (audit_c2, audit_d1, audit_k2, audit_cboost PASS).

## Decision rule for §5 (frozen)

Write CONFIRM_GATE.md (<=30 lines) IFF leg1+leg2 jointly separate Y4-transfer from
non-transfer on the evaluable set with no counterexample (a PASS/PASS that failed Y4,
or a FAIL that transferred on the deployment venue, counts as non-separation).
Otherwise report the counterexample and close without the protocol file.

## Deliverables

PLAN.md (this), REPORT.md (per-candidate leg1/leg2/transfer table + 3-line Vietnamese
verdict), results.json, tests/test_oc_confirmgate.py (>=1 causality/truncation test +
>=1 hand-checked synthetic gate test), pytest run. No heavy_slot use (CPU-only reads).
